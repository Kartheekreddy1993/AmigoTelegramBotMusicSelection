import os
import json
import time
import logging
from functools import wraps
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (ApplicationBuilder, CommandHandler, CallbackQueryHandler,
                          ContextTypes, MessageHandler, filters)

# === CONFIG ===
with open("config.json", "r") as f:
    config = json.load(f)

BOT_TOKEN = config["BOT_TOKEN"]
VIDEO_FOLDERS = config["VIDEO_FOLDER"]
NOTEPAD_FILE = config["NOTEPAD_FILE"]
FILES_PER_PAGE = 50
RATE_LIMIT_SECONDS = config["TIME_LIMIT"]

USER_RATE_LIMITS = {}

# === LOGGING SETUP ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.FileHandler("bot_actions.log"), logging.StreamHandler()]
)

# === Helpers ===
def get_video_files(extensions=('.xml', '.txt')):
    files = []
    for folder in VIDEO_FOLDERS:
        for f in os.listdir(folder):
            if f.endswith(extensions):
                files.append(f"{folder}||{f}")
    return files

def get_files_from_folder(folder, extensions=('.xml', '.txt')):
    return [f"{folder}||{f}" for f in os.listdir(folder) if f.endswith(extensions)]

# === Rate Limiting ===
def rate_limit_start(func):
    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        now = time.time()
        last_time = USER_RATE_LIMITS.get(user_id, 0)
        if now - last_time < RATE_LIMIT_SECONDS:
            remaining = int(RATE_LIMIT_SECONDS - (now - last_time))
            minutes, seconds = divmod(remaining, 60)
            await update.message.reply_text(f"⏳ You can use /start again in {minutes}m {seconds}s.")
            return
        USER_RATE_LIMITS[user_id] = now
        return await func(update, context)
    return wrapper

# === /start ===
@rate_limit_start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logging.info(f"User {user.id} ({user.full_name}) used /start")
    context.user_data.clear()

    keyboard = [[InlineKeyboardButton(f"📁 {os.path.basename(folder)}", callback_data=f"folder_{folder}")]
                for folder in VIDEO_FOLDERS]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Select a folder to view files:", reply_markup=reply_markup)

# === File Page Display ===
async def send_file_page(update_or_query, context, page):
    video_files = context.user_data.get("video_files", [])
    search_active = "search" in context.user_data
    sort = context.user_data.get("sort", "az")

    if sort == "az":
        video_files.sort(key=lambda x: x.split("||")[1])
    elif sort == "za":
        video_files.sort(key=lambda x: x.split("||")[1], reverse=True)
    elif sort == "new":
        video_files.sort(key=lambda x: os.path.getmtime(os.path.join(*x.split("||"))), reverse=True)
    elif sort == "old":
        video_files.sort(key=lambda x: os.path.getmtime(os.path.join(*x.split("||"))))

    total_files = len(video_files)
    total_pages = (total_files - 1) // FILES_PER_PAGE + 1
    start_idx = page * FILES_PER_PAGE
    end_idx = min(start_idx + FILES_PER_PAGE, total_files)

    keyboard = []
    for i in range(start_idx, end_idx):
        folder, filename = video_files[i].split("||", 1)
        folder_name = os.path.basename(folder)
        file_base = os.path.splitext(filename)[0]
        keyboard.append([InlineKeyboardButton(f"[{folder_name}] {file_base}", callback_data=f"file_{i}")])

    keyboard.append([
        InlineKeyboardButton("🔼 A-Z", callback_data="sort_az"),
        InlineKeyboardButton("🔽 Z-A", callback_data="sort_za"),
        InlineKeyboardButton("🆕 Newest", callback_data="sort_new"),
        InlineKeyboardButton("📁 Oldest", callback_data="sort_old")
    ])
    if search_active:
        keyboard.append([InlineKeyboardButton("❌ Clear Search", callback_data="clear_search")])

    page_buttons = [InlineKeyboardButton(str(p+1), callback_data=f"page_{p}")
                    for p in range(max(0, page-2), min(total_pages, page+3))]
    keyboard.append(page_buttons)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page_{page - 1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton("Next ⏭️", callback_data=f"page_{page + 1}"))
    nav_buttons.append(InlineKeyboardButton("🔁 Refresh", callback_data=f"refresh_{page}"))
    keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("🔙 Back to Folders", callback_data="back_folders")])

    title = f"Select a file (Page {page + 1} / {total_pages}):"
    if search_active:
        title += f"\n🔍 Matching: '{context.user_data['search']}'"

    reply_markup = InlineKeyboardMarkup(keyboard)
    if isinstance(update_or_query, Update):
        await update_or_query.message.reply_text(title, reply_markup=reply_markup)
    else:
        await update_or_query.edit_message_text(title, reply_markup=reply_markup)

    context.user_data["page"] = page

# === Button Callback ===
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user = update.effective_user

    if data.startswith("file_"):
        index = int(data.split("_")[1])
        folder, filename = context.user_data["video_files"][index].split("||", 1)
        full_path = os.path.join(folder, filename)
        with open(NOTEPAD_FILE, "a") as f:
            f.write(full_path + "\n")
        file_base = os.path.splitext(filename)[0]
        folder_name = os.path.basename(folder)
        logging.info(f"User {user.id} ({user.full_name}) appended: {full_path}")
        await query.edit_message_text(f"✅ Appended:\n[{folder_name}] {file_base}")

    elif data.startswith("page_") or data.startswith("refresh_"):
        await send_file_page(query, context, int(data.split("_")[1]))

    elif data.startswith("sort_"):
        context.user_data["sort"] = data.split("_")[1]
        await send_file_page(query, context, context.user_data.get("page", 0))

    elif data == "clear_search":
        context.user_data.pop("search", None)
        folder = context.user_data.get("selected_folder")
        if folder:
            context.user_data["video_files"] = get_files_from_folder(folder)
            context.user_data["sort"] = "az"
            context.user_data["page"] = 0
            await send_file_page(query, context, 0)
        else:
            keyboard = [[InlineKeyboardButton(f"📁 {os.path.basename(f)}", callback_data=f"folder_{f}")]
                        for f in VIDEO_FOLDERS]
            await query.edit_message_text("Select a folder to view files:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data == "back_folders":
        context.user_data.clear()
        keyboard = [[InlineKeyboardButton(f"📁 {os.path.basename(f)}", callback_data=f"folder_{f}")]
                    for f in VIDEO_FOLDERS]
        await query.edit_message_text("Select a folder to view files:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("folder_"):
        folder = data.split("_", 1)[1]
        context.user_data["selected_folder"] = folder
        context.user_data["video_files"] = get_files_from_folder(folder)
        context.user_data["sort"] = "az"
        context.user_data["page"] = 0
        await send_file_page(query, context, 0)

# === /search ===
@rate_limit_start
async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    if not context.args:
        await update.message.reply_text("❌ Usage: `/search keyword`", parse_mode='Markdown')
        return

    keyword = " ".join(context.args).lower()
    all_files = [f"{folder}||{f}" for folder in VIDEO_FOLDERS for f in os.listdir(folder)
                 if f.endswith(('.xml', '.txt')) and keyword in f.lower()]

    logging.info(f"User {user.id} ({user.full_name}) searched for: {keyword}")

    if not all_files:
        await update.message.reply_text("🔍 No matching files found.")
        return

    context.user_data["video_files"] = all_files
    context.user_data["search"] = keyword
    context.user_data["sort"] = "az"
    context.user_data["page"] = 0
    await send_file_page(update, context, 0)

# === /list ===
async def list_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    logging.info(f"User {user.id} ({user.full_name}) used /list")

    if os.path.exists(NOTEPAD_FILE):
        with open(NOTEPAD_FILE, "r") as f:
            content_lines = f.read().strip().splitlines()
        if content_lines:
            clean_lines = []
            for line in content_lines:
                folder, filename = line.strip().split("||")
                folder_name = os.path.basename(folder)
                file_base = os.path.splitext(filename)[0]
                clean_lines.append(f"[{folder_name}] {file_base}")
            output = "\n".join(clean_lines)
            await update.message.reply_text(f"📄 Songs IN QUEUE\n```{output}```", parse_mode='Markdown')
        else:
            await update.message.reply_text("📄 Queue is empty.")
    else:
        await update.message.reply_text("📄 Notepad file not found.")

# === MAIN ===
if __name__ == '__main__':
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("list", list_command))
    app.add_handler(CallbackQueryHandler(button_callback))
    print("Bot is running. Press Ctrl+C to stop.")
    app.run_polling()
