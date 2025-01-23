# Hugo Grimmett
# October 2022
#
# This script rings a bell controlled by the MIDI robot whenever a google calendar event is starting
# It also activates the lighting for meetings automatically via Hue.
# The calendar event must involve at least one other participant, and have been accepted by me
# It can handle multiple google calendars, and guide the user through all the settings if required.
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
hue_bridge = None
change_lights = False
lighting = {
    "hue_bridge_ip_address": None,
    "hue_scene_id": None 
}
midi = {"device": None}
play_sound = False
scheduler = BackgroundScheduler()
event_triggered = False  # Flag to track if the event action has been triggered

debug = 0 # 1 for verbose, 0 for basic output

# Main function
def main():
    global email_addresses, hue_bridge, lighting

    # Load settings
    load_settings('settings.json')

    # Connect to Hue bridge
    connectToBridge()

    # Try loading or creating credentials for Google Calendar API
    print("=============================================")
    print("Searching for credentials for email addresses")
    for email in email_addresses:
        # Load credentials for the account in verbose mode
        account_creds = load_credentials(email, True, True)
    print("=============================================")

    # Get next calendar event, and re-run periodically
    getNextEvent() # run the first time
    scheduler.add_job(getNextEvent, 'interval', seconds=60, coalesce=True, misfire_grace_time=60)
    if (debug): print("Job scheduled for getNextEvent")
    scheduler.start()
    if (debug): print("Scheduler started")

    # Start a thread to continuously check event timing
    threading.Thread(target=continuous_event_check, daemon=True).start()

    # Don't crash if computer goes to sleep
    try:
        while True:
            time.sleep(1)  # Keeps the main thread alive
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()

def connectToBridge():
    global lighting, hue_bridge
    if hue_bridge is None:
        try:
            hue_bridge = Bridge(lighting.get("hue_bridge_ip_address"))
            hue_bridge.connect()
            print("Successfully connected to the Hue bridge ({}).".format(lighting.get("hue_bridge_ip_address")))
        except phue.PhueRegistrationException:
            print("Go press the button on your Hue bridge, and then re-run this script within 30s")
            return    
        except Exception as e:
            print(f"Failed to connect to the Hue bridge: {e}")
            return

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
    global next_event, next_start_time, event_triggered, lighting, midi, hue_bridge, play_sound, change_lights
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
                        if play_sound:
                            try:
                                bong(1, midi.get("device"), midi.get("channel"), midi.get("note"), midi.get("duration"))
                            except Exception as e:
                                print(f'⚠️  ERROR: could not play a sound: {e} ⚠️')
                        if change_lights:
                            try:
                                # activate hue scene
                                hue_bridge.activate_scene(1, lighting.get("hue_scene_id"), 0)
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


def load_credentials(email, create_if_not_existent=False, verbose=True):
    token_file = f"token_{email}.json"
    credentials_file = f"credentials_{email}.json"
    
    if verbose: print(f"Trying email address: {email}")

    # Attempt to load the token file
    if os.path.exists(token_file):
        try:
            creds = Credentials.from_authorized_user_file(token_file, SCOPES)
            if creds.valid:
                if verbose: print(f"   ✅ Credentials loaded successfully from {token_file}")
                return creds
            if creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                    with open(token_file, 'w') as token:
                        token.write(creds.to_json())
                    if verbose: print(f"   🔄 Token refreshed and saved to {token_file}")
                    return creds
                except Exception as e:
                    if verbose: print(f"   ❌ Error refreshing token: {e}")
                    return None
        except Exception as e:
            if verbose: print(f"   ⚠️ Error reading token file {token_file}: {e}")
            return None

    # Token file does not exist, handle accordingly
    if create_if_not_existent and os.path.exists(credentials_file):
        if verbose: print(f"   Token file not found, attempting to create from {credentials_file}")
        try:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
            with open(token_file, 'w') as token:
                token.write(creds.to_json())
            if verbose: print(f"   ✅ New token saved to {token_file}")
            return creds
        except Exception as e:
            if verbose: print(f"   ❌ Error generating token from {credentials_file}: {e}")
            return None

    print(f"   ❌ No valid token or credentials available for {email}.")
    return None

def load_settings(file_path="settings.json", verbose=True):
    global email_addresses, lighting, midi, hue_bridge, play_sound, change_lights
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
                change_lights = True
            else:
                if verbose: print("    ⚠️ No Hue Bridge IP address provided. Some features may not work.")
        else:
            print(f"    Hue bridge IP: {lighting.get("hue_bridge_ip_address")}")
            change_lights = True

        # check for missing scene ID
        if not lighting.get("hue_scene_id"):
            scene_id = guide_user_to_lighting_scene_id()
            if scene_id is None:
                if verbose: print("    ⚠️ Hue scene ID is missing. No hue automation will take place.")
                change_lights = False
            else:
                lighting["hue_scene_id"] = scene_id
                save_settings(file_path, settings)  # Save updated settings to file
                change_lights = True
        else:
            print(f"    Hue scene ID: {lighting.get("hue_scene_id")}")

        midi = settings.get("midi", midi)
        # check for missing MIDI
        if not midi.get("device") or not midi.get("channel") or not midi.get("note") or not midi.get("duration"):
            midi = guide_user_to_enter_midi_data(midi)
            if midi.get("device") is None or midi.get("channel") is None or midi.get("note") is None or midi.get("duration") is None:
                if verbose: print("    ⚠️  MIDI information is missing. No MIDI automation will take place.")
                play_sound = False
            else:
                play_sound = True
                print(f"    MIDI:")
                print(f"        Device: {midi.get("device")}")
                print(f"        Channel: {midi.get("channel")}")
                print(f"        Note: {midi.get("note")}")
                print(f"        Duration: {midi.get("duration")}")
                settings["midi"] = midi # update midi dictionary
                save_settings(file_path,settings) # save to settings file
                print(f"    saved to {file_path}")
        else:
            play_sound = True
            print(f"    MIDI:")
            print(f"        Device: {midi.get("device")}")
            print(f"        Channel: {midi.get("channel")}")
            print(f"        Note: {midi.get("note")}")
            print(f"        Duration: {midi.get("duration")}")
        
        if verbose: print("    ✅  Settings loaded successfully.")
    except FileNotFoundError:
        if verbose: print(f"    ⚠️  Error: Settings file '{file_path}' was not found.")
    except json.JSONDecodeError:
        if verbose: print(f"    ⚠️  Error: Settings file '{file_path}' contains invalid JSON.")
    except Exception as e:
        if verbose: print(f"    ⚠️  An unexpected error occurred: {e}")

def save_settings(file_path, settings, verbose = True):
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

def guide_user_to_enter_email_addresses(filename="settings_email.txt", verbose = True):
    # Prompt the user for email addresses if the file doesn't exist
    email_input = input("Enter email addresses for your Google calendars, separated by commas: ").strip()
    email_addresses = [email.strip() for email in email_input.split(',') if email.strip()]
    
    return email_addresses

def guide_user_to_enter_midi_data(midi, verbose = True):
    if midi.get("device") is None:
        # List available input ports
        input_ports = mido.get_input_names()

        # Check if there are any MIDI ports available
        if not input_ports:
            print("No MIDI input ports available.")
            midi["device"] = None
            return midi
        else:
            # Print enumerated list of options
            print("Available MIDI Input Ports:")
            for i, port in enumerate(input_ports):
                print(f"{i}: {port}")

            # Ask the user to select a port
            selection = False
            while selection == False:
                try:
                    selected_index = int(input("Enter the number corresponding to the desired MIDI input port: "))
                    if 0 <= selected_index < len(input_ports):
                        midi["device"] = input_ports[selected_index]
                        selection = True # continue
                    else:
                        print("Invalid selection. Please enter a number from the list.")
                except ValueError:
                    print("Invalid input. Please enter a valid number.")
                    midi["device"] = None
                    return midi
 
    if not midi.get("channel"):
        selection = False
        while selection == False:
            try:
                channel = int(input("Select MIDI channel (0-15): "))
                if 0 <= channel <= 15:
                    midi["channel"] = channel
                    selection = True # continue
                else:
                    print("Invalid selection. Please enter a number in the range 0-15.")
            except ValueError:
                print("Invalid input. Please enter a valid number.")
                midi["channel"] = None
                return midi

    if not midi.get("note"):
        selection = False
        while selection == False:
            try:
                note = int(input("Select MIDI note (0-127): "))
                if 0 <= note <= 127:
                    midi["note"] = note
                    selection = True # continue
                else:
                    print("Invalid selection. Please enter a number in the range 0-127.")
            except ValueError:
                print("Invalid input. Please enter a valid number.")
                midi["note"] = None
                return midi

    if not midi.get("duration"):
        selection = False
        while selection == False:
            try:
                duration = float(input("Select note duration (>0): "))
                if 0 < duration:
                    midi["duration"] = duration
                    selection = True # continue
                else:
                    print("Invalid selection. Please enter a number > 0.")
            except ValueError:
                print("Invalid input. Please enter a valid number.")
                midi["duration"] = None
                return midi
    return midi

def guide_user_to_lighting_scene_id():
    global lighting, hue_bridge
    connectToBridge()
    bridge = hue_bridge
    # Get groups (rooms) from the Hue bridge
    # pdb.set_trace()
    # Get all groups (rooms and zones)
    groups = bridge.groups
    if not groups:
        print("No groups available on the Hue bridge.")
        return None

    # Enumerate all groups (rooms)
    print("Available groups:")
    for i, group in enumerate(groups, start=1):
        print(f"{i}. {group.name}")

    try:
        group_choice = int(input("Select a group by number: ")) - 1
        if group_choice < 0 or group_choice >= len(groups):
            print("Invalid group selection.")
            return None
    except ValueError:
        print("Invalid input. Please enter a number.")
        return None

    selected_group = groups[group_choice]
    selected_group_id = selected_group.group_id
    selected_group_name = selected_group.name

    # pdb.set_trace()
    # Get scenes linked to the selected group
    scenes = bridge.scenes
    group_scenes = {scene.scene_id: scene for scene in scenes if scene.group == str(selected_group_id)}

    if not group_scenes:
        print(f"No scenes available for group: {selected_group_name}")
        return None

    # Enumerate scenes and ask the user to choose one
    print(f"Available scenes for group '{selected_group_name}':")
    for i, (scene_id, scene) in enumerate(group_scenes.items(), start=1):
        print(f"{i}. {scene.name}")

    try:
        scene_choice = int(input("Select a scene by number: ")) - 1
        if scene_choice < 0 or scene_choice >= len(group_scenes):
            print("Invalid scene selection.")
            return None
    except ValueError:
        print("Invalid input. Please enter a number.")
        return None

    selected_scene_id = list(group_scenes.keys())[scene_choice]
    selected_scene_name = group_scenes[selected_scene_id].name

    print(f"You selected scene: '{selected_scene_name}' with ID: {selected_scene_id}")
    return selected_scene_id

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
