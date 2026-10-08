"""Ahşap sandık üretici (PS1 tarzı prop).

Arka planda çalıştır (açık Blender oturumuna dokunmaz):
    blender --background --factory-startup --python blender/props/make_crate.py -- [preview.png]

Çıktılar:
    blender/props/wooden_crate.blend          kaynak dosya (Append ile alınabilir)
    blender/props/textures/wooden_crate.png   64x64 tahta dokusu
    assets/models/wooden_crate.glb            Godot'a giden model
"""

import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

NAME = "wooden_crate"
HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(HERE))
TEX_DIR = os.path.join(HERE, "textures")

SIZE = 0.8          # dış ölçü (m)
BEAM = 0.08         # kiriş kesiti (m)
PROTRUDE = 0.02     # kirişlerin gövdeden taşma payı (m)
TEX_PX = 64
TEX_WORLD = 0.5     # doku bir tekrarda kaç metreyi kaplar
PLANKS = 4          # dokudaki tahta sayısı

BODY_TINT = (1.0, 1.0, 1.0)
BEAM_TINT = (0.72, 0.6, 0.5)

rng = random.Random(7)


# ---------------------------------------------------------------- doku

def make_wood_texture():
    """Yatay tahtalar: tahta başına ton farkı, damar çizgileri, alt kenarda koyu derz."""
    palette = [(0.62, 0.43, 0.26), (0.56, 0.38, 0.22), (0.66, 0.47, 0.29), (0.52, 0.35, 0.21)]
    plank_h = TEX_PX // PLANKS
    px = [0.0] * (TEX_PX * TEX_PX * 4)
    for p in range(PLANKS):
        base = palette[p % len(palette)]
        seam_x = rng.randrange(TEX_PX)
        knot = (rng.randrange(TEX_PX), p * plank_h + rng.randrange(4, plank_h - 4)) if rng.random() < 0.6 else None
        row_shade = [0.88 + 0.2 * rng.random() for _ in range(plank_h)]
        phase = rng.random() * 6.28
        for ry in range(plank_h):
            y = p * plank_h + ry
            for x in range(TEX_PX):
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
                i = (y * TEX_PX + x) * 4
                px[i:i + 4] = [min(1.0, base[0] * s), min(1.0, base[1] * s), min(1.0, base[2] * s), 1.0]
    img = bpy.data.images.new(NAME, TEX_PX, TEX_PX, alpha=False)
    img.pixels[:] = px
    os.makedirs(TEX_DIR, exist_ok=True)
    img.filepath_raw = os.path.join(TEX_DIR, NAME + ".png")
    img.file_format = "PNG"
    img.save()
    img.filepath = img.filepath_raw
    return img


def make_material(img):
    mat = bpy.data.materials.new(NAME)
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

def add_box(bm, parts, center, size, rot=None, long_axis=None, tint=BODY_TINT, v_offset=0.0):
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


def beam_v_offset():
    """Kirişi tek bir tahtanın içine oturt (üstünden derz geçmesin)."""
    k = rng.randrange(PLANKS)
    return k / PLANKS + 0.03 + (BEAM / TEX_WORLD) / 2


def build_mesh():
    bm = bmesh.new()
    parts = []
    h = SIZE / 2
    body = SIZE - 2 * PROTRUDE
    add_box(bm, parts, (0, 0, h), (body, body, body))

    # 12 kenar kirişi
    c = h - BEAM / 2
    for sy in (-1, 1):
        for sz in (-1, 1):
            add_box(bm, parts, (0, sy * c, h + sz * c), (SIZE, BEAM, BEAM), long_axis=0,
                    tint=BEAM_TINT, v_offset=beam_v_offset())
            add_box(bm, parts, (sy * c, 0, h + sz * c), (BEAM, SIZE, BEAM), long_axis=1,
                    tint=BEAM_TINT, v_offset=beam_v_offset())
    for sx in (-1, 1):
        for sy in (-1, 1):
            add_box(bm, parts, (sx * c, sy * c, h), (BEAM, BEAM, SIZE), long_axis=2,
                    tint=BEAM_TINT, v_offset=beam_v_offset())

    # 4 yanda çapraz destek (yönler sırayla değişir)
    inner = SIZE - 2 * BEAM
    diag = inner * math.sqrt(2)
    up = Vector((0, 0, 1))
    for i, n in enumerate([Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((-1, 0, 0)), Vector((0, -1, 0))]):
        t = up.cross(n)
        x_axis = (t + up * (1 if i % 2 == 0 else -1)).normalized()
        z_axis = x_axis.cross(n)
        rot = Matrix((x_axis, n, z_axis)).transposed()
        center = n * (h - PROTRUDE / 2) + Vector((0, 0, h))
        add_box(bm, parts, center, (diag, PROTRUDE, BEAM), rot=rot, long_axis=0,
                tint=BEAM_TINT, v_offset=beam_v_offset())
    return bm, parts


def assign_uv_and_color(bm, parts):
    uv_layer = bm.loops.layers.uv.verify()
    col_layer = bm.loops.layers.float_color.new("Col")
    scale = 1.0 / TEX_WORLD
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
                shade = 0.7 + 0.3 * min(1.0, loop.vert.co.z / SIZE)
                tr, tg, tb = part["tint"]
                loop[col_layer] = (tr * shade, tg * shade, tb * shade, 1.0)


# ---------------------------------------------------------------- ana akış

def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.scale_length = 1.0

    img = make_wood_texture()
    mat = make_material(img)

    bm, parts = build_mesh()
    assign_uv_and_color(bm, parts)
    me = bpy.data.meshes.new(NAME)
    bm.to_mesh(me)
    bm.free()
    me.color_attributes.active_color_name = "Col"
    me.color_attributes.render_color_index = me.color_attributes.find("Col")
    me.materials.append(mat)
    for poly in me.polygons:
        poly.use_smooth = False

    coll = bpy.data.collections.new(NAME)
    scene.collection.children.link(coll)
    obj = bpy.data.objects.new(NAME, me)
    coll.objects.link(obj)
    bpy.context.view_layer.objects.active = obj

    blend_path = os.path.join(HERE, NAME + ".blend")
    bpy.ops.wm.save_as_mainfile(filepath=blend_path, relative_remap=True)

    sys.path.insert(0, os.path.join(PROJECT_DIR, "blender"))
    import export_glb
    res = export_glb.export_glb(NAME, source="collection", collection_name=NAME, project_dir=PROJECT_DIR)
    print("[make_crate] blend:", blend_path)
    print("[make_crate] glb:", res)

    # önizleme render'ı (kaydedilmez)
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if argv:
        render_preview(argv[0], obj)


def render_preview(path, obj):
    scene = bpy.context.scene
    cam_data = bpy.data.cameras.new("preview_cam")
    cam = bpy.data.objects.new("preview_cam", cam_data)
    scene.collection.objects.link(cam)
    cam.location = (1.6, -1.9, 1.5)
    direction = Vector((0, 0, SIZE / 2)) - cam.location
    cam.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.engine = "BLENDER_WORKBENCH"
    scene.display.shading.light = "STUDIO"
    scene.display.shading.color_type = "TEXTURE"
    scene.render.resolution_x = 480
    scene.render.resolution_y = 480
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    print("[make_crate] preview:", path)


main()
