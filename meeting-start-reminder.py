# Hugo Grimmett
# October 2022
#
# This script rings a bell controlled by the MIDI robot whenever a google calendar event is starting
# It also activates the lighting for meetings automatically via Hue.
# The calendar event must involve at least one other participant, and have been accepted by me
# It can handle multiple google calendars, and guide the user to connect to the Hue Bridge the first time,
# although it will not help you find the scene ID.
#
# See README.md for setup and config
#

from __future__ import print_function

import pdb

import datetime
import os.path
import mido
import time
import pytz
import tzlocal
import threading
import phue
import discoverhue
import json
from tzlocal import get_localzone
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
previous_next_event = 1 # 1 to get it to print the next meeting status when you first run the script
next_start_time = None
# creds = None
# email = None
lock = threading.Lock()
email_addresses = []
lighting = {
    "hue_bridge": None,
    "change_lights": False,
    "hue_bridge_ip_address": None,
    "hue_scene_id": None 
}
midi = {
    "play_sound": False,
    "device": None,
    "channel": 0,
    "note": 60,
    "duration": 0.2
}
scheduler = BackgroundScheduler()
event_triggered = False  # Flag to track if the event action has been triggered

debug = 0 # 1 for verbose, 0 for basic output

# Main function
def main():
    global email_addresses, bridge, lighting

    # Load settings
    load_settings('settings.json')

    try:
        # pdb.set_trace()
        lighting["hue_bridge"] = Bridge(lighting.get("hue_bridge_ip_address"))
        lighting["hue_bridge"].connect()
        print("Successfully connected to the Hue bridge ({}).".format(lighting.get("hue_bridge_ip_address")))
    except phue.PhueRegistrationException:
        print("Go press the button on your Hue bridge, and then re-run this script within 30s")
        return    
    except Exception as e:
        print(f"Failed to connect to the Hue bridge: {e}")
        return

    # Try loading or creating credentials for Google Calendar API
    print("=============================================")
    print("Searching for credentials for email addresses")
    for email in email_addresses:
        # Load credentials for the account in verbose mode
        account_creds = load_credentials(email, True, True)
    print("=============================================")

    getNextEvent() # run the first time
    scheduler.add_job(getNextEvent, 'interval', seconds=60, coalesce=True, misfire_grace_time=60)
    if (debug): print("Job scheduled for getNextEvent")
    scheduler.start()
    if (debug): print("Scheduler started")

    # Start a thread to continuously check event timing
    threading.Thread(target=continuous_event_check, daemon=True).start()

    try:
        while True:
            time.sleep(1)  # Keeps the main thread alive
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

def getNextEvent():
    if (debug): print("getNextEvent called", flush=True)
    global next_event, previous_next_event, next_start_time, email_addresses, event_triggered

    with lock:
        try:
            now = datetime.datetime.now(datetime.timezone.utc).isoformat().replace('+00:00', 'Z')
            earliest_event = None
            earliest_start_time = None
            next_email = None

            for email in email_addresses:
                # Load credentials for the account
                account_creds = load_credentials(email, False, False)
                if not account_creds:
                    # print(f"Skipping account {email} due to missing credentials.")
                    continue

                service = build('calendar', 'v3', credentials=account_creds)
                events_result = service.events().list(calendarId='primary', timeMin=now,
                                                      maxResults=10, singleEvents=True,
                                                      orderBy='startTime').execute()
                events = events_result.get('items', [])
                # if not events:
                #     print('No upcoming events found.')
                #     return

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
                            # Compare to find the earliest event across all accounts
                            if earliest_event is None or start_dt_utc < earliest_start_time:
                                earliest_event = event
                                earliest_start_time = start_dt_utc
                                next_email = email
            
            # Update global variables with the earliest event
            previous_next_event = next_event
            next_event = earliest_event
            next_start_time = earliest_start_time
            
            # Get the local timezone dynamically
            local_tz = get_localzone()

            if next_event:
                # print('previous next event: {}'.format(previous_next_event))
                # print('new next event: {}'.format(next_event))
                # Convert UTC to local time before printing
                local_next_start_time = next_start_time.astimezone(local_tz)
                if (debug) or (previous_next_event != next_event): print(f"Next meeting is: {next_event['summary']} at {local_next_start_time} ({next_email})")
                event_triggered = False  # Reset the flag for new event
            else:
                if (debug) or (previous_next_event != next_event): print('No upcoming meetings found.')
                # Clear the event details if no valid events
                previous_next_event = None
                next_event = None
                next_start_time = None

        except HttpError as error:
            print(f'An error occurred: {error}')

def continuous_event_check():
    if (debug): print("Continuous event check started", flush=True)
    global next_event, next_start_time, event_triggered, lighting, midi
    tolerance_seconds = 5
    warning_time_seconds = 15

    while True:
        with lock:
            now = datetime.datetime.now(pytz.utc)
            if next_event:
                time_diff = (next_start_time - now).total_seconds()
                if 0 <= time_diff <= warning_time_seconds:
                    if not event_triggered:
                        print(f'🔔🎥 {next_event["summary"]} is starting now! 🎥🔔')
                        if midi["play_sound"]:
                            try:
                                bong(1, midi.get("midi_device"), midi.get("midi_channel"), midi.get("midi_note"))
                            except Exception as e:
                                print(f'⚠️  ERROR: could not play a sound: {e} ⚠️')
                        if lighting["change_lights"]:
                            try:
                                # activate hue scene
                                lighting.get("hue_bridge").activate_scene(1, lighting.get("hue_scene_id"), 0)
                            except Exception as e:
                                print(f'⚠️  ERROR: could not turn the lights on: {e} ⚠️')
                        else:
                            if verbose: print(f"⚠️  ERROR: no hue bridge scene ID")
                        event_triggered = True  # Set the flag to indicate the event action has been triggered
                    else:
                        if (debug): print('event already triggered')
                elif time_diff < 2:
                    # if we are past the warning window, clear the event
                    next_event = None
                    next_start_time = None
                    event_triggered = False  # Reset the trigger flag
                else:
                    if (debug): print(f"Event '{next_event['summary']}' is not yet within the time window ({warning_time_seconds}s).")
            else:
                if (debug): print("No upcoming event found.")
        time.sleep(1)  # Check every second


def bong(n, device, channel, note, duration):
    outport = mido.open_output(device)
    on_msg = mido.Message('note_on', channel=channel, note=note)
    off_msg = mido.Message('note_off', channel=channel, note=note)
    for _ in range(n):
        outport.send(on_msg)
        time.sleep(duration)
        outport.send(off_msg)
        if n > 1:
            time.sleep(2)

def load_settings(file_path="settings.json", verbose=True):
    global email_addresses, lighting, midi
    if verbose: print(f"🎛️  Loading settings")
    try:
        with open(file_path, 'r') as file:
            settings = json.load(file)
        
        # Assign settings to global variables
        email_addresses = settings.get("email_addresses", email_addresses)
        # check for missing email addresses
        if not email_addresses:
            if verbose: print("    ⚠️ Email addresses are missing.")
            email_addresses = guide_user_to_enter_email_addresses()
            settings["email_addresses"] = email_addresses  # Update settings dictionary
            save_settings(file_path, settings)  # Save updated settings to file
        print(f'    Email addresses: {email_addresses}')
        
        lighting = settings.get("lighting", lighting)
        # Check for missing Hue Bridge IP address
        if not lighting.get("hue_bridge_ip_address"):
            if verbose: print("    ⚠️ Hue Bridge IP address is missing.")
            user_choice = input("Would you like to connect a Hue Bridge now? (y/n): ").strip().lower()
            if user_choice == 'y':
                # Run connection logic and update settings
                lighting["hue_bridge_ip_address"] = guide_user_to_connect_hue_bridge()
                settings["lighting"] = lighting  # Update settings dictionary
                save_settings(file_path, settings)  # Save updated settings to file
                lighting["change_lights"] = True
            else:
                if verbose: print("    ⚠️ No Hue Bridge IP address provided. Some features may not work.")
        else:
            print(f"    Hue bridge IP: {lighting.get("hue_bridge_ip_address")}")
            lighting["change_lights"] = True

        # check for missing scene ID
        if not lighting.get("hue_scene_id"):
            if verbose: print("    ⚠️ Hue scene ID is missing. No hue automation will take place.")
            # to do: guide user to choose scene
        else:
            print(f"    Hue scene ID: {lighting.get("hue_scene_id")}")

        midi = settings.get("midi", midi)
        # check for missing MIDI
        if not midi.get("midi"):
            if verbose: print("    ⚠️  MIDI information is missing. No MIDI automation will take place.")
            midi["play_sound"] = False
        else:
            midi["play_sound"] = True
        
        if verbose: print("    ✅  Settings loaded successfully.")
    except FileNotFoundError:
        if verbose: print(f"    ⚠️  Error: Settings file '{file_path}' was not found.")
    except json.JSONDecodeError:
        if verbose: print(f"    ⚠️  Error: Settings file '{file_path}' contains invalid JSON.")
    except Exception as e:
        if verbose: print(f"    ⚠️  An unexpected error occurred: {e}")

def save_settings(file_path, settings, verbose = True):
    """
    Saves the updated settings back to the JSON file.
    
    Args:
        file_path (str): Path to the JSON file.
        settings (dict): The settings dictionary to save.
    """
    if verbose: print(f"Saving new setting: {settings}")
    try:
        with open(file_path, 'w') as file:
            json.dump(settings, file, indent=4)
        if verbose: print(f"    💾 Settings saved to {file_path}.")
    except Exception as e:
        if verbose: print(f"    ⚠️ Error: Unable to save settings to {file_path}: {e}")

def guide_user_to_connect_hue_bridge(verbose = True):
    if verbose: print('    Scanning for available bridges:')
    bridges = discoverhue.find_bridges()

    for i, (key, value) in enumerate(bridges.items(), start=1):
        print(f".  {i}: {key} - {value}")

    if len(bridges) > 1:
        choice = int(input("    Choose the number of the bridge you want to use: "))
        ip_address = list(bridges.values())[choice - 1]
    else:
        ip_address = next(iter(bridges.values()))  # Automatically choose the single item
    ip_address = ip_address.rstrip('/')
    ip_address = ip_address.lstrip('http://')
    print(f"The selected IP address is: {ip_address}")
    return ip_address

# Function to get the email address from a file or user input
# def get_emails(filename="settings_email.txt"):
#     if os.path.exists(filename):
#         with open(filename, 'r') as file:
#             email_address = file.read().strip()
#             print(f'Chosen email address: {email_address}')
#         return email_address
#     else:
#         email_address = input("Enter the email address for your google calendar: ").strip()
#         with open(filename, 'w') as file:
#             file.write(email_address)
#         return email_address

def guide_user_to_enter_email_addresses(filename="settings_email.txt", verbose = True):
    if os.path.exists(filename):
        with open(filename, 'r') as file:
            # Read all lines, strip whitespace, and filter out empty lines
            email_addresses = [line.strip() for line in file.readlines() if line.strip()]
            print(f'Loaded email addresses: {email_addresses}')
            return email_addresses
    else:
        # Prompt the user for email addresses if the file doesn't exist
        email_input = input("Enter email addresses for your Google calendars, separated by commas: ").strip()
        email_addresses = [email.strip() for email in email_input.split(',') if email.strip()]
        
        # Save to file
        with open(filename, 'w') as file:
            file.write('\n'.join(email_addresses))
        
        print(f'Saved email addresses: {email_addresses}')
        return email_addresses

def load_credentials(email, create_if_not_existent=False, verbose=True):
    """
    Load credentials for a given email address using the token_[email].json format. 
    If that doesn't exist and create_if_non_existent=True, then try to load credentials_{email}.json 
    and generate the token file from that.
    """
    if verbose:
        print(f"📧 Trying email address: {email}")
    token_file = f"token_{email}.json"
    credentials_file = f"credentials_{email}.json"
    
    # Attempt to load the token file if it exists
    if os.path.exists(token_file):
        if verbose: print(f"    Token file {token_file} found")
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)
        if not creds or not creds.valid:
            if verbose: print(f"    ... but credentials are either not present or expired")
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    # Log a detailed error message for debugging
                    if verbose:
                        print(f"   ❌ Error: Failed to refresh token for {email}. Exception: {e}.")
                        print(f"   Deleting token file {token_file} to force reauthorisation next time.")
                    os.remove(token_file)  # Force a reauthorization on the next run
                    return None
        if verbose:
            print(f"   ✅ Credentials loaded")
        return creds
    else:
        if create_if_not_existent:
            if os.path.exists(credentials_file):
                if verbose: 
                    print(f"   Token file {token_file} not found, but credentials file {credentials_file} found - trying to generate token.")
                try:
                    flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
                    creds = flow.run_local_server(port=0)
                    with open(token_file, 'w') as token:
                        token.write(creds.to_json())
                    if verbose:
                        print(f"   Saved generated token to {token_file}.")
                        print(f"   ✅ Credentials loaded")
                except:
                    if verbose:
                        print(f"   ❌ Error: Credentials file {credentials_file} exists, but could not generate token from it.")
                    return None
            else:
                if verbose:
                    print(f"   ❌ Error: The file {credentials_file} was not found. Please check the file path, or generate from via the google cloud console and rename appropriately.")
                return None
            
        else:
            if verbose:
                print(f"   ❌ Error: No token file {token_file} exists. Did not check whether {credentials_file} exists.")
            return None

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
