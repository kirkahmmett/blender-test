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


# guard_overwrite'ın "üretimden beri değişmemiş" bulduğu dosyalar: yol -> parmak izi
_unchanged_on_disk = {}

## Bu süreçte olanların yapılandırılmış kaydı (derleme hattı metin ayrıştırmak yerine bunu okur):
##   {"type": "refused", "blend", "reason"}    elle düzenlenmiş .blend korundu
##   {"type": "forced",  "blend", "backup"}    --force ile yedeklenip üstüne yazıldı
##   {"type": "blend",   "path", "saved"}      .blend kaydı (saved=False: içerik aynıydı)
##   {"type": "glb",     "name", "path", "sha256", "changed", "triangles", "issues"}
EVENTS = []
BUILD_TMP = os.path.join(BLENDER_DIR, "build", "tmp")


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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
        _unchanged_on_disk[os.path.abspath(blend_path)] = current
        return
    reason = ("parmak izi yok (propkit öncesi ya da elle oluşturulmuş)" if stored is None
              else "içerik son üretimden sonra değişmiş (elle düzenlenmiş)")
    if not force:
        EVENTS.append({"type": "refused", "blend": blend_path, "reason": reason})
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
    EVENTS.append({"type": "forced", "blend": blend_path, "backup": backup})
    print(f"[propkit] --force: {reason}; yedek: {backup}")


def save_generated(blend_path):
    """Parmak izini sahneye yazıp kaydet. Diskteki dosya aynı içeriğe sahipse kaydetmez:
    .blend her kayıtta bayt düzeyinde değişir, git'te gereksiz ikili fark oluşmasın."""
    fp = fingerprint()
    if _unchanged_on_disk.get(os.path.abspath(blend_path)) == fp:
        EVENTS.append({"type": "blend", "path": blend_path, "saved": False})
        print("[propkit] blend değişmedi, kaydedilmedi:", blend_path)
        return
    text = bpy.data.texts.get(FINGERPRINT_KEY) or bpy.data.texts.new(FINGERPRINT_KEY)
    text.from_string(fp)
    bpy.ops.wm.save_as_mainfile(filepath=blend_path, relative_remap=True)
    EVENTS.append({"type": "blend", "path": blend_path, "saved": True})
    print("[propkit] blend:", blend_path)


# ---------------------------------------------------------------- kalite kontrolü

STYLES = ("ps1", "pastel")
PLACEMENTS = ("floor", "pedestal")
## Stil başına varsayılan üçgen bütçesi (pastel: bonsai ~5.8k onaylı). Bir prop kendi onaylı
## bütçesini obj["prop_budget"] ile taşıyabilir (ör. domates aşamaları).
BUDGETS = {"ps1": 500, "pastel": 6000}
SIZE_MIN = 0.02   # m
SIZE_MAX = 10.0   # m
ORIGIN_TOL = 0.01  # m: taban z=0'dan en fazla bu kadar sapabilir
PS1_TEX_MAX = 256
QA_KEY = "qa"  # glTF extras ile Godot'a gider; "prop_" öneki yok ki parmak izine girmesin


def _tri_count(obj):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    ev = obj.evaluated_get(depsgraph)
    me = ev.to_mesh()
    me.calc_loop_triangles()
    count = len(me.loop_triangles)
    ev.to_mesh_clear()
    return count


def _local_bounds(obj):
    """Konum hariç dönüşüm uygulanmış köşelerin sınırları (export orijinde yapılır)."""
    m = obj.matrix_basis.copy()
    m.translation = (0, 0, 0)
    co = _attr_array(obj.data.vertices, "co", 3).reshape(-1, 3)
    co = co @ np.array(m.to_3x3()).T
    return co.min(axis=0), co.max(axis=0)


def _images(obj):
    seen = {}
    for slot in obj.material_slots:
        if slot.material and slot.material.node_tree:
            for node in slot.material.node_tree.nodes:
                if node.type == "TEX_IMAGE" and node.image:
                    seen[node.image.name] = (node.image, node)
    return seen.values()


def check_object(obj):
    """Prop kurallarına göre sorun listesi: [("hata"|"uyarı", mesaj), ...]."""
    issues = []
    err = lambda m: issues.append(("hata", m))  # noqa: E731
    warn = lambda m: issues.append(("uyarı", m))  # noqa: E731

    style = obj.get("prop_style")
    if not obj.get("prop_name"):
        err("prop_name eksik (galeride görünen ad)")
    if style not in STYLES:
        err(f"prop_style geçersiz: {style!r} (olmalı: {', '.join(STYLES)})")
    if obj.get("prop_placement") not in PLACEMENTS:
        err(f"prop_placement geçersiz: {obj.get('prop_placement')!r} (olmalı: {', '.join(PLACEMENTS)})")
    if not all(c.islower() or c.isdigit() or c == "_" for c in obj.name):
        warn(f"ad snake_case değil: {obj.name}")

    tris = _tri_count(obj)
    # prop_budget: kullanıcının bu prop için onayladığı bütçe; yoksa stilin varsayılanı
    budget = obj.get("prop_budget", BUDGETS.get(style))
    source = "prop_budget" if "prop_budget" in obj.keys() else style
    if budget is not None and (not isinstance(budget, int) or budget <= 0):
        err(f"prop_budget geçersiz: {budget!r} (pozitif tam sayı olmalı)")
    elif budget and tris > budget:
        err(f"üçgen bütçesi aşıldı: {tris} / {budget} ({source})")

    if any(abs(s - 1.0) > 1e-4 for s in obj.scale) or any(abs(r) > 1e-4 for r in obj.rotation_euler):
        warn("ölçek/dönüş uygulanmamış (Ctrl+A); Godot'ta telafi gerekmesin")

    lo, hi = _local_bounds(obj)
    size = hi - lo
    if abs(lo[2]) > ORIGIN_TOL:
        err(f"merkez noktası tabanda değil: en alt nokta z={lo[2] * 100:.1f} cm (0 olmalı)")
    if not (lo[0] <= 0 <= hi[0] and lo[1] <= 0 <= hi[1]):
        warn("merkez noktası izdüşümün dışında (prop kaideden kayar)")
    if size.max() > SIZE_MAX or size.max() < SIZE_MIN:
        warn(f"ölçü olağan dışı: {size[0]:.2f} × {size[1]:.2f} × {size[2]:.2f} m (1 birim = 1 m)")

    for img, node in _images(obj):
        w, h = img.size
        if w != h or w & (w - 1):
            warn(f"doku kare ve 2'nin kuvveti değil: {img.name} {w}×{h}")
        if style == "ps1":
            if max(w, h) > PS1_TEX_MAX:
                warn(f"PS1 doku büyük: {img.name} {w}×{h} (en fazla {PS1_TEX_MAX})")
            if node.interpolation != "Closest":
                warn(f"PS1 doku nearest değil: {img.name} ({node.interpolation})")
    return issues, tris


# ---------------------------------------------------------------- export

def prop_objects():
    """Galeri bilgisi (prop_style) olan mesh objeleri, ada göre sıralı."""
    return sorted((o for o in bpy.data.objects if o.type == "MESH" and "prop_style" in o.keys()),
                  key=lambda o: o.name)


def export_props(objs=None, project_dir=PROJECT_DIR):
    """Her prop objesini kontrol edip kendi adıyla assets/models/<ad>.glb olarak, orijinde
    export et. Kontrol sonucu glb'ye "qa" extras'ı olarak gömülür (.blend'e kaydedilmez).

    Önce geçici klasöre yazılır; hedefteki dosya bayt düzeyinde aynıysa dokunulmaz
    (değişmeyen dosyanın tarihi değişirse Godot onu boşuna yeniden import eder)."""
    import sys
    if BLENDER_DIR not in sys.path:
        sys.path.insert(0, BLENDER_DIR)
    import export_glb
    export_glb.TRI_BUDGET = max(BUDGETS.values())  # asıl bütçe kontrolü check_object'te
    tmp_dir = os.path.join(BUILD_TMP, str(os.getpid()))

    view_layer = bpy.context.view_layer
    results = []
    for obj in objs or prop_objects():
        issues, tris = check_object(obj)
        obj[QA_KEY] = "\n".join(f"{level}: {msg}" for level, msg in issues)
        for level, msg in issues:
            print(f"[qa] {obj.name}: {level}: {msg}")
        saved = obj.location.copy()
        obj.location = (0, 0, 0)
        view_layer.update()
        for o in view_layer.objects:
            o.select_set(False)
        obj.select_set(True)
        view_layer.objects.active = obj
        try:
            res = export_glb.export_glb(obj.name, source="selection", project_dir=tmp_dir)
        finally:
            obj.location = saved
            del obj[QA_KEY]
            view_layer.update()

        dest = os.path.join(project_dir, "assets", "models", obj.name + ".glb")
        digest = _sha256(res["path"])
        changed = not (os.path.isfile(dest) and _sha256(dest) == digest)
        if changed:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.move(res["path"], dest)
        else:
            os.remove(res["path"])
        res.update(path=dest, issues=issues, sha256=digest, changed=changed)
        EVENTS.append({"type": "glb", "name": obj.name, "path": dest, "sha256": digest,
                       "changed": changed, "triangles": tris,
                       "issues": [f"{level}: {msg}" for level, msg in issues]})
        print(f"[propkit] glb: {dest} {tris} üçgen, "
              f"{sum(1 for i in issues if i[0] == 'hata')} hata, "
              f"{sum(1 for i in issues if i[0] == 'uyarı')} uyarı"
              f"{'' if changed else ' (değişmedi)'}")
        results.append(res)
    return results
