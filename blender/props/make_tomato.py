"""Domates fidanı üretici — 4 aşama: fide → genç → çiçekli → olgun meyveli.

Pastel stil, med-high poly. Aynı bitkinin büyümesi: düğüm (node) azimutları, gövde kıvrımları
ve salkım yerleri her aşamada aynı; boy, yaprak sayısı/boyu ve meyve olgunluğu değişir.
Terakota saksı; 2. aşamadan itibaren bambu destek çubuğu ve ip bağları.

Arka planda çalıştır (açık Blender oturumuna dokunmaz):
    blender --background --factory-startup --python blender/props/make_tomato.py -- \
        --part stage1|stage2|stage3|stage4|all [--preview out.png] [--front] [--export [--force]]
    --build = --part all --export (build_all sözleşmesi)

Çıktılar (--export ile):
    blender/props/tomato.blend                dört aşama yan yana
    assets/models/tomato_stage{1,2,3,4}.glb
"""

import argparse
import math
import os
import sys

import bpy
from mathutils import Vector, noise

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(HERE))
BLEND_PATH = os.path.join(HERE, "tomato.blend")
sys.path.insert(0, os.path.join(PROJECT_DIR, "blender", "lib"))
import propkit  # noqa: E402
from meshkit import (  # noqa: E402
    MeshBuilder, lerp_col, make_material, render_preview, resample, srgb, tri_count, tube,
)

Z = Vector((0, 0, 1))

# ---------------------------------------------------------------- palet (sRGB hex, pastel)

TERRA_LIGHT = "F0C3A8"
TERRA = "E2A88B"
TERRA_DARK = "C98E74"
SOIL = "8C7567"
SOIL_DARK = "6F5C52"
STEM_DARK = "7FA77B"
STEM = "97BD8E"
STEM_LIGHT = "B3D3A6"
LEAF_DARK = "7EAD82"
LEAF = "9FCB92"
LEAF_LIGHT = "C3E2AF"
LEAF_VEIN = "CDE8BC"
LEAF_OLD = "D6D69C"       # alt yaşlı yapraklarda solgunluk
SEPAL = "8DB97F"
FRUIT_GREEN = "BBDA9C"
FRUIT_ORANGE = "F4C38D"
FRUIT_RED = "EE9585"
FRUIT_RED_DEEP = "E3837A"
PETAL = "F7E59C"
PETAL_BASE = "EDCF73"
ANTHER = "E7BF5C"
BAMBOO = "DCCDA2"
BAMBOO_NODE = "BFAE7F"
TWINE = "EDE2C8"

# ---------------------------------------------------------------- ölçüler (m)

POT_SEGMENTS = 40
# Dış profilden iç duvara (yarıçap, z): klasik terakota, üstte kalın kenar bandı
POT_PROFILE = [
    (0.072, 0.000),
    (0.076, 0.004),
    (0.082, 0.040),
    (0.090, 0.090),
    (0.097, 0.140),
    (0.099, 0.146),   # bant altı
    (0.110, 0.150),
    (0.112, 0.178),   # bant üstü dış
    (0.106, 0.183),
    (0.099, 0.181),   # iç kenar
    (0.094, 0.162),   # iç duvar toprağa iner
]
SOIL_Z = 0.164
STAKE_POS = Vector((0.0, 0.045, 0.0))
STAKE_R = 0.0042

# Düğümler arası mesafe (tam boy bitkide); aşamalar ölçekler.
INTERNODES = [0.030, 0.035, 0.045, 0.050, 0.055, 0.055, 0.055, 0.055, 0.055, 0.050, 0.050, 0.045]
GOLDEN = math.radians(137.5)

# Salkım öğeleri: ("fruit", yarıçap, olgunluk 0..1) | ("flower", boy) | ("bud", boy)
STAGES = {
    1: dict(nodes=1, scale=0.55, hypo=0.048, r_base=0.0021, sides=6, lmax=0.055,
            stake=0.0, cotyledon=1.35, cotyledon_age=0.0, trusses={}, budget=2200),
    2: dict(nodes=5, scale=0.75, hypo=0.040, r_base=0.0042, sides=7, lmax=0.130,
            stake=0.32, cotyledon=0.95, cotyledon_age=0.3, trusses={}, budget=5500),
    3: dict(nodes=9, scale=0.92, hypo=0.045, r_base=0.0060, sides=8, lmax=0.190,
            stake=0.52, cotyledon=0.9, cotyledon_age=0.8,
            trusses={6: [("fruit", 0.009, 0.0), ("fruit", 0.007, 0.0), ("flower", 0.014),
                         ("flower", 0.014), ("bud", 0.006)],
                     8: [("flower", 0.014), ("flower", 0.013), ("bud", 0.006), ("bud", 0.005)]},
            budget=10000),
    4: dict(nodes=12, scale=1.0, hypo=0.045, r_base=0.0072, sides=8, lmax=0.220,
            stake=0.62, cotyledon=None, cotyledon_age=1.0,
            trusses={6: [("fruit", 0.027, 1.0), ("fruit", 0.026, 1.0), ("fruit", 0.024, 0.95),
                         ("fruit", 0.022, 0.9)],
                     8: [("fruit", 0.024, 0.55), ("fruit", 0.023, 0.4), ("fruit", 0.020, 0.15),
                         ("fruit", 0.018, 0.05)],
                     11: [("flower", 0.015), ("flower", 0.014), ("fruit", 0.007, 0.0), ("bud", 0.006)]},
            budget=13200),
}

PART_NAMES = {
    "stage1": "Domates — 1. aşama (fide)",
    "stage2": "Domates — 2. aşama (genç)",
    "stage3": "Domates — 3. aşama (çiçekli)",
    "stage4": "Domates — 4. aşama (olgun)",
}

MATERIALS = [
    ("terracotta", 0.75),
    ("soil", 1.0),
    ("stem", 0.8),
    ("leaf", 0.75),
    ("fruit", 0.35),
    ("petal", 0.7),
    ("stake", 0.7),
]
SOFT = ("soil", "stem", "leaf", "fruit", "petal", "stake")


def nz(p, scale, seed):
    return noise.noise(Vector(p) * scale + Vector((seed * 1.37, seed * 2.11, seed * 0.73)))


# ---------------------------------------------------------------- saksı

def build_pot(mb):
    n = POT_SEGMENTS
    bm = mb.bm
    zs = [z for _, z in POT_PROFILE]
    inner_from = len(POT_PROFILE) - 3

    def color(z, k, co):
        t = z / 0.183
        c = lerp_col(srgb(TERRA_DARK), srgb(TERRA), t * 1.5)
        if 5 <= k <= 8:                                  # kenar bandı biraz açık
            c = lerp_col(c, srgb(TERRA_LIGHT), 0.45)
        if k == 4:                                       # bandın altındaki gölge
            c = lerp_col(c, srgb(TERRA_DARK), 0.5)
        if k >= inner_from:
            c = lerp_col(c, srgb(TERRA_DARK), 0.35)
        return lerp_col(c, srgb(TERRA_LIGHT), max(0.0, nz(co, 40, 3)) * 0.25)

    rings = [[bm.verts.new((r * math.cos(2 * math.pi * j / n), r * math.sin(2 * math.pi * j / n), z))
              for j in range(n)] for r, z in POT_PROFILE]
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for j in range(n):
            j2 = (j + 1) % n
            vs = [a[j], a[j2], b[j2], b[j]]
            ks = [k, k, k + 1, k + 1]
            mb.face(vs, "terracotta", [color(zs[kk], kk, v.co) for kk, v in zip(ks, vs)])
    center = bm.verts.new((0, 0, 0))
    base = rings[0]
    c = srgb(TERRA_DARK, 0.9)
    for j in range(n):
        mb.face([center, base[(j + 1) % n], base[j]], "terracotta", [c, c, c])

    # toprak: hafif tümsek, koyu-açık lekeler
    profile = [(0.097, SOIL_Z), (0.075, SOIL_Z + 0.004), (0.050, SOIL_Z + 0.007), (0.025, SOIL_Z + 0.008)]
    srings = [[bm.verts.new((r * math.cos(2 * math.pi * j / n), r * math.sin(2 * math.pi * j / n), z))
               for j in range(n)] for r, z in profile]

    def soil_col(co):
        return lerp_col(srgb(SOIL_DARK), srgb(SOIL), 0.5 + nz(co, 22, 5))   # seyrek mesh: düşük frekans

    for k in range(len(srings) - 1):
        a, b = srings[k], srings[k + 1]
        for j in range(n):
            j2 = (j + 1) % n
            vs = [a[j], a[j2], b[j2], b[j]]
            mb.face(vs, "soil", [soil_col(v.co) for v in vs])
    top = bm.verts.new((0, 0, SOIL_Z + 0.0085))
    last = srings[-1]
    for j in range(n):
        vs = [top, last[j], last[(j + 1) % n]]
        mb.face(vs, "soil", [soil_col(v.co) for v in vs])


# ---------------------------------------------------------------- yaprak

def _frame(direction, up_hint=Z):
    f = direction.normalized()
    u = (up_hint - f * up_hint.dot(f))
    if u.length < 1e-6:
        u = Vector((1, 0, 0))
    u.normalize()
    r = f.cross(u)
    return f, u, r


def leaflet(mb, base, direction, length, width, colors, seed, serrate=True, cup=0.10, droop=0.14,
            rows=7):
    """Tek yaprakçık: ortası (orta damar) açık renkli, kenarları tırtıklı, hafif çanak ve sarkık.
    colors: (koyu, normal, açık) lineer RGBA."""
    f, u, r = _frame(direction)
    cols = (-1.0, -0.5, 0.0, 0.5, 1.0)
    dark, mid, light = colors
    vein = lerp_col(light, srgb(LEAF_VEIN), 0.5)
    teeth = 6 + (seed % 3)
    phase = (seed * 0.37) % 1.0

    def point(t, c):
        w = width * math.sin(math.pi * t ** 0.9) ** 1.15   # dar taban, sivri uç
        if serrate and 0.08 < t < 0.95 and abs(c) == 1.0:
            saw = abs(((t * teeth + phase) % 1.0) * 2 - 1)   # 0..1 testere
            w *= 0.86 + 0.24 * saw
        lift = abs(c) * w * cup - (t * t) * length * droop
        return base + f * (t * length) + r * (c * w) + u * lift

    def color(t, c):
        k = lerp_col(mid, dark, abs(c) * 0.6)
        k = lerp_col(k, vein, (1 - abs(c) * 2) * 0.7 if abs(c) < 0.5 else 0.0)
        return lerp_col(k, light, t * 0.25)

    bm = mb.bm
    start = bm.verts.new(point(0.0, 0.0))
    tip = bm.verts.new(point(1.0, 0.0))
    grid = []
    for j in range(1, rows):
        t = j / rows
        grid.append([(bm.verts.new(point(t, c)), t, c) for c in cols])
    # taban yelpazesi
    first = grid[0]
    for k in range(len(cols) - 1):
        a, b = first[k], first[k + 1]
        mb.face([start, b[0], a[0]], "leaf", [color(0, 0), color(b[1], b[2]), color(a[1], a[2])])
    # bantlar
    for j in range(len(grid) - 1):
        lo, hi = grid[j], grid[j + 1]
        for k in range(len(cols) - 1):
            vs = [lo[k], lo[k + 1], hi[k + 1], hi[k]]
            mb.face([v[0] for v in vs], "leaf", [color(v[1], v[2]) for v in vs])
    # uç yelpazesi
    last = grid[-1]
    for k in range(len(cols) - 1):
        a, b = last[k], last[k + 1]
        mb.face([a[0], b[0], tip], "leaf", [color(a[1], a[2]), color(b[1], b[2]), color(1, 0)])


def leaf_colors(age, n_nodes, seed):
    """Genç yaprak açık, yaşlı koyu; en alttakiler hafif solgun."""
    t = min(1.0, age / 5.0)
    dark = lerp_col(srgb(LEAF), srgb(LEAF_DARK), t)
    mid = lerp_col(srgb(LEAF_LIGHT), srgb(LEAF), t * 0.9 + 0.1)
    light = srgb(LEAF_LIGHT)
    if age >= 10:
        k = 0.35
        dark, mid = lerp_col(dark, srgb(LEAF_OLD), k), lerp_col(mid, srgb(LEAF_OLD), k)
    j = nz((seed, 0, 0), 1.0, seed) * 0.08
    return (lerp_col(dark, light, j), lerp_col(mid, light, j), light)


def compound_leaf(mb, start, azimuth, length, age, n_nodes, seed):
    """Domates bileşik yaprağı: sap (rachis) + karşılıklı yaprakçık çiftleri + uç yaprakçık."""
    elev = math.radians(max(6.0, 50.0 - 12.0 * age))     # yaşlı yapraklar yataya iner, sarkmaz
    d = Vector((math.cos(azimuth), math.sin(azimuth), 0))
    d3 = d * math.cos(elev) + Z * math.sin(elev)
    droop = 0.12 if age < 1 else max(-0.18, -0.04 - 0.035 * age)
    p1 = start + d3 * length * 0.42
    p2 = p1 + d * length * 0.58 + Z * length * droop
    pts = resample([start, p1, p2], 9)
    r0 = max(0.0007, 0.0016 * min(1.0, length / 0.1))
    tube(mb, pts, [r0 * (1 - 0.55 * k / 8) for k in range(9)], 4,
         lambda u, co: lerp_col(srgb(STEM), srgb(STEM_LIGHT), u), cap_end=False, mat="stem")

    colors = leaf_colors(age, n_nodes, seed)
    pairs = 1 if age < 1 else (2 if age < 2.5 else 3)
    spots = [0.36, 0.60, 0.81][3 - pairs:]
    sizes = [0.30, 0.34, 0.37][3 - pairs:]

    def at(t):
        i = min(int(t * 8), 7)
        f = t * 8 - i
        p = pts[i].lerp(pts[i + 1], f)
        tan = (pts[i + 1] - pts[i]).normalized()
        return p, tan

    for k, (t, s) in enumerate(zip(spots, sizes)):
        p, tan = at(t)
        side = tan.cross(Z).normalized()
        for sgn in (1, -1):
            ang = math.radians(58 + 6 * k)
            dirv = (side * sgn * math.cos(ang) + tan * math.sin(ang))
            dirv.z -= 0.18
            L = length * s
            leaflet(mb, p, dirv, L, L * 0.40, colors, seed * 7 + k * 2 + (sgn > 0))
    # büyük çiftlerin arasındaki minik ara yaprakçıklar (domatese özgü)
    if pairs >= 2:
        for k in range(len(spots) - 1):
            p, tan = at((spots[k] + spots[k + 1]) * 0.5)
            side = tan.cross(Z).normalized()
            for sgn in (1, -1):
                dirv = side * sgn * 0.8 + tan * 0.6
                L = length * 0.1
                leaflet(mb, p, dirv, L, L * 0.5, colors, seed * 13 + k * 2 + (sgn > 0),
                        serrate=False, rows=4)
    p, tan = at(1.0)
    L = length * 0.40
    leaflet(mb, pts[-1] - tan * L * 0.05, tan + Vector((0, 0, -0.1)), L, L * 0.42, colors, seed * 7 + 9)


def cotyledons(mb, top, size, age, seed):
    """İki karşılıklı, düz kenarlı uzun çenek yaprağı; yaşlandıkça sararır."""
    base_cols = (srgb(LEAF), srgb(LEAF_LIGHT), srgb(LEAF_VEIN))
    cols = tuple(lerp_col(c, srgb(LEAF_OLD), age * 0.7) for c in base_cols)
    for k in (0, 1):
        az = math.radians(25 + 180 * k)
        d = Vector((math.cos(az), math.sin(az), 0.35 - 0.45 * age))
        leaflet(mb, top, d, 0.030 * size, 0.0065 * size, cols, seed + k, serrate=False, cup=0.15,
                droop=0.1 + 0.2 * age, rows=5)


# ---------------------------------------------------------------- çiçek, tomurcuk, meyve

def calyx(mb, top, axis, radius, count=5, curl=0.25):
    """Yıldız şeklinde yeşil çanak yapraklar (sepal)."""
    _, u, r = _frame(axis)
    col = srgb(SEPAL)
    tip_col = lerp_col(col, srgb(LEAF_LIGHT), 0.4)
    bm = mb.bm
    for k in range(count):
        a = 2 * math.pi * k / count
        radial = u * math.cos(a) + r * math.sin(a)
        side = axis.cross(radial).normalized()
        L = radius * 0.8
        w = radius * 0.16
        b0 = bm.verts.new(top + side * w)
        b1 = bm.verts.new(top - side * w)
        m0 = bm.verts.new(top + radial * L * 0.5 + side * w * 0.7 - axis * L * curl * 0.3)
        m1 = bm.verts.new(top + radial * L * 0.5 - side * w * 0.7 - axis * L * curl * 0.3)
        tip = bm.verts.new(top + radial * L - axis * L * curl)
        mb.face([b0, b1, m1, m0], "leaf", [col, col, col, col])
        mb.face([m0, m1, tip], "leaf", [col, col, tip_col])


def flower(mb, center, size):
    """Aşağı bakan sarı yıldız çiçek: geriye kıvrık 6 taç yaprak + başçık konisi + çanak."""
    axis = Vector((0, 0, -1))     # çiçeğin baktığı yön
    _, u, r = _frame(axis)
    bm = mb.bm
    base_c, mid_c, tip_c = srgb(PETAL_BASE), srgb(PETAL), lerp_col(srgb(PETAL), srgb("FFF6D6"), 0.4)
    for k in range(6):
        a = 2 * math.pi * k / 6 + 0.3
        radial = u * math.cos(a) + r * math.sin(a)
        side = axis.cross(radial).normalized()
        p0 = center + radial * size * 0.12
        w = size * 0.17
        m = center + radial * size * 0.55 - axis * size * 0.05
        t = center + radial * size - axis * size * 0.38     # geriye (yukarı) kıvrık uç
        v = [bm.verts.new(p0 + side * w * 0.5), bm.verts.new(p0 - side * w * 0.5),
             bm.verts.new(m - side * w), bm.verts.new(m + side * w), bm.verts.new(t)]
        mb.face(v[:4], "petal", [base_c, base_c, mid_c, mid_c])
        mb.face([v[3], v[2], v[4]], "petal", [mid_c, mid_c, tip_c])
    # başçık konisi (aşağı doğru)
    cone_col = srgb(ANTHER)
    ring = [bm.verts.new(center + (u * math.cos(2 * math.pi * k / 6) + r * math.sin(2 * math.pi * k / 6))
                         * size * 0.13) for k in range(6)]
    tip = bm.verts.new(center + axis * size * 0.5)
    for k in range(6):
        mb.face([ring[k], ring[(k + 1) % 6], tip], "petal", [cone_col] * 3)
    calyx(mb, center + axis * -size * 0.02, -axis, size * 0.55, count=5, curl=-0.4)


def bud(mb, center, size):
    """Kapalı tomurcuk: yeşil çanakla sarılı küçük sarımsı damla."""
    bm = mb.bm
    segs, rings_n = 8, 4
    verts = []
    for i in range(1, rings_n):
        ph = math.pi * i / rings_n
        verts.append([bm.verts.new(center + Vector((math.sin(ph) * math.cos(2 * math.pi * j / segs) * size * 0.45,
                                                    math.sin(ph) * math.sin(2 * math.pi * j / segs) * size * 0.45,
                                                    math.cos(ph) * size * 0.8)))
                      for j in range(segs)])
    top = bm.verts.new(center + Z * size * 0.8)
    bot = bm.verts.new(center - Z * size * 0.8)
    c_top, c_bot = srgb(SEPAL), lerp_col(srgb(SEPAL), srgb(PETAL), 0.6)
    for j in range(segs):
        j2 = (j + 1) % segs
        mb.face([top, verts[0][j], verts[0][j2]], "fruit", [c_top] * 3)
        mb.face([bot, verts[-1][j2], verts[-1][j]], "fruit", [c_bot] * 3)
    for i in range(len(verts) - 1):
        for j in range(segs):
            j2 = (j + 1) % segs
            ca = lerp_col(c_top, c_bot, i / (len(verts) - 1))
            cb = lerp_col(c_top, c_bot, (i + 1) / (len(verts) - 1))
            mb.face([verts[i][j], verts[i + 1][j], verts[i + 1][j2], verts[i][j2]], "fruit",
                    [ca, cb, cb, ca])


def fruit_color(ripeness, shoulder, co, seed):
    """Olgunluk: yeşil → turuncu → kırmızı; yarı olgunda sap çevresi (omuz) yeşil kalır."""
    if ripeness < 0.5:
        c = lerp_col(srgb(FRUIT_GREEN), srgb(FRUIT_ORANGE), ripeness * 2)
    else:
        c = lerp_col(srgb(FRUIT_ORANGE), srgb(FRUIT_RED), (ripeness - 0.5) * 2)
    if ripeness > 0.95:
        c = lerp_col(c, srgb(FRUIT_RED_DEEP), 0.35)
    c = lerp_col(c, srgb(FRUIT_GREEN), shoulder * (1 - ripeness) * 0.8)
    return lerp_col(c, srgb("FFF1E6"), max(0.0, nz(co, 70, seed)) * 0.12)


def fruit(mb, top, radius, ripeness, seed):
    """Hafif basık, dilimli (rib) domates; tepe çukurunda yıldız çanak."""
    bm = mb.bm
    big = radius > 0.012
    segs, rings_n = (18, 11) if big else (12, 7)
    center = top - Z * radius * 0.86
    phase = seed * 0.9
    rows = []
    for i in range(1, rings_n):
        ph = math.pi * i / rings_n
        row = []
        for j in range(segs):
            th = 2 * math.pi * j / segs
            rib = 1 + (0.045 if big else 0.02) * math.cos(5 * th + phase) * math.sin(ph) ** 1.5
            x = math.sin(ph) * math.cos(th) * radius * rib
            y = math.sin(ph) * math.sin(th) * radius * rib
            z = math.cos(ph) * radius * 0.84
            if ph < 0.5:                              # sap çukuru
                z -= radius * 0.12 * (1 - ph / 0.5)
            row.append(bm.verts.new(center + Vector((x, y, z))))
        rows.append((row, ph))
    tv = bm.verts.new(center + Z * (radius * 0.84 - radius * 0.12))
    bv = bm.verts.new(center - Z * radius * 0.84)

    def col(v, ph):
        return fruit_color(ripeness, max(0.0, 1 - ph / 1.1), v.co, seed)

    first, ph0 = rows[0]
    last, phl = rows[-1]
    for j in range(segs):
        j2 = (j + 1) % segs
        mb.face([tv, first[j], first[j2]], "fruit", [col(tv, 0), col(first[j], ph0), col(first[j2], ph0)])
        mb.face([bv, last[j2], last[j]], "fruit", [col(bv, math.pi), col(last[j2], phl), col(last[j], phl)])
    for i in range(len(rows) - 1):
        (ra, pa), (rb, pb) = rows[i], rows[i + 1]
        for j in range(segs):
            j2 = (j + 1) % segs
            mb.face([ra[j], rb[j], rb[j2], ra[j2]], "fruit",
                    [col(ra[j], pa), col(rb[j], pb), col(rb[j2], pb), col(ra[j2], pa)])
    calyx(mb, top - Z * radius * 0.08, -Z, radius * (0.9 if big else 1.2), count=5 if big else 5,
          curl=-0.35)


def truss(mb, start, azimuth, items, seed):
    """Salkım: gövdeden çıkan kıvrık sap; öğeler sırayla iki yana sapçıklarla dizilir."""
    d = Vector((math.cos(azimuth), math.sin(azimuth), 0))
    big = any(it[0] == "fruit" and it[1] > 0.012 for it in items)
    length = 0.075 if big else 0.05
    pts = resample([start, start + d * length * 0.45 + Z * 0.012,
                    start + d * length - Z * (0.02 if big else 0.004)], 8)
    tube(mb, pts, [0.0018 * (1 - 0.5 * k / 7) for k in range(8)], 5,
         lambda u, co: lerp_col(srgb(STEM), srgb(STEM_LIGHT), u), cap_end=True, mat="stem")
    n = len(items)
    for k, item in enumerate(items):
        t = 0.35 + 0.6 * k / max(1, n - 1)
        i = min(int(t * 7), 6)
        p = pts[i].lerp(pts[i + 1], t * 7 - i)
        tan = (pts[i + 1] - pts[i]).normalized()
        side = tan.cross(Z).normalized() * (1 if k % 2 == 0 else -1)
        kind = item[0]
        hang = 0.022 if kind == "fruit" and item[1] > 0.012 else 0.016
        end = p + side * hang * 0.6 + tan * hang * 0.2 - Z * hang * 0.8
        tube(mb, resample([p, p + side * hang * 0.35 + Z * 0.002, end], 4), [0.0009, 0.0008, 0.0007, 0.0006], 4,
             lambda u, co: srgb(STEM), cap_end=False, mat="stem")
        if kind == "fruit":
            fruit(mb, end, item[1], item[2], seed * 11 + k)
        elif kind == "flower":
            flower(mb, end - Z * 0.002, item[1])
        else:
            bud(mb, end - Z * item[1] * 0.6, item[1])


# ---------------------------------------------------------------- çubuk ve ip

def stake(mb, height):
    """Bambu destek çubuğu; height: topraktan yukarı boy (m)."""
    bottom = STAKE_POS + Vector((0, 0, SOIL_Z - 0.09))
    top = STAKE_POS + Vector((0, 0, SOIL_Z + height))
    n = 26
    pts = [bottom.lerp(top, k / (n - 1)) for k in range(n)]

    def col(u, co):
        z = co.z - SOIL_Z
        node = abs(((z / 0.13) % 1.0) - 0.5) > 0.46        # her 13 cm'de boğum
        c = srgb(BAMBOO_NODE) if node else srgb(BAMBOO)
        return lerp_col(c, srgb("F1E7C7"), max(0.0, nz(co, 90, 13)) * 0.3)

    tube(mb, pts, [STAKE_R] * n, 6, col, cap_end=True, mat="stake")


def tie(mb, stem_point, z):
    """Gövdeyi çubuğa bağlayan ip halkası (gövde ve çubuğu birlikte saran elips)."""
    a = Vector((stem_point.x, stem_point.y, z))
    b = Vector((STAKE_POS.x, STAKE_POS.y, z))
    mid = (a + b) * 0.5
    axis = (b - a)
    half = axis.length * 0.5 + 0.007
    axis.normalize()
    perp = axis.cross(Z)
    n = 14
    pts = [mid + axis * math.cos(2 * math.pi * k / n) * half + perp * math.sin(2 * math.pi * k / n) * 0.0075
           for k in range(n + 1)]
    tube(mb, pts, [0.0011] * (n + 1), 4, lambda u, co: srgb(TWINE), cap_end=False, mat="stake")


# ---------------------------------------------------------------- bitki

def node_layout(stage):
    """Düğüm noktaları: (konum, azimut). Kotiledon düğümü 0. indekste."""
    p = STAGES[stage]
    pts = [Vector((0, 0, SOIL_Z - 0.01))]
    z = SOIL_Z + p["hypo"]
    lean = 0.014 if p["stake"] else 0.0
    nodes = [(Vector((0, 0, z)), 0.0)]
    for i in range(1, p["nodes"] + 1):
        z += INTERNODES[i - 1] * p["scale"]
        az = i * GOLDEN + 0.35
        k = (z - SOIL_Z) / 0.65
        kink = Vector((math.cos(az + math.pi), math.sin(az + math.pi), 0)) * 0.004 * min(1.0, i / 3)
        nodes.append((Vector((0, lean * k, z)) + kink, az))
    pts += [n[0] for n in nodes]
    tip_z = z + INTERNODES[min(p["nodes"], len(INTERNODES) - 1)] * p["scale"] * 0.5
    pts.append(Vector((nodes[-1][0].x * 0.5, lean * (tip_z - SOIL_Z) / 0.65, tip_z)))
    return nodes, pts


def build_plant(mb, stage, seed=21):
    p = STAGES[stage]
    nodes, stem_pts = node_layout(stage)

    # gövde
    pts = resample(stem_pts, max(8, len(stem_pts) * 4))
    total = len(pts)
    radii = [p["r_base"] * (1 - 0.7 * (k / (total - 1)) ** 1.2) for k in range(total)]
    tube(mb, pts, radii, p["sides"],
         lambda u, co: lerp_col(lerp_col(srgb(STEM_DARK), srgb(STEM), u * 1.6), srgb(STEM_LIGHT),
                                max(0.0, u - 0.6) + max(0.0, nz(co, 120, seed)) * 0.15),
         cap_end=True, mat="stem")

    # çenek yaprakları
    if p["cotyledon"]:
        cotyledons(mb, nodes[0][0], p["cotyledon"], p["cotyledon_age"], seed)

    # bileşik yapraklar: yaş = (düğüm sayısı - düğüm indeksi)
    n = p["nodes"]
    for i in range(1, n + 1):
        pos, az = nodes[i]
        age = n - i
        length = p["lmax"] * min(1.0, 0.3 + 0.18 * age)
        compound_leaf(mb, pos, az, length, age, n, seed + i)
    # büyüme ucunda açılmamış minik yaprak
    tip_pos = pts[-1]
    leaflet(mb, tip_pos, Vector((0.3, 0.2, 1.0)), p["lmax"] * 0.12, p["lmax"] * 0.05,
            (srgb(LEAF), srgb(LEAF_LIGHT), srgb(LEAF_VEIN)), seed + 99, cup=0.5, droop=-0.1, rows=4)

    # salkımlar: düğüm ile bir üstteki arasından, yaprağın tersine
    for node_i, items in p["trusses"].items():
        pos, az = nodes[node_i]
        above = nodes[min(node_i + 1, n)][0]
        truss(mb, pos.lerp(above, 0.45), az + math.pi * 0.9, items, seed + node_i)

    # çubuk ve ip bağları
    if p["stake"]:
        stake(mb, p["stake"])
        plant_top = stem_pts[-1].z
        for h in (0.10, 0.27, 0.44):
            z = SOIL_Z + h
            if z < plant_top - 0.04:
                k = min(range(total), key=lambda i: abs(pts[i].z - z))
                tie(mb, pts[k], z)


def build_part(part, collection):
    stage = int(part[-1])
    mats = [make_material("tomato_" + name, rough) for name, rough in MATERIALS]
    for m in mats:
        # ince yüzeyler çift taraflı; kapalı gövdeler arka yüzü çizmez (Godot'taki gibi).
        # glTF'e doubleSided olarak gider.
        m.use_backface_culling = not m.name.endswith(("leaf", "petal"))
    mb = MeshBuilder({name: i for i, (name, _) in enumerate(MATERIALS)})
    build_pot(mb)
    build_plant(mb, stage)
    obj = mb.to_object("tomato_" + part, mats, collection, soft=SOFT)
    obj["prop_name"] = PART_NAMES[part]
    obj["prop_style"] = "pastel"
    obj["prop_placement"] = "pedestal"
    obj["prop_budget"] = STAGES[stage]["budget"]
    return obj


# ---------------------------------------------------------------- sahne

def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser()
    ap.add_argument("--part", default="stage4")
    ap.add_argument("--preview")
    ap.add_argument("--front", action="store_true", help="önizlemeyi tam önden çek")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--force", action="store_true", help="elle düzenlenmiş .blend'i yedekleyip üstüne yaz")
    ap.add_argument("--build", action="store_true", help="build_all sözleşmesi: --part all --export")
    args = ap.parse_args(argv)
    if args.build:
        args.part, args.export = "all", True

    if args.export:
        if args.part != "all":
            print("[make_tomato] DURDU: --export yalnızca --part all ile kullanılabilir.")
            return
        try:
            propkit.guard_overwrite(BLEND_PATH, args.force)
        except propkit.OverwriteRefused as e:
            print("[make_tomato] DURDU:", e)
            return

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.scale_length = 1.0

    parts = [f"stage{i}" for i in range(1, 5)] if args.part == "all" else [args.part]
    objs = []
    for i, part in enumerate(parts):
        coll = bpy.data.collections.new("tomato_" + part)
        scene.collection.children.link(coll)
        obj = build_part(part, coll)
        obj.location.x = (i - (len(parts) - 1) / 2) * 0.5
        objs.append(obj)
        print(f"[make_tomato] {obj.name}: {tri_count(obj)} üçgen (bütçe {obj['prop_budget']})")

    if args.export:
        propkit.save_generated(BLEND_PATH)
        propkit.export_props(objs)

    if args.preview:
        render_preview(args.preview, objs, args.front, tag="make_tomato")


main()
