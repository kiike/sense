#!/usr/bin/env python
"""
sens.py: log and output sensor values
"""

from statistics import mean
import time
import threading

import collections
import psutil
import sensors
import urwid

QUEUE_LENGTH = 60 * 60  # One hour
DATE_FMT = "%Y-%m-%d %H:%M:%S"
QUIT_HINT = "Press 'q' to quit"
BLACKLIST = ("PCH_CHIP_CPU_MAX_TEMP", "PCH_CHIP_TEMP", "PCH_CPU_TEMP",
             "AUXTIN1", "AUXTIN2", "AUXTIN3", "intrusion0", "intrusion1", "intrusion2",
             "fan3", "fan5", "beep_enable")

PALETTE = (("bg", "default", "default"),
           ("symbol", "dark gray", "default"),
           ("chip", "dark cyan", "default"),
           ("title", "light green", "default"),
           ("date", "yellow", "default"),
           ("quit_hint", "dark gray", "default"),
           ("sensor", "light cyan", "default"))

def init_history(chips):
    """
    Build a history tree that will collect all the measurements.
    """

    # Adapted from lm-sensors source code
    # Utility lists to map from lm-sensors type to units
    sensor_units = [" V", " RPM", " °C", "", "", "", "", " V", " ", "", "", "", "", ""]
    sensor_types = ["in", "fan", "temp", "power", "energy", "current",
                    "humidity", "max_main", "vid", "intrusion", "max_other",
                    "beep_enable", "max", "unknown"]

    tree = {}
    for chip in chips:
        sensor_dict = {}
        for feature in chip:
            if feature.label in BLACKLIST:
                continue
            else:
                try:
                    unit = sensor_units[feature.type]
                    sensor_type = sensor_types[feature.type]
                except IndexError:
                    unit = " ???"
                    sensor_type = " ???"

                sensor_dict[feature.label] = {}
                sensor_dict[feature.label]["info"] = {"unit": unit, "type": sensor_type}
                sensor_dict[feature.label]["measurements"] = collections.deque(maxlen=QUEUE_LENGTH)

        tree[str(chip)] = sensor_dict

    tree["CPU Usage"] = {}
    for cpu in range(psutil.cpu_count()):
        core_id = "Core #{}".format(cpu)
        tree["CPU Usage"][core_id] = {}
        tree["CPU Usage"][core_id]["info"] = {"unit": " %", "type": "usage"}
        tree["CPU Usage"][core_id]["measurements"] = collections.deque(maxlen=QUEUE_LENGTH)

    tree["CPU Frequency"] = {}
    for cpu in range(psutil.cpu_count()):
        core_id = "Core #{}".format(cpu)
        tree["CPU Frequency"][core_id] = {}
        tree["CPU Frequency"][core_id]["info"] = {"unit": " MHz", "type": "freq"}
        tree["CPU Frequency"][core_id]["measurements"] = collections.deque(maxlen=QUEUE_LENGTH)

    return tree

def update_data_store(current_value, data_store):
    measurements = data_store["measurements"]
    data_store["measurements"].append(current_value)
    data_store["cur"] = current_value

    if "min" in data_store:
        data_store["min"] = min(*measurements, data_store["min"])
    else:
        data_store["min"] = current_value

    if "max" in data_store:
        data_store["max"] = max(*measurements, data_store["max"])
    else:
        data_store["max"] = current_value

    if "avg" in data_store:
        data_store["avg"] = mean(measurements)
    else:
        data_store["avg"] = current_value

    return data_store

def update_history(history, chips):
    """
    Iterate through the chips and add the measurements to the history.
    """

    for chip in chips:
        for feature in chip:
            try:
                data_store = history[str(chip)][feature.label]
                current_value = feature.get_value()
                data_store = update_data_store(current_value, data_store)

            except KeyError:
                continue

    for i, current_value in enumerate(psutil.cpu_percent(percpu=True)):
        core_id = "Core #{}".format(i)
        data_store = history["CPU Usage"][core_id]
        data_store = update_data_store(current_value, data_store)

    for i, freq in enumerate(psutil.cpu_freq(percpu=True)):
        core_id = "Core #{}".format(i)
        data_store = history["CPU Frequency"][core_id]
        current_value = float(round(freq.current))
        data_store = update_data_store(current_value, data_store)


    return history


def update_footer():
    """
    Create a footer with the program name, the current date and time
    and a small hint to quit.
    """

    title = urwid.AttrMap(urwid.Text("sense.py", align="left"), "title")
    date = urwid.AttrMap(urwid.Text(time.strftime(DATE_FMT), align="center"), "date")
    quit_hint = urwid.AttrMap(urwid.Text(QUIT_HINT, align="right"), "quit_hint")
    return urwid.Columns((title, date, quit_hint))

def format_field(number, unit, s_type):
    """
    Make an urwid text out of a number and unit suitable for putting into columns.
    """

    if s_type in ("fan", "freq", "usage", "temp"):
        field = "{:>7d}{:<3}".format(round(number), unit)
    else:
        field = "{:>7.3f}{:<3}".format(number, unit)

    return urwid.Text(field)

def calculate_values(sensor_data):
    """
    Return desired values from a measurements list, u
    """

    sensor_info = sensor_data["info"]
    sensor_unit = sensor_info["unit"]
    sensor_type = sensor_info["type"]

    cur_value = format_field(sensor_data["cur"], sensor_unit, sensor_type)
    min_value = format_field(sensor_data["min"], sensor_unit, sensor_type)
    max_value = format_field(sensor_data["max"], sensor_unit, sensor_type)
    avg_value = format_field(sensor_data["avg"], sensor_unit, sensor_type)

    return cur_value, min_value, max_value, avg_value

def format_output(history):
    """
    Format the history dict into a series of urwid columns and cells
    """

    out = []

    for chip in history:
        # Print sensor name
        out.append(urwid.AttrMap(urwid.Text(str(chip)), "chip"))

        for i, feature in enumerate(history[chip]):
            # If this is the last element, print a different symbol
            is_last = i + 1 == len(history[chip])
            symbol = "\u2514" if is_last else "\u251c"

            feature_data = history[chip][feature]
            values = calculate_values(feature_data)

            data_fields = urwid.Columns(values)

            line = urwid.Columns(((2, urwid.AttrMap(urwid.Text(symbol), "symbol")),
                                  (16, urwid.AttrMap(urwid.Text(feature), "sensor")),
                                  data_fields))
            out.append(line)

        # Show an empty line between sensors
        out.append(urwid.Text(""))

    return urwid.SimpleListWalker([w for w in out])

def update_frame(frame, loop, listwalker, chips, history):
    """ Loop that replaces the frame listwalker in-place. """
    while True:
        history = update_history(history, chips)
        listwalker[:] = format_output(history)
        frame.footer = update_footer()
        loop.draw_screen()
        time.sleep(1)

def key_handler(key):
    """ Handle keys such as q and Q for quit, etc."""
    if key in ("q", "Q"):
        raise urwid.ExitMainLoop()

def main():
    """
    Initialize screen, sensors, history and display measurements on the screen.
    """

    # Initialize the sensors and the history
    sensors.init()
    chips = [s for s in sensors.iter_detected_chips()]
    history = init_history(chips)
    history = update_history(history, chips)

    # Create the output handler and a preliminary output
    listwalker = format_output(history)
    body = urwid.ListBox(listwalker)

    # Add j/k bindings to scroll up and down
    urwid.command_map["j"] = "cursor down"
    urwid.command_map["k"] = "cursor up"

    header = (urwid.Text(w, align="center") for w in ("cur", "min", "max", "avg"))
    header = urwid.Columns(((2, urwid.Text("")),
                            (16, urwid.Text("")),
                            urwid.Columns(header)))

    frame = urwid.Frame(body, header=header)
    loop = urwid.MainLoop(frame, unhandled_input=key_handler, palette=PALETTE)

    # Create the thread that will update the frame periodically
    frame_updater = threading.Thread(target=update_frame,
                                     args=(frame, loop, listwalker,
                                           chips, history))
    frame_updater.start()
    loop.run()


if __name__ == "__main__":
    main()
