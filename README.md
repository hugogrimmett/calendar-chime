This project is about having a light and sound interaction just before a calendar meeting is about to start. The script scans google calendar(s) every 60s to find the next meeting, and 15s before it starts it actives a Philips Hue scene and plays a MIDI note.
Instructions are for mac.

Written by Hugo Grimmett

Uses python 3.8.15
```
brew install python
pyenv install 3.8.15
```

Recommended: create a virtual environment for this project
```
python3 -m venv venv
source venv/bin/activate
```

Packages required: 
```
pip install -r requirements.txt
``` 

Format for settings.json:
```
{
  "email_addresses": [
    "myemail@domain.com",
    "otheremail@otherdomain.com"
  ],
  "lighting": {
    "hue_bridge_ip_address": "xxx.xxx.xxx.xx:xx",
    "hue_scene_id": "abcdefghijkl"
  },
  "midi": {
    "device": "my_midi_device",
    "channel": 0,
    "note": 49,
    "duration": 0.2
  }
}
```

The latest script is meeting-start-reminder.py:
```
python3 meeting-start-reminder.py
```
