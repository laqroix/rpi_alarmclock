#!/usr/bin/env python3
import os
import csv
import random
from datetime import datetime
from time import sleep
import threading

import RPi.GPIO as GPIO
import st7789
import vlc
import requests
from PIL import Image, ImageDraw, ImageFont

# Constants
BUTTONS = [5, 6, 16, 24]
LABELS = ['A', 'B', 'X', 'Y']
DAY_TO_STRING = ["poniedzialek", "wtorek", "sroda", "czwartek", "piatek", "sobota", "niedziela"]


def draw_in_box(text, font, rect_start, rect_end, draw, color='white'):
    """Draw text centered within a rectangular area."""
    x, y, text_width, text_height = draw.textbbox((0, 0), text, font=font)
    text_x = rect_start[0] + (rect_end[0] - rect_start[0] - text_width) // 2
    text_y = rect_start[1] + (rect_end[1] - rect_start[1] - text_height) // 2
    draw.text((text_x, text_y), text, fill=color, font=font)


def internet_connection():
    """Check if internet connection is available."""
    try:
        response = requests.get("http://192.168.0.1", timeout=2)
        return True
    except requests.ConnectionError:
        return False


def draw_wifi_status(draw, status):
    """Draw WiFi connection status indicator."""
    rect_start = (5, 5)
    rect_mid_end = (25, 25)

    if status:
        draw.rectangle([rect_start, rect_mid_end], fill='green', outline='white', width=2)
    else:
        draw.rectangle([rect_start, rect_mid_end], fill='red', outline='white', width=2)


class Radio:
    """Handle radio player functionality and UI."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.cursor_v_index = 0
        self.cursor_h_index = 0

        self.url = 'https://ice.actve.net/fm-evropa2-128'
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        self.media = self.instance.media_new(self.url)
        self.player.set_media(self.media)

    def set_v_cursor(self, cursor_offset):
        self.cursor_v_index += cursor_offset
        self.cursor_v_index %= 2

    def set_h_cursor(self, cursor_offset):
        self.cursor_h_index += cursor_offset
        self.cursor_h_index %= 2

    def cdraw(self, image):
        self.draw_top_menu(image)

    def draw_top_menu(self, image):
        self.draw = ImageDraw.Draw(image)
        border = 2
        rect_start = (0, 0)
        rect_mid_end = (self.width, self.height * 0.25)
        rect_mid_start = (0, self.height * 0.25)
        rect_end = (self.width, self.height)
        button_v_offset = 69

        button1 = [(0 + 10, self.height * 0.25 + button_v_offset),
                  (self.width * 0.5 - 10, self.height - button_v_offset)]
        button2 = [(self.width * 0.5 + 10, self.height * 0.25 + button_v_offset),
                  (self.width - 10, self.height - button_v_offset)]

        # Define fonts
        font_size = int(self.height * 0.15)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except IOError:
            font = ImageFont.load_default()

        # Draw UI elements based on cursor position
        if self.cursor_v_index == 0:
            self.draw.rectangle([rect_start, rect_mid_end], fill='green', outline='white', width=border)
            self.draw.rectangle([rect_mid_start, rect_end], outline='white', width=border)
        else:
            self.draw.rectangle([rect_start, rect_mid_end], outline='white', width=border)
            self.draw.rectangle([rect_mid_start, rect_end], fill='green', outline='white', width=border)

        self.draw.rectangle([button1[0], button1[1]],
                           fill=('green' if self.cursor_h_index % 2 == 0 else 'grey'),
                           outline='white', width=border)
        self.draw.rectangle([button2[0], button2[1]],
                           fill=('green' if self.cursor_h_index % 2 == 1 else 'grey'),
                           outline='white', width=border)

        # Draw text
        draw_in_box("radio", font, rect_start, rect_mid_end, self.draw)
        draw_in_box("stop", font, button1[0], button1[1], self.draw)
        draw_in_box("play", font, button2[0], button2[1], self.draw)

        # Control player based on selection
        if self.cursor_h_index % 2 == 1:
            self.player.play()
        else:
            self.player.stop()


class Alarm:
    """Handle alarm functionality and UI."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.cursor_v_index = 0
        self.cursor_h_index = 0
        self.alarm_times = self.read_times()

        self.url = 'https://ice.actve.net/fm-evropa2-128'
        self.instance = vlc.Instance()
        self.player = self.instance.media_player_new()
        self.media = self.instance.media_new(self.url)
        self.player.set_media(self.media)

        self.alarm_ringing = 0
        self.alarm_time = 0
        self.backup_alarm = False
        self.internet_status = True

    def is_alarm_ringing(self):
        return self.alarm_ringing > 0

    def read_times(self):
        """Read alarm times from CSV file."""
        times = [{} for _ in range(7)]

        with open('/home/pi/alarmclock.csv', newline='') as csvfile:
            time_reader = csv.reader(csvfile, delimiter=',', quotechar='|')
            for row in time_reader:
                if len(row) > 2:
                    day_idx = int(row[0])
                    times[day_idx] = {
                        "hour": int(row[1]),
                        "minute": int(row[2]),
                        "enabled": int(row[3])
                    }
                    times[day_idx]["seconds_from_midnight"] = (
                        times[day_idx]["hour"] * 3600 + times[day_idx]["minute"] * 60
                    )
        return times

    def refresh_alarm(self):
        self.alarm_times = self.read_times()

    def set_v_cursor(self, cursor_offset):
        self.cursor_v_index += cursor_offset
        self.cursor_v_index %= 2
        self.reset_alarm()

    def set_h_cursor(self, cursor_offset):
        self.cursor_h_index += cursor_offset
        self.cursor_h_index %= 2

    def cdraw(self, image):
        self.draw_top_menu(image)

    def get_next_alarm(self):
        """Find the next scheduled alarm."""
        now = datetime.now()
        current_seconds = now.hour * 3600 + now.minute * 60 + now.second

        for day_offset in range(7):
            current_day = (datetime.today().weekday() + day_offset) % 7
            alarm_data = self.alarm_times[current_day]

            if alarm_data["enabled"] == 1 and (
                day_offset > 0 or
                alarm_data["seconds_from_midnight"] > current_seconds
            ):
                return current_day, alarm_data
        return None, None

    def check_alarm(self):
        """Check if alarm should be triggered and manage alarm state."""
        now = datetime.now()
        current_day = now.weekday()
        current_seconds = now.hour * 3600 + now.minute * 60 + now.second

        # Check if we need to start alarm
        if not self.alarm_ringing:
            if (self.alarm_times[current_day]["enabled"] == 1 and
                abs(self.alarm_times[current_day]["seconds_from_midnight"] - current_seconds) < 30):
                self.player.play()
                self.alarm_ringing = 1
                self.alarm_time = self.alarm_times[current_day]["seconds_from_midnight"]
                self.backup_alarm = False

                # Wait for playback to start
                for _ in range(60):
                    sleep(3)
                    if self.player.is_playing():
                        print("playing")
                        break
        else:
            # Manage running alarm
            print("check player")
            self.alarm_ringing += 1

            working_ok = self.player.is_playing() and internet_connection()
            if not working_ok and not self.backup_alarm:
                print("backup")
                # Fall back to local files if streaming fails
                cwd = "/home/pi/Music"
                music_files = [os.path.join(cwd, f) for f in os.listdir(cwd)
                              if os.path.isfile(os.path.join(cwd, f))]

                if music_files:
                    self.player.stop()
                    self.media = self.instance.media_new(random.choice(music_files))
                    self.player.set_media(self.media)
                    self.player.play()
                    self.backup_alarm = True

            if self.backup_alarm and not self.player.is_playing():
                self.backup_alarm = False

            # Stop alarm after 20 minutes
            if abs(self.alarm_time - current_seconds) > 1200:  # 20 minutes in seconds
                self.player.stop()
                self.alarm_ringing = 0

    def reset_alarm(self):
        """Stop the alarm if it's ringing."""
        self.player.stop()
        self.alarm_ringing = 0

    def draw_top_menu(self, image):
        self.draw = ImageDraw.Draw(image)
        border = 2
        rect_start = (0, 0)
        rect_mid_end = (self.width, self.height * 0.25)
        rect_mid_start = (0, self.height * 0.25)
        rect_text_end = (self.width, self.height - self.height * 0.25)
        rect_end = (self.width, self.height)

        if self.cursor_v_index == 0:
            self.draw.rectangle([rect_start, rect_mid_end], fill='green', outline='white', width=border)
            self.draw.rectangle([rect_mid_start, rect_end], outline='white', width=border)
        else:
            self.draw.rectangle([rect_start, rect_mid_end], outline='white', width=border)
            self.draw.rectangle([rect_mid_start, rect_end], fill='green', outline='white', width=border)

        draw_wifi_status(self.draw, self.internet_status)

        # Setup fonts
        font_size = int(self.height * 0.15)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
            font_large = ImageFont.truetype("arial.ttf", int(font_size * 2))
            font_smaller = ImageFont.truetype("arial.ttf", int(font_size * 0.75))
        except IOError:
            font = ImageFont.load_default()
            font_large = ImageFont.load_default()
            font_smaller = ImageFont.load_default()

        # Draw UI elements
        draw_in_box("budzik", font, rect_start, rect_mid_end, self.draw)

        time_text = datetime.now().strftime('%H:%M')
        draw_in_box(time_text, font_large, rect_mid_start, rect_text_end, self.draw)

        _, _, _, text_height = self.draw.textbbox((0, 0), time_text, font=font_large)

        if not self.is_alarm_ringing():
            next_alarm_day, next_alarm = self.get_next_alarm()
            if next_alarm:
                alarm_text = f"{DAY_TO_STRING[next_alarm_day]}  {next_alarm['hour']:02d}:{next_alarm['minute']:02d}"
                draw_in_box(alarm_text, font_smaller,
                           (0, self.height * 0.5 + text_height), rect_end, self.draw)
        else:
            draw_in_box("STOVAC", font_smaller,
                      (0, self.height * 0.5 + text_height), rect_end, self.draw, color='red')


class AlarmEdit:
    """Handle alarm settings editing."""

    def __init__(self, width, height):
        self.width = width
        self.height = height
        self.cursor_v_index = 0
        self.cursor_h_index = 0
        self.day_index = 0
        self.time_index = 0
        self.enabled_index = 0
        self.alarm_times = self.read_times()

    def read_times(self):
        """Read alarm times from CSV file."""
        times = [{} for _ in range(7)]

        with open('/home/pi/alarmclock.csv', newline='') as csvfile:
            time_reader = csv.reader(csvfile, delimiter=',', quotechar='|')
            for row in time_reader:
                if len(row) > 2:
                    times[int(row[0])] = {
                        "hour": int(row[1]),
                        "minute": int(row[2]),
                        "enabled": int(row[3])
                    }
        return times

    def write_times(self):
        """Write alarm times to CSV file."""
        with open('/home/pi/alarmclock.csv', 'w', newline='') as csvfile:
            time_writer = csv.writer(csvfile, delimiter=',', quotechar='|', quoting=csv.QUOTE_MINIMAL)
            for day in range(7):
                time_writer.writerow([
                    day,
                    self.alarm_times[day]["hour"],
                    self.alarm_times[day]["minute"],
                    self.alarm_times[day]["enabled"]
                ])

    def set_v_cursor(self, cursor_offset):
        if self.cursor_v_index == 2 and self.time_index != 0:
            if self.time_index == 2:
                self.alarm_times[self.day_index]["minute"] -= cursor_offset * 5
                self.alarm_times[self.day_index]["minute"] %= 60
            elif self.time_index == 1:
                self.alarm_times[self.day_index]["hour"] -= cursor_offset
                self.alarm_times[self.day_index]["hour"] %= 24
            self.write_times()
        else:
            self.cursor_v_index += cursor_offset
            self.cursor_v_index %= 4

    def set_h_cursor(self, cursor_offset):
        if self.cursor_v_index == 1:
            self.day_index += cursor_offset
            self.day_index %= 7
        elif self.cursor_v_index == 2:
            self.time_index += cursor_offset
            self.time_index %= 3
        elif self.cursor_v_index == 3:
            self.alarm_times[self.day_index]["enabled"] += cursor_offset
            self.alarm_times[self.day_index]["enabled"] %= 2
            self.write_times()
        else:
            self.cursor_h_index += cursor_offset
            self.cursor_h_index %= 2

    def cdraw(self, image):
        self.draw_top_menu(image)

    def draw_top_menu(self, image):
        self.draw = ImageDraw.Draw(image)
        border = 2

        # Define UI regions
        rect_title_start = (0, 0)
        rect_title_end = (self.width, self.height * 0.25)
        rect_day_start = (0, self.height * 0.25)
        rect_day_end = (self.width, self.height * 0.5)
        rect_time_start = (0, self.height * 0.5)
        rect_time_end = (self.width, self.height * 0.75)
        rect_enabled_start = (0, self.height * 0.75)
        rect_enabled_end = (self.width, self.height)

        time_button1 = [(0 + 10, self.height * 0.5 + 10),
                        (self.width * 0.5 - 10, self.height * 0.75 - 10)]
        time_button2 = [(self.width * 0.5 + 10, self.height * 0.5 + 10),
                        (self.width - 10, self.height * 0.75 - 10)]
        enabled_button = [(0 + 10, self.height * 0.75 + 10),
                          (self.width - 10, self.height - 10)]

        # Draw UI elements based on cursor position
        self.draw.rectangle([rect_title_start, rect_title_end],
                           fill='green' if self.cursor_v_index == 0 else None,
                           outline='white', width=border)
        self.draw.rectangle([rect_day_start, rect_day_end],
                           fill='green' if self.cursor_v_index == 1 else None,
                           outline='white', width=border)

        if self.cursor_v_index == 2:
            self.draw.rectangle([rect_time_start, rect_time_end],
                               fill=('green' if self.time_index % 3 == 0 else 'grey'),
                               outline='white', width=border)
            self.draw.rectangle([time_button1[0], time_button1[1]],
                               fill=('green' if self.time_index % 3 == 1 else 'grey'),
                               outline='white', width=border)
            self.draw.rectangle([time_button2[0], time_button2[1]],
                               fill=('green' if self.time_index % 3 == 2 else 'grey'),
                               outline='white', width=border)
        else:
            self.draw.rectangle([rect_time_start, rect_time_end], outline='white', width=border)
            self.draw.rectangle([time_button1[0], time_button1[1]], outline='white', width=border)
            self.draw.rectangle([time_button2[0], time_button2[1]], outline='white', width=border)

        self.draw.rectangle([rect_enabled_start, rect_enabled_end],
                           fill='green' if self.cursor_v_index == 3 else None,
                           outline='white', width=border)
        self.draw.rectangle([enabled_button[0], enabled_button[1]],
                           fill=('green' if self.alarm_times[self.day_index]["enabled"] else 'red'),
                           outline='white', width=border)

        # Setup fonts
        font_size = int(self.height * 0.15)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
            font_smaller = ImageFont.truetype("arial.ttf", int(font_size * 0.75))
        except IOError:
            font = ImageFont.load_default()
            font_smaller = ImageFont.load_default()

        # Draw text elements
        draw_in_box("nastaveni", font, rect_title_start, rect_title_end, self.draw)
        draw_in_box(DAY_TO_STRING[self.day_index], font_smaller, rect_day_start, rect_day_end, self.draw)
        draw_in_box(":", font_smaller, rect_time_start, rect_time_end, self.draw)
        draw_in_box(str(self.alarm_times[self.day_index]["hour"]), font_smaller,
                   time_button1[0], time_button1[1], self.draw)
        draw_in_box(str(self.alarm_times[self.day_index]["minute"]), font_smaller,
                   time_button2[0], time_button2[1], self.draw)
        draw_in_box("on" if self.alarm_times[self.day_index]["enabled"] else "off",
                   font_smaller, enabled_button[0], enabled_button[1], self.draw)


class Menu:
    """Main menu controller."""

    def __init__(self):
        self.display_type = "square"
        self.disp = st7789.ST7789(
            height=240,
            rotation=90,
            port=0,
            cs=st7789.BG_SPI_CS_FRONT,
            dc=9,
            backlight=None,
            spi_speed_hz=80 * 1000 * 1000,
            offset_left=0,
            offset_top=0,
        )

        GPIO.setmode(GPIO.BCM)
        GPIO.setup(13, GPIO.OUT)
        self.backlight = GPIO.PWM(13, 500)
        self.backlight.start(50)
        self.lights_up = True

        self.WIDTH = self.disp.width
        self.HEIGHT = self.disp.height

        # Load background image
        image_path = "/home/pi/cat.jpg"
        if os.path.exists(image_path):
            self.background_image = Image.open(image_path)
        else:
            self.background_image = Image.new("RGB", (self.WIDTH, self.HEIGHT), color="black")

        self.menu_index = 0
        self.alarm_index = 0
        self.editor_index = 1

        # Initialize menu components
        self.top_menu = [
            Alarm(self.WIDTH, self.HEIGHT),
            AlarmEdit(self.WIDTH, self.HEIGHT),
            Radio(self.WIDTH, self.HEIGHT)
        ]

    def check_alarm(self):
        self.top_menu[self.alarm_index].check_alarm()

    def is_alarm_ringing(self):
        return self.top_menu[self.alarm_index].is_alarm_ringing()

    def dim(self):
        """Turn display backlight off or keep it on if alarm is ringing."""
        if self.is_alarm_ringing():
            self.backlight.start(100)
            self.lights_up = True
        else:
            self.backlight.start(0)
            self.lights_up = False

    def light_up(self):
        """Turn display backlight on and reset alarm if ringing."""
        self.backlight.start(60)
        self.lights_up = True
        self.top_menu[self.alarm_index].reset_alarm()

    def refresh(self):
        """Update display with current menu content."""
        image = self.background_image.copy()
        self.top_menu[self.menu_index].cdraw(image)
        self.disp.display(image)

    def refresh_alarm(self):
        """Reload alarm settings if in editor mode."""
        if self.menu_index == self.editor_index:
            self.top_menu[self.alarm_index].refresh_alarm()

    def check_internet_status(self):
        self.top_menu[self.alarm_index].internet_status = internet_connection()

    def top_prew(self):
        image = self.background_image.copy()
        if self.top_menu[self.menu_index].cursor_v_index == 0:
            self.menu_index -= 1
            self.menu_index %= len(self.top_menu)
        else:
            self.top_menu[self.menu_index].set_h_cursor(-1)
        self.top_menu[self.menu_index].cdraw(image)
        self.disp.display(image)

    def top_next(self):
        image = self.background_image.copy()
        if self.top_menu[self.menu_index].cursor_v_index == 0:
            self.menu_index += 1
            self.menu_index %= len(self.top_menu)
        else:
            self.top_menu[self.menu_index].set_h_cursor(1)
        self.top_menu[self.menu_index].cdraw(image)
        self.disp.display(image)

    def bottom_prew(self):
        image = self.background_image.copy()
        self.top_menu[self.menu_index].set_v_cursor(-1)
        self.top_menu[self.menu_index].cdraw(image)
        self.disp.display(image)

    def bottom_next(self):
        image = self.background_image.copy()
        self.top_menu[self.menu_index].set_v_cursor(1)
        self.top_menu[self.menu_index].cdraw(image)
        self.disp.display(image)


def handle_button(pin):
    """Handle button press events."""
    label = LABELS[BUTTONS.index(pin)]
    if label == "A":
        menu.bottom_prew()
    elif label == "B":
        menu.bottom_next()
    elif label == "X":
        menu.top_prew()
    elif label == "Y":
        menu.top_next()


# Initialize the menu system
menu = Menu()
menu.refresh()

# Set up GPIO buttons
for pin in BUTTONS:
    GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
    GPIO.add_event_detect(pin, GPIO.FALLING, bouncetime=250)


# Set up background threads
def alarm_thread_func():
    """Background thread to check alarm status."""
    while True:
        menu.check_alarm()
        sleep(1)


def internet_thread_func():
    """Background thread to check internet connectivity."""
    while True:
        if menu.lights_up:
            menu.check_internet_status()
        sleep(5)


alarm_thread = threading.Thread(target=alarm_thread_func, daemon=True)
internet_thread = threading.Thread(target=internet_thread_func, daemon=True)
alarm_thread.start()
internet_thread.start()

# Main loop
refresh_counter = 0
while True:
    if menu.is_alarm_ringing():
        menu.menu_index = menu.alarm_index
        menu.refresh()
        menu.dim()
        refresh_counter = 0
    elif menu.lights_up:
        menu.refresh()

    # Auto-dim after timeout (about 30 seconds)
    if refresh_counter > 300:  # 30 seconds at 10 counts/second
        menu.dim()
        refresh_counter = 0
    else:
        refresh_counter += 1

    sleep(0.100)  # 100ms refresh rate

    # Check for button presses
    for pin in BUTTONS:
        if GPIO.event_detected(pin):
            if not menu.lights_up or menu.is_alarm_ringing():
                menu.refresh_alarm()
                menu.refresh()
                menu.light_up()
            elif menu.lights_up:
                handle_button(pin)
                menu.refresh_alarm()
            refresh_counter = 0
