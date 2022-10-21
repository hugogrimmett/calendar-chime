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
import time
import pdb
import threading
import phue
import json


from phue import Bridge



def main():
    # connect to philips hue bridge
    bridge = Bridge('192.168.178.96')
    bridge.connect()
    checkSensorBatteryLevels(bridge)

def checkSensorBatteryLevels(bridge):
    sensor_names = bridge.get_sensor_objects('name')
    sensor_ids = bridge.get_sensor_objects('id')
    sensors = bridge.get_sensor_objects()
    # print(sensors)
    # print(len(sensors))
    # pdb.set_trace()
    for sensor in sensors:
        config = sensor._get('config')
        if "battery" in config:
            # print(sensor._get('name'), ' - ', config['battery'])
            if config['battery'] < 15:
                print('Warning: ', sensor._get('name'), ' battery is low (',config['battery'],'%)')

if __name__ == '__main__':
    main()