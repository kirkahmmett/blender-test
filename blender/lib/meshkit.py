"""Mesh kiti: prop üreticilerinin ortak geometri ve renk yardımcıları.

- srgb / lerp_col: pastel paletler için renk (Blender color attribute lineer saklar)
- make_material: Base Color = "Col" color attribute olan malzeme
- MeshBuilder: bmesh + malzeme indeksli yüzler + köşe (loop) başına renk
- catmull_rom / sample_at / resample: noktalardan geçen yumuşak eğriler
- tube: eğri boyunca incelen tüp (gövde, dal, sap, kök)
- render_preview: EEVEE önizleme render'ı (sahneye kaydedilmez)
"""

import math

import bmesh
import bpy
from mathutils import Vector


# ---------------------------------------------------------------- renk

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


# ---------------------------------------------------------------- malzeme + mesh

def make_material(name, roughness):
    """Base color = Color Attribute. Godot tarafında malzeme adı sonekine göre shader seçilir
    (PropStyle.PASTEL_PRESETS)."""
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

    def to_object(self, name, mat_list, collection, sharp_angle=50.0, soft=("foliage", "bark")):
        """soft: her zaman yumuşak gölgelenecek malzemeler (keskin kenar açısından muaf)."""
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
        soft_idx = {self.materials[m] for m in soft if m in self.materials}
        sharp = me.attributes.get("sharp_edge")
        if sharp:
            soft_verts = {v for p in me.polygons if p.material_index in soft_idx for v in p.vertices}
            for e in me.edges:
                if e.vertices[0] in soft_verts and e.vertices[1] in soft_verts:
                    sharp.data[e.index].value = False
        obj = bpy.data.objects.new(name, me)
        collection.objects.link(obj)
        return obj


def tri_count(obj):
    me = obj.data
    me.calc_loop_triangles()
    return len(me.loop_triangles)


# ---------------------------------------------------------------- eğriler

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


def tube(mb, pts, radii, sides, color_fn, ring_mod=None, cap_end=True, mat="bark"):
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
            mb.face(vs, mat, [color_fn(u, v.co) for u, v in zip(us, vs)])
    if cap_end:
        tip = bm.verts.new(pts[-1] + tangents[-1] * radii[-1] * 0.6)
        last = rings[-1]
        for j in range(sides):
            vs = [last[j], last[(j + 1) % sides], tip]
            mb.face(vs, mat, [color_fn(1.0, v.co) for v in vs])


# ---------------------------------------------------------------- önizleme

def render_preview(path, objs, front=False, tag="meshkit"):
    """EEVEE önizleme: yumuşak gökyüzü + güneş; kamera objelerin sınırlarına göre."""
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    corners = [o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    lo = Vector((min(c.x for c in corners), min(c.y for c in corners), min(c.z for c in corners)))
    hi = Vector((max(c.x for c in corners), max(c.y for c in corners), max(c.z for c in corners)))
    cx = (lo.x + hi.x) / 2
    width, height = hi.x - lo.x, hi.z - lo.z
    # uzun objelerde dikey kadraj; objeyi kadraja oturt (lens 50 mm, sensör 36 mm)
    portrait = len(objs) == 1 and height > width * 1.3
    res_x, res_y = (640, 900) if portrait else ((900 if len(objs) > 1 else 560), 560)
    cam_data = bpy.data.cameras.new("preview_cam")
    cam_data.lens = 50
    cam_data.sensor_fit = "AUTO"
    half = 18.0 / 50.0                       # uzun kenarın yarım açı tanjantı
    half_x = half if res_x >= res_y else half * res_x / res_y
    half_y = half if res_y > res_x else half * res_y / res_x
    depth = hi.y - lo.y
    dist = max(width / 2 / half_x, height / 2 / half_y) * 1.18 + depth * 0.5
    cam = bpy.data.objects.new("preview_cam", cam_data)
    scene.collection.objects.link(cam)
    target = Vector((cx, 0, (lo.z + hi.z) / 2))
    view = Vector((0.0, -1.0, 0.08)) if front else Vector((0.25, -1.0, 0.35))
    cam.location = target + view.normalized() * dist
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    scene.camera = cam
    scene.render.engine = "BLENDER_EEVEE"
    scene.view_settings.view_transform = "Standard"

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

    scene.render.resolution_x = res_x
    scene.render.resolution_y = res_y
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)
    for o in (cam, sun):
        bpy.data.objects.remove(o)
    scene.world = None
    print(f"[{tag}] preview:", path)
