"""Blender -> Godot 4.7 .glb export (godot-blender-lab).

Kullanım (Blender içinde, Text Editor'de çalıştırarak ya da MCP üzerinden):

    import sys; sys.path.insert(0, r"C:\\Users\\pc\\Desktop\\godot-blender-lab\\blender")
    import export_glb
    export_glb.export_glb("exp01_kutu")                              # seçili objeler
    export_glb.export_glb("exp01_oda", source="collection", collection_name="oda")
    export_glb.export_glb("exp01_sahne", source="scene")

Çıktı: <lab>/godot/assets/models/<name>.glb
Lab kökü, .blend dosyasından yukarı doğru godot/project.godot aranarak bulunur;
bulunamazsa LAB_ROOT_FALLBACK kullanılır.

Blender sürümleri arasında glTF exporter parametreleri değiştiği için, parametreler
operatörün gerçekten desteklediği alanlara göre süzülür.
"""

import os

import bpy

LAB_ROOT_FALLBACK = r"C:\Users\pc\Desktop\godot-blender-lab"
MODELS_SUBDIR = os.path.join("godot", "assets", "models")

TRI_BUDGET = 1500       # bu sayının üstü uyarı verir (PS1 bütçesi)
MAX_TEXTURE_PX = 256    # bu boyutun üstündeki dokular uyarı verir


def find_lab_root(start=None):
    """godot/project.godot içeren en yakın üst klasörü bul."""
    start = start or (os.path.dirname(bpy.data.filepath) if bpy.data.filepath else None)
    if start:
        d = os.path.abspath(start)
        while True:
            if os.path.isfile(os.path.join(d, "godot", "project.godot")):
                return d
            parent = os.path.dirname(d)
            if parent == d:
                break
            d = parent
    return LAB_ROOT_FALLBACK


def _objects_for(source, collection_name):
    view_layer = bpy.context.view_layer
    if source == "selection":
        objs = [o for o in view_layer.objects if o.select_get()]
    elif source == "collection":
        coll = bpy.data.collections.get(collection_name)
        if coll is None:
            raise ValueError(f"Koleksiyon bulunamadı: {collection_name!r}")
        objs = [o for o in coll.all_objects if o.name in view_layer.objects]
    elif source == "scene":
        objs = list(view_layer.objects)
    else:
        raise ValueError("source 'selection', 'collection' veya 'scene' olmalı")
    if not objs:
        raise RuntimeError("Export edilecek obje yok.")
    return objs


def _supported(op, **kwargs):
    props = op.get_rna_type().properties
    return {k: v for k, v in kwargs.items() if k in props.keys()}


def _vertex_color_kwargs(op):
    props = op.get_rna_type().properties
    if "export_vertex_color" in props.keys():
        items = props["export_vertex_color"].enum_items.keys()
        return {"export_vertex_color": "ACTIVE" if "ACTIVE" in items else "MATERIAL"}
    if "export_colors" in props.keys():
        return {"export_colors": True}
    return {}


def _stats(objs):
    depsgraph = bpy.context.evaluated_depsgraph_get()
    tris = 0
    images = set()
    for o in objs:
        if o.type == "MESH":
            ev = o.evaluated_get(depsgraph)
            me = ev.to_mesh()
            me.calc_loop_triangles()
            tris += len(me.loop_triangles)
            ev.to_mesh_clear()
        for slot in getattr(o, "material_slots", []):
            mat = slot.material
            if mat and mat.use_nodes:
                for n in mat.node_tree.nodes:
                    if n.type == "TEX_IMAGE" and n.image:
                        images.add(n.image)
    return tris, images


def export_glb(name=None, source="selection", collection_name=None, subdir="", project_dir=None):
    """Objeleri .glb olarak yaz. Sonuç sözlüğü döner.

    Varsayılan hedef: <lab>/godot/assets/models/. project_dir verilirse
    (Godot projesinin kök klasörü, project.godot'un olduğu yer) hedef
    <project_dir>/assets/models/ olur.
    """
    if bpy.context.object and bpy.context.object.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")

    if name is None:
        name = os.path.splitext(os.path.basename(bpy.data.filepath))[0] or "untitled"

    objs = _objects_for(source, collection_name)
    if project_dir:
        out_dir = os.path.join(project_dir, "assets", "models", subdir)
    else:
        out_dir = os.path.join(find_lab_root(), MODELS_SUBDIR, subdir)
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, name + ".glb")

    warnings = []
    if abs(bpy.context.scene.unit_settings.scale_length - 1.0) > 1e-6:
        warnings.append("Scene Unit Scale 1.0 değil; Godot'ta ölçek bozuk görünebilir.")
    tris, images = _stats(objs)
    if tris > TRI_BUDGET:
        warnings.append(f"{tris} üçgen, bütçe {TRI_BUDGET}.")
    for img in images:
        if max(img.size[0], img.size[1]) > MAX_TEXTURE_PX:
            warnings.append(f"Doku büyük: {img.name} {tuple(img.size)}")

    view_layer = bpy.context.view_layer
    prev_selected = [o for o in view_layer.objects if o.select_get()]
    prev_active = view_layer.objects.active

    try:
        for o in view_layer.objects:
            o.select_set(False)
        for o in objs:
            o.select_set(True)

        op = bpy.ops.export_scene.gltf
        kwargs = dict(
            filepath=out_path,
            export_format="GLB",
            use_selection=True,
            export_apply=True,        # modifier'ları uygula
            export_yup=True,          # Godot Y-up
            export_texcoords=True,
            export_normals=True,
            export_materials="EXPORT",
            export_cameras=False,
            export_lights=False,
            export_animations=True,
            export_extras=True,       # custom property'ler Godot'a metadata olarak gelir
        )
        kwargs.update(_vertex_color_kwargs(op))
        op(**_supported(op, **kwargs))
    finally:
        for o in view_layer.objects:
            o.select_set(False)
        for o in prev_selected:
            o.select_set(True)
        view_layer.objects.active = prev_active

    result = {
        "path": out_path,
        "objects": [o.name for o in objs],
        "triangles": tris,
        "warnings": warnings,
        "blender": bpy.app.version_string,
    }
    print("[export_glb]", result)
    return result


if __name__ == "__main__":
    export_glb()
