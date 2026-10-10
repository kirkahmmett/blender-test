"""Kutu sandık ailesi (PS1 tarzı): gövde + 12 kenar kirişi + 4 yanda çapraz destek,
prosedürel piksel tahta dokusu, vertex color ile kiriş tonu ve sahte AO.

Varyant alanları: size, beam, protrude (m), tex_px, tex_world, planks, seed,
body_tint, beam_tint, wood (doku paleti, sRGB 0..1 üçlüleri).
"""

import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

TEX_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "props", "textures")


def build(ctx, v, collection):
    name = v["object"]
    rng = random.Random(v["seed"])      # sıra önemli: doku, kiriş ofsetleri, UV kaydırmaları
    img = _wood_texture(ctx, v, name, rng)
    mat = _material(name, img)

    bm, parts = _mesh(v, rng)
    _uv_and_color(bm, parts, v, rng)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.color_attributes.active_color_name = "Col"
    me.color_attributes.render_color_index = me.color_attributes.find("Col")
    me.materials.append(mat)
    for poly in me.polygons:
        poly.use_smooth = False

    obj = bpy.data.objects.new(name, me)
    collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    return obj


# ---------------------------------------------------------------- doku

def _wood_texture(ctx, v, name, rng):
    """Yatay tahtalar: tahta başına ton farkı, damar çizgileri, alt kenarda koyu derz."""
    palette = [ctx.style.rgb(tuple(c)) for c in v["wood"]]
    tex_px, planks = v["tex_px"], v["planks"]
    plank_h = tex_px // planks
    px = [0.0] * (tex_px * tex_px * 4)
    for p in range(planks):
        base = palette[p % len(palette)]
        seam_x = rng.randrange(tex_px)
        knot = (rng.randrange(tex_px), p * plank_h + rng.randrange(4, plank_h - 4)) if rng.random() < 0.6 else None
        row_shade = [0.88 + 0.2 * rng.random() for _ in range(plank_h)]
        phase = rng.random() * 6.28
        for ry in range(plank_h):
            y = p * plank_h + ry
            for x in range(tex_px):
                if ry == 0:
                    s = 0.35                                   # derz
                elif x == seam_x:
                    s = 0.55                                   # tahta eki
                else:
                    wave = math.sin(x * 0.35 + ry * 0.9 + phase) * 0.06
                    s = row_shade[ry] + wave
                    if ry == 1:
                        s *= 1.12                              # derzin üstünde parlak kenar
                    if knot and (x - knot[0]) ** 2 + ((y - knot[1]) * 2) ** 2 < 6:
                        s *= 0.6                               # budak
                i = (y * tex_px + x) * 4
                px[i:i + 4] = [min(1.0, base[0] * s), min(1.0, base[1] * s), min(1.0, base[2] * s), 1.0]
    img = bpy.data.images.new(name, tex_px, tex_px, alpha=False)
    img.pixels[:] = px
    os.makedirs(TEX_DIR, exist_ok=True)
    img.filepath_raw = os.path.join(TEX_DIR, name + ".png")
    img.file_format = "PNG"
    img.save()
    img.filepath = img.filepath_raw
    return img


def _material(name, img):
    mat = bpy.data.materials.new(name)
    if mat.node_tree is None:   # Blender 5.x: yeni malzemede düğüm ağacı zaten var
        mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Roughness"].default_value = 1.0
    tex = nt.nodes.new("ShaderNodeTexImage")
    tex.image = img
    tex.interpolation = "Closest"
    nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    return mat


# ---------------------------------------------------------------- geometri

def _add_box(bm, parts, center, size, rot=None, long_axis=None, tint=(1.0, 1.0, 1.0), v_offset=0.0):
    """Döndürülmüş kutu ekle; UV/renk için parça bilgisini kaydet."""
    rot = rot or Matrix.Identity(3)
    res = bmesh.ops.create_cube(bm, size=1.0)
    verts = res["verts"]
    bmesh.ops.scale(bm, vec=Vector(size), verts=verts)
    bmesh.ops.transform(bm, matrix=rot.to_4x4(), verts=verts)
    bmesh.ops.translate(bm, vec=Vector(center), verts=verts)
    faces = {f for v in verts for f in v.link_faces}
    parts.append(dict(faces=faces, center=Vector(center), rot=rot, long_axis=long_axis,
                      tint=tint, v_offset=v_offset))


def _mesh(v, rng):
    size, beam, protrude = v["size"], v["beam"], v["protrude"]
    planks, tex_world = v["planks"], v["tex_world"]
    body_tint, beam_tint = tuple(v["body_tint"]), tuple(v["beam_tint"])

    def beam_v_offset():
        """Kirişi tek bir tahtanın içine oturt (üstünden derz geçmesin)."""
        k = rng.randrange(planks)
        return k / planks + 0.03 + (beam / tex_world) / 2

    bm = bmesh.new()
    parts = []
    h = size / 2
    body = size - 2 * protrude
    _add_box(bm, parts, (0, 0, h), (body, body, body), tint=body_tint)

    # 12 kenar kirişi
    c = h - beam / 2
    for sy in (-1, 1):
        for sz in (-1, 1):
            _add_box(bm, parts, (0, sy * c, h + sz * c), (size, beam, beam), long_axis=0,
                     tint=beam_tint, v_offset=beam_v_offset())
            _add_box(bm, parts, (sy * c, 0, h + sz * c), (beam, size, beam), long_axis=1,
                     tint=beam_tint, v_offset=beam_v_offset())
    for sx in (-1, 1):
        for sy in (-1, 1):
            _add_box(bm, parts, (sx * c, sy * c, h), (beam, beam, size), long_axis=2,
                     tint=beam_tint, v_offset=beam_v_offset())

    # 4 yanda çapraz destek (yönler sırayla değişir)
    inner = size - 2 * beam
    diag = inner * math.sqrt(2)
    up = Vector((0, 0, 1))
    for i, n in enumerate([Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((-1, 0, 0)), Vector((0, -1, 0))]):
        t = up.cross(n)
        x_axis = (t + up * (1 if i % 2 == 0 else -1)).normalized()
        z_axis = x_axis.cross(n)
        rot = Matrix((x_axis, n, z_axis)).transposed()
        center = n * (h - protrude / 2) + Vector((0, 0, h))
        _add_box(bm, parts, center, (diag, protrude, beam), rot=rot, long_axis=0,
                 tint=beam_tint, v_offset=beam_v_offset())
    return bm, parts


def _uv_and_color(bm, parts, v, rng):
    uv_layer = bm.loops.layers.uv.verify()
    col_layer = bm.loops.layers.float_color.new("Col")
    scale = 1.0 / v["tex_world"]
    size = v["size"]
    for part in parts:
        inv = part["rot"].transposed()
        u_shift = rng.random()
        for f in part["faces"]:
            n_local = inv @ f.normal
            axis_n = max(range(3), key=lambda a: abs(n_local[a]))
            plane = [a for a in range(3) if a != axis_n]
            la = part["long_axis"]
            if la in plane:
                u_ax = la
            else:
                # gövde: yan yüzlerde tahtalar yatay (U yatay eksen)
                u_ax = plane[0] if plane[0] != 2 else plane[1]
            v_ax = plane[1] if u_ax == plane[0] else plane[0]
            for loop in f.loops:
                p = inv @ (loop.vert.co - part["center"])
                loop[uv_layer].uv = (p[u_ax] * scale + u_shift, p[v_ax] * scale + part["v_offset"])
                # sahte AO: tabana doğru koyulaş
                shade = 0.7 + 0.3 * min(1.0, loop.vert.co.z / size)
                tr, tg, tb = part["tint"]
                loop[col_layer] = (tr * shade, tg * shade, tb * shade, 1.0)
