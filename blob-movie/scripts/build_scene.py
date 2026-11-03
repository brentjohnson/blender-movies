"""Build the green blob character on a kitchen counter.

Run:  ./run.sh -b --factory-startup -P scripts/build_scene.py
Saves blob.blend in the project root. ANIM=walk builds the walk test instead (scripts/walk.py) and saves
blob_walk.blend: he walks a circle, runs, hops onto a rolling pin, rides it, and gets thrown.

The body is a metaball field (body + stubby arms/feet melt into one surface), converted to a mesh.
It's a refractive shell around a green absorbing/scattering volume, with sparkles suspended inside.
Front of the character faces -Y. He's built and animated in design units (about 0.58 tall); everything that
belongs to him (body, rig, eyes, flakes, rolling pin, camera) hangs off the "Character" empty, which scales him
to BLOB_H (12 cm). The kitchen (scripts/kitchen.py) is in real meters, countertop at z = 0.
"""
import bpy
import bmesh
import math
import os
import random
import sys
from mathutils import Vector, Quaternion, Matrix

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import walk  # noqa: E402
import kitchen  # noqa: E402

ANIM = os.environ.get("ANIM", "idle")      # idle: standing hero pose; walk: walk/run/hop test
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
                                            "Transmission Weight": 1.0,
                                            "Roughness": float(os.environ.get("SKIN_ROUGH", "0.2")),
                                            "IOR": 1.36})
    if os.environ.get("GREEN_SHADOW", "1") == "1":
        # Cycles can't find light paths through refracting jelly from soft lights, so the floor gets a plain
        # grey shadow. Let shadow rays pass the skin instead: the volume still absorbs them, so the shadow
        # turns green and thick parts cast deeper green than thin ones.
        # Only rays coming from outside (front face, or already through the near side) pass. Shadow rays
        # starting inside him stay blocked, so his milky interior isn't lit directly and doesn't wash out.
        lp = n("ShaderNodeLightPath")
        geo = n("ShaderNodeNewGeometry")
        outside = n.math('MAXIMUM', n.math('SUBTRACT', 1.0, geo.outputs["Backfacing"]),
                         n.math('MINIMUM', lp.outputs["Transparent Depth"], 1.0))
        # The skin tints the light too (once in, once out), on top of the volume's absorption, so the
        # green survives AgX and the grey fill on the floor.
        tint = float(os.environ.get("SHADOW_TINT", "1.5"))
        clear = n("ShaderNodeBsdfTransparent", Color=(1 - 0.6 * tint, 1 - 0.05 * tint, 1 - 0.65 * tint, 1))
        mix = n("ShaderNodeMixShader", Factor=n.math('MULTIPLY', lp.outputs["Is Shadow Ray"], outside))
        n.link(surf.outputs[0], mix.inputs[1])
        n.link(clear.outputs[0], mix.inputs[2])
        n.link(mix.outputs[0], out.inputs["Surface"])
    else:
        n.link(surf.outputs[0], out.inputs["Surface"])
    # Volume: green absorption + a little milky scatter so light glows through him.
    absorb = n("ShaderNodeVolumeAbsorption", Color=(*BODY_GREEN, 1),
               Density=float(os.environ.get("ABSORB", "11.0")))
    scat = n("ShaderNodeVolumeScatter", Color=(0.55, 1.0, 0.5, 1),
             Density=float(os.environ.get("SCATTER", "1.2")), Anisotropy=0.3)
    add = n("ShaderNodeAddShader")
    n.link(absorb.outputs[0], add.inputs[0])
    n.link(scat.outputs[0], add.inputs[1])
    n.link(add.outputs[0], out.inputs["Volume"])
    return m


def mat_sparkle_flake():
    """Silver glitter flakes: no emission, just polished metal that glints when it catches a light.
    Each flake gets a slightly different roughness so some flash sharply and some shimmer."""
    m, n, out = material("SparkleFlake")
    info = n("ShaderNodeObjectInfo")
    r0 = float(os.environ.get("FLAKE_ROUGH", "0.04"))
    rough = n.math('MULTIPLY_ADD', info.outputs["Random"], r0 * 3.0, r0)
    b = n("ShaderNodeBsdfPrincipled", **{"Base Color": (0.92, 0.93, 0.95, 1), "Metallic": 1.0,
                                         "Roughness": rough})
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
ARM_C, ARM_DIR = (0.22, -0.01, 0.23), (1, -0.15, -0.55)    # right arm mirrors x
for s in (-1, 1):
    ball('CAPSULE', (s * ARM_C[0], ARM_C[1], ARM_C[2]), 0.085, size=(0.045, 1, 1),
         rot=axis_rot((s * ARM_DIR[0], ARM_DIR[1], ARM_DIR[2])))
# short cylindrical legs: vertical capsules here; their round bottoms are flattened after meshing
LEG_X = float(os.environ.get("LEG_X", "0.105"))       # leg axis offset from the centre line, m
LEG_Y = -0.02
LEG_R = float(os.environ.get("LEG_R", "0.12"))       # metaball radius of a leg
LEG_FILLET = float(os.environ.get("LEG_FILLET", "0.35"))  # sole edge radius, as a fraction of leg radius
LEG_Z = float(os.environ.get("LEG_Z", "0.03"))   # leg capsule centre, before sitting him on the floor
for s in (-1, 1):
    ball('CAPSULE', (s * LEG_X, LEG_Y, LEG_Z), LEG_R, size=(0.03, 1, 1), rot=axis_rot((0, 0, 1)))

meta_obj = link(bpy.data.objects.new("BlobMeta", mb))
dg = bpy.context.evaluated_depsgraph_get()
me = bpy.data.meshes.new_from_object(meta_obj.evaluated_get(dg))
bpy.data.objects.remove(meta_obj)
bpy.data.metaballs.remove(mb)

# sit him on the floor
zmin = min(v.co.z for v in me.vertices)
for v in me.vertices:
    v.co.z -= zmin


def voxel_remesh(me, size):
    """Even, clean topology (the metaball mesh is dense and uneven, and stretches poorly)."""
    tmp = bpy.data.objects.new("_remesh", me)
    scene.collection.objects.link(tmp)
    rm = tmp.modifiers.new("remesh", 'REMESH')
    rm.mode = 'VOXEL'
    rm.voxel_size = size
    out = bpy.data.meshes.new_from_object(tmp.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    bpy.data.objects.remove(tmp)
    return out


def mirror_right_to_left(me):
    """Make him exactly symmetric: keep his right half (-X) and mirror it onto his left."""
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.symmetrize(bm, input=bm.verts[:] + bm.edges[:] + bm.faces[:], direction='-X', dist=1e-5)
    bm.to_mesh(me)
    bm.free()


me = voxel_remesh(me, float(os.environ.get("VOXEL", "0.005")))


def flatten_soles(me):
    """Turn each leg's round bottom into a flat sole with a soft, filleted edge.

    Below the hemisphere centre, every vertex moves along its ray from that centre, from the sphere out
    onto a rounded-cylinder profile (flat bottom, quarter-circle fillet, vertical side). Straight-down and
    sideways rays keep their length, so the sole stays at the floor and the side joins smoothly.
    The left pass also reworks his right side (the measured radius spans the whole base), and that double
    pass is what gives the chosen merged-base look. It leaves his left side lopsided, so mirror_right_to_left()
    then copies the right half over it."""
    for s in (-1, 1):
        axis = Vector((s * LEG_X, LEG_Y))
        near = [v for v in me.vertices if (v.co.xy - axis).length < LEG_R * 2.5]
        # leg radius: widest point of the leg a little above the floor
        R = max((v.co.xy - axis).length for v in near if v.co.z < 0.03)
        f = R * LEG_FILLET
        cz = R                                        # hemisphere centre height (sole sits at z = 0)
        for v in near:
            dz = v.co.z - cz
            rv = v.co.xy - axis
            dr = rv.length
            if dz >= 0 or dr > R * 1.2:
                continue
            L = math.hypot(dr, dz)
            ur, uz = dr / L, dz / L                   # ray direction in the (radial, z) plane, uz < 0
            t = R / -uz                               # hit the flat sole?
            if t * ur > R - f:
                t = R / ur if ur > 1e-9 else t        # hit the vertical side?
                if ur <= 1e-9 or cz + t * uz < f:     # otherwise the fillet (circle at (R-f, f))
                    ox, oz = -(R - f), cz - f         # ray origin relative to the fillet centre
                    b = ox * ur + oz * uz
                    t = -b + math.sqrt(max(b * b - (ox * ox + oz * oz - f * f), 0.0))
            k = t / R                                 # sphere -> rounded cylinder along this ray
            new_r = rv.normalized() * dr * k if dr > 1e-9 else rv
            v.co.x, v.co.y = (axis + new_r)
            v.co.z = cz + dz * k
    # The measured "leg radius" spans the whole merged base (~0.26 m), which gives the chosen look. Anything
    # pushed below the floor sits inside the footprint, so lifting it onto the sole plane completes the sole.
    for v in me.vertices:
        if v.co.z < 0:
            v.co.z = 0.0


flatten_soles(me)
mirror_right_to_left(me)
for p in me.polygons:
    p.use_smooth = True
me.materials.append(M_BODY)
body = link(bpy.data.objects.new("Blob", me))
sm = body.modifiers.new("smooth", 'CORRECTIVE_SMOOTH')
sm.iterations = 6
sm.use_only_smooth = True
height = max(v.co.z for v in me.vertices)
print("BLOB HEIGHT", round(height, 3))
# Real size. Everything of his is built in design units and scaled by the Character empty. Volume densities
# are per world meter, so they go up by 1/SCALE to keep the same look.
BLOB_H = float(os.environ.get("BLOB_H", "0.12"))
SCALE = BLOB_H / height
ROOT_XY = (0.0, -0.03)          # where his design origin sits on the counter
for nd in M_BODY.node_tree.nodes:
    if nd.bl_idname in ("ShaderNodeVolumeAbsorption", "ShaderNodeVolumeScatter"):
        nd.inputs["Density"].default_value /= SCALE


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
mouth = link(bpy.data.objects.new("Mouth", cu))
# "Frown" shape key: the curve flips (ends down, middle up). Pushing it negative gives a bigger grin.
mouth.shape_key_add(name="Basis")
frown = mouth.shape_key_add(name="Frown", from_mix=False)
frown.slider_min = -0.6
frown.value = 0.0                 # new curve shape keys start at 1.0
for i in range(N):
    t = i / (N - 1) * 2 - 1
    loc, nrm = surface_point(t * 0.05, mouth_z - 0.010 + 0.014 * (1 - t * t))
    frown.data[i].co = loc - nrm * 0.002


# --------------------------------------------------------------------------- sparkles inside
# Weightless glitter, like a snow globe with no gravity. Each flake drifts on a slowly changing swirl
# (curl noise, so the flow neither bunches up nor thins out) and tumbles, so its glints come and go.
# The skin and the eyeballs push flakes away, so they never leave the body or pass through the eyes.
# Every frame is simulated here and stored as one point per flake per frame in the "Flakes" mesh.
# A geometry-nodes tree keeps only the current frame's points and puts a hex flake on each.
from mathutils import noise
from mathutils.bvhtree import BVHTree

scene.render.fps = 24
scene.frame_start = 1
if ANIM == "walk":
    PLAN = walk.plan(scene.render.fps, LEG_X, LEG_Y, height)
    scene.frame_end = len(PLAN["frames"])
else:
    scene.frame_end = int(os.environ.get("FRAMES", "240"))
F0, F1 = scene.frame_start, scene.frame_end

FLAKE_COUNT = int(os.environ.get("FLAKE_COUNT", "900"))
FLAKE_SIZE = float(os.environ.get("FLAKE_SIZE", "0.0055"))      # hex radius, m
DRIFT = float(os.environ.get("DRIFT", "0.0125"))               # typical drift speed, m/s
TUMBLE = float(os.environ.get("TUMBLE", "0.5"))                # typical spin, rad/s
SWIRL_SCALE = 0.12                                             # size of the flow's eddies, m
WALL = 0.03                                                    # skin starts pushing within this, m
MARGIN = FLAKE_SIZE * 1.6                                      # closest a flake centre gets to the skin
FLAKE_FLOOR = 0.12        # flakes stay in the torso, above the legs, so leg deformation can't expose them

bvh = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
EYES = [(o.location.copy(), max(o.scale) * o.dimensions.x / o.scale.x / 2 + MARGIN)
        for o in bpy.data.objects if o.name.startswith("Eye")]


def depth(pnt):
    """(distance inside the allowed space, negative outside; inward normal of the nearest boundary).
    The boundary is the skin plus a floor at FLAKE_FLOOR."""
    loc, nrm, _, dist = bvh.find_nearest(pnt)
    d = dist if (loc - pnt).dot(nrm) > 0 else -dist
    if pnt.z - FLAKE_FLOOR < d:
        return pnt.z - FLAKE_FLOOR, Vector((0, 0, 1))
    return d, -nrm


def swirl(pnt, t):
    """Divergence-free velocity: the curl of a slowly evolving noise potential."""
    q = pnt / SWIRL_SCALE + Vector((0.065, 0.145, 0.105)) * t   # the flow pattern itself evolves slowly too
    e = 0.01

    def pot(dx, dy, dz):
        return noise.noise_vector(q + Vector((dx, dy, dz)))
    dpx, dmx = pot(e, 0, 0), pot(-e, 0, 0)
    dpy, dmy = pot(0, e, 0), pot(0, -e, 0)
    dpz, dmz = pot(0, 0, e), pot(0, 0, -e)
    return Vector(((dpy.z - dmy.z) - (dpz.y - dmz.y),
                   (dpz.x - dmz.x) - (dpx.z - dmx.z),
                   (dpx.y - dmx.y) - (dpy.x - dmy.x))) / (2 * e)


def avoid_eyes(pnt):
    for c, r in EYES:
        d = pnt - c
        if d.length < r:
            pnt = c + d.normalized() * r
    return pnt


# scatter the flakes through the body, clear of the skin and eyes
lo = Vector(tuple(min(v.co[i] for v in body.data.vertices) for i in range(3)))
hi = Vector(tuple(max(v.co[i] for v in body.data.vertices) for i in range(3)))
flakes = []
while len(flakes) < FLAKE_COUNT:
    pnt = Vector(tuple(random.uniform(lo[i], hi[i]) for i in range(3)))
    if depth(pnt)[0] > MARGIN * 1.5 and avoid_eyes(pnt) == pnt:
        flakes.append({
            "p": pnt,
            "q": Quaternion(Vector([random.gauss(0, 1) for _ in range(3)]).normalized(),
                            random.uniform(0, math.tau)),
            "axis": Vector([random.gauss(0, 1) for _ in range(3)]).normalized(),
            "spin": TUMBLE * random.uniform(0.4, 1.6) * random.choice((-1, 1)),
            "size": FLAKE_SIZE * (1 - 0.6 * random.random()),
        })

# normalise the swirl so its typical speed is DRIFT
SPEED_K = DRIFT / (sum(swirl(f["p"], 0).length for f in flakes[:200]) / min(200, len(flakes)))

dt = 1.0 / scene.render.fps
pos, rot, size, frame = [], [], [], []
for fr in range(F0, F1 + 1):
    t = (fr - F0) * dt
    for f in flakes:
        if fr > F0:
            v = swirl(f["p"], t) * SPEED_K
            d, inward = depth(f["p"])
            if d < WALL:                       # near the skin: cancel the outward part and push in
                out = -v.dot(inward)
                if out > 0:
                    v += inward * out
                v += inward * DRIFT * 2.0 * (1 - max(d, 0) / WALL)
            pnt = f["p"] + v * dt
            d, inward = depth(pnt)
            if d < MARGIN:                     # hard stop: never closer than MARGIN to the skin
                pnt += inward * (MARGIN - d)
            f["p"] = avoid_eyes(pnt)
            f["q"] = Quaternion(f["axis"], f["spin"] * dt) @ f["q"]
        pos.append(f["p"].copy())
        rot.append(f["q"].to_euler())
        size.append(f["size"])
        frame.append(fr)

fme = bpy.data.meshes.new("Flakes")
fme.vertices.add(len(pos))
fme.vertices.foreach_set("co", [c for v in pos for c in v])
for name, kind, vals in (("rot", 'FLOAT_VECTOR', [c for e in rot for c in e]),
                         ("size", 'FLOAT', size), ("frame", 'INT', frame)):
    at = fme.attributes.new(name, kind, 'POINT')
    at.data.foreach_set("vector" if kind == 'FLOAT_VECTOR' else "value", vals)
flake_obj = link(bpy.data.objects.new("Flakes", fme))

gn = bpy.data.node_groups.new("FlakeInstances", 'GeometryNodeTree')
gn.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
gn.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
g = NT(gn)
gin = g("NodeGroupInput")
now = g("GeometryNodeInputSceneTime")
cur = g.math('MAXIMUM', g.math('MINIMUM', g.math('ROUND', now.outputs["Frame"]), F1), F0)
fr_attr = g("GeometryNodeInputNamedAttribute", data_type='INT', Name="frame")
other = g("FunctionNodeCompare", data_type='FLOAT', operation='NOT_EQUAL',
          A=fr_attr.outputs["Attribute"], B=cur, Epsilon=0.5)
keep = g("GeometryNodeDeleteGeometry", domain='POINT', Geometry=gin.outputs[0],
         Selection=other.outputs[0])
hexf = g("GeometryNodeMeshCircle", fill_type='NGON', Vertices=6, Radius=1.0)
hexm = g("GeometryNodeSetMaterial", Geometry=hexf.outputs["Mesh"], Material=M_FLAKE)
rot_attr = g("GeometryNodeInputNamedAttribute", data_type='FLOAT_VECTOR', Name="rot")
size_attr = g("GeometryNodeInputNamedAttribute", data_type='FLOAT', Name="size")
e2r = g("FunctionNodeEulerToRotation", Euler=rot_attr.outputs["Attribute"])
inst = g("GeometryNodeInstanceOnPoints", Points=keep.outputs[0], Instance=hexm.outputs[0],
         Rotation=e2r.outputs[0], Scale=size_attr.outputs["Attribute"])
gout = g("NodeGroupOutput")
g.link(inst.outputs[0], gout.inputs[0])
flake_obj.modifiers.new("instances", 'NODES').node_group = gn
print("FLAKES", FLAKE_COUNT, "frames", F0, F1, "points", len(pos))


# --------------------------------------------------------------------------- walk test: rig + animation
def smoothstep(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


if ANIM == "walk":
    # Bones, none parented: the body, one per leg standing on its sole, a chest above the body for
    # follow-through, and one per arm. The legs are free, so a planted foot stays put while the body moves on,
    # and the jelly between them stretches. Chest and arms are keyed relative to the body (see below).
    arm = bpy.data.armatures.new("Rig")
    rig = link(bpy.data.objects.new("Rig", arm))
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm.edit_bones.new("body")
    eb.head, eb.tail = (0, 0, walk.PIVOT), (0, 0, walk.PIVOT + 0.3)
    LEGS = (("leg.R", -1), ("leg.L", 1))        # his right leg is at -X (he faces -Y)
    for name, sd in LEGS:
        eb = arm.edit_bones.new(name)
        eb.head, eb.tail = (sd * LEG_X, LEG_Y, 0), (sd * LEG_X, LEG_Y, 0.12)
    CHEST_Z = 0.12
    eb = arm.edit_bones.new("chest")
    eb.head, eb.tail = (0, 0, CHEST_Z), (0, 0, CHEST_Z + 0.33)
    ARMS = (("arm.R", -1), ("arm.L", 1))
    arm_axis = {}
    for name, sd in ARMS:
        d = Vector((sd * ARM_DIR[0], ARM_DIR[1], ARM_DIR[2])).normalized()
        c = Vector((sd * ARM_C[0], ARM_C[1], ARM_C[2] - zmin))
        shoulder, hand = c - d * 0.07, c + d * 0.08
        arm_axis[name] = (shoulder, d, (hand - shoulder).length)
        eb = arm.edit_bones.new(name)
        eb.head, eb.tail = shoulder, hand
    bpy.ops.object.mode_set(mode='OBJECT')

    # Skin weights: the whole lower base belongs to the legs, fading into the body by LEG_TOP. It's split
    # left/right with a soft seam down the middle. (A radius around each leg axis left the base's outer
    # corners on the body, so they hung down like a fixed skirt while the feet stepped.)
    # Each arm owns the stub along its axis, fading in from the shoulder. What's left goes to the chest
    # above CHEST_LO..CHEST_HI and to the body below.
    LEG_TOP = 0.11
    CHEST_LO, CHEST_HI = 0.14, 0.24
    groups = {n: body.vertex_groups.new(name=n) for n in ("body", "chest", "leg.R", "leg.L", "arm.R", "arm.L")}
    for v in me.vertices:
        low = 1 - smoothstep(0.015, LEG_TOP, v.co.z)
        left = smoothstep(-0.035, 0.035, v.co.x)
        ws = {"leg.R": low * (1 - left), "leg.L": low * left}
        for name, (sh, d, ln) in arm_axis.items():
            rel = v.co - sh
            t = rel.dot(d) / ln
            r = (rel - d * rel.dot(d)).length
            ws[name] = smoothstep(0.15, 0.6, t) * (1 - smoothstep(0.07, 0.11, r))
        rest_w = max(0.0, 1.0 - sum(ws.values()))
        ws["chest"] = rest_w * smoothstep(CHEST_LO, CHEST_HI, v.co.z)
        ws["body"] = rest_w - ws["chest"]
        for name, w in ws.items():
            if w > 1e-4:
                groups[name].add([v.index], w, 'REPLACE')
    body.modifiers.remove(sm)                   # armature must deform before the smoothing pass
    am = body.modifiers.new("rig", 'ARMATURE')
    am.object = rig
    sm = body.modifiers.new("smooth", 'CORRECTIVE_SMOOTH')
    sm.iterations = 6
    sm.use_only_smooth = True

    # Mouth and flakes ride on the chest bone. The eyes are keyed in world space (below), because they leave
    # him; each pupil is parented to its eyeball so it rolls with it.
    bb = arm.bones["chest"]
    bone_rest = rig.matrix_world @ bb.matrix_local @ Matrix.Translation((0, bb.length, 0))
    EYES = sorted([o for o in scene.objects if o.name.startswith("Eye")], key=lambda o: o.location.x)
    PUPILS = sorted([o for o in scene.objects if o.name.startswith("Pupil")], key=lambda o: o.location.x)
    for eye, pupil in zip(EYES, PUPILS):        # right eye (-X) first
        pupil.parent = eye
        pupil.matrix_parent_inverse = eye.matrix_world.inverted()
    for o in [o for o in scene.objects if o.name.startswith("Mouth")] + [flake_obj]:
        o.parent, o.parent_type, o.parent_bone = rig, 'BONE', "chest"
        o.matrix_parent_inverse = bone_rest.inverted()

    # Smoosh: a world-space squash measured from the floor, applied after the rig to the body and to
    # everything riding on it (eyes, mouth, flakes), so they all deform together. A slice at height z (u = z/H)
    # moves to H*(a*u + b*u^2), with a + b = HEAD_SQUASH. Its local vertical compression a + 2*b*u is strongest at
    # the floor, and it spreads out from the contact point by 1/sqrt(compression) to keep its volume. The floor
    # slice puddles out (~2.9x) and the far end stays domed (~1.35x). Controlled by the "Smoosh" empty:
    # location = contact point, scale.x - 1 = amount (0..1), scale.y = H. It's a child of the Character
    # empty, so in world space the floor is the countertop (z = 0) and every length is SCALEd.
    SM_A = 0.12
    SM_B = walk.HEAD_SQUASH - SM_A
    smoosh_ctrl = link(bpy.data.objects.new("Smoosh", None))
    smoosh_ctrl.scale = (1.0, height, 1.0)
    sg = bpy.data.node_groups.new("Smoosh", 'GeometryNodeTree')
    sg.interface.new_socket("Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    sg.interface.new_socket("Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    g = NT(sg)
    gin = g("NodeGroupInput")
    me_info = g("GeometryNodeObjectInfo", transform_space='ORIGINAL', Object=g("GeometryNodeSelfObject").outputs[0])
    ctl = g("GeometryNodeObjectInfo", transform_space='ORIGINAL', Object=smoosh_ctrl)
    wp = g("FunctionNodeTransformPoint", Vector=g("GeometryNodeInputPosition").outputs[0],
           Transform=me_info.outputs["Transform"])
    p_ = g("ShaderNodeSeparateXYZ", Vector=wp.outputs[0])
    c_ = g("ShaderNodeSeparateXYZ", Vector=ctl.outputs["Location"])
    k_ = g("ShaderNodeSeparateXYZ", Vector=ctl.outputs["Scale"])
    amount = g.math('SUBTRACT', g.math('DIVIDE', k_.outputs["X"], k_.outputs["Z"]), 1.0)   # world scale is SCALE*(1+amount, H, 1)
    H = k_.outputs["Y"]
    u = g.math('DIVIDE', p_.outputs["Z"], H, clamp=True)
    f = g.math('MULTIPLY', g.math('MULTIPLY', g.math('MULTIPLY_ADD', u, SM_B, SM_A), u), H)   # H*u*(a + b*u)
    z_new = g.math('MULTIPLY_ADD', g.math('SUBTRACT', f, g.math('MULTIPLY', u, H)), amount, p_.outputs["Z"])
    comp = g.math('MULTIPLY_ADD', g.math('SUBTRACT', g.math('MULTIPLY_ADD', u, 2 * SM_B, SM_A), 1.0), amount, 1.0)
    spread = g.math('POWER', comp, -0.5)
    x_new = g.math('MULTIPLY_ADD', g.math('SUBTRACT', p_.outputs["X"], c_.outputs["X"]), spread, c_.outputs["X"])
    y_new = g.math('MULTIPLY_ADD', g.math('SUBTRACT', p_.outputs["Y"], c_.outputs["Y"]), spread, c_.outputs["Y"])
    comb = g("ShaderNodeCombineXYZ", X=x_new, Y=y_new, Z=z_new)
    inv = g("FunctionNodeInvertMatrix", Matrix=me_info.outputs["Transform"])
    lp = g("FunctionNodeTransformPoint", Vector=comb.outputs[0], Transform=inv.outputs[0])
    setp = g("GeometryNodeSetPosition", Geometry=gin.outputs[0], Position=lp.outputs[0])
    g.link(setp.outputs[0], g("NodeGroupOutput").inputs[0])
    # body: armature -> smoosh -> smoothing
    body.modifiers.remove(sm)
    body.modifiers.new("smoosh", 'NODES').node_group = sg
    sm = body.modifiers.new("smooth", 'CORRECTIVE_SMOOTH')
    sm.iterations = 6
    sm.use_only_smooth = True
    for o in [o for o in scene.objects if o.name.startswith("Mouth")] + [flake_obj]:
        o.modifiers.new("smoosh", 'NODES').node_group = sg

    # Bake the plan into per-frame keys. Every bone gets an affine world transform M applied to its rest
    # geometry: matrix_basis = rest^-1 @ M @ rest. M is rigid times a volume-keeping squash along the body's
    # up axis about some anchor height. Body, chest and legs point up in rest, so this never needs shear.
    # The chest is the body tilted in world space about the chest root by the planner's lag spring. The arms
    # can't take the squash (they point sideways, so it would need shear): each one is rigid, turned by the
    # chest's rotation and its swing/raise angles about the shoulder, which rides the squashed chest.
    def keyframe(pb, M, fr):
        rest = pb.bone.matrix_local
        pb.matrix_basis = rest.inverted() @ M @ rest
        for path in ("location", "rotation_quaternion", "scale"):
            pb.keyframe_insert(path, frame=fr)

    def squash_about(sq, anchor):
        side = 1 / math.sqrt(sq)
        return (Matrix.Translation((0, 0, anchor)) @ Matrix.Diagonal((side, side, sq, 1.0))
                @ Matrix.Translation((0, 0, -anchor)))

    # a sparse set of rest vertices, to keep him on (and out of) the floor while tumbling
    floor_probe = [v.co.copy() for v in list(me.vertices)[::12]]
    # while walking the feet carry themselves; probe only what the body bone fully owns
    body_gi = groups["body"].index
    body_probe = [v.co.copy() for v in list(me.vertices)[::6]
                  if any(g.group == body_gi and g.weight > 0.98 for g in v.groups)]
    piv = Matrix.Translation((0, 0, walk.PIVOT))
    hold = {}
    body_M = []                                 # chest bone's world transform per frame, for the eyes

    def key_upper(M, f, fr):
        """Key the chest and arms from the body transform M; return the chest's transform."""
        p = M @ Vector((0, 0, CHEST_Z))
        lx, ly = f["lag"]
        R = Matrix.Rotation(lx, 4, 'Y') @ Matrix.Rotation(-ly, 4, 'X')
        MC = Matrix.Translation(p) @ R @ Matrix.Translation(-p) @ M
        keyframe(rig.pose.bones["chest"], MC, fr)
        rc = MC.to_3x3().normalized().to_4x4()
        for name, sd in ARMS:
            sh = arm_axis[name][0]
            side = "R" if sd < 0 else "L"
            Rl = (Matrix.Rotation(f["swing_" + side], 4, 'X')
                  @ Matrix.Rotation(-sd * (f["abd_" + side] - 0.12), 4, 'Y'))
            keyframe(rig.pose.bones[name], Matrix.Translation(MC @ sh) @ rc @ Rl @ Matrix.Translation(-sh), fr)
        return MC

    for i, f in enumerate(PLAN["frames"]):
        fr = F0 + i
        smoosh_ctrl.location = (f["x"], f["y"], 0.0)
        smoosh_ctrl.scale = (1.0 + f["smoosh"], height, 1.0)
        smoosh_ctrl.keyframe_insert("location", frame=fr)
        smoosh_ctrl.keyframe_insert("scale", frame=fr)
        if f["mode"] == "gait":
            W = (Matrix.Translation((f["x"], f["y"], f["z"])) @ Matrix.Rotation(f["yaw"], 4, 'Z')
                 @ Matrix.Translation((f["sway"], 0, 0))
                 @ piv @ Matrix.Rotation(f["pitch"], 4, 'X') @ Matrix.Rotation(f["roll"], 4, 'Y')
                 @ piv.inverted())
            M = W @ squash_about(f["squash"], walk.PIVOT)
            low = min((M @ q).z for q in body_probe)
            if low < 0:                             # banking/leaning swings the wide base down: lift him
                M = Matrix.Translation((0, 0, -low)) @ M
            keyframe(rig.pose.bones["body"], M, fr)
            body_M.append(key_upper(M, f, fr))
            for (name, sd), (fx, fy, fz, fyaw) in zip(LEGS, f["feet"]):
                W = (Matrix.Translation((fx, fy, fz)) @ Matrix.Rotation(fyaw, 4, 'Z')
                     @ Matrix.Translation((-sd * LEG_X, -LEG_Y, 0)))
                keyframe(rig.pose.bones[name], W, fr)
            continue
        # tumble: rigid rotation about the body's middle, squash about head / middle / feet
        W = (Matrix.Translation((f["x"], f["y"], f["cz"])) @ Matrix.Rotation(f["yaw"], 4, 'Z')
             @ Matrix.Rotation(f["theta"], 4, 'X') @ Matrix.Rotation(f["roll"], 4, 'Y')
             @ Matrix.Translation((0, 0, -f["C"])))
        M = W @ squash_about(f["squash"], f["anchor"])
        low = min((M @ q).z for q in floor_probe)
        if f["contact"] or low < 0:                 # touching the floor exactly, never through it
            M = Matrix.Translation((0, 0, -low)) @ M
        keyframe(rig.pose.bones["body"], M, fr)
        body_M.append(key_upper(M, f, fr))
        for name, sd in LEGS:
            ML = M @ Matrix.Translation((0, 0, f["tuck"]))
            if f["hold_w"] > 0:                     # the feet get dragged back with the pin, then come free
                sole = ML @ Vector((sd * LEG_X, LEG_Y, 0))
                if name not in hold:
                    hold[name] = sole.copy()
                ML = Matrix.Translation((hold[name] - sole) * f["hold_w"]) @ ML
            keyframe(rig.pose.bones[name], ML, fr)

    # The eyes. They ride the body until the head splat, then pop out, bounce and roll to a stop. A while
    # after he's back on his feet, each one rolls back (approaching from in front so it doesn't pass through
    # his base), pushes in through the front of his base, floats up through the jelly turning to face
    # forward, and pops out into its socket. Keys are world loc/rot/scale every frame.
    fps = scene.render.fps
    G = 9.81
    R_EYE = 0.044                               # rolling radius

    def ease(x):
        x = min(max(x, 0.0), 1.0)
        return x * x * (3 - 2 * x)

    def ease_out_back(x):
        c1 = 1.70158
        return 1 + (c1 + 1) * (x - 1) ** 3 + c1 * (x - 1) ** 2

    def bezier(p0, p1, p2, s):
        return p0 * (1 - s) ** 2 + p1 * 2 * s * (1 - s) + p2 * s * s

    def rot_of(M):
        return M.to_3x3().normalized().to_quaternion()

    def roll(q, disp):
        """Turn q as if rolling along the floor by disp (no slipping)."""
        if disp.length < 1e-9:
            return q
        axis = Vector((0, 0, 1)).cross(Vector((disp.x, disp.y, 0)))
        return Quaternion(axis.normalized(), disp.length / R_EYE) @ q

    nF = len(PLAN["frames"])
    for k, (eye, tm) in enumerate(zip(EYES, PLAN["eyes"])):
        side = -1 if k == 0 else 1
        rest = eye.matrix_world.copy()
        e_loc, _, e_scale = rest.decompose()
        eye.parent = None
        eye.matrix_basis = rest
        eye.rotation_mode = 'QUATERNION'
        i_eject, i_ret, i_abs, i_flt, i_pop, i_done = (int(round(tm[n] * fps)) for n in
                                                      ("t_eject", "t_return", "t_absorb", "t_float", "t_pop", "t_done"))
        out_dir = Vector((e_loc.x * 0.6, -1.0, 0.15)).normalized()
        L_sock = e_loc - out_dir * 0.06             # just behind the socket, inside him

        # free flight + rolling, simulated from the splat until it's called back
        M0 = body_M[i_eject] @ rest
        p, q, _ = M0.decompose()
        centre = body_M[i_eject] @ Vector((0, 0, height / 2))
        away = Vector((p.x - centre.x, p.y - centre.y, 0))
        away = away.normalized() if away.length > 1e-6 else Vector((0, -1, 0))
        d = (away * 0.35 + Vector((0.3 + 0.35 * side, -1.3, 0))).normalized()   # mostly toward the camera
        v = d * (0.6 + 0.1 * k)
        v.z = 0.7
        spin = Vector((0.3 * side, 1.0, 0.25)).normalized() * 10.0
        free = {}
        sub = 10
        dt = 1.0 / (fps * sub)
        for i in range(i_eject, i_ret + 1):
            free[i] = (p.copy(), q.copy())
            for _ in range(sub):
                v.z -= G * dt
                p += v * dt
                grounded = False
                if p.z <= R_EYE:
                    p.z = R_EYE
                    v.z = -v.z * 0.45 if v.z < -0.25 else 0.0
                    grounded = v.z == 0.0
                if grounded:                        # rolling, slowing to a stop
                    damp = math.exp(-dt / 0.6)
                    v.x *= damp
                    v.y *= damp
                    q = roll(q, Vector((v.x, v.y, 0)) * dt)
                else:
                    q = Quaternion(spin.normalized(), spin.length * dt) @ q
        p_rest, q = free[i_ret]
        # It goes back in through the leg nearest to where it stopped, from that side (body rest coordinates).
        # If both eyes pick the same leg, the second comes in a little round from the first.
        pl = body_M[i_abs].inverted() @ p_rest
        leg_d = [abs(pl.x - sd * LEG_X) + abs(pl.y - LEG_Y) for sd in (-1, 1)]
        leg_i = 0 if leg_d[0] < leg_d[1] else 1
        axis = Vector(((-1, 1)[leg_i] * LEG_X, LEG_Y, 0.0))
        out_l = Vector((pl.x - axis.x, pl.y - axis.y, 0.0))
        out_l = out_l.normalized() if out_l.length > 1e-6 else Vector((0, -1, 0))
        if k == 1 and leg_i == first_leg:
            turn = 0.7 if out_l.cross(first_out).z < 0 else -0.7
            out_l = Matrix.Rotation(turn, 3, 'Z') @ out_l
        if k == 0:
            first_leg, first_out = leg_i, out_l.copy()
        o_ = axis + out_l * 0.6 + Vector((0, 0, R_EYE))
        hit, _, _, _ = bvh.ray_cast(o_, -out_l)
        hit = hit if hit is not None else axis + out_l * 0.13 + Vector((0, 0, R_EYE))
        L_touch = hit + out_l * R_EYE * 0.6
        L_touch.z = R_EYE
        L_in = axis + Vector((0, 0, 0.08))

        prev = None
        for i in range(nF):
            M = body_M[i]
            scale = e_scale
            if i < i_eject or i >= i_done:          # in his head
                loc, rq, scale = (M @ rest).decompose()
                scale = scale.copy()
                scale.z *= walk.blink(i / fps)          # blinks: the eye (and its pupil) squash flat
            elif i <= i_ret:
                loc, rq = free[i]
            elif i < i_abs:                         # rolling back to him
                T = M @ L_touch
                T.z = R_EYE
                out_w = rot_of(M) @ out_l              # approach from that side of the leg
                out_w.z = 0
                P1 = T + out_w.normalized() * 0.3
                P1.z = R_EYE
                s0 = ease((i - 1 - i_ret) / (i_abs - i_ret))
                s1 = ease((i - i_ret) / (i_abs - i_ret))
                a, b = bezier(p_rest, P1, T, s0), bezier(p_rest, P1, T, s1)
                q = roll(q, b - a)
                loc, rq = b, q
                if i == i_abs - 1:
                    q_local0 = rot_of(M).inverted() @ q
            else:                                   # in through the skin, up through the jelly, out
                if i < i_flt:
                    L = L_touch.lerp(L_in, ease((i - i_abs) / max(i_flt - i_abs, 1)))
                    ql = q_local0
                elif i < i_pop:
                    u = (i - i_flt) / max(i_pop - i_flt, 1)
                    ctrl = Vector((L_in.x, (L_in.y + L_sock.y) / 2 + 0.03, (L_in.z + L_sock.z) / 2))
                    L = bezier(L_in, ctrl, L_sock, ease(u))
                    L.x += 0.012 * math.sin(2 * math.pi * 1.5 * u) * (1 - u)   # a little wobble on the way up
                    ql = q_local0.slerp(Quaternion(), ease(u))
                else:
                    u = (i - i_pop) / max(i_done - i_pop, 1)
                    L = L_sock.lerp(e_loc, ease_out_back(u))
                    ql = Quaternion()
                    scale = e_scale * (1 + 0.18 * math.sin(math.pi * u))     # pops out with a bulge
                loc, rq = M @ L, rot_of(M) @ ql
            if prev is not None and prev.dot(rq) < 0:
                rq = -rq
            prev = rq.copy()
            eye.matrix_basis = Matrix.LocRotScale(loc, rq, scale)
            for path in ("location", "rotation_quaternion", "scale"):
                eye.keyframe_insert(path, frame=F0 + i)

    # the rolling pin: maple, one lathe along its axis (handles, collars, barrel with eased edges). It lies
    # across his path; it rolls (angle = distance / radius) as the planner moves it.
    R_, L_, hr, hl = walk.PIN_R, walk.PIN_LEN, walk.HANDLE_R, walk.HANDLE_LEN
    e_ = 0.012
    prof = [(0.0, -L_ / 2 - hl - hr * 0.3), (hr * 0.9, -L_ / 2 - hl - hr * 0.15), (hr * 1.08, -L_ / 2 - hl + 0.04),
            (hr, -L_ / 2 - hl * 0.5), (hr * 0.82, -L_ / 2 - 0.04), (hr * 0.9, -L_ / 2 - 0.012), (R_ - e_, -L_ / 2),
            (R_, -L_ / 2 + e_)]
    prof += [(r_, -z_) for r_, z_ in reversed(prof)]
    M_PIN = kitchen.mat_wood(material, "PinMaple", (0.72, 0.52, 0.32), (0.60, 0.40, 0.22), scale=2.5,
                             rough=0.5, coat=0.0, grain=(1.0, 0.1, 1.0))
    pin_obj = kitchen._lathe("RollingPin", prof, M_PIN, segs=64, axis='Y')
    link(pin_obj)
    pin_obj.rotation_mode = 'XYZ'
    for i, (px, py, ang) in enumerate(PLAN["pin"]):
        pin_obj.location = (px, py, R_)
        pin_obj.rotation_euler = (0, ang, PLAN["pin_h"])
        pin_obj.keyframe_insert("location", frame=F0 + i)
        pin_obj.keyframe_insert("rotation_euler", frame=F0 + i)


# --------------------------------------------------------------------------- scale him onto the counter
char = link(bpy.data.objects.new("Character", None))
char.location = (*ROOT_XY, 0.0)
char.scale = (SCALE, SCALE, SCALE)
for o in list(scene.objects):
    if o.parent is None and o is not char:
        o.parent = char                         # identity parent inverse: his values stay in design units


def to_world(p):
    return char.matrix_world @ Vector(p)


bpy.context.view_layer.update()
_course = []
if ANIM == "walk":
    _course = [to_world((f["x"], f["y"], 0)) for f in PLAN["frames"]] + [to_world((q[0], q[1], 0)) for q in PLAN["pin"]]
else:
    _course = [to_world((0, 0, 0))]
REACH = 0.32 * SCALE + 0.02                     # his half-width plus a little room


def keep_clear(x, y, r):
    return all((c.x - x) ** 2 + (c.y - y) ** 2 > (r + REACH) ** 2 for c in _course[::3])


kitchen.build(link, material, mat_simple, keep_clear)


# --------------------------------------------------------------------------- lights (real meters)
def area(name, loc, target, power, size, color=(1, 1, 1), spread=180, size_y=None):
    ld = bpy.data.lights.new(name, 'AREA')
    ld.energy = power
    if size_y:
        ld.shape = 'RECTANGLE'
        ld.size, ld.size_y = size, size_y
    else:
        ld.size = size
    ld.spread = math.radians(spread)
    ld.color = color
    o = link(bpy.data.objects.new(name, ld))
    o.location = loc
    o.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    o.visible_camera = False      # the back of a big area light shows up as a dark panel
    return o


LK = float(os.environ.get("LIGHT", "0.3"))
mid = Vector((0.15 if ANIM == "walk" else 0.0, 0.0, 0.05))
# daylight from a window on the left wall, a little in front of the counter
area("Window", (kitchen.X0 + 0.05, -0.55, 0.55), mid, 260 * LK, 1.1, (0.88, 0.93, 1.0), size_y=0.9)
# soft ceiling light over the room, behind the camera
area("Ceiling", (0.3, -1.4, 1.5), mid, 110 * LK, 1.2, (1.0, 0.92, 0.80))
# Under-cabinet puck lights: small warm spots under the uppers, behind him. They throw short crisp shadows
# toward the camera, where the light that comes through him shows up green on the marble.
PUCK_W = float(os.environ.get("PUCK_W", "60"))
for i, x in enumerate((-0.75, -0.15, 0.45, 1.05, 1.65)):
    sd = bpy.data.lights.new("Puck", 'SPOT')
    sd.energy = PUCK_W * LK
    sd.shadow_soft_size = 0.012
    sd.spot_size = math.radians(120)
    sd.spot_blend = 0.6
    sd.color = (1.0, 0.86, 0.68)
    pk = link(bpy.data.objects.new("Puck", sd))
    pk.location = (x, kitchen.BACK - 0.08, kitchen.TILE_TOP - 0.005)
    pk.rotation_euler = (math.radians(-12), 0, 0)  # aimed down, tipped a little toward the front
    pk.visible_camera = False

# Late-afternoon sun through the window in the left wall: low and raking along the counter, so he throws a
# long shadow across the marble, and the light that comes through him paints it green.
SUN_W = float(os.environ.get("SUN_W", "18"))
SUN_EL = math.radians(float(os.environ.get("SUN_EL", "21")))
SUN_AZ = math.radians(float(os.environ.get("SUN_AZ", "6")))     # + swings the beam toward the backsplash
sun_d = bpy.data.lights.new("Sun", 'SUN')
sun_d.energy = SUN_W
sun_d.angle = math.radians(1.2)
sun_d.color = (1.0, 0.86, 0.66)
sun = link(bpy.data.objects.new("Sun", sun_d))
beam = Vector((math.cos(SUN_EL) * math.cos(SUN_AZ), math.cos(SUN_EL) * math.sin(SUN_AZ), -math.sin(SUN_EL)))
sun.rotation_euler = beam.to_track_quat('-Z', 'Y').to_euler()

world = bpy.data.worlds.new("World")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.55, 0.52, 0.48, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.15


# --------------------------------------------------------------------------- camera (design units, under Character)
aim = bpy.data.objects.new("CamAim", None)
aim.location = (0, 0, height * 0.48)
cam_data = bpy.data.cameras.new("Camera")
cam_data.lens = 85
cam_data.dof.use_dof = True
cam_data.dof.focus_object = aim
cam_data.dof.aperture_fstop = float(os.environ.get("FSTOP", "8.0"))
cam = bpy.data.objects.new("Camera", cam_data)
cam.location = (0.85, -2.9, 0.42)
for o in (aim, cam):
    link(o)
    o.parent = char
tt = cam.constraints.new('TRACK_TO')
tt.target = aim
tt.track_axis = 'TRACK_NEGATIVE_Z'
tt.up_axis = 'UP_Y'
scene.camera = cam
if ANIM == "walk":
    # The aim follows him with operator-style lag; the camera trucks sideways after it, lagging more.
    # After he lands, the camera keeps going along its track, straight past him, so it ends up ahead of him
    # looking back at his face (3/4 front); the aim moves up to his face. (Interpolating an orbit angle here
    # spun the camera a full 360: his heading has accumulated 2*pi from the walk circle.)
    cam_data.lens = 55
    fps = scene.render.fps
    CAM_AHEAD = float(os.environ.get("CAM_AHEAD", "2.6"))   # design m ahead of him / out to the side, run-up to fall
    CAM_SIDE = float(os.environ.get("CAM_SIDE", "2.5"))

    def smooth_(e0, e1, x):
        x = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
        return x * x * (3 - 2 * x)
    t_orbit = PLAN["t_feet"] + walk.CAM_DELAY
    end = PLAN["frames"][-1]
    hub = Vector((end["x"], end["y"], 0.0))
    face = hub + Vector((0, 0, 0.36))
    heading = end["yaw"] - math.pi / 2
    ahead = Vector((math.cos(heading), math.sin(heading), 0))
    # For the run-up, the pin ride and the fall, the camera swings round to a 3/4 front view ahead of him
    # along the run line, so his arms (which swing about his left-right axis) read.
    h_run = PLAN["pin_h"]
    u_run = Vector((math.cos(h_run), math.sin(h_run), 0))
    perp = Vector((math.sin(h_run), -math.cos(h_run), 0))          # the camera's side of the run line
    t_front = PLAN["t_takeoff"]
    a = c = None
    orbit0 = None
    for i, f in enumerate(PLAN["frames"]):
        t = i / fps
        want = Vector((f["x"], f["y"], 0.27 + 0.6 * f["z"]))
        a = want if a is None else a + (want - a) * 0.2
        cwant = Vector((0.2 + 0.85 * a.x, -3.4, 0.5))
        w = smooth_(t_front - 2.4, t_front - 0.9, t)
        if w > 0:
            front = Vector((a.x, a.y, 0)) + u_run * CAM_AHEAD + perp * CAM_SIDE
            front.z = 0.6                                            # a bit higher, to see his shadow on the counter
            cwant = cwant.lerp(front, w)
        c = cwant if c is None else c + (cwant - c) * 0.08
        aim_loc, cam_loc = a, c
        # Opening: hold close on him while he stands, pushing in slowly, so the drifting sparkles read. As he
        # starts walking, ease back out to the tracking camera.
        w_open = 1 - smooth_(walk.STAND_BEFORE - 0.2, walk.STAND_BEFORE + 1.6, t)
        if w_open > 0:
            f0 = PLAN["frames"][0]
            hub0 = Vector((f0["x"], f0["y"], 0.0))
            close = hub0 + Vector((0.45, -1.0, 0.0)) * (2.0 - 0.35 * smooth_(0.0, walk.STAND_BEFORE, t))
            close.z = 0.34
            cam_loc = c.lerp(close, w_open)
            aim_loc = a.lerp(hub0 + Vector((0, 0, 0.29)), w_open)
        if t >= t_orbit:
            if orbit0 is None:
                c_end = hub + ahead * 2.2 + (c - hub - ahead * (c - hub).dot(ahead)) * 0.8
                c_end.z = 0.42
                orbit0 = (c.copy(), c_end, a.copy())
            c0, c_end, a0 = orbit0
            u = min((t - t_orbit) / walk.CAM_MOVE, 1.0)
            e = u * u * (3 - 2 * u)
            cam_loc = c0.lerp(c_end, e)
            aim_loc = a0.lerp(face, e)
        aim.location, cam.location = aim_loc, cam_loc
        aim.keyframe_insert("location", frame=F0 + i)
        cam.keyframe_insert("location", frame=F0 + i)

    # Face: he frowns when he realises his eyes are gone, and grins when they're back.
    kb = mouth.data.shape_keys.key_blocks["Frown"]
    for t, val in ((PLAN["t_frown"], 0.0), (PLAN["t_frown"] + 0.25, 1.0), (PLAN["t_smile"], 1.0),
                   (PLAN["t_smile"] + 0.15, -0.5), (PLAN["t_smile"] + 0.7, 0.0)):
        kb.value = val
        kb.keyframe_insert("value", frame=F0 + int(round(t * fps)))


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
vs_.exposure = float(os.environ.get("EXPOSURE", "-1.6"))

OUT = os.path.join(ROOT, "blob_walk.blend" if ANIM == "walk" else "blob.blend")
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED", OUT)
