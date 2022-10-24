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

from __future__ import print_function

import datetime
import os.path
import mido
import time
import pdb
import pytz
import threading
import phue


from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from mido import Message
from phue import Bridge


# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']
next_event = None
next_start_time = None
lock = threading.Lock()
creds = None
email = 'hugo.grimmett@woven-planet.global'
debug = 1
# service = None

def main():
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    # creds = None
    global creds

    # print('%s',mido.get_input_names())
    device = 'HAPAX'
    channel = 15 # base 0
    note = 49 # the chime
    warning_time_seconds = 15 # how long before the meeting things should happen

    # connect to philips hue bridge
    bridge = Bridge('192.168.178.96')
    bridge.connect()

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
        getNextEvent() # returns global next_event and next_start_time
        while(1):
            with lock:
            	if (next_event): # if there are no valid next events, then just cycle
                    if (datetime.datetime.now(pytz.utc) == next_start_time - datetime.timedelta(seconds=warning_time_seconds)):
                        print('🔔🎥 ',next_event['summary'] ,'is starting now! 🎥🔔')
                        bong(1, device, channel, note)
                        # pdb.set_trace()
                        bridge.activate_scene(1,'aoYhBTLiGLJYEYy',0) # activate video call scene in office
                        time.sleep(1)


    except HttpError as error:
        print('An error occurred: %s' % error)

def getNextEvent():
    # threading.Timer(60, getNextEvent).start()
    global next_event
    global next_start_time
    global creds
    global email
    global debug
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
        if ('dateTime' in event['start']) and (event['eventType'] == 'default'): # exclude all-day events (which have 'date' but not 'dateTime'), and OOO and focus time events
            if (debug): print('   ✅ Not all-day, OOO, or focus-time event')
            start_dt = datetime.datetime.strptime(event['start'].get('dateTime'),'%Y-%m-%dT%H:%M:%S%z')
            start_dt_utc = start_dt.astimezone(pytz.utc)
            now_dt_utc = datetime.datetime.now(pytz.utc)
            

            if not next_event:
                # pdb.set_trace()
                if "attendees" in event: # only continue if the event has other people in it
                    if (debug): print('   ✅ Has other attendees')
                    for attendee in event['attendees']: # only continue if I have accepted the meeting
                        if (attendee['email'] == email) and (attendee['responseStatus'] == 'accepted'):
                            if (debug): print('   ✅ I am marked as attending')
                            if (start_dt_utc > now_dt_utc):
                                if (debug): print('   ✅ Starts in the future')
                                with lock:
                                    next_event = event
                                    next_start_time = start_dt_utc
                                    if (debug): print('   🔔 This is the next chime event!')
                                    break
                                    # pdb.set_trace()
                            else:
                                if (debug): print('   ❌ Already started')
                        else:
                            if (debug): print('   ❌ I am not marked as attending')
                            pdb.set_trace()
                else:
                    if (debug): print('   ❌ No other attendees')
        else:
            if (debug): print('   ❌ All-day, OOO, or focus-time event')




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


if __name__ == '__main__':
    main()