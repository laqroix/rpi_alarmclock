# RPi Alarm Clock & Radio

Simple alarm clock & internet radio for Raspberry Pi, streaming via VLC, rendering to an SPI ST7789 LCD and controlled by 4 GPIO buttons.

## Features
- Per‑day schedule (7 entries) with enable/disable.
- Automatic calculation of the next upcoming alarm.
- Internet radio playback (default stream `https://ice.actve.net/fm-evropa2-128`).
- Fallback: if stream / internet fails while ringing, plays a random local file from `~/Music`.
- Power saving: display backlight auto‑dims after inactivity, wakes on button press.
- Wi‑Fi status indicator (green / red square).
- On‑device alarm time editor (day, hour, minute in 5‑minute steps, enabled flag).
- Separate radio screen (play/stop selection).

## Hardware
- Tested only on: Raspberry Pi Zero / Zero W + Pimoroni PIM485 (1.54" / 240×240 ST7789 SPI LCD).
- Other Raspberry Pi models should work (may need wiring / backlight adjustments) but are untested.
- 4 × momentary push buttons on GPIO: 5 (A), 6 (B), 16 (X), 24 (Y) using internal pull‑ups.
- Pin 13 (GPIO13) – PWM backlight (prefer via transistor / FET for higher current).
- (Optional) Audio output device (3.5 mm jack, USB sound card, HDMI audio).

## Button logic
| Button | Top row meaning | Bottom row meaning |
|--------|------------------|--------------------|
| A (GPIO5) | Vertical up / switch section | – |
| B (GPIO6) | Vertical down / switch section | – |
| X (GPIO16)| Left (change item / menu) | – |
| Y (GPIO24)| Right (change item / menu) | – |

Note: If the display is off (dimmed), the first press only wakes and refreshes it.

## Screens (top menu indexes)
1. Alarm – current time, next alarm, Wi‑Fi indicator. When ringing shows text "STOVAC" in red.
2. Settings – edit: day, hour, minute, enabled.
3. Radio – area with two buttons STOP / PLAY.

## Alarm times file format
CSV: `~/alarmclock.csv`

Each line: `day,hour,minute,enabled`

Day index (0=Monday ... 6=Sunday). Example:
```
0,7,30,1
1,7,30,1
2,7,30,1
3,7,30,1
4,7,30,1
5,9,00,0
6,9,00,0
```

Seconds from midnight are derived on load. Editing in the UI writes immediately to the file.

## Background image
Optional image `~/cat.jpg` (code path `/home/pi/cat.jpg`). If missing, a black background is used.

## Dependencies (Python)
| Library | Purpose |
|---------|---------|
| RPi.GPIO | GPIO & buttons |
| st7789   | SPI LCD control |
| python-vlc | Stream / local audio playback |
| requests | Connectivity check |
| Pillow (PIL) | UI drawing |

Install example:
```bash
sudo apt update
sudo apt install -y python3-pip vlc
pip3 install RPi.GPIO pillow requests python-vlc
# st7789 library – depending on your board (e.g. Pimoroni):
pip3 install st7789
```

## Run
```bash
python3 rpi-alarmclock.py
```

First run expects `~/alarmclock.csv`. Create manually if missing.

## systemd service (autostart on boot)
Create `/etc/systemd/system/rpi-alarmclock.service`:
```
[Unit]
Description=RPi Alarm Clock
After=network-online.target sound.target
Wants=network-online.target

[Service]
User=pi
WorkingDirectory=/home/pi/rpi-alarmclock
ExecStart=/usr/bin/python3 /home/pi/rpi-alarmclock/rpi-alarmclock.py
Restart=on-failure
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
```
Then:
```bash
sudo systemctl daemon-reload
sudo systemctl enable rpi-alarmclock
sudo systemctl start rpi-alarmclock
sudo systemctl status rpi-alarmclock
```

## How the alarm logic works
1. Threads:
	- `alarm_thread` checks alarm activation every second.
	- `internet_thread` updates connectivity every 5 s (only if display is lit).
2. Trigger: if alarm time within ± <30 s and not ringing yet, start stream.
3. Monitor: if stream stops or internet fails, switch to random local file.
4. Stop: after 20 minutes or by user (button press that wakes + resets).

## Customization
- Change stream: edit `self.url` in `Alarm` and `Radio` classes.
- Auto dim interval: `refresh_counter` logic (~30 s currently).
- Backlight brightness: change values passed to `self.backlight.start(…)` (0–100).

## Troubleshooting
| Issue | Fix |
|-------|-----|
| Blank display | Check SPI wiring, `rotation`, `cs`, `dc`, power. |
| Buttons ignored | Confirm pull‑ups (code uses `GPIO.PUD_UP`) and correct BCM numbers. |
| Radio silent | Check internet; run `vlc` manually; verify stream URL alive. |
| Fallback not used | Ensure `~/Music` has at least one VLC‑playable file. |
| Font warning | `arial.ttf` missing; default font used. Install `ttf-mscorefonts-installer` if desired. |
| CSV not updating | File permissions for `~/alarmclock.csv` (User=pi). |

## Security & limitations
- Connectivity check uses plain HTTP (`http://192.168.0.1`). Adapt for your network/security needs.
- CSV parsing has minimal error handling; malformed lines can break logic.

## Possible future improvements
- Multiple radio presets.
- Web UI for editing alarms.
- Logging (stream OK / fallback triggered).
- Adaptive brightness (time / light sensor).
- Long press = snooze.

## License
Choose a license (e.g. MIT) and add here. (Currently unspecified.)

## Author
Personal Raspberry Pi alarm clock experiment.

---
Contributions via pull requests are welcome.

