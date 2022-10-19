#  pipenv install mido python-rtmidi 

from __future__ import print_function

import datetime
import os.path
import mido
import time
import faulthandler

from mido import Message

def main():
	faulthandler.enable()

	# print('%s',mido.get_input_names())
	device = 'HAPAX'
	channel = 15 # base 0
	note = 49 # the chime
	first_hour = 9
	last_hour = 22
	
	# Get current time
	while (1):
		time_now = time.localtime()
		n_bongs = time_now.tm_hour % 12
		if (time_now.tm_min == 0) and (time_now.tm_sec == 0) and (time_now.tm_hour >= first_hour) and (time_now.tm_hour <= last_hour):
			print('bong! it\'s ', n_bongs, ' o\'clock')
			bong(n_bongs, device, channel, note)
	
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