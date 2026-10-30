"""Shared Cycles device selection. DEV=CPU (default) | GPU | BOTH.
On the `fedora` machine the CPU is ~4x faster than CPU+iGPU, so CPU is the default."""
import bpy, os


def setup(default="CPU"):
    mode = os.environ.get("DEV", default).upper()
    sc = bpy.context.scene
    prefs = bpy.context.preferences.addons['cycles'].preferences
    if mode != "CPU":
        for kind in ('HIP', 'CUDA', 'OPTIX', 'METAL', 'ONEAPI'):
            try:
                prefs.compute_device_type = kind
            except TypeError:
                continue
            prefs.get_devices()
            if any(d.type == kind for d in prefs.devices):
                break
        for d in prefs.devices:
            d.use = mode == "BOTH" or d.type != 'CPU'
    sc.cycles.device = 'CPU' if mode == "CPU" else 'GPU'
    return mode
