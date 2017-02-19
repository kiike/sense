"""
This module is part of the sense project.

Parse an nVidia info log via nvidia-smi
"""
import subprocess
import xml.etree.ElementTree as etree


def get_nvidia_smi_log():
    """
    Return a list of dictionaries with the nVidia GPU(s) status.
    """

    out = []

    smi_log = subprocess.check_output(["nvidia-smi", "-x", "-q"])
    tree = etree.fromstring(smi_log)
    get_text = lambda element, tag: element.find(tag).text

    for gpu_index, gpu in enumerate(tree.findall("gpu")):
        model = get_text(gpu, "product_name")
        gpu_id = "GPU #{}: {}".format(gpu_index, model)
        utilization = gpu.find("utilization")

        gpu_info = {
            "GPU ID": gpu_id,
            "Temperature": {
                "value": get_text(gpu.find("temperature"), "gpu_temp"),
                "unit": " °C",
                "type": "temp"
            },
            "Fan Speed": {
                "value": get_text(gpu, "fan_speed"),
                "unit": " %",
                "type": " RPM",
            },
            "Usage": {
                "value": get_text(utilization, "gpu_util"),
                "unit": " %",
                "type": "usage"
            },
            "VRAM Usage": {
                "value": get_text(utilization, "gpu_util"),
                "unit": " %",
                "type": "usage"
            },
            "Encoder Usage": {
                "value": get_text(utilization, "encoder_util"),
                "unit": " %",
                "type": "usage"
            },
            "Decoder Usage": {
                "value": get_text(utilization, "decoder_util"),
                "unit": " %",
                "type": "usage"
            },

            "Graphics Clock": {
                "value": get_text(gpu.find("clocks"), "graphics_clock"),
                "unit": " MHz",
                "type": "usage"
            },
            "SM Clock": {
                "value": get_text(gpu.find("clocks"), "sm_clock"),
                "unit": " MHz",
                "type": "usage"
            },
            "Memory Clock": {
                "value": get_text(gpu.find("clocks"), "mem_clock"),
                "unit": " MHz",
                "type": "usage"
            },
            "Video Clock": {
                "value": get_text(gpu.find("clocks"), "video_clock"),
                "unit": " MHz",
                "type": "usage"
            },
        }

        out.append(gpu_info)

    return out
