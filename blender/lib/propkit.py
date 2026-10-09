"""Prop kiti: üretici script'lerin ortak parçaları.

Elle düzenleme koruması
-----------------------
Üretici script .blend'i kaydederken içeriğin parmak izini (fingerprint) dosyanın içine
yazar ("propkit_fingerprint" adlı Text bloğu; glTF ile export edilmez). Bir sonraki üretimden
önce guard_overwrite() dosyayı açar, parmak izini yeniden hesaplar ve kayıtlıyla uyuşmazsa
üretimi durdurur: kullanıcı dosyayı elle düzenlemiş demektir. Dosyayı yalnızca açıp kaydetmek (pencere düzeni vb.)
içeriği değiştirmediği için uyarı vermez.

Parmak izi: mesh objelerinin adı, dönüşümü, köşe/yüz/UV/renk verisi, malzeme düğümleri,
prop_* bilgileri ve malzemelerin kullandığı doku dosyalarının içeriği.
"""

import datetime
import hashlib
import os
import shutil

import bpy
import numpy as np

FINGERPRINT_KEY = "propkit_fingerprint"
LIB_DIR = os.path.dirname(os.path.abspath(__file__))
BLENDER_DIR = os.path.dirname(LIB_DIR)
PROJECT_DIR = os.path.dirname(BLENDER_DIR)
BACKUP_DIR = os.path.join(BLENDER_DIR, "props", "_backup")


class OverwriteRefused(Exception):
    pass


# ---------------------------------------------------------------- parmak izi

def _floats(h, values, digits=5):
    h.update(np.round(np.asarray(values, dtype=np.float64), digits).tobytes())


def _attr_array(collection, prop, width, dtype=np.float32):
    arr = np.empty(len(collection) * width, dtype=dtype)
    if len(collection):
        collection.foreach_get(prop, arr)
    return arr


def _hash_mesh(h, me):
    _floats(h, _attr_array(me.vertices, "co", 3))
    h.update(_attr_array(me.loops, "vertex_index", 1, np.int32).tobytes())
    h.update(_attr_array(me.polygons, "loop_total", 1, np.int32).tobytes())
    h.update(_attr_array(me.polygons, "material_index", 1, np.int32).tobytes())
    for uv in me.uv_layers:
        h.update(uv.name.encode())
        _floats(h, _attr_array(uv.data, "uv", 2))
    for attr in me.color_attributes:
        h.update(attr.name.encode())
        _floats(h, _attr_array(attr.data, "color", 4), 4)


def _hash_material(h, mat, seen_images):
    h.update(mat.name.encode())
    if not mat.node_tree:
        return
    for node in sorted(mat.node_tree.nodes, key=lambda n: n.name):
        h.update(f"{node.name}|{node.bl_idname}".encode())
        for sock in node.inputs:
            if sock.is_linked or not hasattr(sock, "default_value"):
                continue
            v = sock.default_value
            try:
                _floats(h, list(v), 4)
            except TypeError:
                h.update(repr(v).encode())
        img = getattr(node, "image", None)
        if img and img.name not in seen_images:
            seen_images.add(img.name)
            path = bpy.path.abspath(img.filepath)
            if os.path.isfile(path):
                with open(path, "rb") as f:
                    h.update(hashlib.sha256(f.read()).digest())
    for link in mat.node_tree.links:
        h.update(f"{link.from_node.name}.{link.from_socket.identifier}>"
                 f"{link.to_node.name}.{link.to_socket.identifier}".encode())


def fingerprint():
    """Açık dosyanın içerik parmak izi (UI/pencere durumundan bağımsız)."""
    h = hashlib.sha256()
    seen_images = set()
    for obj in sorted((o for o in bpy.data.objects if o.type == "MESH"), key=lambda o: o.name):
        h.update(obj.name.encode())
        # matrix_world değil: depsgraph güncellenmeden okunursa bayat kalır
        h.update((obj.parent.name if obj.parent else "").encode())
        _floats(h, [v for row in obj.matrix_basis for v in row])
        for key in sorted(k for k in obj.keys() if k.startswith("prop_")):
            h.update(f"{key}={obj[key]}".encode())
        _hash_mesh(h, obj.data)
        for slot in obj.material_slots:
            if slot.material:
                _hash_material(h, slot.material, seen_images)
    return h.hexdigest()


# ---------------------------------------------------------------- koruma

def guard_overwrite(blend_path, force=False):
    """blend_path elle düzenlendiyse OverwriteRefused fırlat. force=True ise önce yedekle.

    Not: dosyayı açar; çağıran sonra read_factory_settings ile temiz sahneye dönmeli.
    """
    if not os.path.isfile(blend_path):
        return
    bpy.ops.wm.open_mainfile(filepath=blend_path)
    text = bpy.data.texts.get(FINGERPRINT_KEY)
    stored = text.as_string().strip() if text else None
    current = fingerprint()
    if stored == current:
        return
    reason = ("parmak izi yok (propkit öncesi ya da elle oluşturulmuş)" if stored is None
              else "içerik son üretimden sonra değişmiş (elle düzenlenmiş)")
    if not force:
        raise OverwriteRefused(
            f"{os.path.basename(blend_path)}: {reason}. Üstüne yazılmadı.\n"
            f"  - Düzenlemeyi Godot'a almak için: blender --background {blend_path} "
            f"--python blender/tools/export_props.py\n"
            f"  - Yine de yeniden üretmek için --force (eski dosya {BACKUP_DIR} altına yedeklenir)")
    os.makedirs(BACKUP_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    base = os.path.splitext(os.path.basename(blend_path))[0]
    backup = os.path.join(BACKUP_DIR, f"{base}-{stamp}.blend")
    shutil.copy2(blend_path, backup)
    print(f"[propkit] --force: {reason}; yedek: {backup}")


def save_generated(blend_path):
    """Parmak izini sahneye yazıp kaydet."""
    text = bpy.data.texts.get(FINGERPRINT_KEY) or bpy.data.texts.new(FINGERPRINT_KEY)
    text.from_string(fingerprint())
    bpy.ops.wm.save_as_mainfile(filepath=blend_path, relative_remap=True)
    print("[propkit] blend:", blend_path)


# ---------------------------------------------------------------- export

def prop_objects():
    """Galeri bilgisi (prop_style) olan mesh objeleri, ada göre sıralı."""
    return sorted((o for o in bpy.data.objects if o.type == "MESH" and "prop_style" in o.keys()),
                  key=lambda o: o.name)


def export_props(objs=None, tri_budget=None, project_dir=PROJECT_DIR):
    """Her prop objesini kendi adıyla assets/models/<ad>.glb olarak, orijinde export et."""
    import sys
    if BLENDER_DIR not in sys.path:
        sys.path.insert(0, BLENDER_DIR)
    import export_glb
    if tri_budget:
        export_glb.TRI_BUDGET = tri_budget

    view_layer = bpy.context.view_layer
    results = []
    for obj in objs or prop_objects():
        saved = obj.location.copy()
        obj.location = (0, 0, 0)
        view_layer.update()
        for o in view_layer.objects:
            o.select_set(False)
        obj.select_set(True)
        view_layer.objects.active = obj
        try:
            res = export_glb.export_glb(obj.name, source="selection", project_dir=project_dir)
        finally:
            obj.location = saved
            view_layer.update()
        print("[propkit] glb:", res["path"], res["triangles"], res["warnings"])
        results.append(res)
    return results
