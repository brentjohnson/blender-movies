"""Build the green blob character in a simple studio set.

Run:  ./run.sh -b --factory-startup -P scripts/build_scene.py
Saves blob.blend in the project root.

The body is a metaball field (body + stubby arms/feet melt into one surface), converted to a mesh.
It's a refractive shell around a green absorbing/scattering volume, with sparkles suspended inside.
Front of the character faces -Y. Units are meters; he's about 0.55 m tall.
"""
import bpy
import math
import os
import random
from mathutils import Vector, Quaternion

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
random.seed(11)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene


# --------------------------------------------------------------------------- helpers
def link(obj, coll=None):
    (coll or scene.collection).objects.link(obj)
    return obj


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


def mat_simple(name, color, rough=0.5, coat=0.0):
    m, n, out = material(name)
    b = n("ShaderNodeBsdfPrincipled", **{"Base Color": (*color, 1), "Roughness": rough,
                                         "Coat Weight": coat})
    n.link(b.outputs[0], out.inputs["Surface"])
    return m


# --------------------------------------------------------------------------- materials
BODY_GREEN = (0.25, 0.85, 0.22)


def mat_body():
    m, n, out = material("BlobBody")
    # Surface: clear jelly skin. The green comes mostly from the volume, so thick parts read deeper.
    surf = n("ShaderNodeBsdfPrincipled", **{"Base Color": (0.82, 1.0, 0.8, 1),
                                            "Transmission Weight": 1.0, "Roughness": 0.12,
                                            "IOR": 1.36})
    n.link(surf.outputs[0], out.inputs["Surface"])
    # Volume: green absorption + a little milky scatter so light glows through him.
    absorb = n("ShaderNodeVolumeAbsorption", Color=(*BODY_GREEN, 1),
               Density=float(os.environ.get("ABSORB", "9.0")))
    scat = n("ShaderNodeVolumeScatter", Color=(0.55, 1.0, 0.5, 1),
             Density=float(os.environ.get("SCATTER", "0.8")), Anisotropy=0.3)
    add = n("ShaderNodeAddShader")
    n.link(absorb.outputs[0], add.inputs[0])
    n.link(scat.outputs[0], add.inputs[1])
    n.link(add.outputs[0], out.inputs["Volume"])
    return m


def mat_sparkle_glow():
    """Tiny self-lit motes; each one gets a slightly different warm/cool tint and brightness."""
    m, n, out = material("SparkleGlow")
    info = n("ShaderNodeObjectInfo")
    ramp = n("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (1.0, 0.92, 0.55, 1)   # warm gold
    ramp.color_ramp.elements[1].color = (0.75, 1.0, 0.95, 1)   # cool mint-white
    n.link(info.outputs["Random"], ramp.inputs["Factor"])
    strength = n.math('MULTIPLY_ADD', info.outputs["Random"], 120.0, 30.0)
    em = n("ShaderNodeEmission", Color=ramp.outputs[0], Strength=strength)
    n.link(em.outputs[0], out.inputs["Surface"])
    return m


def mat_sparkle_flake():
    """Glitter flakes: mirror-like, so they glint when they catch a light."""
    m, n, out = material("SparkleFlake")
    b = n("ShaderNodeBsdfPrincipled", **{"Base Color": (1.0, 0.97, 0.85, 1), "Metallic": 1.0,
                                         "Roughness": 0.08})
    n.link(b.outputs[0], out.inputs["Surface"])
    return m


def mat_backdrop():
    m, n, out = material("Backdrop")
    # Soft vertical gradient: slightly darker on the floor, lighter up the wall.
    tc = n("ShaderNodeTexCoord")
    sep = n("ShaderNodeSeparateXYZ")
    n.link(tc.outputs["Generated"], sep.inputs[0])
    ramp = n("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].color = (0.20, 0.19, 0.25, 1)
    ramp.color_ramp.elements[1].color = (0.32, 0.32, 0.40, 1)
    n.link(sep.outputs["Z"], ramp.inputs["Factor"])
    b = n("ShaderNodeBsdfPrincipled", **{"Base Color": ramp.outputs[0], "Roughness": 0.85})
    n.link(b.outputs[0], out.inputs["Surface"])
    return m


M_BODY = mat_body()
M_GLOW = mat_sparkle_glow()
M_FLAKE = mat_sparkle_flake()
M_EYE_WHITE = mat_simple("EyeWhite", (0.9, 0.9, 0.88), rough=0.25, coat=1.0)
M_PUPIL = mat_simple("Pupil", (0.01, 0.012, 0.015), rough=0.15, coat=1.0)
M_MOUTH = mat_simple("Mouth", (0.02, 0.08, 0.02), rough=0.4)
M_BACKDROP = mat_backdrop()


# --------------------------------------------------------------------------- body (metaballs)
mb = bpy.data.metaballs.new("BlobMeta")
mb.resolution = mb.render_resolution = 0.008
mb.threshold = 0.6


def ball(kind, co, radius, size=(1, 1, 1), rot=Quaternion(), stiffness=2.0):
    e = mb.elements.new(type=kind)
    e.co = co
    e.radius = radius
    e.size_x, e.size_y, e.size_z = size
    e.rotation = rot
    e.stiffness = stiffness
    return e


def axis_rot(direction):
    """Quaternion turning the capsule's local +X onto `direction`."""
    return Vector((1, 0, 0)).rotation_difference(Vector(direction).normalized())


# gumdrop body: a round head-top merged into a wider, slightly squashed base
ball('BALL', (0, 0, 0.34), 0.30)
ball('ELLIPSOID', (0, 0, 0.18), 0.34, size=(1.05, 0.95, 0.75))
# stubby arms, angled out and a bit down
for s in (-1, 1):
    ball('CAPSULE', (s * 0.22, -0.01, 0.23), 0.085, size=(0.045, 1, 1),
         rot=axis_rot((s, -0.15, -0.55)))
# short feet, poking forward
for s in (-1, 1):
    ball('ELLIPSOID', (s * 0.11, -0.05, 0.03), 0.13, size=(0.85, 1.15, 0.6))

meta_obj = link(bpy.data.objects.new("BlobMeta", mb))
dg = bpy.context.evaluated_depsgraph_get()
me = bpy.data.meshes.new_from_object(meta_obj.evaluated_get(dg))
bpy.data.objects.remove(meta_obj)
bpy.data.metaballs.remove(mb)

# sit him on the floor
zmin = min(v.co.z for v in me.vertices)
for v in me.vertices:
    v.co.z -= zmin
for p in me.polygons:
    p.use_smooth = True
me.materials.append(M_BODY)
body = link(bpy.data.objects.new("Blob", me))
sm = body.modifiers.new("smooth", 'CORRECTIVE_SMOOTH')
sm.iterations = 6
sm.use_only_smooth = True
height = max(v.co.z for v in me.vertices)
print("BLOB HEIGHT", round(height, 3))


# --------------------------------------------------------------------------- face
def surface_point(x, z):
    """Where a ray from the front at (x, z) hits the body: (location, normal)."""
    ok, loc, nrm, _ = body.ray_cast(Vector((x, -5, z)), Vector((0, 1, 0)))
    assert ok, (x, z)
    return loc, nrm


def sphere(name, loc, r, mat, scale=(1, 1, 1)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32, ring_count=16, radius=r, location=loc)
    o = bpy.context.object
    o.name = name
    o.scale = scale
    o.data.materials.append(mat)
    bpy.ops.object.shade_smooth()
    return o


EYE_Z = 0.36 * height / 0.55
for s in (-1, 1):
    loc, nrm = surface_point(s * 0.085, EYE_Z)
    eye = sphere("Eye", loc - nrm * 0.012, 0.042, M_EYE_WHITE, scale=(0.9, 0.9, 1.1))
    pupil = sphere("Pupil", loc + nrm * 0.022 + Vector((-s * 0.004, 0, 0.004)), 0.024,
                   M_PUPIL, scale=(0.9, 0.6, 1.1))

# small smile: a beveled curve laid just under the skin
cu = bpy.data.curves.new("Mouth", 'CURVE')
cu.dimensions = '3D'
cu.bevel_depth = 0.0055
cu.bevel_resolution = 4
spl = cu.splines.new('POLY')
N = 16
spl.points.add(N - 1)
mouth_z = EYE_Z - 0.085
for i in range(N):
    t = i / (N - 1) * 2 - 1
    loc, nrm = surface_point(t * 0.05, mouth_z - 0.018 * (1 - t * t))
    spl.points[i].co = (*(loc - nrm * 0.002), 1)
cu.materials.append(M_MOUTH)
link(bpy.data.objects.new("Mouth", cu))


# --------------------------------------------------------------------------- sparkles inside
# Instance sources live far below the floor, out of view.
bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1, location=(0, 0, -50))
glow_src = bpy.context.object
glow_src.name = "SparkleGlowSrc"
glow_src.data.materials.append(M_GLOW)

bpy.ops.mesh.primitive_plane_add(size=2, location=(0, 0, -52))
flake_src = bpy.context.object
flake_src.name = "SparkleFlakeSrc"
flake_src.data.materials.append(M_FLAKE)


def sparkle_system(name, src, count, size, rand, seed):
    ps = body.modifiers.new(name, 'PARTICLE_SYSTEM').particle_system
    ps.seed = seed
    p = ps.settings
    p.name = name
    p.type = 'HAIR'
    p.count = count
    p.emit_from = 'VOLUME'
    p.distribution = 'RAND'
    p.hair_length = 1.0          # hair instances are scaled by hair length
    p.render_type = 'OBJECT'
    p.instance_object = src
    p.particle_size = size
    p.size_random = rand
    p.use_rotations = True
    p.rotation_mode = 'NONE'
    p.rotation_factor_random = 1.0
    p.use_advanced_hair = True
    return ps


sparkle_system("glow", glow_src, int(os.environ.get("GLOW_COUNT", "70")), 0.0035, 0.7, 3)
sparkle_system("flakes", flake_src, int(os.environ.get("FLAKE_COUNT", "400")), 0.006, 0.6, 5)
body.show_instancer_for_render = True


# --------------------------------------------------------------------------- set: cyclorama
cyc = bpy.data.meshes.new("Cyclorama")
prof = [(y, 0.0) for y in (-6, -2, 0.5)]
R = 1.5
for i in range(1, 13):
    a = i / 12 * math.pi / 2
    prof.append((0.5 + R * math.sin(a), R - R * math.cos(a)))
prof.append((0.5 + R, 5.0))
W = 6.0
verts = [(x, y, z) for (y, z) in prof for x in (-W, W)]
faces = [(2 * i, 2 * i + 1, 2 * i + 3, 2 * i + 2) for i in range(len(prof) - 1)]
cyc.from_pydata(verts, [], faces)
for p in cyc.polygons:
    p.use_smooth = True
cyc.materials.append(M_BACKDROP)
link(bpy.data.objects.new("Cyclorama", cyc))


# --------------------------------------------------------------------------- lights
def area(name, loc, target, power, size, color=(1, 1, 1), spread=180):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = power
    ld.size = size
    ld.spread = math.radians(spread)
    ld.color = color
    o = link(bpy.data.objects.new(name, ld))
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    return o


center = (0, 0, height * 0.5)
area("Key", (-1.4, -1.6, 1.7), center, 70, 1.2, (1.0, 0.95, 0.88), spread=50)
area("Fill", (1.8, -1.2, 0.6), center, 50, 2.0, (0.85, 0.92, 1.0))
area("Rim", (0.9, 1.3, 1.3), center, 260, 0.8, (1.0, 0.98, 0.92))   # back light makes him glow
area("RimL", (-1.0, 1.2, 0.5), center, 120, 0.6, (0.9, 1.0, 0.95))

world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.05, 0.05, 0.06, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 1.0


# --------------------------------------------------------------------------- camera
aim = link(bpy.data.objects.new("CamAim", None))
aim.location = (0, 0, height * 0.48)
cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 85
cam_data.dof.use_dof = True
cam_data.dof.focus_object = aim
cam_data.dof.aperture_fstop = 4.0
cam = link(bpy.data.objects.new("Camera", cam_data))
cam.location = (0.85, -2.9, 0.42)
tt = cam.constraints.new('TRACK_TO')
tt.target = aim
tt.track_axis = 'TRACK_NEGATIVE_Z'
tt.up_axis = 'UP_Y'
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
c.samples = int(os.environ.get("SAMPLES", "128"))
c.use_denoising = True
c.denoiser = 'OPENIMAGEDENOISE'
c.max_bounces = 16
c.transmission_bounces = 12
c.transparent_max_bounces = 16
c.volume_bounces = 2
c.glossy_bounces = 6
c.caustics_refractive = True
c.blur_glossy = 0.5
c.volume_step_rate = 0.5    # body is small; finer steps keep the volume clean
c.use_light_tree = True

vs_ = scene.view_settings
vs_.view_transform = 'AgX'
vs_.look = 'AgX - Medium High Contrast'
vs_.exposure = float(os.environ.get("EXPOSURE", "-0.6"))

# compositor: a soft bloom so the sparkles twinkle
ng = bpy.data.node_groups.new("Composite", 'CompositorNodeTree')
ng.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
cb = NT(ng)
rl = cb("CompositorNodeRLayers")
glare = cb("CompositorNodeGlare")
glare.inputs["Type"].default_value = 'Bloom'
glare.inputs["Threshold"].default_value = 1.5
glare.inputs["Strength"].default_value = 0.4
glare.inputs["Size"].default_value = 0.45
gout = cb("NodeGroupOutput")
cb.link(rl.outputs["Image"], glare.inputs["Image"])
cb.link(glare.outputs[0], gout.inputs[0])
scene.compositing_node_group = ng

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(ROOT, "blob.blend"))
print("SAVED", os.path.join(ROOT, "blob.blend"))
