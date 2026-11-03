"""Shared Cycles device selection. DEV=AUTO (default) | CPU | GPU | BOTH.
AUTO renders on an NVIDIA GPU (OptiX, else CUDA) if there is one, otherwise on the CPU: on the AMD laptop the
iGPU is ~4x slower than the CPU, while on the RTX 4070 SUPER desktop the GPU is much faster (see ../CLAUDE.md).
GPU_API=OPTIX|CUDA|HIP|ONEAPI|METAL forces one backend for GPU/BOTH."""
import bpy, os

APIS = ('OPTIX', 'CUDA', 'HIP', 'ONEAPI', 'METAL')


def _pick_api(prefs, apis):
    for kind in apis:
        try:
            prefs.compute_device_type = kind
        except TypeError:
            continue
        prefs.get_devices()
        if any(d.type == kind for d in prefs.devices):
            return kind
    return None


def setup(default="AUTO"):
    mode = os.environ.get("DEV", default).upper()
    sc = bpy.context.scene
    prefs = bpy.context.preferences.addons['cycles'].preferences
    if mode != "CPU":
        forced = os.environ.get("GPU_API", "").upper()
        api = _pick_api(prefs, (forced,) if forced else APIS[:2] if mode == "AUTO" else APIS)
        if api is None:
            mode = "CPU"
        else:
            if mode == "AUTO":
                mode = "GPU"
            for d in prefs.devices:
                d.use = d.type == api or (mode == "BOTH" and d.type == 'CPU')
            mode = "%s:%s" % (mode, api)
    sc.cycles.device = 'CPU' if mode == "CPU" else 'GPU'
    return mode
