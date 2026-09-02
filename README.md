This project is about having a light and sound interaction just before a calendar meeting is about to start. The script scans google calendar(s) every 60s to find the next meeting, and 15s before it starts it actives a Philips Hue scene and plays a MIDI note.
Instructions are for mac.

Written by Hugo Grimmett

Requires python 3.10 or newer (verified on 3.13). Several pinned packages —
including urllib3, protobuf, aiohttp and requests — declare `requires_python >=3.10`,
so older interpreters will fail at `pip install`.
```
brew install python
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

Format for settings.json — lighting can be either Philips Hue OR Home Assistant:

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

For Home Assistant instead of Hue, replace the `lighting` block:

```
  "lighting": {
    "ha_url": "http://192.168.x.x:8123",
    "ha_token": "<long-lived access token from HA>",
    "ha_scene_id": "scene.your_scene_name"
  },
```

## Home Assistant + VPN gotcha

If you use a full-tunnel VPN (ProtonVPN, etc.), avoid using `homeassistant.local`
in `ha_url`. mDNS may resolve HA to an IP on a subnet that isn't your Mac's own
LAN (e.g. a Deco IoT-network subnet), and even with "Allow LAN connections"
enabled the VPN will send that traffic into the tunnel because the destination
isn't on your local /24.

Fix: put HA's LAN IP directly in `ha_url` (e.g. `http://192.168.0.63:8123`) and
reserve that address in your router's DHCP settings so it doesn't drift. In the
Deco app: **More → Advanced → Address Reservation → Add**.

To confirm which IP is actually on your LAN when HA has multiple:

```
route get <candidate-ip>   # should show interface: enX (your Wi-Fi), not utunN
```

The latest script is meeting-start-reminder.py:
```
python3 meeting-start-reminder.py
```
