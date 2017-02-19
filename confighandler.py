import os
import logging

import yaml

DEFAULT_CONFIG = """
    update_delay: 1
    queue_length: 3600  # One hour for update_delay=1
    date_format: "%Y-%m-%d %H:%M:%S"
    quit_hint: Press "q" to quit
    blacklist:
        - PCH_CHIP_CPU_MAX_TEMP
        - PCH_CHIP_TEMP
        - PCH_CPU_TEMP
        - AUXTIN1
        - AUXTIN2
        - AUXTIN3
        - intrusion0
        - intrusion1
        - intrusion2
        - fan3
        - fan5
        - beep_enable

    palette:
        - background:
            fg: default
            bg: default
        - symbol:
            fg: dark gray
            bg: default
        - chip:
            fg: dark cyan
            bg: default
        - title:
            fg: light green
            bg: default
        - date:
            fg: yellow
            bg: default
        - quit_hint:
            fg: dark gray
            bg: default
        - sensor:
            fg: light cyan
            bg: default
"""

def parse_palette(palette):
    """
    Return a list of tuples with the color definitions.
    """

    colors = []
    for section in palette:
        for attribute in section:
            color_def = (attribute,
                         section[attribute]["fg"],
                         section[attribute]["bg"])
            colors.append(color_def)

    return colors

def parse_config(source):
    """
    Return a configuration dictionary from a yaml source.
    """

    yaml_config = yaml.load(source)
    config = {}

    for item in yaml_config:
        if item == "palette":
            palette = parse_palette(yaml_config["palette"])
            config["palette"] = palette
        else:
            config[item] = yaml_config[item]

    return config

def get_config():
    """
    Return a config dictionary from either a readable yaml
    file or the default yaml config.
    """

    default_xdg_config_dir = os.path.join(os.getenv("HOME"), ".config")
    xdg_config_dir = os.getenv("XDG_CONFIG_DIR", default_xdg_config_dir)

    config_dir = os.path.join(xdg_config_dir, "sense")
    config_file = os.path.join(config_dir, "config.yaml")

    if os.path.exists(config_file):
        with open(config_file) as f:
            config = parse_config(f.read())
    else:
        if not os.path.isdir(config_dir):
            os.mkdir(config_dir)

        with open(config_file, "w") as f:
            f.writelines(DEFAULT_CONFIG)

        config = parse_config(DEFAULT_CONFIG)

        msg = ("Couldn't find a config file, so one was created for your "
               "convenience at {}. Feel free to edit it. This program will "
               "now run with a default configuration.")
        msg = msg.format(config_file)
        logging.warning(msg)

    return config
