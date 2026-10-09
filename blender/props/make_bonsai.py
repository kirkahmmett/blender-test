"""Bonsai üretici — han-kengai (yarı şelale), ardıç bulutları, seladon porselen saksı.

PS1 kurallarının dışında bir stil deneyi: med poly, smooth gölgelendirme, pastel vertex color.

Arka planda çalıştır (açık Blender oturumuna dokunmaz):
    blender --background --factory-startup --python blender/props/make_bonsai.py -- \
        --part pot|stage1|stage2|stage3|all [--preview out.png] [--export [--force]]

--export yalnızca --part all ile; bonsai.blend elle düzenlendiyse üstüne yazmaz (propkit).

Çıktılar (--export ile):
    blender/props/bonsai.blend               üç aşama yan yana, her biri kendi koleksiyonunda
    assets/models/bonsai_stage{1,2,3}.glb
"""

import argparse
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector, noise

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(HERE))
BLEND_PATH = os.path.join(HERE, "bonsai.blend")
sys.path.insert(0, os.path.join(PROJECT_DIR, "blender", "lib"))
import propkit  # noqa: E402

SEED = 11

# ---------------------------------------------------------------- saksı ölçüleri (m)

POT_A = 0.18        # oval yarı eksen, X (gövde bu yöne sarkar)
POT_B = 0.13        # oval yarı eksen, Y
POT_SEGMENTS = 32
FOOT_H = 0.010
SOIL_Z = 0.090

# Dış profilden iç duvara: (yarıçap oranı, z). Merkez kapağı ayrıca eklenir.
POT_PROFILE = [
    (0.86, FOOT_H),
    (0.90, 0.016),
    (0.95, 0.040),
    (0.975, 0.075),
    (0.985, 0.092),
    (1.02, 0.096),
    (1.02, 0.104),
    (0.985, 0.108),
    (0.94, 0.106),
    (0.92, 0.088),
]

# ---------------------------------------------------------------- renkler (sRGB hex)

CELADON_LIGHT = "C6DFCB"
CELADON = "A9C9B2"
CELADON_DARK = "8DAE98"
SOIL = "8E7C6E"
SOIL_DARK = "77685D"
MOSS = "AFCC9C"


def srgb(hexstr, mul=1.0):
    """sRGB hex -> lineer RGBA (Blender color attribute lineer saklar)."""
    out = []
    for i in (0, 2, 4):
        c = int(hexstr[i:i + 2], 16) / 255.0 * mul
        c = min(1.0, c)
        out.append(c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4)
    return (*out, 1.0)


def lerp_col(a, b, t):
    t = max(0.0, min(1.0, t))
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(4))


# ---------------------------------------------------------------- yardımcılar

def make_material(name, roughness):
    """Base color = Color Attribute. Godot tarafında malzeme adına göre shader seçilir."""
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = roughness
    attr = nt.nodes.new("ShaderNodeVertexColor")
    attr.layer_name = "Col"
    nt.links.new(attr.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


class MeshBuilder:
    """bmesh + malzeme indeksli yüzler + loop başına renk."""

    def __init__(self, materials):
        self.bm = bmesh.new()
        self.col = self.bm.loops.layers.float_color.new("Col")
        self.materials = materials  # isim -> indeks

    def face(self, verts, mat, colors):
        f = self.bm.faces.new(verts)
        f.material_index = self.materials[mat]
        for loop, c in zip(f.loops, colors):
            loop[self.col] = c
        return f

    def to_object(self, name, mat_list, collection, sharp_angle=50.0):
        me = bpy.data.meshes.new(name)
        self.bm.normal_update()
        self.bm.to_mesh(me)
        self.bm.free()
        for m in mat_list:
            me.materials.append(m)
        me.color_attributes.active_color_name = "Col"
        me.color_attributes.render_color_index = me.color_attributes.find("Col")
        for p in me.polygons:
            p.use_smooth = True
        me.set_sharp_from_angle(angle=math.radians(sharp_angle))
        # yaprak ve kabuk her zaman yumuşak: keskin kenar yalnızca saksıda kalsın
        soft = {self.materials[m] for m in ("foliage", "bark") if m in self.materials}
        sharp = me.attributes.get("sharp_edge")
        if sharp:
            soft_verts = {v for p in me.polygons if p.material_index in soft for v in p.vertices}
            for e in me.edges:
                if e.vertices[0] in soft_verts and e.vertices[1] in soft_verts:
                    sharp.data[e.index].value = False
        obj = bpy.data.objects.new(name, me)
        collection.objects.link(obj)
        return obj


# ---------------------------------------------------------------- saksı

def pot_color(z, inner=False):
    t = (z - FOOT_H) / (0.108 - FOOT_H)
    c = lerp_col(srgb(CELADON_DARK), srgb(CELADON), t * 1.4)
    if t > 0.85 or inner:
        c = lerp_col(c, srgb(CELADON_LIGHT), 0.6)
    return c


def build_pot(mb, moss_amount):
    n = POT_SEGMENTS
    bm = mb.bm

    def ring(r, z):
        return [bm.verts.new((POT_A * r * math.cos(2 * math.pi * j / n),
                              POT_B * r * math.sin(2 * math.pi * j / n), z)) for j in range(n)]

    rings = [ring(r, z) for r, z in POT_PROFILE]
    zs = [z for _, z in POT_PROFILE]
    inner_from = len(POT_PROFILE) - 2  # son iki halka iç duvar
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for j in range(n):
            j2 = (j + 1) % n
            inner = k >= inner_from
            ca, cb = pot_color(zs[k], inner), pot_color(zs[k + 1], inner)
            mb.face([a[j], a[j2], b[j2], b[j]], "porcelain", [ca, ca, cb, cb])

    # taban kapağı
    center = bm.verts.new((0, 0, FOOT_H))
    base = rings[0]
    c = pot_color(FOOT_H)
    for j in range(n):
        mb.face([center, base[(j + 1) % n], base[j]], "porcelain", [c, c, c])

    # 4 ayak (üst kapaksız, tabana gömülü)
    for ang in (35, 145, 215, 325):
        cx = POT_A * 0.72 * math.cos(math.radians(ang))
        cy = POT_B * 0.72 * math.sin(math.radians(ang))
        m = 8
        r = 0.022
        top = [bm.verts.new((cx + r * math.cos(2 * math.pi * j / m), cy + r * 0.8 * math.sin(2 * math.pi * j / m), FOOT_H + 0.002)) for j in range(m)]
        bot = [bm.verts.new((cx + r * 0.85 * math.cos(2 * math.pi * j / m), cy + r * 0.68 * math.sin(2 * math.pi * j / m), 0.0)) for j in range(m)]
        cf = srgb(CELADON_DARK, 0.92)
        for j in range(m):
            j2 = (j + 1) % m
            mb.face([bot[j], bot[j2], top[j2], top[j]], "porcelain", [cf] * 4)
        mb.face(list(reversed(bot)), "porcelain", [cf] * m)

    build_soil(mb, moss_amount)


def build_soil(mb, moss_amount):
    """Hafif tümsekli toprak; yosun lekeleri vertex color ile (moss_amount 0..1)."""
    n = POT_SEGMENTS
    bm = mb.bm
    profile = [(0.93, SOIL_Z), (0.76, SOIL_Z + 0.005), (0.56, SOIL_Z + 0.008),
               (0.36, SOIL_Z + 0.010), (0.16, SOIL_Z + 0.0115)]

    def soil_col(co):
        v = noise.noise(Vector((co.x * 9, co.y * 9, SEED)))
        base = lerp_col(srgb(SOIL_DARK), srgb(SOIL), 0.5 + v)
        m = noise.noise(Vector((co.x * 7 + 5, co.y * 7, SEED * 2)))
        moss = m * 1.5 + (moss_amount - 0.5) * 1.2
        return lerp_col(base, srgb(MOSS), moss * 2.0)

    rings = []
    for r, z in profile:
        rings.append([bm.verts.new((POT_A * r * math.cos(2 * math.pi * j / n),
                                    POT_B * r * math.sin(2 * math.pi * j / n), z)) for j in range(n)])
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for j in range(n):
            j2 = (j + 1) % n
            vs = [a[j], a[j2], b[j2], b[j]]
            mb.face(vs, "soil", [soil_col(v.co) for v in vs])
    center = bm.verts.new((0, 0, SOIL_Z + 0.012))
    last = rings[-1]
    for j in range(n):
        vs = [center, last[j], last[(j + 1) % n]]
        mb.face(vs, "soil", [soil_col(v.co) for v in vs])


# ---------------------------------------------------------------- ağaç: eğri yardımcıları

BARK_DARK = "857469"
BARK = "9E8D83"
BARK_LIGHT = "BBADA3"
LEAF_SHADOW = "86AA90"
LEAF = "A3C6A2"
LEAF_LIGHT = "CDE6C0"

# Olgun gövdenin yolu (han-kengai): saksının -X yanından yükselir, kemer yapar,
# +X kenarını aşıp saksı tabanı hizasına kadar sarkar. Genç aşamalar bu yolun başını kullanır.
TRUNK_PATH = [
    (-0.050, 0.000, 0.088),
    (-0.045, 0.006, 0.140),
    (-0.020, -0.012, 0.195),
    (0.030, 0.008, 0.222),
    (0.095, -0.006, 0.215),
    (0.160, 0.014, 0.185),
    (0.215, -0.004, 0.135),
    (0.250, 0.012, 0.085),
    (0.280, -0.006, 0.045),
]

# Aşama parametreleri: gövde uzunluğu (tam yolun oranı), taban/uç yarıçapı,
# kesit kenar sayısı, halka sayısı, kök sayısı, taban genişlemesi, uç bulutu yarıçapı
STAGES = {
    1: dict(trunk_frac=0.45, r_base=0.006, r_tip=0.0025, sides=6, rings=12, roots=0, flare=0.0, tip_pad=0.030),
    2: dict(trunk_frac=0.72, r_base=0.018, r_tip=0.0040, sides=8, rings=22, roots=2, flare=0.35, tip_pad=0.045),
    3: dict(trunk_frac=1.00, r_base=0.030, r_tip=0.0085, sides=10, rings=32, roots=4, flare=0.8, tip_pad=0.068),
}

# Dallar: (gövdedeki konum s, yan yönü ±Y, yukarı bileşeni, dışarı (+X) bileşeni,
#          uzunluk, çıktığı aşama, bulut yarıçapı)
BRANCHES = [
    (0.12, -1, 0.35, -0.6, 0.08, 3, 0.060),   # dengeleyici arka dal
    (0.22, 1, 0.25, 0.0, 0.09, 1, 0.068),
    (0.30, 0, 1.00, -0.2, 0.06, 2, 0.065),    # tepe (apeks)
    (0.40, -1, 0.20, 0.3, 0.10, 1, 0.072),
    (0.52, 1, 0.15, 0.5, 0.10, 2, 0.072),
    (0.63, -1, 0.10, 0.5, 0.10, 3, 0.068),
    (0.74, 1, 0.10, 0.6, 0.09, 3, 0.062),
    (0.85, -1, 0.05, 0.6, 0.08, 3, 0.058),
]
AGE_SCALE = [0.7, 0.88, 1.0]   # dalın yaşına (aşama - çıktığı aşama) göre boyut

ROOTS = [(200, 0.070), (140, 0.055), (250, 0.060), (90, 0.050)]  # (açı°, uzunluk)


def catmull_rom(points, samples=200):
    """Noktalardan geçen yumuşak eğri; yay uzunluğuna göre (nokta, kümülatif uzunluk) döner."""
    pts = [Vector(p) for p in points]
    pts = [pts[0] * 2 - pts[1]] + pts + [pts[-1] * 2 - pts[-2]]
    out = []
    segs = len(pts) - 3
    for i in range(segs):
        p0, p1, p2, p3 = pts[i:i + 4]
        steps = max(2, samples // segs)
        for k in range(steps):
            t = k / steps
            t2, t3 = t * t, t * t * t
            out.append(0.5 * ((2 * p1) + (-p0 + p2) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t2
                              + (-p0 + 3 * p1 - 3 * p2 + p3) * t3))
    out.append(pts[-2].copy())
    lengths = [0.0]
    for a, b in zip(out, out[1:]):
        lengths.append(lengths[-1] + (b - a).length)
    return out, lengths


def sample_at(curve, lengths, dist):
    """Eğri üzerinde baştan 'dist' uzaklıktaki nokta."""
    dist = max(0.0, min(lengths[-1], dist))
    for i in range(1, len(lengths)):
        if lengths[i] >= dist:
            seg = lengths[i] - lengths[i - 1]
            t = (dist - lengths[i - 1]) / seg if seg > 0 else 0.0
            return curve[i - 1].lerp(curve[i], t)
    return curve[-1].copy()


def resample(points, count, frac=1.0):
    curve, lengths = catmull_rom(points)
    total = lengths[-1] * frac
    return [sample_at(curve, lengths, total * k / (count - 1)) for k in range(count)]


def tube(mb, pts, radii, sides, color_fn, ring_mod=None, cap_end=True):
    """Paralel taşıma çerçeveli tüp. color_fn(u, co) -> renk; ring_mod(u, theta) -> yarıçap çarpanı."""
    bm = mb.bm
    n = len(pts)
    tangents = []
    for i in range(n):
        a = pts[max(0, i - 1)]
        b = pts[min(n - 1, i + 1)]
        tangents.append((b - a).normalized())
    up = Vector((0, 0, 1)) if abs(tangents[0].z) < 0.9 else Vector((1, 0, 0))
    normal = tangents[0].cross(up).normalized()
    rings = []
    for i in range(n):
        if i > 0:
            normal = tangents[i - 1].rotation_difference(tangents[i]) @ normal
            normal = (normal - tangents[i] * normal.dot(tangents[i])).normalized()
        binormal = tangents[i].cross(normal)
        u = i / (n - 1)
        ring = []
        for j in range(sides):
            th = 2 * math.pi * j / sides
            r = radii[i] * (ring_mod(u, th) if ring_mod else 1.0)
            ring.append(bm.verts.new(pts[i] + (normal * math.cos(th) + binormal * math.sin(th)) * r))
        rings.append(ring)
    for i in range(n - 1):
        a, b = rings[i], rings[i + 1]
        ua, ub = i / (n - 1), (i + 1) / (n - 1)
        for j in range(sides):
            j2 = (j + 1) % sides
            vs = [a[j], a[j2], b[j2], b[j]]
            us = [ua, ua, ub, ub]
            mb.face(vs, "bark", [color_fn(u, v.co) for u, v in zip(us, vs)])
    if cap_end:
        tip = bm.verts.new(pts[-1] + tangents[-1] * radii[-1] * 0.6)
        last = rings[-1]
        for j in range(sides):
            vs = [last[j], last[(j + 1) % sides], tip]
            mb.face(vs, "bark", [color_fn(1.0, v.co) for v in vs])


def bark_color(base_t):
    """base_t: 0 = gövde dibi (koyu), 1 = uçlar (açık). Hafif boyuna çizgiler."""
    def fn(u, co):
        t = base_t + (1 - base_t) * u * 0.6
        c = lerp_col(srgb(BARK_DARK), srgb(BARK), t * 1.6)
        c = lerp_col(c, srgb(BARK_LIGHT), max(0.0, t - 0.55))
        streak = noise.noise(Vector((co.x * 90, co.y * 90, co.z * 25 + SEED)))
        return lerp_col(c, srgb(BARK_LIGHT if streak > 0 else BARK_DARK), abs(streak) * 0.35)
    return fn


def foliage_pad(mb, center, radius, heading, seed):
    """Ardıç bulutu: bir ana kabarcık + dal yönünde öne taşan ikinci bir kabarcık."""
    # bmesh'te subdivisions=1 bölünmemiş ikosahedrondur: 2 -> 80, 3 -> 320 üçgen
    blob(mb, center, radius, heading, seed, 3 if radius >= 0.035 else 2)
    if radius >= 0.035:
        ch, sh = math.cos(heading), math.sin(heading)
        along, side = 0.7, 0.3 if seed % 2 else -0.3
        off = Vector((along * ch - side * sh, along * sh + side * ch, -0.1)) * radius
        blob(mb, center + off, radius * 0.7, heading + 0.6, seed * 7, 2)


def blob(mb, center, radius, heading, seed, subdiv):
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
    faces = {f for v in verts for f in v.link_faces}
    for f in faces:
        f.material_index = mb.materials["foliage"]
        for loop in f.loops:
            d = dirs[loop.vert]
            t = 0.5 + 0.5 * d.z
            c = lerp_col(srgb(LEAF_SHADOW), srgb(LEAF), t * 1.5)
            c = lerp_col(c, srgb(LEAF_LIGHT), (t - 0.6) * 2.2)
            n = noise.noise(loop.vert.co * 60 + off)
            loop[mb.col] = lerp_col(c, srgb(LEAF_LIGHT), max(0.0, n) * 0.35)


# ---------------------------------------------------------------- ağaç

def build_tree(mb, stage):
    p = STAGES[stage]

    # gövde
    pts = resample(TRUNK_PATH, p["rings"], p["trunk_frac"])
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

    tube(mb, pts, radii, p["sides"], bark_color(0.0), trunk_mod, cap_end=True)

    # gövde uzunluğu boyunca konum -> nokta ve yarıçap
    full_curve, full_len = catmull_rom(TRUNK_PATH)
    trunk_len = full_len[-1] * p["trunk_frac"]

    def trunk_point(s):
        return sample_at(full_curve, full_len, full_len[-1] * s)

    def trunk_radius(s):
        u = min(1.0, full_len[-1] * s / trunk_len)
        return p["r_tip"] + (p["r_base"] - p["r_tip"]) * (1 - u) ** 1.3

    # kökler (nebari)
    base = pts[0] + Vector((0, 0, 0.006))
    for ang, length in ROOTS[:p["roots"]]:
        a = math.radians(ang)
        d = Vector((math.cos(a), math.sin(a), 0))
        scale = 1.0 if stage == 3 else 0.6
        rp = [base, base + d * length * 0.45 * scale + Vector((0, 0, 0.002)),
              base + d * length * scale - Vector((0, 0, 0.010))]
        rpts = resample(rp, 5)
        r0 = p["r_base"] * 0.45
        rradii = [r0 * (1 - 0.75 * k / 4) for k in range(5)]
        tube(mb, rpts, rradii, 6, bark_color(0.1), cap_end=False)

    # dallar ve bulutlar
    for i, (s, side, up, out, length, appear, pad_r) in enumerate(BRANCHES):
        if stage < appear or s > p["trunk_frac"] - 0.03:
            continue
        f = AGE_SCALE[stage - appear]
        start = trunk_point(s)
        d = Vector((out, side, up)).normalized()
        L = length * f
        bp = [start, start + d * L * 0.45 - Vector((0, 0, 0.006 * f)), start + d * L]
        bpts = resample(bp, 5)
        r0 = max(0.002, trunk_radius(s) * 0.5)
        bradii = [r0 * (1 - 0.7 * k / 4) for k in range(5)]
        tube(mb, bpts, bradii, 6, bark_color(0.5), cap_end=True)
        r = pad_r * f
        heading = math.atan2(d.y, d.x) if (abs(d.x) + abs(d.y)) > 0.1 else 0.0
        foliage_pad(mb, bpts[-1] + Vector((0, 0, r * 0.12)), r, heading, seed=i + 1)

    # gövde ucunda bulut
    tip = pts[-1]
    tan = (pts[-1] - pts[-2]).normalized()
    foliage_pad(mb, tip + Vector((tan.x, tan.y, 0)) * 0.01, p["tip_pad"],
                math.atan2(tan.y, tan.x), seed=99)


# ---------------------------------------------------------------- sahne

MATERIALS = [
    ("porcelain", 0.2),
    ("soil", 1.0),
    ("bark", 0.9),
    ("foliage", 0.8),
]


def build_part(part, collection):
    mats = [make_material("bonsai_" + name, rough) for name, rough in MATERIALS]
    mb = MeshBuilder({name: i for i, (name, _) in enumerate(MATERIALS)})
    moss = {"pot": 0.3, "stage1": 0.15, "stage2": 0.45, "stage3": 0.8}[part]
    build_pot(mb, moss)
    if part.startswith("stage"):
        build_tree(mb, int(part[-1]))
    obj = mb.to_object("bonsai_" + part, mats, collection)
    # galeri bilgisi: glTF "extras" olarak Godot'a metadata diye gider
    obj["prop_name"] = PART_NAMES[part]
    obj["prop_style"] = "pastel"
    obj["prop_placement"] = "pedestal"
    return obj


PART_NAMES = {
    "pot": "Bonsai saksısı",
    "stage1": "Bonsai — 1. aşama (fidan)",
    "stage2": "Bonsai — 2. aşama (orta)",
    "stage3": "Bonsai — 3. aşama (olgun)",
}


def tri_count(obj):
    me = obj.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


def render_preview(path, objs, front=False):
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    corners =[o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    cx = (lo.x + hi.x) / 2
    span = max(hi.x - lo.x, (hi.z - lo.z) * 1.6) + 0.2
    cam_data = bpy.data.cameras.new("preview_cam")
    cam_data.lens = 50
    cam = bpy.data.objects.new("preview_cam", cam_data)
    scene.collection.objects.link(cam)
    target = Vector((cx, 0, (lo.z + hi.z) / 2))
    view = Vector((0.0, -1.0, 0.08)) if front else Vector((0.25, -1.0, 0.35))
    cam.location = target + view.normalized() * span * 1.35
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.engine = "BLENDER_EEVEE"
    scene.view_settings.view_transform = "Standard"

    # yumuşak gökyüzü ışığı + bir güneş; sahneye kaydedilmez
    world = bpy.data.worlds.new("preview_world")
    world.color = (0.62, 0.64, 0.68)
    if world.node_tree is None:
        world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    bg.inputs["Color"].default_value = (0.62, 0.64, 0.68, 1.0)
    bg.inputs["Strength"].default_value = 0.9
    scene.world = world
    sun_data = bpy.data.lights.new("preview_sun", "SUN")
    sun_data.energy = 2.2
    sun_data.angle = math.radians(25)
    sun = bpy.data.objects.new("preview_sun", sun_data)
    sun.rotation_euler = (math.radians(50), math.radians(10), math.radians(30))
    scene.collection.objects.link(sun)

    scene.render.resolution_x = 900 if len(objs) > 1 else 560
    scene.render.resolution_y = 560
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for o in (cam, sun):
        bpy.data.objects.remove(o)
    scene.world = None
    print("[make_bonsai] preview:", path)


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="pot")
    ap.add_argument("--preview")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--front", action="store_true", help="önizlemeyi tam önden çek")
    ap.add_argument("--force", action="store_true", help="elle düzenlenmiş .blend'i yedekleyip üstüne yaz")
    ap.add_argument("--build", action="store_true", help="build_all sözleşmesi: --part all --export")
    args = ap.parse_args(argv)
    if args.build:
        args.part, args.export = "all", True

    if args.export:
        # bonsai.blend üç aşamayı birlikte tutar; tek parçayla kaydetmek diğerlerini silerdi
        if args.part != "all":
            print("[make_bonsai] DURDU: --export yalnızca --part all ile kullanılabilir.")
            return
        try:
            propkit.guard_overwrite(BLEND_PATH, args.force)
        except propkit.OverwriteRefused as e:
            print("[make_bonsai] DURDU:", e)
            return

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.scale_length = 1.0

    parts = ["stage1", "stage2", "stage3"] if args.part == "all" else [args.part]
    objs = []
    for i, part in enumerate(parts):
        coll = bpy.data.collections.new("bonsai_" + part)
        scene.collection.children.link(coll)
        obj = build_part(part, coll)
        obj.location.x = (i - (len(parts) - 1) / 2) * 0.7
        objs.append(obj)
        print(f"[make_bonsai] {obj.name}: {tri_count(obj)} üçgen")

    if args.export:
        export_all(objs)

    if args.preview:
        render_preview(args.preview, objs, args.front)


def export_all(objs):
    """.blend'i kaydet (aşamalar yan yana), her aşamayı orijinde .glb olarak yaz."""
    propkit.save_generated(BLEND_PATH)
    propkit.export_props(objs)


main()
