"""Build the green blob character in a simple studio set.

Run:  ./run.sh -b --factory-startup -P scripts/build_scene.py
Saves blob.blend in the project root. ANIM=walk builds the walk test instead (scripts/walk.py) and saves
blob_walk.blend: he walks a circle, runs, hops a hurdle and skids to a stop.

The body is a metaball field (body + stubby arms/feet melt into one surface), converted to a mesh.
It's a refractive shell around a green absorbing/scattering volume, with sparkles suspended inside.
Front of the character faces -Y. Units are meters; he's about 0.55 m tall.
"""
import bpy
import math
import os
import random
import sys
from mathutils import Vector, Quaternion, Matrix

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))
import walk  # noqa: E402

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
                                            "Roughness": float(os.environ.get("SKIN_ROUGH", "0.12")),
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
        tint = float(os.environ.get("SHADOW_TINT", "1.0"))
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
             Density=float(os.environ.get("SCATTER", "0.8")), Anisotropy=0.3)
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
for s in (-1, 1):
    ball('CAPSULE', (s * 0.22, -0.01, 0.23), 0.085, size=(0.045, 1, 1),
         rot=axis_rot((s, -0.15, -0.55)))
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


def flatten_soles(me):
    """Turn each leg's round bottom into a flat sole with a soft, filleted edge.

    Below the hemisphere centre, every vertex moves along its ray from that centre, from the sphere out
    onto a rounded-cylinder profile (flat bottom, quarter-circle fillet, vertical side). Straight-down and
    sideways rays keep their length, so the sole stays at the floor and the side joins smoothly."""
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
    # The measured "leg radius" spans the whole merged base (~0.26 m), which gives the chosen look, but the
    # second leg's pass pushes a few hundred already-moved vertices on his left below the floor. They sit
    # inside the footprint, so lifting them onto the sole plane just completes the flat sole. Unlifted, they
    # stayed hidden under the floor while standing, but floated him 7 cm up whenever he left the ground.
    for v in me.vertices:
        if v.co.z < 0:
            v.co.z = 0.0


flatten_soles(me)
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
FLAKE_SIZE = float(os.environ.get("FLAKE_SIZE", "0.004"))      # hex radius, m
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
    # Three bones, none parented: the body, and one per leg standing on its sole. The legs are free, so a
    # planted foot stays put while the body moves on, and the jelly between them stretches.
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
    bpy.ops.object.mode_set(mode='OBJECT')

    # Skin weights: the whole lower base belongs to the legs, fading into the body by LEG_TOP. It's split
    # left/right with a soft seam down the middle. (A radius around each leg axis left the base's outer
    # corners on the body, so they hung down like a fixed skirt while the feet stepped.)
    LEG_TOP = 0.11
    groups = {n: body.vertex_groups.new(name=n) for n in ("body", "leg.R", "leg.L")}
    for v in me.vertices:
        low = 1 - smoothstep(0.015, LEG_TOP, v.co.z)
        left = smoothstep(-0.035, 0.035, v.co.x)
        ws = {"leg.R": low * (1 - left), "leg.L": low * left}
        ws["body"] = max(0.0, 1.0 - sum(ws.values()))
        for name, w in ws.items():
            if w > 1e-4:
                groups[name].add([v.index], w, 'REPLACE')
    body.modifiers.remove(sm)                   # armature must deform before the smoothing pass
    am = body.modifiers.new("rig", 'ARMATURE')
    am.object = rig
    sm = body.modifiers.new("smooth", 'CORRECTIVE_SMOOTH')
    sm.iterations = 6
    sm.use_only_smooth = True

    # Eyes, mouth and flakes ride on the body bone.
    bb = arm.bones["body"]
    bone_rest = rig.matrix_world @ bb.matrix_local @ Matrix.Translation((0, bb.length, 0))
    for o in [o for o in scene.objects if o.name.startswith(("Eye", "Pupil", "Mouth"))] + [flake_obj]:
        o.parent, o.parent_type, o.parent_bone = rig, 'BONE', "body"
        o.matrix_parent_inverse = bone_rest.inverted()

    # Smoosh: a world-space squash measured from the floor, applied after the rig to the body and to
    # everything riding on it (eyes, mouth, flakes), so they all deform together. A slice at height z (u = z/H)
    # moves to H*(a*u + b*u^2), with a + b = HEAD_SQUASH. Its local vertical compression a + 2*b*u is strongest at
    # the floor, and it spreads out from the contact point by 1/sqrt(compression) to keep its volume. The floor
    # slice puddles out (~2.9x) and the far end stays domed (~1.35x). Controlled by the "Smoosh" empty:
    # location = contact point, scale.x - 1 = amount (0..1), scale.y = H.
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
    amount = g.math('SUBTRACT', k_.outputs["X"], 1.0)
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
    for o in [o for o in scene.objects if o.name.startswith(("Eye", "Pupil", "Mouth"))] + [flake_obj]:
        o.modifiers.new("smoosh", 'NODES').node_group = sg

    # Bake the plan into per-frame keys. Every bone gets an affine world transform M applied to its rest
    # geometry: matrix_basis = rest^-1 @ M @ rest. M is rigid times a volume-keeping squash along the body's
    # up axis about some anchor height. All three bones point up in rest, so this never needs shear.
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
    hold = None
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
        for name, sd in LEGS:
            ML = M @ Matrix.Translation((0, 0, f["tuck"]))
            if name == "leg.R" and f["hold_w"] > 0:  # the foot that clipped the bar lags behind
                sole = ML @ Vector((sd * LEG_X, LEG_Y, 0))
                if hold is None:
                    hold = sole.copy()
                ML = Matrix.Translation((hold - sole) * f["hold_w"]) @ ML
            keyframe(rig.pose.bones[name], ML, fr)

    # the hurdle: two white posts on little feet and a red bar, square across his path. It hangs from an
    # empty on the front edge of its feet, so when he clips it, it rocks forward and rattles back down.
    hx, hy, hh = PLAN["hurdle"]
    fwd = Vector((math.cos(hh), math.sin(hh), 0))
    across = Vector((-math.sin(hh), math.cos(hh), 0))
    rocker = link(bpy.data.objects.new("Hurdle", None))
    rocker.location = Vector((hx, hy, 0)) + fwd * 0.07
    rocker.rotation_euler = (0, 0, hh)
    M_HURDLE = mat_simple("HurdleWhite", (0.85, 0.85, 0.82), rough=0.35)
    M_BAR = mat_simple("HurdleRed", (0.75, 0.05, 0.04), rough=0.3, coat=0.5)
    parts = []
    for sd in (-1, 1):
        base = Vector((hx, hy, 0)) + across * sd * 0.32
        bpy.ops.mesh.primitive_cylinder_add(radius=0.01, depth=walk.HURDLE_H, location=base + Vector((0, 0, walk.HURDLE_H / 2)))
        bpy.context.object.data.materials.append(M_HURDLE)
        parts.append(bpy.context.object)
        bpy.ops.mesh.primitive_cube_add(size=1, location=base + Vector((0, 0, 0.006)), rotation=(0, 0, hh))
        bpy.context.object.scale = (0.14, 0.03, 0.012)
        bpy.context.object.data.materials.append(M_HURDLE)
        parts.append(bpy.context.object)
    bpy.ops.mesh.primitive_cylinder_add(radius=0.012, depth=0.66, location=(hx, hy, walk.HURDLE_H),
                                        rotation=(math.pi / 2, 0, hh))
    bpy.context.object.data.materials.append(M_BAR)
    bpy.ops.object.shade_smooth()
    parts.append(bpy.context.object)
    bpy.context.view_layer.update()
    for o in parts:
        o.parent = rocker
        o.matrix_parent_inverse = rocker.matrix_world.inverted()
    for i in range(len(PLAN["frames"])):
        tau = (F0 + i - 1) / scene.render.fps - PLAN["t_clip"]
        tip = 0.0 if tau < 0 else math.radians(22) * math.exp(-tau / 0.22) * abs(math.sin(2 * math.pi * 2.2 * tau))
        rocker.rotation_euler = (0, tip, hh)
        rocker.keyframe_insert("rotation_euler", frame=F0 + i)


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
    o.visible_camera = False      # the back of a big area light shows up as a dark panel
    return o


if ANIM == "walk":
    # same rig, pulled back 1.6x around the middle of the course with a wider key, to light the whole run
    LC, LS = Vector((0.4, 0.1, 0)), 1.6
else:
    LC, LS = Vector((0, 0, 0)), 1.0
center = LC + Vector((0, 0, height * 0.5))


def lamp(name, loc, power, size, color, spread=180):
    area(name, LC + Vector(loc) * LS, center, power * LS * LS, size * LS, color, spread)


lamp("Key", (-1.4, -1.6, 1.7), 70 * (2.2 if ANIM == "walk" else 1), 1.2, (1.0, 0.95, 0.88),
     spread=80 if ANIM == "walk" else 50)
lamp("Fill", (1.8, -1.2, 0.6), 50, 2.0, (0.85, 0.92, 1.0))
lamp("Rim", (0.9, 1.3, 1.3), 260, 0.8, (1.0, 0.98, 0.92))   # back light makes him glow
lamp("RimL", (-1.0, 1.2, 0.5), 120, 0.6, (0.9, 1.0, 0.95))

# Hard back light, high behind him: throws a crisp shadow toward the camera, where the light that
# comes through him shows up green on the floor.
BACK_W = float(os.environ.get("BACK_W", "1500"))
sd = bpy.data.lights.new("Back", 'SPOT')
sd.energy = BACK_W * LS * LS
sd.shadow_soft_size = 0.04
sd.spot_size = math.radians(70 if ANIM == "walk" else 40)
sd.spot_blend = 0.4
sd.color = (1.0, 0.97, 0.9)
back = link(bpy.data.objects.new("Back", sd))
back.location = LC + Vector((0.35, 1.4, 1.5)) * LS
back.rotation_euler = (center - back.location).to_track_quat('-Z', 'Y').to_euler()
back.visible_camera = False

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
if ANIM == "walk":
    # the aim follows him with operator-style lag; the camera trucks sideways after it, lagging more
    cam_data.lens = 55
    cam_data.dof.aperture_fstop = 5.6
    a = c = None
    for i, f in enumerate(PLAN["frames"]):
        want = Vector((f["x"], f["y"], 0.27 + 0.6 * f["z"]))
        a = want if a is None else a + (want - a) * 0.2
        cwant = Vector((0.2 + 0.85 * a.x, -3.4, 0.5))
        c = cwant if c is None else c + (cwant - c) * 0.08
        aim.location, cam.location = a, c
        aim.keyframe_insert("location", frame=F0 + i)
        cam.keyframe_insert("location", frame=F0 + i)


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

OUT = os.path.join(ROOT, "blob_walk.blend" if ANIM == "walk" else "blob.blend")
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print("SAVED", OUT)
