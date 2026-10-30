"""Render a single still, from a movie dir:
   ./run.sh -b <scene>.blend -P ../scripts/still.py -- FRAME OUT [PCT] [SAMPLES]
Env: DEV (see devices.py), EXPOSURE, SUN_ROT (degrees, if the world has a "Sky Texture" node)."""
import bpy, sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import devices

a = sys.argv[sys.argv.index("--") + 1:]
sc = bpy.context.scene
devices.setup()
sc.frame_set(int(a[0]))
if len(a) > 2: sc.render.resolution_percentage = int(a[2])
if len(a) > 3: sc.cycles.samples = int(a[3])
if "EXPOSURE" in os.environ: sc.view_settings.exposure = float(os.environ["EXPOSURE"])
if "SUN_ROT" in os.environ and sc.world and "Sky Texture" in sc.world.node_tree.nodes:
    sc.world.node_tree.nodes["Sky Texture"].sun_rotation = math.radians(float(os.environ["SUN_ROT"]))
print("VIEW", sc.view_settings.view_transform, sc.view_settings.look, sc.view_settings.exposure)
sc.render.filepath = os.path.abspath(a[1])
bpy.ops.render.render(write_still=True)
