"""Final render settings, applied at render time (not saved):
   [RES=1280x720] [SAMPLES=40] [DEV=AUTO] ./run.sh -b <scene>.blend -P ../scripts/render_setup.py -a
Without RES/SAMPLES the scene's own values are kept. Writes <movie>/frames/f_####.png.
Previews: PCT=40 renders at a fraction of RES; OUT=tests/preview writes there instead of frames/.
Resumable: existing frames are skipped, and several processes can share a frame range."""
import bpy, sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import devices

sc = bpy.context.scene
r = sc.render
devices.setup()
if "RES" in os.environ:
    r.resolution_x, r.resolution_y = map(int, os.environ["RES"].lower().split("x"))
r.resolution_percentage = int(os.environ.get("PCT", "100"))
if "SAMPLES" in os.environ:
    sc.cycles.samples = int(os.environ["SAMPLES"])
r.use_overwrite = False
r.use_placeholder = True
r.filepath = os.path.join(os.path.dirname(bpy.data.filepath), os.environ.get("OUT", "frames"), "f_")
print("RENDER", r.resolution_x, "x", r.resolution_y, sc.cycles.samples, "spp", sc.cycles.device, flush=True)
