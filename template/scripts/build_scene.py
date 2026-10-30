"""Build the __NAME__ scene from scratch.

Run:  ./run.sh -b --factory-startup -P scripts/build_scene.py
Saves __NAME__.blend in the movie root. Env overrides: SAMPLES, RES_PCT, EXPOSURE.
Units are meters and seconds.
"""
import bmesh
import bpy
import math
import os
import random

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPS = 24
FRAMES = 5 * FPS
random.seed(1)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = FPS
scene.frame_start, scene.frame_end = 1, FRAMES


def link(obj, coll=None):
    (coll or scene.collection).objects.link(obj)
    return obj


# --------------------------------------------------------------------------- world
world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.5

# --------------------------------------------------------------------------- subject
mesh = bpy.data.meshes.new("Subject")
bm = bmesh.new()
bmesh.ops.create_uvsphere(bm, u_segments=48, v_segments=24, radius=0.5)
bm.to_mesh(mesh)
bm.free()
for p in mesh.polygons:
    p.use_smooth = True
subject = link(bpy.data.objects.new("Subject", mesh))
subject.location = (0, 0, 0.5)

# --------------------------------------------------------------------------- light + camera
sun = link(bpy.data.objects.new("Sun", bpy.data.lights.new("Sun", 'SUN')))
sun.data.energy = 3.0
sun.rotation_euler = (math.radians(50), 0, math.radians(30))

cam = link(bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera")))
cam.data.lens = 85
cam.location = (0, -6, 1.2)
track = cam.constraints.new('TRACK_TO')
track.target = subject
scene.camera = cam

# --------------------------------------------------------------------------- render settings
r = scene.render
r.engine = 'CYCLES'
r.resolution_x, r.resolution_y = 1280, 720
r.resolution_percentage = int(os.environ.get("RES_PCT", "100"))
r.image_settings.file_format = 'PNG'
r.filepath = os.path.join(ROOT, "frames", "f_")

c = scene.cycles
c.device = 'CPU'
c.samples = int(os.environ.get("SAMPLES", "64"))
c.use_denoising = True
c.denoiser = 'OPENIMAGEDENOISE'

vs = scene.view_settings
vs.view_transform = 'AgX'
vs.look = 'AgX - Medium High Contrast'
vs.exposure = float(os.environ.get("EXPOSURE", "0"))

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "__NAME__.blend"))
