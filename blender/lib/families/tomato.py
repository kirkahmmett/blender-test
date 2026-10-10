"""Domates (otsu, çubuklu bitki) ailesi: düğümlerde sarmal dizilen bileşik yapraklar, çenek
yaprakları, salkımlarda çiçek / tomurcuk / meyve, bambu destek çubuğu ve ip bağları.
Aynı bitkinin büyümesi: düğüm azimutları, gövde kıvrımı ve salkım yerleri aşamalar boyunca sabit.

Spec alanları: [plant] seed, internodes, phyllotaxis_deg, stake_pos, stake_r, soil_z (saksının
toprağıyla aynı olmalı); pot ("@parts/..."); palette.
Varyant alanları: stage, nodes, scale, hypo, r_base, sides, lmax, stake (boy; 0 = yok),
cotyledon (boyut; 0 = yok), cotyledon_age, trusses ({düğüm = [[tür, ...], ...]}).
Salkım öğeleri: ["fruit", yarıçap, olgunluk 0..1] | ["flower", boy] | ["bud", boy].
"""

import math

from mathutils import Vector, noise

from meshkit import MeshBuilder, lerp_col, make_material, resample, tube
from parts import pots

Z = Vector((0, 0, 1))
BASE_MATERIALS = [("stem", 0.8), ("leaf", 0.75), ("fruit", 0.35), ("petal", 0.7), ("stake", 0.7)]
SOFT = ("soil", "stem", "leaf", "fruit", "petal", "stake")
DOUBLE_SIDED = ("leaf", "petal")


def nz(p, scale, seed):
    return noise.noise(Vector(p) * scale + Vector((seed * 1.37, seed * 2.11, seed * 0.73)))


def build(ctx, v, collection):
    pot = ctx.spec["pot"]
    materials = [(pot["material"], pot["roughness"]), ("soil", 1.0)] + BASE_MATERIALS
    mats = [make_material(ctx.material_name(name), rough) for name, rough in materials]
    for m in mats:
        # ince yüzeyler çift taraflı; kapalı gövdeler arka yüzü çizmez (Godot'taki gibi).
        # glTF'e doubleSided olarak gider.
        m.use_backface_culling = not m.name.endswith(DOUBLE_SIDED)
    mb = MeshBuilder({name: i for i, (name, _) in enumerate(materials)})
    pots.build(mb, ctx, pot)
    Plant(ctx).build(mb, v)
    return mb.to_object(v["object"], mats, collection, soft=SOFT)


def _frame(direction, up_hint=Z):
    f = direction.normalized()
    u = (up_hint - f * up_hint.dot(f))
    if u.length < 1e-6:
        u = Vector((1, 0, 0))
    u.normalize()
    r = f.cross(u)
    return f, u, r


class Plant:
    def __init__(self, ctx):
        self.ctx = ctx
        self.c = ctx.color
        plant = ctx.spec["plant"]
        self.soil_z = plant["soil_z"]
        self.internodes = plant["internodes"]
        self.golden = math.radians(plant["phyllotaxis_deg"])
        self.stake_pos = Vector(plant["stake_pos"])
        self.stake_r = plant["stake_r"]
        self.seed = plant["seed"]

    # ------------------------------------------------------------ yaprak

    def leaflet(self, mb, base, direction, length, width, colors, seed, serrate=True, cup=0.10,
                droop=0.14, rows=7):
        """Tek yaprakçık: ortası (orta damar) açık renkli, kenarları tırtıklı, hafif çanak ve sarkık.
        colors: (koyu, normal, açık) lineer RGBA."""
        f, u, r = _frame(direction)
        cols = (-1.0, -0.5, 0.0, 0.5, 1.0)
        dark, mid, light = colors
        vein = lerp_col(light, self.c("leaf_vein"), 0.5)
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

    def leaf_colors(self, age, n_nodes, seed):
        """Genç yaprak açık, yaşlı koyu; en alttakiler hafif solgun."""
        c = self.c
        t = min(1.0, age / 5.0)
        dark = lerp_col(c("leaf"), c("leaf_dark"), t)
        mid = lerp_col(c("leaf_light"), c("leaf"), t * 0.9 + 0.1)
        light = c("leaf_light")
        if age >= 10:
            k = 0.35
            dark, mid = lerp_col(dark, c("leaf_old"), k), lerp_col(mid, c("leaf_old"), k)
        j = nz((seed, 0, 0), 1.0, seed) * 0.08
        return (lerp_col(dark, light, j), lerp_col(mid, light, j), light)

    def compound_leaf(self, mb, start, azimuth, length, age, n_nodes, seed):
        """Bileşik yaprak: sap (rachis) + karşılıklı yaprakçık çiftleri + uç yaprakçık."""
        c = self.c
        elev = math.radians(max(6.0, 50.0 - 12.0 * age))     # yaşlı yapraklar yataya iner, sarkmaz
        d = Vector((math.cos(azimuth), math.sin(azimuth), 0))
        d3 = d * math.cos(elev) + Z * math.sin(elev)
        droop = 0.12 if age < 1 else max(-0.18, -0.04 - 0.035 * age)
        p1 = start + d3 * length * 0.42
        p2 = p1 + d * length * 0.58 + Z * length * droop
        pts = resample([start, p1, p2], 9)
        r0 = max(0.0007, 0.0016 * min(1.0, length / 0.1))
        stem, stem_light = c("stem"), c("stem_light")
        tube(mb, pts, [r0 * (1 - 0.55 * k / 8) for k in range(9)], 4,
             lambda u, co: lerp_col(stem, stem_light, u), cap_end=False, mat="stem")

        colors = self.leaf_colors(age, n_nodes, seed)
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
                self.leaflet(mb, p, dirv, L, L * 0.40, colors, seed * 7 + k * 2 + (sgn > 0))
        # büyük çiftlerin arasındaki minik ara yaprakçıklar (domatese özgü)
        if pairs >= 2:
            for k in range(len(spots) - 1):
                p, tan = at((spots[k] + spots[k + 1]) * 0.5)
                side = tan.cross(Z).normalized()
                for sgn in (1, -1):
                    dirv = side * sgn * 0.8 + tan * 0.6
                    L = length * 0.1
                    self.leaflet(mb, p, dirv, L, L * 0.5, colors, seed * 13 + k * 2 + (sgn > 0),
                                 serrate=False, rows=4)
        p, tan = at(1.0)
        L = length * 0.40
        self.leaflet(mb, pts[-1] - tan * L * 0.05, tan + Vector((0, 0, -0.1)), L, L * 0.42, colors,
                     seed * 7 + 9)

    def cotyledons(self, mb, top, size, age, seed):
        """İki karşılıklı, düz kenarlı uzun çenek yaprağı; yaşlandıkça sararır."""
        c = self.c
        base_cols = (c("leaf"), c("leaf_light"), c("leaf_vein"))
        cols = tuple(lerp_col(col, c("leaf_old"), age * 0.7) for col in base_cols)
        for k in (0, 1):
            az = math.radians(25 + 180 * k)
            d = Vector((math.cos(az), math.sin(az), 0.35 - 0.45 * age))
            self.leaflet(mb, top, d, 0.030 * size, 0.0065 * size, cols, seed + k, serrate=False, cup=0.15,
                         droop=0.1 + 0.2 * age, rows=5)

    # ------------------------------------------------------------ çiçek, tomurcuk, meyve

    def calyx(self, mb, top, axis, radius, count=5, curl=0.25):
        """Yıldız şeklinde yeşil çanak yapraklar (sepal)."""
        _, u, r = _frame(axis)
        col = self.c("sepal")
        tip_col = lerp_col(col, self.c("leaf_light"), 0.4)
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

    def flower(self, mb, center, size):
        """Aşağı bakan sarı yıldız çiçek: geriye kıvrık 6 taç yaprak + başçık konisi + çanak."""
        c = self.c
        axis = Vector((0, 0, -1))     # çiçeğin baktığı yön
        _, u, r = _frame(axis)
        bm = mb.bm
        base_c, mid_c, tip_c = c("petal_base"), c("petal"), lerp_col(c("petal"), c("petal_tip"), 0.4)
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
        cone_col = c("anther")
        ring = [bm.verts.new(center + (u * math.cos(2 * math.pi * k / 6) + r * math.sin(2 * math.pi * k / 6))
                             * size * 0.13) for k in range(6)]
        tip = bm.verts.new(center + axis * size * 0.5)
        for k in range(6):
            mb.face([ring[k], ring[(k + 1) % 6], tip], "petal", [cone_col] * 3)
        self.calyx(mb, center + axis * -size * 0.02, -axis, size * 0.55, count=5, curl=-0.4)

    def bud(self, mb, center, size):
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
        c_top, c_bot = self.c("sepal"), lerp_col(self.c("sepal"), self.c("petal"), 0.6)
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

    def fruit_color(self, ripeness, shoulder, co, seed):
        """Olgunluk: yeşil → turuncu → kırmızı; yarı olgunda sap çevresi (omuz) yeşil kalır."""
        c = self.c
        if ripeness < 0.5:
            col = lerp_col(c("fruit_green"), c("fruit_orange"), ripeness * 2)
        else:
            col = lerp_col(c("fruit_orange"), c("fruit_red"), (ripeness - 0.5) * 2)
        if ripeness > 0.95:
            col = lerp_col(col, c("fruit_red_deep"), 0.35)
        col = lerp_col(col, c("fruit_green"), shoulder * (1 - ripeness) * 0.8)
        return lerp_col(col, c("fruit_highlight"), max(0.0, nz(co, 70, seed)) * 0.12)

    def fruit(self, mb, top, radius, ripeness, seed):
        """Hafif basık, dilimli (rib) meyve; tepe çukurunda yıldız çanak."""
        bm = mb.bm
        big = radius > 0.012
        segs, rings_n = (self.ctx.style.seg(18), 11) if big else (self.ctx.style.seg(12), 7)
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
            return self.fruit_color(ripeness, max(0.0, 1 - ph / 1.1), v.co, seed)

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
        self.calyx(mb, top - Z * radius * 0.08, -Z, radius * (0.9 if big else 1.2), count=5 if big else 5,
                   curl=-0.35)

    def truss(self, mb, start, azimuth, items, seed):
        """Salkım: gövdeden çıkan kıvrık sap; öğeler sırayla iki yana sapçıklarla dizilir."""
        c = self.c
        d = Vector((math.cos(azimuth), math.sin(azimuth), 0))
        big = any(it[0] == "fruit" and it[1] > 0.012 for it in items)
        length = 0.075 if big else 0.05
        pts = resample([start, start + d * length * 0.45 + Z * 0.012,
                        start + d * length - Z * (0.02 if big else 0.004)], 8)
        stem, stem_light = c("stem"), c("stem_light")
        tube(mb, pts, [0.0018 * (1 - 0.5 * k / 7) for k in range(8)], 5,
             lambda u, co: lerp_col(stem, stem_light, u), cap_end=True, mat="stem")
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
                 lambda u, co: stem, cap_end=False, mat="stem")
            if kind == "fruit":
                self.fruit(mb, end, item[1], item[2], seed * 11 + k)
            elif kind == "flower":
                self.flower(mb, end - Z * 0.002, item[1])
            else:
                self.bud(mb, end - Z * item[1] * 0.6, item[1])

    # ------------------------------------------------------------ çubuk ve ip

    def stake(self, mb, height):
        """Bambu destek çubuğu; height: topraktan yukarı boy (m)."""
        c = self.c
        soil_z = self.soil_z
        bottom = self.stake_pos + Vector((0, 0, soil_z - 0.09))
        top = self.stake_pos + Vector((0, 0, soil_z + height))
        n = 26
        pts = [bottom.lerp(top, k / (n - 1)) for k in range(n)]
        bamboo, node_c, hi = c("bamboo"), c("bamboo_node"), c("bamboo_highlight")

        def col(u, co):
            z = co.z - soil_z
            node = abs(((z / 0.13) % 1.0) - 0.5) > 0.46        # her 13 cm'de boğum
            base = node_c if node else bamboo
            return lerp_col(base, hi, max(0.0, nz(co, 90, 13)) * 0.3)

        tube(mb, pts, [self.stake_r] * n, 6, col, cap_end=True, mat="stake")

    def tie(self, mb, stem_point, z):
        """Gövdeyi çubuğa bağlayan ip halkası (gövde ve çubuğu birlikte saran elips)."""
        a = Vector((stem_point.x, stem_point.y, z))
        b = Vector((self.stake_pos.x, self.stake_pos.y, z))
        mid = (a + b) * 0.5
        axis = (b - a)
        half = axis.length * 0.5 + 0.007
        axis.normalize()
        perp = axis.cross(Z)
        n = 14
        pts = [mid + axis * math.cos(2 * math.pi * k / n) * half + perp * math.sin(2 * math.pi * k / n) * 0.0075
               for k in range(n + 1)]
        twine = self.c("twine")
        tube(mb, pts, [0.0011] * (n + 1), 4, lambda u, co: twine, cap_end=False, mat="stake")

    # ------------------------------------------------------------ bitki

    def node_layout(self, p):
        """Düğüm noktaları: (konum, azimut). Çenek düğümü 0. indekste."""
        soil_z, internodes = self.soil_z, self.internodes
        pts = [Vector((0, 0, soil_z - 0.01))]
        z = soil_z + p["hypo"]
        lean = 0.014 if p["stake"] else 0.0
        nodes = [(Vector((0, 0, z)), 0.0)]
        for i in range(1, p["nodes"] + 1):
            z += internodes[i - 1] * p["scale"]
            az = i * self.golden + 0.35
            k = (z - soil_z) / 0.65
            kink = Vector((math.cos(az + math.pi), math.sin(az + math.pi), 0)) * 0.004 * min(1.0, i / 3)
            nodes.append((Vector((0, lean * k, z)) + kink, az))
        pts += [n[0] for n in nodes]
        tip_z = z + internodes[min(p["nodes"], len(internodes) - 1)] * p["scale"] * 0.5
        pts.append(Vector((nodes[-1][0].x * 0.5, lean * (tip_z - soil_z) / 0.65, tip_z)))
        return nodes, pts

    def build(self, mb, p):
        c = self.c
        seed = self.seed
        nodes, stem_pts = self.node_layout(p)

        # gövde
        pts = resample(stem_pts, max(8, len(stem_pts) * 4))
        total = len(pts)
        radii = [p["r_base"] * (1 - 0.7 * (k / (total - 1)) ** 1.2) for k in range(total)]
        stem_dark, stem, stem_light = c("stem_dark"), c("stem"), c("stem_light")
        tube(mb, pts, radii, self.ctx.style.seg(p["sides"]),
             lambda u, co: lerp_col(lerp_col(stem_dark, stem, u * 1.6), stem_light,
                                    max(0.0, u - 0.6) + max(0.0, nz(co, 120, seed)) * 0.15),
             cap_end=True, mat="stem")

        # çenek yaprakları
        if p["cotyledon"]:
            self.cotyledons(mb, nodes[0][0], p["cotyledon"], p["cotyledon_age"], seed)

        # bileşik yapraklar: yaş = (düğüm sayısı - düğüm indeksi)
        n = p["nodes"]
        for i in range(1, n + 1):
            pos, az = nodes[i]
            age = n - i
            length = p["lmax"] * min(1.0, 0.3 + 0.18 * age)
            self.compound_leaf(mb, pos, az, length, age, n, seed + i)
        # büyüme ucunda açılmamış minik yaprak
        tip_pos = pts[-1]
        self.leaflet(mb, tip_pos, Vector((0.3, 0.2, 1.0)), p["lmax"] * 0.12, p["lmax"] * 0.05,
                     (c("leaf"), c("leaf_light"), c("leaf_vein")), seed + 99, cup=0.5, droop=-0.1, rows=4)

        # salkımlar: düğüm ile bir üstteki arasından, yaprağın tersine
        for node_key, items in p.get("trusses", {}).items():
            node_i = int(node_key)
            pos, az = nodes[node_i]
            above = nodes[min(node_i + 1, n)][0]
            self.truss(mb, pos.lerp(above, 0.45), az + math.pi * 0.9, items, seed + node_i)

        # çubuk ve ip bağları
        if p["stake"]:
            self.stake(mb, p["stake"])
            plant_top = stem_pts[-1].z
            for h in (0.10, 0.27, 0.44):
                z = self.soil_z + h
                if z < plant_top - 0.04:
                    k = min(range(total), key=lambda i: abs(pts[i].z - z))
                    self.tie(mb, pts[k], z)
