# Hugo Grimmett
# October 2022
#
# This script rings a bell controlled by the MIDI robot whenever a google calendar event is starting
# It also activates the lighting for meetings automatically
# The calendar event must involve at least one other participant, and have been accepted by me
#
#
# To install necessary packages:
# pipenv install google-api-python-client google-auth-httplib2 google-auth-oauthlib mido python-rtmidi pytz phue

# bug 2023-01-12: if the hapax is turned off or disconnected, the lights don't come on either

from __future__ import print_function

import datetime
import os.path
import mido
import time
import pdb
import pytz
import threading
import phue
import discoverhue # for finding the bridge


from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from mido import Message
from phue import Bridge
from phue import PhueRegistrationException



# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
next_event = None
next_start_time = None
lock = threading.Lock()
creds = None
email = 'hugo.grimmett@zencohen.io'
debug = 1
max_time = 0
global bridge
# service = None

def main():
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    # creds = None
    global creds
    global max_time
    global bridge

    # print('%s',mido.get_input_names())
    device = 'HAPAX'
    channel = 15 # base 0
    note = 49 # the chime
    warning_time_seconds = 15 # how long before the meeting things should happen

    # connect to philips hue bridge
    ip_address = get_hue_bridge_ip()
    # print('ip_address: {}'.format(ip_address))
    try:
        bridge = Bridge(ip_address)
        bridge.connect()
        print("Successfully connected to the Hue bridge.")
    except: 
        print("Failed to connect to the Hue bridge. Make sure you pressed the link button, and try again.")
        exit()
    

	# n_minutes_warning = 1

    # The file token.json stores the user's access and refresh tokens, and is
    # created automatically when the authorization flow completes for the first
    # time.
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    # If there are no (valid) credentials available, let the user log in.
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES)
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    try:
        #GD: avoid loops that try things all the time. Use select() function instead. It waits for a signal and is very low level
        # while(1) loop with select that is waiting for a queue of events. Second thread pushes new events to the queue.
        # alternatively, use cron to run code in the future at a particular time. Will need a dictionary of what events were already 
        # sent to the cron job. 
        # advent of code
        getNextEvent() # returns global next_event and next_start_time
        while(1):
            tic = time.time()
            chime = 0 # change to true / false
            with lock: 
            	if (next_event): # if there are no valid next events, then just cycle
                    if (datetime.datetime.now(pytz.utc) == next_start_time - datetime.timedelta(seconds=warning_time_seconds)): # .replace(microseconds=0)
                        print('🔔🎥 ',next_event['summary'] ,'is starting now! 🎥🔔')
                        try:
                            bong(1, device, channel, note)
                        except:
                            print('⚠️  ERROR: could not play a sound ⚠️')
                        # pdb.set_trace()
                        try: 
                            bridge.activate_scene(1,'aoYhBTLiGLJYEYy',0) # activate video call scene in office
                        except:
                            print('⚠️  ERROR: could not turn the lights on ⚠️') 
                        time.sleep(1)
                        chime = 1
            toc = time.time()
            if (toc > max_time) & (chime == 0):
                    max_time = max(max_time,toc-tic)
            # print(toc-tic, 'sec elapsed')

    except HttpError as error:
        print('An error occurred: %s' % error)


def getNextEvent():
    tic = time.time()
    threading.Timer(60, getNextEvent).start()
    global next_event
    global next_start_time
    global creds
    global email
    global debug
    global max_time
    # Call the Calendar API
    now = datetime.datetime.utcnow().isoformat() + 'Z'
    service = build('calendar', 'v3', credentials=creds)
    events_result = service.events().list(calendarId='primary', timeMin=now,
                                          maxResults=10, singleEvents=True,
                                          orderBy='startTime').execute()
    events = events_result.get('items', [])
    if not events:
        print('No upcoming events found.')
        exit

    # for event in events:
    #     print(event['start'],' - ', event['summary'])

    if (debug): print('Upcoming events:')
    next_event = None
    for event in events:
        # pdb.set_trace()
        if (debug): print(event['start'],' - ',event['summary'])
        
        # Exclude all-day, OOO, and focus-time events (which have 'date' but not 'dateTime'), and OOO and focus time events
        if ('dateTime' in event['start']) and (event['eventType'] == 'default'): 
            if (debug): print('   ✅ Not all-day, OOO, or focus-time event')
            start_dt = datetime.datetime.strptime(event['start'].get('dateTime'),'%Y-%m-%dT%H:%M:%S%z')
            start_dt_utc = start_dt.astimezone(pytz.utc)
            now_dt_utc = datetime.datetime.now(pytz.utc)
        else:
            if (debug): print('   ❌ All-day, OOO, or focus-time event')
            continue
            
        # Exclude events for which I am the only attendee
        if "attendees" in event: 
            if (debug): print('   ✅ Has other attendees')
        else:
            if (debug): print('   ❌ No other attendees')
            continue

        # Exclude events that I haven't accepted
        attending = 0
        for attendee in event['attendees']: 
            if (attendee['email'] == email) and (attendee['responseStatus'] == 'accepted'):
                if (debug): print('   ✅ I am marked as attending')
                attending = 1
                break
        if not attending:
            if (debug): print('   ❌ I am not marked as attending')
            continue
                
        # Exclude events that started in the past
        if (start_dt_utc > now_dt_utc):
            if (debug): print('   ✅ Starts in the future')
            with lock:
                next_event = event
                next_start_time = start_dt_utc
                if (debug): print('   🔔 This is the next chime event!')
                # print(start_dt_utc)
                break
                # pdb.set_trace()
        else:
            if (debug): print('   ❌ Already started')

    # pdb.set_trace()
    checkSensorBatteryLevels(bridge)
    toc = time.time()
    print('Calendar check time: ', round(toc-tic,2), 's')
    print('Max small loop time: ', '%.2g' % max_time, 's')


def bong(n, device, channel, note):
	outport = mido.open_output(device)
	on_msg = mido.Message('note_on', channel=channel, note=note)
	off_msg = mido.Message('note_off', channel=channel, note=note)
	for x in range(n):
		outport.send(on_msg)
		time.sleep(0.2)
		outport.send(off_msg)
		if n > 1:
			time.sleep(2)


def get_hue_bridge_ip(filename="settings_hue-bridge-ip.txt"):
    # Check if the file exists
    if os.path.exists(filename):
        # If the file exists, open it and read the contents
        with open(filename, 'r') as file:
            ip_address = file.read().strip()
        return ip_address
    else:
        # If the file doesn't exist, prompt the user to enter an IP address
        # ip_address = input("Enter the Hue Bridge IP address: ").strip()
        print('No bridge ip address config file found, so scanning for available bridges:')
        bridges = discoverhue.find_bridges()

        for i, (key, value) in enumerate(bridges.items(), start=1):
            print(f".  {i}: {key} - {value}")

        # If there's more than one item, ask the user to choose
        if len(bridges) > 1:
            choice = int(input("Choose the number of the bridge you want to use: "))
            ip_address = list(bridges.values())[choice - 1]
        else:
            ip_address = next(iter(bridges.values()))  # Automatically choose the single item

        ip_address = ip_address.rstrip('/')
        ip_address = ip_address.lstrip('http://')

        print(f"The selected IP address is: {ip_address}")

        # Save the IP address to the file
        with open(filename, 'w') as file:
            file.write(ip_address)
        
        return ip_address

def get_email(filename="settings_email.txt"):
    # Check if the file exists
    if os.path.exists(filename):
        # If the file exists, open it and read the contents
        with open(filename, 'r') as file:
            email_address = file.read().strip()
        return email_address
    else:
        # If the file doesn't exist, prompt the user to enter an email address
        email_address = input("Enter the email address for your google calendar: ").strip()
        
        # Save the email address to the file
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
        if "battery" in config:
            # print(sensor._get('name'), ' - ', config['battery'])
            if config['battery'] < 15:
                print('🔋🚨: ', sensor._get('name'), ' battery is low (',config['battery'],'%)')
                counter += 1
    if counter == 0:
        print('🔋: all good - no sensors have < 15% battery')


if __name__ == '__main__':
    main()