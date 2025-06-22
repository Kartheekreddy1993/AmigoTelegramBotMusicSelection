import os
import pyodbc
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
import time
import chardet
from lxml import etree

file_path = "playitems.txt"






def fetch_xml(file_path):
    # Check if the file is not empty
    with open(file_path, "r") as file:
        lines = file.readlines()

    if lines:  # Non-empty list means file has at least one line
        first_line = lines[0].strip()

        # Remove the first line and write the rest back
        with open(file_path, "w") as file:
            file.writelines(lines[1:])

        return first_line
    else:
        print("File is empty.")
        return None
        
        
        
def parse_xml(line):
    with open(line, 'rb') as file:
        raw_data = file.read()
        result = chardet.detect(raw_data)
        encoding = result['encoding']
    print(encoding)
    # Read XML data
    with open(line, 'r', encoding=encoding) as file:
        xml_data = file.read()  
    #xml_data = re.sub(r'[\x00-\x1F\x7F]', '', xml_data)    

    try:
        root = etree.fromstring(xml_data)
        for mitem in root.findall(".//info[@duration]"):
            duration = mitem.get("duration")
            print(duration)
            duration_seconds = float(duration)
            finalduration = time.strftime("%H:%M:%S", time.gmtime(duration_seconds))
            return finalduration
            
    except etree.XMLSyntaxError as e:
            print(f"XML syntax error in file {filename}: {e}")        


def fetch_database(line,line_name,line_duration):
    conn_str = (
    r'DRIVER={Microsoft Access Driver (*.mdb, *.accdb)};'
    r'DBQ=C:\Program Files (x86)\Amigo\MultiCaster\Channel4\Database\MultiCasterDatabase.mdb;'
    )
    con = pyodbc.connect(conn_str)
    cur = con.cursor()
    query = f"SELECT MAX(Scheduleid) FROM Schedule;"
    cur.execute(query)
    row_count = cur.fetchone()[0]
    cur.execute("SELECT * FROM Schedule WHERE scheduleid = ?", (row_count,))
    row = cur.fetchone()
    print("Full row:", row)
    last_schedule_time = row[1]
    last_schedule_date = row[2]
    last_schedule_duration = row[5]
    #print(last_schedule_time)
    #print(row_count)
    
    # Combine start_date and start_time into a datetime object
    start_datetime = datetime.strptime(f"{last_schedule_date} {last_schedule_time}", "%d %b %Y %I:%M:%S %p")

    # Convert duration to timedelta
    h, m, s = last_schedule_duration.split(":")
    if "." in s:
        s, ms = map(float, s.split("."))
        ms = int(ms * 1000)
    else:
        s = int(s)
        ms = 0

    duration_delta = timedelta(hours=int(h), minutes=int(m), seconds=int(s), milliseconds=ms)

    # Calculate end time
    file_end_time = start_datetime + duration_delta
    print("last file schedule ends at" , file_end_time)
    now = datetime.now()

    # Compare and update
    if now > file_end_time:
        schedule_time = now + timedelta(minutes=1)
        # Extract date and time with milliseconds
        start_date = schedule_time.strftime("%d %b %Y")  # e.g., "16 Jun 2025"
        start_time = schedule_time.strftime("%I:%M:%S %p")  # e.g., "07:45:30 PM"
        row_count += 1
        print(start_time)
        cur.execute("INSERT INTO Schedule VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (row_count, start_time, start_date, line_name, line, line_duration, 1, False))
        con.commit() 
        print("schedule starts starts at:" , line_name , start_date , start_time) 
        print("------------------------------------------------------")        
    else:
        start_date = file_end_time.strftime("%d %b %Y")  # e.g., "16 Jun 2025"
        start_time = file_end_time.strftime("%I:%M:%S %p")  # e.g., "07:45:30 PM" 
        row_count += 1
        cur.execute("INSERT INTO Schedule VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                        (row_count, start_time, start_date, line_name, line, line_duration, 1, False))
        con.commit() 
        print("schedule starts starts at:" , line_name , start_date , start_time) 
        print("------------------------------------------------")        
    

    
while True:
    if os.path.getsize(file_path) > 0:
        # Call the function and store the result
        line = fetch_xml(file_path)
        if line:
            print("Returned line:", line)
        line_name = os.path.splitext(os.path.basename(line))[0]    
    
        #call to parse xml file
        line_duration = parse_xml(line)

        #call to database to obtain schedule info
        fetch_database(line,line_name,line_duration)
        
    else:
        time.sleep(10) 
        print("waiting for Telegram Bot Request")        