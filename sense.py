#!/usr/bin/env python
"""
sense.py: log and output sensor values
"""

import collections
import logging
from statistics import mean
import time
import threading
import os
import sys

import psutil
import sensors
import urwid

from util import confighandler
from workers import cpu_msr
from workers import nvidia_smi


def init_history(chips, blacklist, queue_length):
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
            if feature.label in blacklist:
                continue

            try:
                unit = sensor_units[feature.type]
                sensor_type = sensor_types[feature.type]
            except IndexError:
                unit = " ???"
                sensor_type = " ???"

            sensor_dict[feature.label] = {}
            sensor_dict[feature.label]["info"] = {"unit": unit, "type": sensor_type}
            sensor_dict[feature.label]["measurements"] = collections.deque(maxlen=queue_length)

        tree[str(chip)] = sensor_dict

    msr_path = "/dev/cpu/0/msr"
    if "msr" not in blacklist \
        and os.path.exists(msr_path) \
        and os.access(msr_path, os.R_OK):

        tree["CPU VCCIN"] = {}
        for cpu in range(psutil.cpu_count()):
            core_id = "Core #{}".format(cpu)
            tree["CPU VCCIN"][core_id] = {}
            tree["CPU VCCIN"][core_id]["info"] = {"unit": " V", "type": "voltage"}
            tree["CPU VCCIN"][core_id]["measurements"] = collections.deque(maxlen=queue_length)
    else:
        logging.warning("No access to MSR. Either run as root, enable reading "
                        f"capabilites for {msr_path} or add 'msr' to blacklist to "
                        "disable reading the MSR.  Press enter to continue.")
        input()

    tree["CPU Usage"] = {}
    for cpu in range(psutil.cpu_count()):
        core_id = "Core #{}".format(cpu)
        tree["CPU Usage"][core_id] = {}
        tree["CPU Usage"][core_id]["info"] = {"unit": " %", "type": "usage"}
        tree["CPU Usage"][core_id]["measurements"] = collections.deque(maxlen=queue_length)

    tree["CPU Frequency"] = {}
    for cpu in range(psutil.cpu_count()):
        core_id = "Core #{}".format(cpu)
        tree["CPU Frequency"][core_id] = {}
        tree["CPU Frequency"][core_id]["info"] = {"unit": " MHz", "type": "freq"}
        tree["CPU Frequency"][core_id]["measurements"] = collections.deque(maxlen=queue_length)

    if "nvidia-smi" not in blacklist and os.path.exists("/usr/bin/nvidia-smi"):
        for gpu in nvidia_smi.get_nvidia_smi_log():
            tree[gpu["GPU ID"]] = {}
            for sensor in gpu:
                if sensor == "GPU ID":
                    continue

                tree[gpu["GPU ID"]][sensor] = {}
                tree[gpu["GPU ID"]][sensor]["info"] = {"unit": gpu[sensor]["unit"],
                                                       "type": gpu[sensor]["type"]}
                tree[gpu["GPU ID"]][sensor]["measurements"] = collections.deque(maxlen=queue_length)

    return tree


def update_readouts(current_value, readouts):
    """
    Updates the min, max and average values of the readouts
    """
    measurements = readouts["measurements"]
    readouts["measurements"].append(current_value)
    readouts["cur"] = current_value

    if "min" in readouts:
        readouts["min"] = min(*measurements, readouts["min"])
    else:
        readouts["min"] = current_value

    if "max" in readouts:
        readouts["max"] = max(*measurements, readouts["max"])
    else:
        readouts["max"] = current_value

    if "avg" in readouts:
        readouts["avg"] = mean(measurements)
    else:
        readouts["avg"] = current_value

    return readouts


def update_history(history, chips):
    """
    Iterate through the chips and add the measurements to the history.
    """

    for chip in chips:
        for feature in chip:
            if feature.label not in history[str(chip)].keys():
                continue
            readouts = history[str(chip)][feature.label]
            current_value = feature.get_value()
            readouts = update_readouts(current_value, readouts)

    for i, current_value in enumerate(psutil.cpu_percent(percpu=True)):
        core_id = "Core #{}".format(i)
        readouts = history["CPU Usage"][core_id]
        readouts = update_readouts(current_value, readouts)

    for i, freq in enumerate(psutil.cpu_freq(percpu=True)):
        core_id = "Core #{}".format(i)
        readouts = history["CPU Frequency"][core_id]
        current_value = float(round(freq.current))
        readouts = update_readouts(current_value, readouts)

    try:
        for core in range(psutil.cpu_count()):
            core_id = "Core #{}".format(core)
            current_value = cpu_msr.get_vccin(core)
            readouts = history["CPU VCCIN"][core_id]
            readouts = update_readouts(current_value, readouts)
    except KeyError:
        # We haven't loaded the `msr` module or there's no MSR support on our
        # machine.
        pass

    nvidia_gpus = None
    if os.path.exists("/usr/bin/nvidia-smi"):
        nvidia_gpus = nvidia_smi.get_nvidia_smi_log()
    if nvidia_gpus:
        for gpu in nvidia_gpus:
            for sensor in gpu:
                if sensor == "GPU ID":
                    continue

                readouts = history[gpu["GPU ID"]][sensor]
                current_value = float(gpu[sensor]["value"].split()[0])
                readouts = update_readouts(current_value, readouts)

    return history


def update_footer(date_fmt, quit_hint):
    """
    Create a footer with the program name, the current date and time
    and a small hint to quit.
    """

    title = urwid.AttrMap(urwid.Text("sense.py", align="left"), "title")
    date = urwid.AttrMap(urwid.Text(time.strftime(date_fmt), align="center"), "date")
    quit_hint = urwid.AttrMap(urwid.Text(quit_hint, align="right"), "quit_hint")
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


def update_frame(frame, loop, listwalker, chips, history, config):
    """ Loop that replaces the frame listwalker in-place. """
    while True:
        history = update_history(history, chips)
        listwalker[:] = format_output(history)
        frame.footer = update_footer(config["date_format"], config["quit_hint"])
        try:
            loop.draw_screen()
            time.sleep(config["update_delay"])
        except AssertionError:  # Urwid thread breaking, for instance
            break



def key_handler(key):
    """ Handle keys such as q and Q for quit, etc."""
    if key in ("q", "Q"):
        raise urwid.ExitMainLoop()


def main():
    """
    Initialize screen, sensors, history and display measurements on the screen.
    """

    config = confighandler.get_config()
    if not config: sys.exit()

    # Initialize the sensors and the history
    sensors.init()
    chips = [chip for chip in sensors.iter_detected_chips()]
    history = init_history(chips,
                           config["blacklist"],
                           config["queue_length"])
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
    loop = urwid.MainLoop(frame, unhandled_input=key_handler,
                          palette=config["palette"])

    # Create the thread that will update the frame periodically
    frame_updater = threading.Thread(target=update_frame,
                                     args=(frame, loop, listwalker, chips,
                                           history, config))
    frame_updater.start()
    loop.run()


if __name__ == "__main__":
    main()
