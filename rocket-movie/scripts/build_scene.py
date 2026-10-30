"""Build the rocket launch test scene procedurally.

Run:  OCIO=ocio/config.ocio blender -b --factory-startup -P scripts/build_scene.py
Saves rocket_launch.blend in the project root.
"""
import bpy
import bmesh
import math
import os
import random
from mathutils import Vector, Matrix

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPS = 24
FRAMES = 240                 # 10 seconds
IGNITION = 36                # 1.5 s
LIFTOFF = 78                 # 3.25 s
ACCEL = 3.4                  # net upward acceleration, m/s^2
PAD_DECK = 3.0               # top of concrete pad
ROCKET_BASE = PAD_DECK + 6.0 # nozzle exit height while on the mount
SOUND_DELAY = int(700 / 343 * FPS)  # camera is ~700 m away

random.seed(7)

# --------------------------------------------------------------------------- reset
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.fps = FPS
scene.frame_start, scene.frame_end = 1, FRAMES


def rocket_z(frame):
    t = max(0.0, (frame - LIFTOFF) / FPS)
    return ROCKET_BASE + 0.5 * ACCEL * t * t


# --------------------------------------------------------------------------- helpers
def link(obj, coll=None):
    (coll or scene.collection).objects.link(obj)
    return obj


def new_obj(name, mesh, coll=None):
    return link(bpy.data.objects.new(name, mesh), coll)


def bm_to_obj(bm, name, smooth=False, coll=None):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    return new_obj(name, me, coll)


def revolve(profile, segs=64, cap_bottom=False, cap_top=False):
    """profile: list of (radius, z). Returns a bmesh lathe."""
    bm = bmesh.new()
    rings = []
    for r, z in profile:
        ring = []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            ring.append(bm.verts.new((r * math.cos(a), r * math.sin(a), z)))
        rings.append(ring)
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for i in range(segs):
            j = (i + 1) % segs
            bm.faces.new((a[i], a[j], b[j], b[i]))
    if cap_bottom:
        bm.faces.new(list(reversed(rings[0])))
    if cap_top:
        bm.faces.new(rings[-1])
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-4)
    if profile[-1][1] < profile[0][1]:      # profile runs downward: faces point inward
        bmesh.ops.reverse_faces(bm, faces=bm.faces)
    bm.normal_update()
    return bm


def add_box(bm, center, size, rot=None):
    m = Matrix.Translation(center)
    if rot is not None:
        m = m @ rot
    m = m @ Matrix.Diagonal((*size, 1.0))
    bmesh.ops.create_cube(bm, size=1.0, matrix=m)


def add_beam(bm, p1, p2, t):
    p1, p2 = Vector(p1), Vector(p2)
    d = p2 - p1
    rot = d.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    add_box(bm, (p1 + p2) / 2, (t, t, d.length), rot)


class NT:
    """Tiny node-tree builder."""

    def __init__(self, tree):
        self.t = tree
        self.n = tree.nodes
        self.x = 0

    def __call__(self, kind, **inputs):
        node = self.n.new(kind)
        node.location = (self.x, 0)
        self.x += 200
        for k, v in inputs.items():
            if hasattr(node, k) and not k[0].isupper():
                setattr(node, k, v)
            else:
                sock = next(i for i in node.inputs if i.name == k and i.enabled)
                self.set(sock, v)
        return node

    def set(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.t.links.new(v, sock)
        else:
            sock.default_value = v

    def link(self, a, b):
        self.t.links.new(a, b)

    def math(self, op, a, b=0.0, c=None, clamp=False):
        m = self("ShaderNodeMath", operation=op, use_clamp=clamp)
        self.set(m.inputs[0], a)
        self.set(m.inputs[1], b)
        if c is not None:
            self.set(m.inputs[2], c)
        return m.outputs[0]


def material(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    return m, NT(nt), out


# --------------------------------------------------------------------------- materials
def mat_rocket_white():
    m, b, out = material("RocketWhite")
    tc = b("ShaderNodeTexCoord")
    sep = b("ShaderNodeSeparateXYZ", Vector=tc.outputs["Object"])
    # panel seams: thin rings along the body plus streaky grime
    wave = b("ShaderNodeTexWave", wave_type='BANDS', bands_direction='Z',
             Vector=tc.outputs["Object"], Scale=0.55, Distortion=0.0)
    seam = b("ShaderNodeMapRange", Value=wave.outputs["Factor"],
             **{"From Min": 0.0, "From Max": 0.04, "To Min": 1.0, "To Max": 0.0})
    streak = b("ShaderNodeTexNoise", Vector=b("ShaderNodeMapping",
               Vector=tc.outputs["Object"], Scale=(6, 6, 0.08)).outputs[0],
               Scale=3.0, Detail=8.0)
    # soot near the base
    soot = b("ShaderNodeMapRange", Value=sep.outputs["Z"],
             **{"From Min": 1.5, "From Max": 7.0, "To Min": 0.55, "To Max": 0.0})
    grime = b.math('MULTIPLY', streak.outputs["Factor"], 0.12)
    dark = b.math('ADD', grime, soot.outputs[0], clamp=True)
    col = b("ShaderNodeMix", data_type='RGBA', Factor=dark,
            A=(0.82, 0.82, 0.80, 1), B=(0.12, 0.11, 0.10, 1))
    bump = b("ShaderNodeBump", Strength=0.25, Distance=0.01, Height=seam.outputs[0])
    bsdf = b("ShaderNodeBsdfPrincipled", **{"Base Color": col.outputs[2], "Roughness": 0.38,
             "Coat Weight": 0.15, "Normal": bump.outputs[0]})
    b.link(bsdf.outputs[0], out.inputs[0])
    return m


def mat_simple(name, color, rough=0.5, metal=0.0, noise_var=0.0, scale=4.0, bump=0.0):
    m, b, out = material(name)
    base = color + (1,)
    if noise_var:
        tc = b("ShaderNodeTexCoord")
        nz = b("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=scale, Detail=10.0)
        dark = tuple(c * (1 - noise_var) for c in color) + (1,)
        mix = b("ShaderNodeMix", data_type='RGBA', Factor=nz.outputs["Factor"], A=dark, B=base)
        base = mix.outputs[2]
    kw = {"Base Color": base, "Roughness": rough, "Metallic": metal}
    if bump:
        tc = b("ShaderNodeTexCoord")
        nz2 = b("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=scale * 6, Detail=12.0)
        kw["Normal"] = b("ShaderNodeBump", Strength=bump, Height=nz2.outputs["Factor"]).outputs[0]
    bsdf = b("ShaderNodeBsdfPrincipled", **kw)
    b.link(bsdf.outputs[0], out.inputs[0])
    return m


def mat_ground():
    m, b, out = material("Ground")
    tc = b("ShaderNodeTexCoord")
    co = tc.outputs["Object"]
    big = b("ShaderNodeTexNoise", Vector=co, Scale=0.004, Detail=6.0, Roughness=0.6)
    mid = b("ShaderNodeTexNoise", Vector=co, Scale=0.05, Detail=8.0)
    fine = b("ShaderNodeTexNoise", Vector=co, Scale=2.0, Detail=10.0)
    ramp = b("ShaderNodeValToRGB", Factor=b.math('MULTIPLY_ADD', big.outputs["Factor"], 0.7,
                                               b.math('MULTIPLY', mid.outputs["Factor"], 0.3)))
    cr = ramp.color_ramp
    cr.elements[0].position, cr.elements[0].color = 0.40, (0.10, 0.11, 0.045, 1)
    cr.elements[1].position, cr.elements[1].color = 0.62, (0.26, 0.24, 0.13, 1)
    e = cr.elements.new(0.52)
    e.color = (0.16, 0.17, 0.07, 1)
    # sandy apron around the pad
    dist = b("ShaderNodeVectorMath", operation='LENGTH', Vector=co)
    apron = b("ShaderNodeMapRange", Value=dist.outputs["Value"],
              **{"From Min": 70.0, "From Max": 110.0, "To Min": 1.0, "To Max": 0.0})
    sand = b("ShaderNodeMix", data_type='RGBA', Factor=apron.outputs[0],
             A=ramp.outputs[0], B=(0.42, 0.38, 0.30, 1))
    vary = b("ShaderNodeMix", data_type='RGBA', blend_type='MULTIPLY',
             Factor=0.35, A=sand.outputs[2],
             B=b("ShaderNodeValToRGB", Factor=fine.outputs["Factor"]).outputs[0])
    bump = b("ShaderNodeBump", Strength=0.6, Height=fine.outputs["Factor"])
    bsdf = b("ShaderNodeBsdfPrincipled", **{"Base Color": vary.outputs[2], "Roughness": 0.92,
             "Normal": bump.outputs[0]})
    b.link(bsdf.outputs[0], out.inputs[0])
    return m


def mat_water():
    m, b, out = material("Ocean")
    tc = b("ShaderNodeTexCoord")
    mp = b("ShaderNodeMapping", Vector=tc.outputs["Object"], Scale=(1.0, 3.0, 1.0))
    wav = b("ShaderNodeTexNoise", Vector=mp.outputs[0], Scale=0.35, Detail=12.0, Roughness=0.65)
    bump = b("ShaderNodeBump", Strength=0.35, Distance=0.3, Height=wav.outputs["Factor"])
    bsdf = b("ShaderNodeBsdfPrincipled", **{"Base Color": (0.01, 0.035, 0.05, 1),
             "Roughness": 0.06, "IOR": 1.33, "Normal": bump.outputs[0]})
    b.link(bsdf.outputs[0], out.inputs[0])
    return m


def mat_bush():
    m, b, out = material("Scrub")
    ob = b("ShaderNodeObjectInfo")
    ramp = b("ShaderNodeValToRGB", Factor=ob.outputs["Random"])
    cr = ramp.color_ramp
    cr.elements[0].color = (0.02, 0.03, 0.01, 1)
    cr.elements[1].color = (0.07, 0.075, 0.03, 1)
    tc = b("ShaderNodeTexCoord")
    nz = b("ShaderNodeTexNoise", Vector=tc.outputs["Object"], Scale=6.0, Detail=8.0)
    bump = b("ShaderNodeBump", Strength=1.0, Height=nz.outputs["Factor"])
    bsdf = b("ShaderNodeBsdfPrincipled", **{"Base Color": ramp.outputs[0], "Roughness": 0.85,
             "Normal": bump.outputs[0], "Subsurface Weight": 0.1})
    b.link(bsdf.outputs[0], out.inputs[0])
    return m


def mat_plume():
    """Volumetric exhaust: blackbody emission fading along the plume, flickering noise."""
    m, b, out = material("Plume")
    tc = b("ShaderNodeTexCoord")
    sep = b("ShaderNodeSeparateXYZ", Vector=tc.outputs["Object"])
    depth = b.math('MULTIPLY', sep.outputs["Z"], -1.0)                 # 0 at nozzle
    d = b.math('DIVIDE', depth, 42.0, clamp=True)
    rxy = b("ShaderNodeVectorMath", operation='LENGTH',
            Vector=b("ShaderNodeCombineXYZ", X=sep.outputs["X"], Y=sep.outputs["Y"]).outputs[0])
    rad = b.math('MULTIPLY_ADD', depth, 0.085, 0.75)
    rn = b.math('DIVIDE', rxy.outputs["Value"], rad)
    radial = b.math('POWER', b.math('SUBTRACT', 1.0, rn, clamp=True), 1.3)
    core = b.math('POWER', b.math('SUBTRACT', 1.0, d, clamp=True), 2.2)
    mp = b("ShaderNodeMapping", Vector=tc.outputs["Object"], Scale=(0.6, 0.6, 0.18))
    nz = b("ShaderNodeTexNoise", noise_dimensions='4D', Vector=mp.outputs[0], Scale=1.6,
           Detail=6.0, Roughness=0.6)
    drv = nz.inputs["W"].driver_add("default_value").driver
    drv.expression = "frame / 3.0"
    flick = b("ShaderNodeMapRange", Value=nz.outputs["Factor"],
              **{"From Min": 0.3, "From Max": 0.7, "To Min": 0.25, "To Max": 1.6})
    s = b.math('MULTIPLY', b.math('MULTIPLY', core, radial), flick.outputs[0])
    strength = b.math('MULTIPLY', s, 320.0)
    temp = b.math('MULTIPLY_ADD', b.math('POWER', b.math('SUBTRACT', 1.0, d), 2.0), 1300.0, 1800.0)
    bb = b("ShaderNodeBlackbody", Temperature=temp)
    tint = b("ShaderNodeMix", data_type='RGBA', blend_type='MULTIPLY', Factor=1.0, A=bb.outputs[0],
             B=(1.0, 0.78, 0.45, 1))
    em = b("ShaderNodeEmission", Color=tint.outputs[2], Strength=strength)
    b.link(em.outputs[0], out.inputs["Volume"])
    return m


def mat_smoke():
    m, b, out = material("LaunchSmoke")
    dens = b("ShaderNodeAttribute", attribute_name="density")
    flame = b("ShaderNodeAttribute", attribute_name="flame")
    dmul = b.math('MULTIPLY', dens.outputs["Factor"], 4.0)
    fl = b.math('POWER', flame.outputs["Factor"], 2.0)
    em_s = b.math('MULTIPLY', fl, 14.0)
    ftemp = b.math('MULTIPLY_ADD', flame.outputs["Factor"], 1300.0, 1500.0)
    bb = b("ShaderNodeBlackbody", Temperature=ftemp)
    vol = b("ShaderNodeVolumePrincipled", **{
        "Color": (0.95, 0.94, 0.92, 1), "Density": dmul, "Anisotropy": 0.3,
        "Emission Strength": em_s, "Emission Color": bb.outputs[0]})
    vol.inputs["Density Attribute"].default_value = ""
    b.link(vol.outputs[0], out.inputs["Volume"])
    return m


def mat_haze():
    m, b, out = material("Haze")
    vol = b("ShaderNodeVolumePrincipled", **{"Color": (0.75, 0.82, 0.95, 1),
            "Density": 0.00007, "Anisotropy": 0.6})
    vol.inputs["Density Attribute"].default_value = ""
    b.link(vol.outputs[0], out.inputs["Volume"])
    return m


M_WHITE = mat_rocket_white()
M_BLACK = mat_simple("Interstage", (0.025, 0.025, 0.027), rough=0.45, noise_var=0.3)
M_ENGINE = mat_simple("EngineBell", (0.25, 0.20, 0.17), rough=0.35, metal=1.0, noise_var=0.5,
                      scale=8.0)
M_HEATSHIELD = mat_simple("HeatShield", (0.06, 0.055, 0.05), rough=0.8, noise_var=0.5)
M_STEEL = mat_simple("TowerSteel", (0.38, 0.36, 0.33), rough=0.55, metal=0.6, noise_var=0.45,
                     scale=0.6)
M_REDSTEEL = mat_simple("RedSteel", (0.35, 0.07, 0.03), rough=0.6, noise_var=0.4, scale=0.5)
M_CONCRETE = mat_simple("Concrete", (0.32, 0.31, 0.29), rough=0.9, noise_var=0.45, scale=0.3,
                        bump=0.3)
M_DARK = mat_simple("TrenchDark", (0.02, 0.02, 0.02), rough=0.9)
M_TANK = mat_simple("WaterTank", (0.7, 0.7, 0.68), rough=0.4, noise_var=0.3, scale=0.5)
M_SAND = mat_simple("Sand", (0.55, 0.50, 0.40), rough=0.95, noise_var=0.3, scale=0.05, bump=0.3)

# --------------------------------------------------------------------------- rocket
rocket = link(bpy.data.objects.new("Rocket", None))
rocket.empty_display_size = 3

R = 1.85
body_profile = [
    (0.0, 1.45), (R, 1.45), (R, 6.0), (R, 30.5), (R, 34.5), (R, 37.0),
    (2.25, 38.4), (2.25, 43.2), (2.12, 44.6), (1.82, 45.9), (1.38, 47.0),
    (0.85, 47.9), (0.35, 48.5), (0.0, 48.7),
]
bm = revolve(body_profile, segs=96)
body = bm_to_obj(bm, "RocketBody", smooth=True)
for mtl in (M_WHITE, M_BLACK, M_HEATSHIELD):
    body.data.materials.append(mtl)
for p in body.data.polygons:
    z = p.center.z
    if z < 1.5:
        p.material_index = 2
    elif 30.5 < z < 34.5:
        p.material_index = 1
body.data.polygons.foreach_get  # noqa (keep data alive)
body.parent = rocket
# flat-shade the hard edges by edge split
es = body.modifiers.new("split", 'EDGE_SPLIT')
es.split_angle = math.radians(35)

# engine bells: 1 centre + 8 ring
bell_profile = [(0.30, 1.45), (0.27, 1.25), (0.33, 0.95), (0.42, 0.55), (0.52, 0.15), (0.56, 0.0)]
bm = bmesh.new()
positions = [(0, 0)] + [(1.22 * math.cos(a), 1.22 * math.sin(a))
                        for a in (2 * math.pi * k / 8 for k in range(8))]
for x, y in positions:
    b2 = revolve(bell_profile, segs=32)
    bmesh.ops.translate(b2, verts=b2.verts, vec=(x, y, 0))
    me_tmp = bpy.data.meshes.new("tmp")
    b2.to_mesh(me_tmp)
    b2.free()
    bm.from_mesh(me_tmp)
    bpy.data.meshes.remove(me_tmp)
bells = bm_to_obj(bm, "EngineBells", smooth=True)
bells.data.materials.append(M_ENGINE)
sol = bells.modifiers.new("thick", 'SOLIDIFY')
sol.thickness = 0.04
bells.parent = rocket

# fins
bm = bmesh.new()
for k in range(4):
    a = math.pi / 4 + k * math.pi / 2
    rot = Matrix.Rotation(a, 4, 'Z')
    t = 0.09
    pts = [(R - 0.05, 1.6), (3.1, 1.6), (3.1, 3.0), (R - 0.05, 6.4)]
    vs_front = [bm.verts.new(rot @ Vector((r, t, z))) for r, z in pts]
    vs_back = [bm.verts.new(rot @ Vector((r, -t, z))) for r, z in pts]
    bm.faces.new(vs_front)
    bm.faces.new(list(reversed(vs_back)))
    for i in range(4):
        j = (i + 1) % 4
        bm.faces.new((vs_front[j], vs_front[i], vs_back[i], vs_back[j]))
fins = bm_to_obj(bm, "Fins")
fins.data.materials.append(M_BLACK)
bev = fins.modifiers.new("bev", 'BEVEL')
bev.width = 0.03
fins.parent = rocket

# cable raceways running up the stages
bm = bmesh.new()
for a_ in (math.radians(100), math.radians(280)):
    rot = Matrix.Rotation(a_, 4, 'Z')
    add_box(bm, rot @ Vector((R + 0.1, 0, 16.0)), (0.28, 0.55, 28.0), rot)
    add_box(bm, rot @ Vector((R + 0.08, 0, 35.7)), (0.22, 0.45, 2.4), rot)
race = bm_to_obj(bm, "Raceways")
race.data.materials.append(M_WHITE)
bev = race.modifiers.new("bev", 'BEVEL')
bev.width = 0.06
race.parent = rocket

# plume volume
plume_profile = [(0.0, 0.05), (0.45, 0.0), (0.9, -2.0), (1.6, -6.0), (2.6, -14.0),
                 (3.6, -26.0), (4.4, -38.0), (3.5, -44.0), (0.0, -46.0)]
bm = revolve(plume_profile, segs=32)
plume = bm_to_obj(bm, "Plume", smooth=True)
plume.data.materials.append(mat_plume())
plume.parent = rocket
plume.visible_shadow = False

# engine light
light_data = bpy.data.lights.new("EngineGlow", 'POINT')
light_data.shadow_soft_size = 3.0
light_data.color = (1.0, 0.52, 0.2)
engine_light = link(bpy.data.objects.new("EngineGlow", light_data))
engine_light.parent = rocket
engine_light.location = (0, 0, -3.5)

# smoke/fire emitter under the nozzles
bpy.ops.mesh.primitive_cylinder_add(radius=1.9, depth=1.2, location=(0, 0, -1.0), vertices=24)
engine_flow = bpy.context.object
engine_flow.name = "EngineFlow"
engine_flow.parent = rocket
engine_flow.hide_render = True
engine_flow.display_type = 'WIRE'

# animate rocket
for f in range(1, FRAMES + 1):
    rocket.location = (0, 0, rocket_z(f))
    # tiny attitude wobble once free
    w = max(0.0, (f - LIFTOFF) / FPS)
    rocket.rotation_euler = (0.0015 * math.sin(f * 0.21) * min(w, 1),
                             0.0012 * math.sin(f * 0.17 + 1) * min(w, 1), 0)
    rocket.keyframe_insert("location", frame=f)
    rocket.keyframe_insert("rotation_euler", frame=f)

    # plume grows at ignition, lengthens as it clears the pad
    ig = min(1.0, max(0.0, (f - IGNITION) / 8.0))
    flick = 1.0 + 0.06 * math.sin(f * 2.3) + 0.04 * math.sin(f * 5.1 + 0.7)
    sxy = max(ig * 1.35, 0.001)
    plume.scale = (sxy, sxy, max(0.001, ig * (0.55 + 0.45 * min(1, w / 3))) * flick)
    plume.keyframe_insert("scale", frame=f)
    light_data.energy = 7e5 * ig * flick * (1.0 + 0.15 * random.random())
    light_data.keyframe_insert("energy", frame=f)

# --------------------------------------------------------------------------- pad
pad_coll = bpy.data.collections.new("LaunchPad")
scene.collection.children.link(pad_coll)

bm = bmesh.new()
hole = 5.5
add_box(bm, (0, 0, PAD_DECK / 2 - 0.5), (60, 40, PAD_DECK + 1))
pad = bm_to_obj(bm, "PadDeck", coll=pad_coll)
pad.data.materials.append(M_CONCRETE)
# cut the flame hole with a boolean
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 0))
cutter = bpy.context.object
cutter.scale = (2 * hole, 2 * hole, 20)
boo = pad.modifiers.new("hole", 'BOOLEAN')
boo.object = cutter
boo.operation = 'DIFFERENCE'
bpy.context.view_layer.objects.active = pad
bpy.ops.object.modifier_apply(modifier="hole")
bpy.data.objects.remove(cutter)
bev = pad.modifiers.new("bev", 'BEVEL')
bev.width = 0.3
bev.segments = 2

bm = bmesh.new()
add_box(bm, (0, 0, -3), (2 * hole, 2 * hole, 1))
trench = bm_to_obj(bm, "TrenchFloor", coll=pad_coll)
trench.data.materials.append(M_DARK)

# launch mount: four hold-down pedestals + ring
bm = bmesh.new()
for sx in (-1, 1):
    for sy in (-1, 1):
        add_box(bm, (sx * 3.3, sy * 3.3, PAD_DECK + 3.0), (1.3, 1.3, 6.0))
        add_box(bm, (sx * 2.6, sy * 2.6, ROCKET_BASE + 0.9), (0.6, 0.6, 1.4))
for k in range(4):
    a = k * math.pi / 2
    rot = Matrix.Rotation(a, 4, 'Z')
    add_box(bm, rot @ Vector((3.3, 0, ROCKET_BASE - 0.4)), (0.8, 7.4, 0.8), rot)
mount = bm_to_obj(bm, "LaunchMount", coll=pad_coll)
mount.data.materials.append(M_STEEL)


def lattice_tower(name, width, height, seg, post, brace, coll, mat):
    bm = bmesh.new()
    h2 = width / 2
    corners = [(-h2, -h2), (h2, -h2), (h2, h2), (-h2, h2)]
    for x, y in corners:
        add_box(bm, (x, y, height / 2), (post, post, height))
    n = int(height / seg)
    for i in range(n + 1):
        z = i * seg
        for k in range(4):
            (x1, y1), (x2, y2) = corners[k], corners[(k + 1) % 4]
            add_beam(bm, (x1, y1, z), (x2, y2, z), brace)
            if i < n:
                if i % 2 == 0:
                    add_beam(bm, (x1, y1, z), (x2, y2, z + seg), brace * 0.8)
                else:
                    add_beam(bm, (x2, y2, z), (x1, y1, z + seg), brace * 0.8)
    obj = bm_to_obj(bm, name, coll=coll)
    obj.data.materials.append(mat)
    return obj


tower = lattice_tower("ServiceTower", 7.0, 66.0, 4.0, 0.55, 0.3, pad_coll, M_STEEL)
tower.location = (-11.5, 2.0, PAD_DECK)
# access arms and a mast on top
bm = bmesh.new()
for z, L in ((16, 5.2), (40, 5.2), (52, 5.0)):
    add_box(bm, (3.5 + L / 2, -2.0, z), (L, 2.2, 2.4))
add_box(bm, (0, 0, 66.0 + 6), (0.5, 0.5, 12))
add_box(bm, (0, 0, 66.3), (8.0, 8.0, 0.6))
arms = bm_to_obj(bm, "AccessArms", coll=pad_coll)
arms.data.materials.append(M_REDSTEEL)
arms.parent = tower

# lightning protection towers
for i, (x, y) in enumerate(((-55, -35), (55, -30), (8, 55))):
    lt = lattice_tower(f"LightningTower{i}", 2.2, 92.0, 3.0, 0.25, 0.14, pad_coll, M_STEEL)
    lt.location = (x, y, 0)
    bm = bmesh.new()
    add_box(bm, (0, 0, 92 + 5), (0.3, 0.3, 10))
    mast = bm_to_obj(bm, f"LightningMast{i}", coll=pad_coll)
    mast.data.materials.append(M_STEEL)
    mast.parent = lt

# catenary wires between lightning masts (thin curves, sagging)
tops = [Vector((-55, -35, 101)), Vector((55, -30, 101)), Vector((8, 55, 101))]
for k in range(3):
    a, b_ = tops[k], tops[(k + 1) % 3]
    cu = bpy.data.curves.new(f"wire{k}", 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = 0.05
    sp = cu.splines.new('POLY')
    pts = 24
    sp.points.add(pts - 1)
    for i in range(pts):
        t = i / (pts - 1)
        p = a.lerp(b_, t)
        p.z -= 14 * 4 * t * (1 - t)
        sp.points[i].co = (*p, 1)
    w = new_obj(f"Wire{k}", cu, pad_coll)
    w.data.materials.append(M_STEEL)

# water tower
bm = bmesh.new()
for k in range(4):
    a = k * math.pi / 2 + math.pi / 4
    add_beam(bm, (9 * math.cos(a), 9 * math.sin(a), 0), (5 * math.cos(a), 5 * math.sin(a), 52), 0.8)
add_box(bm, (0, 0, 26), (1.8, 1.8, 52))
legs = bm_to_obj(bm, "WaterTowerLegs", coll=pad_coll)
legs.data.materials.append(M_STEEL)
legs.location = (170, 140, 0)
bpy.ops.mesh.primitive_uv_sphere_add(radius=9, location=(170, 140, 60), segments=48, ring_count=24)
tank = bpy.context.object
tank.name = "WaterTank"
tank.scale.z = 0.8
bpy.ops.object.shade_smooth()
for c in tank.users_collection:
    c.objects.unlink(tank)
pad_coll.objects.link(tank)
tank.data.materials.append(M_TANK)

# a few low service buildings
for (x, y, sx, sy, sz) in ((-70, 25, 22, 12, 8), (60, -10, 14, 10, 6), (-30, 60, 30, 14, 12),
                           (110, 30, 18, 18, 10)):
    bm = bmesh.new()
    add_box(bm, (x, y, sz / 2), (sx, sy, sz))
    o = bm_to_obj(bm, "Building", coll=pad_coll)
    o.data.materials.append(M_CONCRETE)

# --------------------------------------------------------------------------- terrain
env_coll = bpy.data.collections.new("Environment")
scene.collection.children.link(env_coll)

bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=200, y_segments=200, size=1.0)
ground = bm_to_obj(bm, "Ground", coll=env_coll)
ground.scale = (1600, 950, 1)
ground.location = (0, -700, 0)
bpy.context.view_layer.objects.active = ground
ground.select_set(True)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
ground.data.materials.append(mat_ground())
# gentle undulation away from the pad
tex = bpy.data.textures.new("terrain", 'CLOUDS')
tex.noise_scale = 60.0
dsp = ground.modifiers.new("undulate", 'DISPLACE')
dsp.texture = tex
dsp.texture_coords = 'GLOBAL'
dsp.strength = 1.4
dsp.mid_level = 0.6
vg = ground.vertex_groups.new(name="far")
for v in ground.data.vertices:
    wco = Vector((v.co.x, v.co.y - 700, 0))
    vg.add([v.index], min(1.0, max(0.0, (wco.length - 90) / 120)), 'REPLACE')
dsp.vertex_group = "far"
# ground stops at the beach; the domain and pad sit on top of it near y=0
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 300, 0.02))
beach = bpy.context.object
beach.name = "Beach"
beach.scale = (3200, 120, 1)
for c in beach.users_collection:
    c.objects.unlink(beach)
env_coll.objects.link(beach)
bpy.context.view_layer.objects.active = beach
bpy.ops.object.select_all(action='DESELECT')
beach.select_set(True)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
beach.data.materials.append(M_SAND)
bpy.ops.mesh.primitive_plane_add(size=1, location=(0, 5000, -0.3))
ocean = bpy.context.object
ocean.name = "Ocean"
ocean.scale = (40000, 9500, 1)
for c in ocean.users_collection:
    c.objects.unlink(ocean)
env_coll.objects.link(ocean)
bpy.context.view_layer.objects.active = ocean
bpy.ops.object.select_all(action='DESELECT')
ocean.select_set(True)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
ocean.data.materials.append(mat_water())

# scrub vegetation scattered over the field in front of the pad
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1.0, location=(0, 0, -50))
bush = bpy.context.object
bush.name = "BushProto"
tex_b = bpy.data.textures.new("bushnoise", 'VORONOI')
tex_b.noise_scale = 0.35
dspb = bush.modifiers.new("lumpy", 'DISPLACE')
dspb.texture = tex_b
dspb.strength = 0.7
bush.scale = (0.8, 0.8, 0.5)
bush.data.materials.append(mat_bush())
bpy.ops.object.shade_smooth()

bpy.ops.mesh.primitive_plane_add(size=1, location=(0, -360, 0.0))
field = bpy.context.object
field.name = "ScrubField"
field.scale = (1400, 580, 1)
for c in field.users_collection:
    c.objects.unlink(field)
env_coll.objects.link(field)
field.data.materials.append(M_SAND)
ps = field.modifiers.new("scrub", 'PARTICLE_SYSTEM').particle_system
pset = ps.settings
pset.type = 'HAIR'
pset.count = 160000
pset.distribution = 'RAND'
pset.hair_length = 1.0
pset.render_type = 'OBJECT'
pset.instance_object = bush
pset.particle_size = 0.6
pset.size_random = 0.9
pset.use_rotations = True
pset.rotation_mode = 'GLOB_Z'
pset.phase_factor_random = 2.0
pset.use_advanced_hair = True
field.show_instancer_for_render = False
field.show_instancer_for_viewport = False

# --------------------------------------------------------------------------- smoke simulation
bpy.ops.mesh.primitive_cube_add(size=1)
domain = bpy.context.object
domain.name = "SmokeDomain"
domain.scale = (260, 140, 130)
domain.location = (0, 0, 65 - 0.5)
dmod = domain.modifiers.new("Fluid", 'FLUID')
dmod.fluid_type = 'DOMAIN'
ds = dmod.domain_settings
ds.domain_type = 'GAS'
ds.resolution_max = int(os.environ.get("SMOKE_RES", "160"))
ds.use_adaptive_domain = True
ds.adapt_margin = 6
ds.adapt_threshold = 0.005
ds.use_noise = os.environ.get("SMOKE_NOISE", "1") == "1"
ds.noise_scale = 2
ds.noise_strength = 1.4
ds.noise_pos_scale = 1.6
ds.vorticity = 0.12
ds.alpha = 0.15
ds.beta = 0.45
ds.burning_rate = 0.8
ds.flame_smoke = 1.2
ds.flame_vorticity = 0.6
ds.flame_max_temp = 2.5
ds.flame_smoke_color = (0.85, 0.83, 0.8)
ds.use_dissolve_smoke = True
ds.dissolve_speed = 140
ds.use_dissolve_smoke_log = True
ds.time_scale = 1.0
ds.cfl_condition = 3.0
ds.timesteps_max = 6
ds.cache_type = 'ALL'
ds.cache_frame_start = 1
ds.cache_frame_end = FRAMES
ds.cache_directory = os.path.join(ROOT, "cache", "smoke")
ds.cache_data_format = 'OPENVDB'
ds.openvdb_cache_compress_type = 'BLOSC'
domain.data.materials.append(mat_smoke())
domain.display_type = 'WIRE'
domain.cycles.use_motion_blur = False   # adaptive domain moves; blurring its transform streaks
for attr in ("use_collision_border_top", "use_collision_border_front", "use_collision_border_back",
             "use_collision_border_left", "use_collision_border_right"):
    setattr(ds, attr, False)
ds.use_collision_border_bottom = True

ef = engine_flow.modifiers.new("Fluid", 'FLUID')
ef.fluid_type = 'FLOW'
fs = ef.flow_settings
fs.flow_type = 'BOTH'
fs.flow_behavior = 'INFLOW'
fs.flow_source = 'MESH'
fs.surface_distance = 1.2
fs.use_initial_velocity = True
fs.velocity_coord = (0, 0, -70)
fs.smoke_color = (0.82, 0.8, 0.77)
fs.temperature = 2.0
fs.subframes = 2

trench_flows = []
for side in (-1, 1):
    bpy.ops.mesh.primitive_cube_add(size=1, location=(side * 34, 0, 2.5))
    tf = bpy.context.object
    tf.name = f"TrenchExit{'L' if side < 0 else 'R'}"
    tf.scale = (4, 9, 4)
    tf.hide_render = True
    tf.display_type = 'WIRE'
    m = tf.modifiers.new("Fluid", 'FLUID')
    m.fluid_type = 'FLOW'
    s = m.flow_settings
    s.flow_type = 'BOTH'
    s.flow_behavior = 'INFLOW'
    s.flow_source = 'MESH'
    s.surface_distance = 1.5
    s.use_initial_velocity = True
    s.velocity_coord = (side * 45, 0, 6)
    s.smoke_color = (0.88, 0.87, 0.85)
    s.temperature = 1.0
    s.velocity_random = 0.3
    trench_flows.append(s)

# small LOX vent near the top before ignition
bpy.ops.mesh.primitive_uv_sphere_add(radius=0.6, location=(R + 0.3, 0, 36.0))
vent = bpy.context.object
vent.name = "LoxVent"
vent.parent = rocket
vent.location = (R + 0.3, 0, 27.0)
vent.hide_render = True
vent.display_type = 'WIRE'
vm = vent.modifiers.new("Fluid", 'FLUID')
vm.fluid_type = 'FLOW'
vs = vm.flow_settings
vs.flow_type = 'SMOKE'
vs.flow_behavior = 'INFLOW'
vs.flow_source = 'MESH'
vs.surface_distance = 0.8
vs.use_initial_velocity = True
vs.velocity_coord = (4, -1, -2)
vs.temperature = -0.4
vs.smoke_color = (0.95, 0.95, 0.95)

for f in range(1, FRAMES + 1):
    scene.frame_set(f)
    ig = min(1.0, max(0.0, (f - IGNITION) / 6.0))
    alt = rocket_z(f) - ROCKET_BASE
    near = max(0.0, 1.0 - alt / 25.0)
    fs.density = ig * (0.45 + 0.55 * near)
    fs.fuel_amount = 0.7 * ig * near
    fs.temperature = 2.5 * ig
    fs.use_inflow = ig > 0
    engine_flow.location = (0, 0, -min(ROCKET_BASE - PAD_DECK + alt, 24.0))
    engine_flow.keyframe_insert("location", frame=f)
    for p in ("density", "fuel_amount", "temperature", "use_inflow"):
        fs.keyframe_insert(p, frame=f)
    # trench output: fireball burst at ignition then steamy smoke that fades as the rocket climbs
    tr = min(1.0, max(0.0, (f - IGNITION - 6) / 8.0)) * max(0.0, 1.0 - alt / 45.0)
    burst = max(0.0, 1.0 - (f - IGNITION - 6) / 30.0) if f > IGNITION + 6 else 0.0
    for s in trench_flows:
        s.density = 1.0 * tr
        s.fuel_amount = 0.6 * burst * tr
        s.temperature = 0.6 + burst
        s.use_inflow = tr > 0.01
        for p in ("density", "fuel_amount", "temperature", "use_inflow"):
            s.keyframe_insert(p, frame=f)
    vs.use_inflow = f < IGNITION + 10
    vs.density = 0.6 if f < IGNITION + 10 else 0.0
    for p in ("density", "use_inflow"):
        vs.keyframe_insert(p, frame=f)
scene.frame_set(1)

# --------------------------------------------------------------------------- atmosphere haze
bpy.ops.mesh.primitive_cube_add(size=1, location=(0, 0, 150))
haze = bpy.context.object
haze.name = "AtmosphereHaze"
haze.scale = (4000, 4000, 300)
haze.data.materials.append(mat_haze())
haze.display_type = 'WIRE'
haze.visible_shadow = False
haze.hide_render = os.environ.get("HAZE", "1") != "1"

# --------------------------------------------------------------------------- world / sky
world = bpy.data.worlds.new("Sky")
scene.world = world
world.use_nodes = True
wn = world.node_tree
wn.nodes.clear()
wb = NT(wn)
sky = wb("ShaderNodeTexSky", sky_type='MULTIPLE_SCATTERING')
sky.sun_elevation = math.radians(13)
sky.sun_rotation = math.radians(float(os.environ.get("SUN_ROT", "205")))
sky.altitude = 5
sky.air_density = 1.2
sky.aerosol_density = 1.0
sky.ozone_density = 1.0
sky.sun_intensity = 1.0
sky.sun_size = math.radians(0.6)
bg = wb("ShaderNodeBackground", Color=sky.outputs[0], Strength=0.3)
wo = wb("ShaderNodeOutputWorld")
wb.link(bg.outputs[0], wo.inputs["Surface"])

# --------------------------------------------------------------------------- camera
cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 135
cam_data.sensor_width = 36
cam_data.clip_start = 1.0
cam_data.clip_end = 30000
camera = link(bpy.data.objects.new("Camera", cam_data))
camera.location = (-40, -720, 6.0)
scene.camera = camera
target = link(bpy.data.objects.new("CamTarget", None))
tt = camera.constraints.new('TRACK_TO')
tt.target = target
tt.track_axis = 'TRACK_NEGATIVE_Z'
tt.up_axis = 'UP_Y'

aim = 31.0
for f in range(1, FRAMES + 1):
    rz = rocket_z(f) - ROCKET_BASE
    desired = 31.0 + 0.95 * rz
    aim += (desired - aim) * 0.12          # operator lag
    shake_t = f - (IGNITION + SOUND_DELAY)
    amp = 0.0
    if shake_t > 0:
        amp = 0.9 * min(1.0, shake_t / 10.0) * (0.55 + 0.45 * math.exp(-shake_t / 40.0))
    sx = amp * (math.sin(f * 1.7) * 0.6 + math.sin(f * 3.1 + 1.3) * 0.4 + random.uniform(-0.3, 0.3))
    sz = amp * (math.sin(f * 2.3 + 0.4) * 0.6 + math.sin(f * 4.7) * 0.4 + random.uniform(-0.3, 0.3))
    drift = 0.004 * f                      # slow handheld drift
    target.location = (-4 + drift + sx, 0, aim + sz)
    target.keyframe_insert("location", frame=f)

# --------------------------------------------------------------------------- render settings
r = scene.render
r.engine = 'CYCLES'
r.resolution_x, r.resolution_y = 1920, 1080
r.resolution_percentage = int(os.environ.get("RES_PCT", "100"))
r.use_motion_blur = True
r.motion_blur_shutter = 0.5
r.film_transparent = False
r.use_persistent_data = True
r.image_settings.file_format = 'PNG'
r.image_settings.color_depth = '8'
r.filepath = os.path.join(ROOT, "frames", "f_")

c = scene.cycles
c.device = 'GPU'
c.samples = int(os.environ.get("SAMPLES", "96"))
c.adaptive_threshold = 0.02
c.use_denoising = True
c.denoiser = 'OPENIMAGEDENOISE'
c.max_bounces = 6
c.diffuse_bounces = 3
c.glossy_bounces = 3
c.volume_bounces = 2
c.transparent_max_bounces = 16
c.volume_step_rate = 2.0
c.volume_max_steps = 512
c.use_light_tree = True

prefs = bpy.context.preferences.addons['cycles'].preferences
prefs.compute_device_type = 'HIP'
prefs.get_devices()
for d in prefs.devices:
    d.use = True

vs_ = scene.view_settings
vs_.view_transform = 'AgX'
vs_.look = 'AgX - Medium High Contrast'
vs_.exposure = -1.8

# compositor: bloom around the flame + subtle lens distortion
ng = bpy.data.node_groups.new("Composite", 'CompositorNodeTree')
ng.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
cb = NT(ng)
rl = cb("CompositorNodeRLayers")
glare = cb("CompositorNodeGlare")
for ident in ('Bloom', 'BLOOM'):
    try:
        glare.inputs["Type"].default_value = ident
        break
    except Exception:
        pass
glare.inputs["Threshold"].default_value = 1.2
glare.inputs["Strength"].default_value = 0.35
glare.inputs["Size"].default_value = 0.7
lens = cb("CompositorNodeLensdist")
lens.inputs["Dispersion"].default_value = 0.008
gout = cb("NodeGroupOutput")
cb.link(rl.outputs["Image"], glare.inputs["Image"])
cb.link(glare.outputs[0], lens.inputs["Image"])
cb.link(lens.outputs[0], gout.inputs[0])
scene.compositing_node_group = ng

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "rocket_launch.blend"))
print("SAVED", os.path.join(ROOT, "rocket_launch.blend"))
