"""
This module is part of sense.py.

The function of cpu_msr is to gather data from the CPU MSR pseudo-devices.

Hint: run `modprobe msr` before running this module.
"""

import struct

def get_msr_register(register, core):
    """
    Read a register from the MSR pseudo-device. Needs MSR support from the
    Kernel and the CPU.
    """

    msr_path = '/dev/cpu/{}/msr'.format(core)

    with open(msr_path, mode='rb') as f:
        f.seek(register)
        value = f.read(8)
        value = struct.unpack('<Q', value)[0]

    return value

def get_vccin(core):
    """
    Get VCCIN voltage as read by the CPU voltage regulator. This value
    approximates the Vcore that is supplied by the motherboard.
    """

    register = get_msr_register(0x198, core)
    return float(register >> 32) / float(1 << 13)
