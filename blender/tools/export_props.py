"""Yalnızca export: açık .blend'deki propları yeniden üretmeden Godot'a gönder.

Elle düzenlenmiş bir prop için:
    blender --background blender/props/<ad>.blend --python blender/tools/export_props.py

prop_style bilgisi olan her mesh objesi assets/models/<obje adı>.glb olarak, orijinde yazılır.
.blend'e dokunmaz (kaydetmez).
"""

import os
import sys

import bpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import propkit  # noqa: E402

objs = propkit.prop_objects()
for o in bpy.data.objects:
    if o.type == "MESH" and o not in objs:
        print(f"[qa] {o.name}: hata: galeri bilgisi (prop_style) yok; export edilmedi")
if not objs:
    print("[export_props] prop_style bilgisi olan obje yok; hiçbir şey export edilmedi.")
else:
    propkit.export_props(objs)
