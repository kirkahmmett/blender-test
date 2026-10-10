"""Bonsai ailesi: tek bir gövde yolu (trunk_path) boyunca büyüyen ağaç; dallar ve ardıç bulutları
(foliage pad), kök yayılması (nebari). Aşamalar aynı yolun başını kullanır: aynı ağacın büyümesi.

Spec alanları: seed, trunk_path, branches (s, yan, yukarı, dışarı, uzunluk, çıktığı aşama, bulut
yarıçapı), age_scale, roots ([açı°, uzunluk]), pot ("@parts/..."), palette (bark_*, leaf_*).
Varyant alanları: stage, moss, trunk_frac, r_base, r_tip, sides, rings, roots, root_scale, flare, tip_pad.
"""

import math

import bmesh
from mathutils import Vector, noise

from meshkit import MeshBuilder, catmull_rom, lerp_col, make_material, resample, sample_at, tube
from parts import pots

BASE_MATERIALS = [("bark", 0.9), ("foliage", 0.8)]


def build(ctx, v, collection):
    tree = ctx.spec["tree"]
    pot = ctx.spec["pot"]
    materials = [(pot["material"], pot["roughness"]), ("soil", 1.0)] + BASE_MATERIALS
    mats = [make_material(ctx.material_name(name), rough) for name, rough in materials]
    mb = MeshBuilder({name: i for i, (name, _) in enumerate(materials)})
    pots.build(mb, ctx, pot, v["moss"])
    _tree(mb, ctx, tree, v)
    return mb.to_object(v["object"], mats, collection)


def _bark_color(ctx, seed, base_t):
    """base_t: 0 = gövde dibi (koyu), 1 = uçlar (açık). Hafif boyuna çizgiler."""
    dark, mid, light = ctx.color("bark_dark"), ctx.color("bark"), ctx.color("bark_light")

    def fn(u, co):
        t = base_t + (1 - base_t) * u * 0.6
        c = lerp_col(dark, mid, t * 1.6)
        c = lerp_col(c, light, max(0.0, t - 0.55))
        streak = noise.noise(Vector((co.x * 90, co.y * 90, co.z * 25 + seed)))
        return lerp_col(c, light if streak > 0 else dark, abs(streak) * 0.35)
    return fn


def _foliage_pad(mb, ctx, center, radius, heading, seed):
    """Ardıç bulutu: bir ana kabarcık + dal yönünde öne taşan ikinci bir kabarcık."""
    # bmesh'te subdivisions=1 bölünmemiş ikosahedrondur: 2 -> 80, 3 -> 320 üçgen
    _blob(mb, ctx, center, radius, heading, seed, 3 if radius >= 0.035 else 2)
    if radius >= 0.035:
        ch, sh = math.cos(heading), math.sin(heading)
        along, side = 0.7, 0.3 if seed % 2 else -0.3
        off = Vector((along * ch - side * sh, along * sh + side * ch, -0.1)) * radius
        _blob(mb, ctx, center + off, radius * 0.7, heading + 0.6, seed * 7, 2)


def _blob(mb, ctx, center, radius, heading, seed, subdiv):
    """Noise ile kabartılmış, altı basık elipsoid. Üstü açık nane, altı adaçayı."""
    bm = mb.bm
    res = bmesh.ops.create_icosphere(bm, subdivisions=subdiv, radius=1.0)
    verts = res["verts"]
    rx, ry, rz = radius, radius * 0.82, radius * 0.5
    ch, sh = math.cos(heading), math.sin(heading)
    off = Vector((seed * 3.1, seed * 1.7, seed * 2.3))
    dirs = {}
    for v in verts:
        d = v.co.normalized()
        dirs[v] = d
        detail = 0.08 if subdiv >= 3 else 0.0   # seyrek kabarcıkta ince gürültü köşe yapar
        amp = 0.2 if subdiv >= 3 else 0.1
        bump = 1.0 + amp * noise.noise(d * 2.4 + off) + detail * noise.noise(d * 5.5 + off)
        x, y, z = d.x * rx * bump, d.y * ry * bump, d.z * rz * bump
        if z < 0:
            z *= 0.55
        v.co = center + Vector((x * ch - y * sh, x * sh + y * ch, z))
    shadow, leaf, light = ctx.color("leaf_shadow"), ctx.color("leaf"), ctx.color("leaf_light")
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mb.materials["foliage"]
        for loop in f.loops:
            d = dirs[loop.vert]
            t = 0.5 + 0.5 * d.z
            c = lerp_col(shadow, leaf, t * 1.5)
            c = lerp_col(c, light, (t - 0.6) * 2.2)
            n = noise.noise(loop.vert.co * 60 + off)
            loop[mb.col] = lerp_col(c, light, max(0.0, n) * 0.35)


def _tree(mb, ctx, tree, p):
    stage = p["stage"]
    seed = tree["seed"]
    path = tree["trunk_path"]
    sides = ctx.style.seg(p["sides"])

    # gövde
    pts = resample(path, p["rings"], p["trunk_frac"])
    radii = []
    for k in range(len(pts)):
        u = k / (len(pts) - 1)
        radii.append(p["r_tip"] + (p["r_base"] - p["r_tip"]) * (1 - u) ** 1.3)
    flare = p["flare"]

    def trunk_mod(u, th):
        if flare <= 0 or u > 0.18:
            return 1.0
        k = (1 - u / 0.18) ** 2
        lobes = 0.5 + 0.5 * math.cos(4 * th + 0.7)
        return 1 + flare * k * (0.6 + 0.8 * lobes)

    tube(mb, pts, radii, sides, _bark_color(ctx, seed, 0.0), trunk_mod, cap_end=True)

    # gövde uzunluğu boyunca konum -> nokta ve yarıçap
    full_curve, full_len = catmull_rom(path)
    trunk_len = full_len[-1] * p["trunk_frac"]

    def trunk_point(s):
        return sample_at(full_curve, full_len, full_len[-1] * s)

    def trunk_radius(s):
        u = min(1.0, full_len[-1] * s / trunk_len)
        return p["r_tip"] + (p["r_base"] - p["r_tip"]) * (1 - u) ** 1.3

    # kökler (nebari)
    base = pts[0] + Vector((0, 0, 0.006))
    for ang, length in tree["roots"][:p["roots"]]:
        a = math.radians(ang)
        d = Vector((math.cos(a), math.sin(a), 0))
        scale = p["root_scale"]
        rp = [base, base + d * length * 0.45 * scale + Vector((0, 0, 0.002)),
              base + d * length * scale - Vector((0, 0, 0.010))]
        rpts = resample(rp, 5)
        r0 = p["r_base"] * 0.45
        rradii = [r0 * (1 - 0.75 * k / 4) for k in range(5)]
        tube(mb, rpts, rradii, 6, _bark_color(ctx, seed, 0.1), cap_end=False)

    # dallar ve bulutlar
    for i, (s, side, up, out, length, appear, pad_r) in enumerate(tree["branches"]):
        if stage < appear or s > p["trunk_frac"] - 0.03:
            continue
        f = tree["age_scale"][stage - appear]
        start = trunk_point(s)
        d = Vector((out, side, up)).normalized()
        L = length * f
        bp = [start, start + d * L * 0.45 - Vector((0, 0, 0.006 * f)), start + d * L]
        bpts = resample(bp, 5)
        r0 = max(0.002, trunk_radius(s) * 0.5)
        bradii = [r0 * (1 - 0.7 * k / 4) for k in range(5)]
        tube(mb, bpts, bradii, 6, _bark_color(ctx, seed, 0.5), cap_end=True)
        r = pad_r * f
        heading = math.atan2(d.y, d.x) if (abs(d.x) + abs(d.y)) > 0.1 else 0.0
        _foliage_pad(mb, ctx, bpts[-1] + Vector((0, 0, r * 0.12)), r, heading, seed=i + 1)

    # gövde ucunda bulut
    tip = pts[-1]
    tan = (pts[-1] - pts[-2]).normalized()
    _foliage_pad(mb, ctx, tip + Vector((tan.x, tan.y, 0)) * 0.01, p["tip_pad"],
                 math.atan2(tan.y, tan.x), seed=99)
