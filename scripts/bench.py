"""Time one frame under a device/quality config:
   DEV=AUTO PCT=30 SPP=16 VB=2 VSR=2 ./run.sh -b <scene>.blend -P ../scripts/bench.py -- FRAME OUT"""
import bpy, sys, time, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import devices

a = sys.argv[sys.argv.index("--") + 1:]
sc = bpy.context.scene
mode = devices.setup()
sc.cycles.volume_bounces = int(os.environ.get("VB", "2"))
sc.cycles.volume_step_rate = float(os.environ.get("VSR", "2"))
sc.render.resolution_percentage = int(os.environ.get("PCT", "30"))
sc.cycles.samples = int(os.environ.get("SPP", "16"))
sc.frame_set(int(a[0])); sc.render.filepath = os.path.abspath(a[1])
t = time.time(); bpy.ops.render.render(write_still=True)
print("BENCH", mode, os.environ.get("VB"), os.environ.get("VSR"), "%.1f" % (time.time() - t))
