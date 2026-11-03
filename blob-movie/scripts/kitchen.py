"""Kitchen counter set for the blob: marble countertop, subway-tile backsplash, white cabinets and
everyday countertop clutter. Real meters, with the countertop surface at z = 0. Imported by build_scene.py.

build(link, material, mat_simple, keep_clear) builds everything. keep_clear(x, y, r) -> bool says whether
a prop of radius r at (x, y) stays out of the character's path; props that fail it are skipped.
"""
import math
import random

import bpy
import bmesh
from mathutils import Vector, Matrix

# counter footprint (m). Camera looks toward +Y at the backsplash.
X0, X1 = -1.6, 2.2
FRONT, BACK = -0.40, 0.27
SLAB = 0.03
TILE_TOP = 0.46            # backsplash height; upper cabinets start here
UPPER_D = 0.33
WIN_Y = (-0.95, -0.12)     # window in the left wall, in front of the upper cabinets
WIN_Z = (0.25, 1.15)


def _box(name, lo, hi, mat, bevel=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector(((lo[i] + hi[i]) / 2 + v.co[i] * (hi[i] - lo[i]) for i in range(3)))
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    o = bpy.data.objects.new(name, me)
    if bevel:
        b = o.modifiers.new("bevel", 'BEVEL')
        b.width = bevel
        b.segments = 3
        b.limit_method = 'ANGLE'
        for p in me.polygons:
            p.use_smooth = True
        o.modifiers.new("wn", 'WEIGHTED_NORMAL')
    return o


def _lathe(name, profile, mat, segs=48, axis='Z', cap=True):
    """Surface of revolution from (r, h) points, bottom to top. Axis Z (or Y). Ends capped with fans."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    rings = []
    for r, hgt in profile:
        ring = []
        for i in range(segs):
            a = 2 * math.pi * i / segs
            if axis == 'Z':
                co = (r * math.cos(a), r * math.sin(a), hgt)
            else:
                co = (r * math.cos(a), hgt, r * math.sin(a))
            ring.append(bm.verts.new(co))
        rings.append(ring)
    for ra, rb in zip(rings, rings[1:]):
        for i in range(segs):
            j = (i + 1) % segs
            f = bm.faces.new((ra[i], ra[j], rb[j], rb[i]))
    if cap:
        for ring, h_ in ((rings[0], profile[0][1]), (rings[-1], profile[-1][1])):
            if profile[0][0] > 1e-6 or h_ != profile[0][1]:
                try:
                    bm.faces.new(ring)
                except ValueError:
                    pass
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    for p in me.polygons:
        p.use_smooth = True
    me.materials.append(mat)
    return bpy.data.objects.new(name, me)


def mat_wood(material, name, c1, c2, scale=12.0, rough=0.45, coat=0.2, grain=(1.0, 1.0, 0.08)):
    """Procedural wood: stretched rings, the long grain along the axis whose grain scale is small."""
    m, n, out = material(name)
    tc = n("ShaderNodeTexCoord")
    mp = n("ShaderNodeMapping")
    n.link(tc.outputs["Object"], mp.inputs["Vector"])
    mp.inputs["Scale"].default_value = grain
    w = n("ShaderNodeTexWave", wave_type='RINGS', Scale=scale, Distortion=4.0, Detail=3.0)
    n.link(mp.outputs[0], w.inputs["Vector"])
    col = n("ShaderNodeMix", data_type='RGBA', Factor=w.outputs["Factor"], A=(*c1, 1), B=(*c2, 1))
    b = n("ShaderNodeBsdfPrincipled", **{"Roughness": rough, "Coat Weight": coat})
    n.link(col.outputs[2], b.inputs["Base Color"])
    n.link(b.outputs[0], out.inputs["Surface"])
    return m


def build(link, material, mat_simple, keep_clear):
    random.seed(23)

    # ------------------------------------------------------------------ materials
    def mat_marble():
        m, n, out = material("Marble")
        tc = n("ShaderNodeTexCoord")
        warp = n("ShaderNodeTexNoise", Scale=1.6, Detail=6.0, Roughness=0.6)
        n.link(tc.outputs["Object"], warp.inputs["Vector"])
        co = n("ShaderNodeVectorMath", operation='MULTIPLY_ADD')
        n.link(warp.outputs["Color"], co.inputs[0])
        co.inputs[1].default_value = (0.35, 0.35, 0.35)
        n.link(tc.outputs["Object"], co.inputs[2])
        veins = []
        for scale, dist, rot in ((1.4, 6.0, 0.6), (4.5, 9.0, -0.9)):
            mp = n("ShaderNodeMapping")
            n.link(co.outputs[0], mp.inputs["Vector"])
            mp.inputs["Rotation"].default_value = (0, 0, rot)
            w = n("ShaderNodeTexWave", wave_type='BANDS', wave_profile='SIN', Scale=scale, Distortion=dist,
                  Detail=8.0, **{"Detail Scale": 1.5, "Detail Roughness": 0.6})
            n.link(mp.outputs[0], w.inputs["Vector"])
            # a vein where the band crosses 0.5: 1 - |2f - 1| sharpened
            d = n.math('ABSOLUTE', n.math('MULTIPLY_ADD', w.outputs["Factor"], 2.0, -1.0))
            veins.append(n.math('POWER', n.math('SUBTRACT', 1.0, d), 14.0))
        v = n.math('MAXIMUM', veins[0], n.math('MULTIPLY', veins[1], 0.45))
        cloud = n("ShaderNodeTexNoise", Scale=6.0, Detail=4.0)
        n.link(tc.outputs["Object"], cloud.inputs["Vector"])
        base = n("ShaderNodeMix", data_type='RGBA', Factor=cloud.outputs["Factor"],
                 A=(0.86, 0.86, 0.84, 1), B=(0.93, 0.93, 0.91, 1))
        col = n("ShaderNodeMix", data_type='RGBA', Factor=v, B=(0.42, 0.43, 0.46, 1))
        n.link(base.outputs[2], next(i for i in col.inputs if i.name == "A" and i.enabled))
        b = n("ShaderNodeBsdfPrincipled", **{"Roughness": 0.14, "Coat Weight": 0.4, "Coat Roughness": 0.05,
                                             "Subsurface Weight": 0.1, "Subsurface Scale": 0.004})
        n.link(col.outputs[2], b.inputs["Base Color"])
        n.link(b.outputs[0], out.inputs["Surface"])
        return m

    def mat_tile():
        m, n, out = material("SubwayTile")
        tc = n("ShaderNodeTexCoord")
        sep = n("ShaderNodeSeparateXYZ")
        n.link(tc.outputs["Object"], sep.inputs[0])
        uv = n("ShaderNodeCombineXYZ", X=sep.outputs["X"], Y=sep.outputs["Z"])
        br = n("ShaderNodeTexBrick", offset=0.5, squash=1.0,
               Color1=(0.88, 0.89, 0.87, 1), Color2=(0.82, 0.84, 0.82, 1), Mortar=(0.50, 0.49, 0.46, 1),
               Scale=1.0, **{"Mortar Size": 0.0025, "Mortar Smooth": 0.6, "Bias": 0.0,
                             "Brick Width": 0.15, "Row Height": 0.075})
        n.link(uv.outputs[0], br.inputs["Vector"])
        fac = br.outputs[1]
        rough = n.math('MULTIPLY_ADD', fac, 0.6, 0.06)
        bump = n("ShaderNodeBump", Strength=0.6, Distance=0.002)
        n.link(n.math('SUBTRACT', 1.0, fac), bump.inputs["Height"])
        b = n("ShaderNodeBsdfPrincipled", **{"Coat Weight": n.math('SUBTRACT', 1.0, fac), "Coat Roughness": 0.03})
        n.link(br.outputs["Color"], b.inputs["Base Color"])
        n.link(rough, b.inputs["Roughness"])
        n.link(bump.outputs[0], b.inputs["Normal"])
        n.link(b.outputs[0], out.inputs["Surface"])
        return m

    M_MARBLE = mat_marble()
    M_TILE = mat_tile()
    M_PAINT = mat_simple("WallPaint", (0.80, 0.78, 0.72), rough=0.8)
    M_CAB = mat_simple("Cabinet", (0.82, 0.83, 0.80), rough=0.35, coat=0.2)
    M_STEEL = mat_simple("Steel", (0.75, 0.75, 0.76), rough=0.25)
    M_STEEL.node_tree.nodes["Principled BSDF"].inputs["Metallic"].default_value = 1.0
    M_WOOD = mat_wood(material, "Maple", (0.62, 0.42, 0.24), (0.50, 0.32, 0.17))
    M_DARKWOOD = mat_wood(material, "Walnut", (0.20, 0.11, 0.06), (0.13, 0.07, 0.04), rough=0.4)
    M_CERAMIC = mat_simple("Ceramic", (0.86, 0.83, 0.76), rough=0.15, coat=0.6)
    M_MUG = mat_simple("MugGlaze", (0.10, 0.20, 0.38), rough=0.12, coat=0.8)
    M_BLACK = mat_simple("BlackPoly", (0.02, 0.02, 0.02), rough=0.35)
    M_PAPER = mat_simple("Paper", (0.88, 0.88, 0.86), rough=0.9)
    M_CORK = mat_simple("Cork", (0.55, 0.40, 0.25), rough=0.8)
    M_TERRACOTTA = mat_simple("Terracotta", (0.55, 0.22, 0.12), rough=0.75)
    M_SOIL = mat_simple("Soil", (0.06, 0.04, 0.03), rough=0.95)
    M_LEAF = mat_simple("Basil", (0.08, 0.30, 0.05), rough=0.45)
    M_LEMON = mat_simple("Lemon", (0.85, 0.62, 0.05), rough=0.35, coat=0.3)
    m, n, out = material("BottleGlass")
    b = n("ShaderNodeBsdfPrincipled", **{"Base Color": (0.25, 0.45, 0.12, 1), "Transmission Weight": 1.0,
                                         "Roughness": 0.03, "IOR": 1.5})
    n.link(b.outputs[0], out.inputs["Surface"])
    vol = n("ShaderNodeVolumeAbsorption", Color=(0.35, 0.40, 0.05, 1), Density=60.0)
    n.link(vol.outputs[0], out.inputs["Volume"])
    M_BOTTLE = m

    # ------------------------------------------------------------------ architecture
    slab = link(_box("Countertop", (X0, FRONT, -SLAB), (X1, BACK, 0.0), M_MARBLE, bevel=0.003))
    link(_box("BaseCabinets", (X0, FRONT + 0.03, -0.90), (X1, BACK, -SLAB), M_CAB))
    link(_box("ToeKick", (X0, FRONT + 0.03, -0.92), (X1, BACK, -0.90), M_BLACK))
    # door seams on the base cabinets
    for x in [X0 + 0.45 * i for i in range(1, 9)]:
        link(_box("DoorGap", (x - 0.002, FRONT + 0.028, -0.88), (x + 0.002, FRONT + 0.031, -0.05), M_BLACK))
    tile = link(_box("Backsplash", (X0, BACK, 0.0), (X1, BACK + 0.01, TILE_TOP), M_TILE))
    tile.location.y -= 0.0
    link(_box("Wall", (X0 - 1, BACK + 0.01, -1.0), (X1 + 1, BACK + 0.02, 2.6), M_PAINT))
    link(_box("UpperCabinets", (X0, BACK - UPPER_D, TILE_TOP), (X1, BACK, 1.20), M_CAB, bevel=0.004))
    link(_box("Floor", (-6, -6, -0.93), (6, 6, -0.92), mat_simple("FloorBoards", (0.35, 0.24, 0.15), 0.6)))
    # left wall with a window (WIN_Y x WIN_Z) that lets a low sunbeam rake across the counter
    wy0, wy1 = WIN_Y
    wz0, wz1 = WIN_Z
    for lo, hi in (((-4.0, -1.0), (wy0, 2.6)), ((wy1, -1.0), (BACK + 0.02, 2.6)),
                   ((wy0, -1.0), (wy1, wz0)), ((wy0, wz1), (wy1, 2.6))):
        link(_box("SideWall", (X0 - 0.02, lo[0], lo[1]), (X0, hi[0], hi[1]), M_PAINT))
    M_FRAME = mat_simple("WindowFrame", (0.9, 0.9, 0.88), rough=0.4)
    link(_box("Sill", (X0 - 0.02, wy0 - 0.03, wz0 - 0.02), (X0 + 0.05, wy1 + 0.03, wz0), M_FRAME))
    link(_box("Mullion", (X0 - 0.02, (wy0 + wy1) / 2 - 0.012, wz0), (X0, (wy0 + wy1) / 2 + 0.012, wz1), M_FRAME))

    # ------------------------------------------------------------------ props
    def place(o, x, y, r, rot=0.0):
        if not keep_clear(x, y, r):
            bpy.data.objects.remove(o)
            return None
        o.location.x += x
        o.location.y += y
        o.rotation_euler.z = rot
        link(o)
        return o

    # canister set: ceramic cylinders with walnut lids
    for x, r, hgt in ((-0.95, 0.065, 0.22), (-0.80, 0.056, 0.18), (-0.675, 0.047, 0.14)):
        y = BACK - 0.012 - r
        c = _lathe("Canister", [(0.0, 0.0), (r - 0.004, 0.0), (r, 0.004), (r, hgt - 0.004), (r - 0.003, hgt),
                                (r - 0.006, hgt)], M_CERAMIC)
        place(c, x, y, r)
        lid = _lathe("CanisterLid", [(0.0, hgt), (r + 0.002, hgt), (r + 0.002, hgt + 0.018),
                                     (r * 0.4, hgt + 0.02), (r * 0.25, hgt + 0.04), (0.0, hgt + 0.042)], M_DARKWOOD)
        place(lid, x, y, r)

    # paper towel holder
    o = _lathe("TowelRoll", [(0.0, 0.012), (0.06, 0.012), (0.061, 0.016), (0.061, 0.27), (0.06, 0.275),
                             (0.022, 0.275), (0.0, 0.275)], M_PAPER)
    place(o, -1.25, BACK - 0.09, 0.07)
    o = _lathe("TowelBase", [(0.0, 0.0), (0.075, 0.0), (0.075, 0.012), (0.0, 0.012)], M_STEEL)
    place(o, -1.25, BACK - 0.09, 0.08)
    o = _lathe("TowelPost", [(0.0, 0.0), (0.006, 0.0), (0.006, 0.31), (0.012, 0.31), (0.012, 0.32), (0.0, 0.32)],
               M_STEEL, segs=16)
    place(o, -1.25, BACK - 0.09, 0.02)

    # mug
    o = _lathe("Mug", [(0.0, 0.0), (0.038, 0.0), (0.041, 0.006), (0.041, 0.095), (0.037, 0.095),
                       (0.037, 0.010), (0.0, 0.010)], M_MUG)
    mug = place(o, 0.30, BACK - 0.07, 0.06, rot=-0.5)
    if mug:
        bpy.ops.mesh.primitive_torus_add(major_radius=0.026, minor_radius=0.0065, location=(0, 0, 0))
        hnd = bpy.context.object
        hnd.name = "MugHandle"
        hnd.rotation_euler = (math.pi / 2, 0, 0)
        hnd.location = (0.045, 0, 0.05)
        hnd.data.materials.append(M_MUG)
        bpy.ops.object.shade_smooth()
        hnd.parent = mug

    # cutting board leaning on the backsplash, oil bottle and grinders in front of it
    board = _box("CuttingBoard", (-0.2, -0.009, 0.0), (0.2, 0.009, 0.30), M_WOOD, bevel=0.004)
    board.rotation_euler.x = -0.12
    place(board, 0.62, BACK - 0.045, 0.05)
    o = _lathe("OilBottle", [(0.0, 0.0), (0.03, 0.0), (0.032, 0.006), (0.032, 0.17), (0.028, 0.20),
                             (0.011, 0.235), (0.011, 0.26), (0.0, 0.26)], M_BOTTLE)
    place(o, 0.52, BACK - 0.11, 0.04)
    o = _lathe("BottleCap", [(0.0, 0.258), (0.0125, 0.258), (0.0125, 0.28), (0.0, 0.282)], M_BLACK, segs=24)
    place(o, 0.52, BACK - 0.11, 0.02)
    for dx, mat in ((0.64, M_DARKWOOD), (0.71, M_WOOD)):
        o = _lathe("Grinder", [(0.0, 0.0), (0.024, 0.0), (0.025, 0.02), (0.019, 0.05), (0.023, 0.10),
                               (0.022, 0.15), (0.012, 0.165), (0.006, 0.18), (0.0, 0.18)], mat, segs=32)
        place(o, dx, BACK - 0.13, 0.03)

    # potted basil
    px, py = 1.00, BACK - 0.085
    o = _lathe("Pot", [(0.0, 0.0), (0.045, 0.0), (0.06, 0.10), (0.066, 0.10), (0.066, 0.115), (0.056, 0.115),
                       (0.056, 0.10), (0.0, 0.10)], M_TERRACOTTA)
    if place(o, px, py, 0.07):
        o = _lathe("Soil", [(0.0, 0.098), (0.057, 0.098), (0.0, 0.099)], M_SOIL)
        place(o, px, py, 0.06)
        leaf_me = bpy.data.meshes.new("BasilLeaf")
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=1.0)
        for v in bm.verts:
            v.co = Vector((v.co.x * 0.014, v.co.y * 0.022 + 0.02, v.co.z * 0.002 + 0.006 * v.co.x ** 2 - 0.003 * (v.co.y + 1) ** 2))   # cupped, tip curling down
        bm.to_mesh(leaf_me)
        bm.free()
        for p in leaf_me.polygons:
            p.use_smooth = True
        leaf_me.materials.append(M_LEAF)
        for i in range(90):
            u = random.random()
            stem_h = 0.11 + 0.14 * u                        # taller leaves sit nearer the middle
            a = random.uniform(0, 2 * math.pi)
            rr = 0.012 + random.uniform(0.02, 0.07) * (1 - 0.6 * u)
            lf = bpy.data.objects.new("Leaf", leaf_me)
            lf.location = (px + rr * math.cos(a), py + rr * math.sin(a), stem_h)
            # the leaf runs along its local +Y: point it outward and let it droop a little
            lf.rotation_euler = (random.uniform(-0.7, 0.15), random.uniform(-0.3, 0.3), a - math.pi / 2)
            s_ = random.uniform(0.8, 1.35) * (1.15 - 0.3 * u)
            lf.scale = (s_, s_, s_)
            link(lf)

    # knife block with handles
    kb = _box("KnifeBlock", (-0.06, -0.05, 0.0), (0.06, 0.05, 0.22), M_DARKWOOD, bevel=0.005)
    kb.rotation_euler.x = 0.25
    if place(kb, 1.30, BACK - 0.08, 0.09, rot=0.2):
        for i, (dx, dz) in enumerate(((-0.03, 0.0), (0.0, 0.01), (0.03, -0.005), (-0.015, 0.03), (0.018, 0.035))):
            bpy.ops.mesh.primitive_cylinder_add(radius=0.011, depth=0.11, location=(dx, 0.0, 0.27 + dz))
            hd = bpy.context.object
            hd.name = "KnifeHandle"
            hd.scale = (1.0, 0.6, 1.0)
            hd.data.materials.append(M_BLACK)
            bpy.ops.object.shade_smooth()
            hd.parent = kb
            hd.location = (dx, -0.01 + 0.012 * (i % 2), 0.255 + dz)

    # fruit bowl with lemons, out front on the right
    bx, by = 1.55, -0.05
    o = _lathe("FruitBowl", [(0.0, 0.0), (0.06, 0.0), (0.07, 0.01), (0.13, 0.06), (0.135, 0.065),
                             (0.128, 0.065), (0.065, 0.017), (0.0, 0.015)], M_CERAMIC, segs=64)
    if place(o, bx, by, 0.14):
        lemon_me = bpy.data.meshes.new("Lemon")
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=16, radius=1.0)
        for v in bm.verts:
            tip = 1 + 0.18 * max(abs(v.co.x) - 0.85, 0) / 0.15
            v.co = Vector((v.co.x * 0.040 * tip, v.co.y * 0.029, v.co.z * 0.029))
        bm.to_mesh(lemon_me)
        bm.free()
        for p in lemon_me.polygons:
            p.use_smooth = True
        lemon_me.materials.append(M_LEMON)
        for (dx, dy, z, rz) in ((-0.04, 0.0, 0.045, 0.3), (0.04, 0.02, 0.045, 1.9), (0.0, -0.045, 0.045, -0.7),
                                (0.0, 0.0, 0.085, 1.1)):
            lm = bpy.data.objects.new("Lemon", lemon_me)
            lm.location = (bx + dx, by + dy, z)
            lm.rotation_euler = (random.uniform(-0.3, 0.3), random.uniform(-0.3, 0.3), rz)
            link(lm)
    return slab
