#  pipenv install google-api-python-client google-auth-httplib2 google-auth-oauthlib mido python-rtmidi pytz

from __future__ import print_function

import datetime
import os.path
import mido
import time
import pdb
import pytz

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from mido import Message
from datetime import datetime

# If modifying these scopes, delete the file token.json.
SCOPES = ['https://www.googleapis.com/auth/calendar.readonly']


def main():
    """Shows basic usage of the Google Calendar API.
    Prints the start and name of the next 10 events on the user's calendar.
    """
    creds = None

    # print('%s',mido.get_input_names())
    device = 'HAPAX'
    channel = 15 # base 0
    note = 49 # the chime

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
        service = build('calendar', 'v3', credentials=creds)

        
       
        # Call the Calendar API
        now = datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
        print('Fetching upcoming events')
        events_result = service.events().list(calendarId='primary', timeMin=now,
                                              maxResults=3, singleEvents=True,
                                              orderBy='startTime').execute()
        events = events_result.get('items', [])

        # Prints the start and name of the next 10 events
        next_event = None
        for event in events:
            start_dt = datetime.strptime(event['start'].get('dateTime'),'%Y-%m-%dT%H:%M:%S%z')
            start_dt_utc = start_dt.astimezone(pytz.utc)
            now_dt_utc = datetime.now(pytz.utc)
            # pdb.set_trace()

            if not next_event:
                if (start_dt_utc > now_dt_utc):
                    next_event = event
                    next_start_time = start_dt_utc
        
        
        while(1):
            if (datetime.now(pytz.utc) == next_start_time):
                print(next_event['summary'] ,'is starting!')
                bong(1, device, channel, note)
                # pdb.set_trace()
                time.sleep(1)


    except HttpError as error:
        print('An error occurred: %s' % error)

def bong(n, device, channel, note):
	outport = mido.open_output(device)
	on_msg = mido.Message('note_on', channel=channel, note=note)
	off_msg = mido.Message('note_off', channel=channel, note=note)
	for x in range(n):
		outport.send(on_msg)
		time.sleep(0.2)
		outport.send(off_msg)
		time.sleep(2)


if __name__ == '__main__':
    main()