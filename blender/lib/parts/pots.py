"""Tornalanmış (lathe) saksı + toprak. Saksılar kendi spec'lerinde durur (blender/specs/parts/)
ve birden çok asset tarafından paylaşılır; asset spec'inde pot = "@parts/<saksı>".

Saksı spec'i:
    material = "porcelain"      # Blender malzeme soneki (Godot pastel preset'i buna göre)
    roughness = 0.2
    segments = 32
    scale = [0.18, 0.13]        # profil yarıçapı çarpanı (X, Y); oval saksı için farklı
    profile = [[r, z], ...]     # dış duvardan iç duvara; ilk halka taban
    color_mode = "glaze" | "terracotta"
    [colors]                    # moda göre: dark/mid/light
    [glaze] rim_t, inner_rings, foot_mul      # sırlı: yükseklik gradyanı + açık kenar
    [terracotta] band, shadow_ring, inner_rings, cap_mul, noise_freq, noise_seed
    [feet] count/angles, radius, ...          # isteğe bağlı ayaklar
    [soil] z, center_dz, profile=[[r, dz]...], mode = "moss" | "plain", renkler, gürültü

Renk modlarının matematiği bonsai/domates script'lerindekiyle birebir aynıdır (çıktı bayt
bayt korunur); yeni bir saksı türü yeni bir mod ya da mevcut modların parametreleridir.
"""

import math

from mathutils import Vector, noise

from meshkit import lerp_col


def nz(p, scale, seed):
    return noise.noise(Vector(p) * scale + Vector((seed * 1.37, seed * 2.11, seed * 0.73)))


def _rings(bm, profile, sx, sy, n):
    return [[bm.verts.new((sx * r * math.cos(2 * math.pi * j / n), sy * r * math.sin(2 * math.pi * j / n), z))
             for j in range(n)] for r, z in profile]


def build(mb, ctx, pot, moss_amount=0.0):
    """Saksıyı ve toprağı mb'ye ekle. ctx: renk/stil; moss_amount: yosun (0..1), moss modunda."""
    n = ctx.style.seg(pot["segments"], minimum=8)
    sx, sy = pot["scale"]
    profile = pot["profile"]
    zs = [z for _, z in profile]
    z0, ztop = zs[0], max(zs)
    mat = pot["material"]
    C = pot["colors"]

    def col(key, mul=1.0):
        return ctx.color(C[key], mul)

    rings = _rings(mb.bm, profile, sx, sy, n)
    if pot["color_mode"] == "glaze":
        g = pot["glaze"]
        inner_from = len(profile) - g["inner_rings"]

        def glaze(z, inner=False):
            t = (z - z0) / (ztop - z0)
            c = lerp_col(col("dark"), col("mid"), t * 1.4)
            if t > g["rim_t"] or inner:
                c = lerp_col(c, col("light"), 0.6)
            return c

        for k in range(len(rings) - 1):
            a, b = rings[k], rings[k + 1]
            for j in range(n):
                j2 = (j + 1) % n
                inner = k >= inner_from
                ca, cb = glaze(zs[k], inner), glaze(zs[k + 1], inner)
                mb.face([a[j], a[j2], b[j2], b[j]], mat, [ca, ca, cb, cb])
        cap = glaze(z0)
    else:
        tc = pot["terracotta"]
        inner_from = len(profile) - tc["inner_rings"]
        band_lo, band_hi = tc["band"]

        def terracotta(z, k, co):
            t = (z - z0) / (ztop - z0)
            c = lerp_col(col("dark"), col("mid"), t * 1.5)
            if band_lo <= k <= band_hi:                      # kenar bandı biraz açık
                c = lerp_col(c, col("light"), 0.45)
            if k == tc["shadow_ring"]:                       # bandın altındaki gölge
                c = lerp_col(c, col("dark"), 0.5)
            if k >= inner_from:
                c = lerp_col(c, col("dark"), 0.35)
            return lerp_col(c, col("light"), max(0.0, nz(co, tc["noise_freq"], tc["noise_seed"])) * 0.25)

        for k in range(len(rings) - 1):
            a, b = rings[k], rings[k + 1]
            for j in range(n):
                j2 = (j + 1) % n
                vs = [a[j], a[j2], b[j2], b[j]]
                ks = [k, k, k + 1, k + 1]
                mb.face(vs, mat, [terracotta(zs[kk], kk, v.co) for kk, v in zip(ks, vs)])
        cap = col("dark", tc["cap_mul"])

    # taban kapağı
    center = mb.bm.verts.new((0, 0, z0))
    base = rings[0]
    for j in range(n):
        mb.face([center, base[(j + 1) % n], base[j]], mat, [cap, cap, cap])

    if "feet" in pot:
        _feet(mb, ctx, pot, mat, sx, sy, z0)
    _soil(mb, ctx, pot["soil"], sx, sy, n, moss_amount)


def _feet(mb, ctx, pot, mat, sx, sy, z0):
    """Saksı ayakları (üst kapaksız, tabana gömülü kısa oval silindirler)."""
    f = pot["feet"]
    bm = mb.bm
    for ang in f["angles"]:
        cx = sx * f["ring"] * math.cos(math.radians(ang))
        cy = sy * f["ring"] * math.sin(math.radians(ang))
        m = f["sides"]
        r = f["radius"]
        top = [bm.verts.new((cx + r * math.cos(2 * math.pi * j / m), cy + r * 0.8 * math.sin(2 * math.pi * j / m), z0 + 0.002)) for j in range(m)]
        bot = [bm.verts.new((cx + r * 0.85 * math.cos(2 * math.pi * j / m), cy + r * 0.68 * math.sin(2 * math.pi * j / m), 0.0)) for j in range(m)]
        cf = ctx.color(pot["colors"]["dark"], f["color_mul"])
        for j in range(m):
            j2 = (j + 1) % m
            mb.face([bot[j], bot[j2], top[j2], top[j]], mat, [cf] * 4)
        mb.face(list(reversed(bot)), mat, [cf] * m)


def _soil(mb, ctx, soil, sx, sy, n, moss_amount):
    """Hafif tümsekli toprak. moss: yosun lekeli (moss_amount 0..1); plain: koyu-açık lekeler."""
    bm = mb.bm
    sz = soil["z"]
    profile = [(r, sz + dz) for r, dz in soil["profile"]]

    if soil["mode"] == "moss":
        seed = soil["seed"]

        def soil_col(co):
            v = noise.noise(Vector((co.x * soil["freq"], co.y * soil["freq"], seed)))
            base = lerp_col(ctx.color(soil["dark"]), ctx.color(soil["mid"]), 0.5 + v)
            m = noise.noise(Vector((co.x * soil["moss_freq"] + 5, co.y * soil["moss_freq"], seed * 2)))
            moss = m * 1.5 + (moss_amount - 0.5) * 1.2
            return lerp_col(base, ctx.color(soil["moss"]), moss * 2.0)
    else:
        def soil_col(co):
            return lerp_col(ctx.color(soil["dark"]), ctx.color(soil["mid"]), 0.5 + nz(co, soil["freq"], soil["seed"]))

    rings = _rings(bm, profile, sx, sy, n)
    for k in range(len(rings) - 1):
        a, b = rings[k], rings[k + 1]
        for j in range(n):
            j2 = (j + 1) % n
            vs = [a[j], a[j2], b[j2], b[j]]
            mb.face(vs, "soil", [soil_col(v.co) for v in vs])
    center = bm.verts.new((0, 0, sz + soil["center_dz"]))
    last = rings[-1]
    for j in range(n):
        vs = [center, last[j], last[(j + 1) % n]]
        mb.face(vs, "soil", [soil_col(v.co) for v in vs])
