"""Bake every Mantaflow domain in the scene (or only DOMAIN=<object name>), then save:
   ./run.sh -b <scene>.blend -P ../scripts/bake.py"""
import bpy, os, time
only = os.environ.get("DOMAIN")
domains = [(o, m) for o in bpy.context.scene.objects for m in o.modifiers
           if m.type == 'FLUID' and m.fluid_type == 'DOMAIN' and (not only or o.name == only)]
if not domains:
    print("BAKE nothing to bake", flush=True)
for dom, mod in domains:
    ds = mod.domain_settings
    print("BAKE", dom.name, "res", ds.resolution_max, "noise", ds.use_noise, flush=True)
    t = time.time()
    with bpy.context.temp_override(object=dom, active_object=dom, selected_objects=[dom]):
        bpy.ops.fluid.free_all()
        bpy.ops.fluid.bake_all()
    print("BAKE %s done %.1fs" % (dom.name, time.time() - t), flush=True)
if domains:
    bpy.ops.wm.save_mainfile()
