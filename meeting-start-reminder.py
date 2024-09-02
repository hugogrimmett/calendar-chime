# Hugo Grimmett
# October 2022
#
# This script rings a bell controlled by the MIDI robot whenever a google calendar event is starting
# It also activates the lighting for meetings automatically
# The calendar event must involve at least one other participant, and have been accepted by me
#
#
# To install necessary packages:
# pipenv install google-api-python-client google-auth-httplib2 google-auth-oauthlib mido python-rtmidi pytz phue apscheduler

from __future__ import print_function

import datetime
import os.path
import mido
import time
import pytz
import threading
import phue
import discoverhue
from apscheduler.schedulers.background import BackgroundScheduler
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from mido import Message
from phue import Bridge

# Global variables
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
next_event = None
next_start_time = None
creds = None
email = None
lock = threading.Lock()
bridge = None
max_time = 0
debug = 1

# Main function
def main():
    global creds, bridge, email

    # Get email address
    email = get_email()

    # Initialize and connect to Philips Hue bridge
    ip_address = get_hue_bridge_ip()
    try:
        bridge = Bridge(ip_address)
        bridge.connect()
        print("Successfully connected to the Hue bridge.")
    except:
        print("Failed to connect to the Hue bridge. Make sure you pressed the link button, and try again.")
        return

    # Load or create credentials for Google Calendar API
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            try:
                flow = InstalledAppFlow.from_client_secrets_file('credentials.json', SCOPES)
                creds = flow.run_local_server(port=0)
            except FileNotFoundError:
                print("The 'credentials.json' file was not found. Please check the file path, or generate from via the google cloud console.")
                return
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    # Start the scheduler to check for the next event
    schedule_event_check()

def schedule_event_check():
    scheduler = BackgroundScheduler()
    scheduler.add_job(getNextEvent, 'interval', minutes=1)
    print("Job scheduled for getNextEvent")  # Add this line to confirm scheduling
    scheduler.start()
    print("Job started") 


    try:
        while True:
            time.sleep(1)  # Keeps the main thread alive
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

def getNextEvent():
    print("getNextEvent called", flush=True)
    global next_event, next_start_time, creds, email, max_time

    tic = time.time()
    with lock:
        try:

            print('got to part 1')
            # Call the Calendar API
            now = datetime.datetime.utcnow().isoformat() + 'Z'
            service = build('calendar', 'v3', credentials=creds)
            events_result = service.events().list(calendarId='primary', timeMin=now,
                                                  maxResults=10, singleEvents=True,
                                                  orderBy='startTime').execute()
            events = events_result.get('items', [])
            if not events:
                print('No upcoming events found.')
                return

            print('got to part 2')

            next_event = None
            for event in events:
                start_dt = None
                if 'dateTime' in event['start'] and event['eventType'] == 'default':
                    start_dt = datetime.datetime.strptime(event['start'].get('dateTime'), '%Y-%m-%dT%H:%M:%S%z')
                    start_dt_utc = start_dt.astimezone(pytz.utc)
                    now_dt_utc = datetime.datetime.now(pytz.utc)
                else:
                    continue

                if 'attendees' in event and any(attendee['email'] == email and attendee['responseStatus'] == 'accepted' for attendee in event['attendees']):
                    if start_dt_utc > now_dt_utc:
                        next_event = event
                        next_start_time = start_dt_utc
                        break

            print('got to part 3')
            if next_event:
                check_event_time()
            else:
                print('No valid upcoming events found.')

        except HttpError as error:
            print(f'An error occurred: {error}')

    toc = time.time()
    print('Calendar check time: ', round(toc - tic, 2), 's')
    print('Max small loop time: ', '%.2g' % max_time, 's')

def check_event_time():
    print("checking event time", flush=True)
    global next_event, next_start_time, max_time, bridge

    tolerance_seconds = 5
    warning_time_seconds = 15

    while True:
        time.sleep(1)
        with lock:
            if next_event:
                event_start_window = next_start_time - datetime.timedelta(seconds=warning_time_seconds)
                now = datetime.datetime.now(pytz.utc)
                if event_start_window <= now < event_start_window + datetime.timedelta(seconds=tolerance_seconds):
                    print(f'🔔🎥 {next_event["summary"]} is starting now! 🎥🔔')
                    try:
                        bong(1, 'HAPAX', 15, 49)
                    except Exception as e:
                        print(f'⚠️  ERROR: could not play a sound: {e} ⚠️')
                    try:
                        bridge.activate_scene(1, 'aoYhBTLiGLJYEYy', 0)  # activate video call scene in office
                    except Exception as e:
                        print(f'⚠️  ERROR: could not turn the lights on: {e} ⚠️')
                    break

def bong(n, device, channel, note):
    outport = mido.open_output(device)
    on_msg = mido.Message('note_on', channel=channel, note=note)
    off_msg = mido.Message('note_off', channel=channel, note=note)
    for _ in range(n):
        outport.send(on_msg)
        time.sleep(0.2)
        outport.send(off_msg)
        if n > 1:
            time.sleep(2)

def get_hue_bridge_ip(filename="settings_hue-bridge-ip.txt"):
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            ip_address = file.read().strip()
        return ip_address
    else:
        print('No bridge IP address config file found, so scanning for available bridges:')
        bridges = discoverhue.find_bridges()

        for i, (key, value) in enumerate(bridges.items(), start=1):
            print(f".  {i}: {key} - {value}")

        if len(bridges) > 1:
            choice = int(input("Choose the number of the bridge you want to use: "))
            ip_address = list(bridges.values())[choice - 1]
        else:
            ip_address = next(iter(bridges.values()))  # Automatically choose the single item

        ip_address = ip_address.rstrip('/')
        ip_address = ip_address.lstrip('http://')

        print(f"The selected IP address is: {ip_address}")

        with open(filename, 'w') as file:
            file.write(ip_address)

        return ip_address

# Function to get the email address from a file or user input
def get_email(filename="settings_email.txt"):
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            email_address = file.read().strip()
            print(f'Chosen email address: {email_address}')
        return email_address
    else:
        email_address = input("Enter the email address for your google calendar: ").strip()
        with open(filename, 'w') as file:
            file.write(email_address)
        return email_address

def checkSensorBatteryLevels(bridge):
    sensor_names = bridge.get_sensor_objects('name')
    sensor_ids = bridge.get_sensor_objects('id')
    sensors = bridge.get_sensor_objects()
    counter = 0
    for sensor in sensors:
        config = sensor._get('config')
        if "battery" in config and config['battery'] < 15:
            print(f'🔋🚨: {sensor._get("name")} battery is low ({config["battery"]}% )')
            counter += 1
    if counter == 0:
        print('🔋: all good - no sensors have < 15% battery')

if __name__ == '__main__':
    main()
