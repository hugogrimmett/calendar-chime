This project is about having a light and chime interaction when a meeting is about to start. Instructions are for mac.

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
OR
```
pip install google-api-python-client google-auth-httplib2 google-auth-oauthlib mido python-rtmidi python-rtmidi pytz phue discoverhue apscheduler
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
python meeting-start-reminder.py
```
