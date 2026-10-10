"""Asset kiti: TOML tanımından (spec) asset üretimi.

Bir asset = veri (blender/specs/<ad>.toml) + algoritma (blender/lib/families/<aile>.py)
+ ortak parçalar (blender/lib/parts/) + stil (blender/styles/<stil>.toml).

Spec biçimi
-----------
    [asset]
    family = "tomato"          # families/tomato.py, build(ctx, variant, collection) -> obj
    blend = "tomato"           # blender/props/tomato.blend (tüm varyantlar yan yana)
    style = "pastel"           # blender/styles/pastel.toml
    placement = "pedestal"     # galeri: "floor" | "pedestal"
    material_prefix = "tomato" # Blender malzeme adları: tomato_leaf ...
    spacing = 0.5              # .blend içinde varyantlar arası mesafe (m)

    [[variant]]                # her varyant bir obje = bir glb
    id = "stage1"              # --part ile seçilir
    object = "tomato_stage1"   # obje / koleksiyon / glb adı
    name = "Domates — 1. aşama (fide)"
    budget = 2200              # isteğe bağlı: onaylı üçgen bütçesi (prop_budget)
    ...                        # aileye özgü varyant alanları

Başka bir TOML'a başvuru: değeri "@" ile başlayan dize, ör. pot = "@parts/pot_terracotta"
(blender/specs/parts/pot_terracotta.toml). Başvurulan dosyalar artımlı derlemenin girdisidir.

Stil (blender/styles/<ad>.toml): godot (galeri shader'ı), renk açıklığı/doygunluk/değer ve
poly yoğunluğu çarpanı. Varsayılan değerlerde stil hiçbir hesap yapmaz (çıktı birebir aynı).
"""

import argparse
import colorsys
import importlib
import os
import sys
import tomllib

LIB_DIR = os.path.dirname(os.path.abspath(__file__))
BLENDER_DIR = os.path.dirname(LIB_DIR)
SPECS_DIR = os.path.join(BLENDER_DIR, "specs")
STYLES_DIR = os.path.join(BLENDER_DIR, "styles")
PROPS_DIR = os.path.join(BLENDER_DIR, "props")


# ---------------------------------------------------------------- spec ve stil dosyaları

def _load_toml(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


def _resolve(value, deps):
    if isinstance(value, str) and value.startswith("@"):
        path = os.path.join(SPECS_DIR, value[1:] + ".toml")
        deps.append(path)
        return _resolve(_load_toml(path), deps)
    if isinstance(value, dict):
        return {k: _resolve(v, deps) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, deps) for v in value]
    return value


def load_spec(path):
    """(spec sözlüğü, bağımlı dosyalar) — bağımlılar: "@" başvuruları + stil dosyası."""
    deps = []
    spec = _resolve(_load_toml(path), deps)
    deps.append(style_path(spec["asset"]["style"]))
    return spec, deps


def style_path(name):
    return os.path.join(STYLES_DIR, name + ".toml")


class Style:
    """Stil tokenları. Varsayılan değerlerde (lift 0, saturation 1, value 1, density 1) her
    yöntem doğrudan eski yoldan geçer: mevcut asset'ler bayt bayt aynı kalır."""

    def __init__(self, name):
        data = _load_toml(style_path(name))
        self.name = name
        self.godot = data["godot"]
        color = data.get("color", {})
        self.lift = float(color.get("lift", 0.0))
        self.saturation = float(color.get("saturation", 1.0))
        self.value = float(color.get("value", 1.0))
        self.density = float(data.get("mesh", {}).get("density", 1.0))
        self._color_identity = (self.lift, self.saturation, self.value) == (0.0, 1.0, 1.0)

    def rgb(self, rgb):
        """sRGB 0..1 üçlüsüne stil dönüşümü."""
        if self._color_identity:
            return rgb
        h, s, v = colorsys.rgb_to_hsv(*rgb)
        r, g, b = colorsys.hsv_to_rgb(h, min(1.0, s * self.saturation), min(1.0, v * self.value))
        return tuple(c + (1.0 - c) * self.lift for c in (r, g, b))

    def color(self, hexstr, mul=1.0):
        """Palet rengi (sRGB hex) -> lineer RGBA (Blender color attribute)."""
        from meshkit import srgb
        if self._color_identity:
            return srgb(hexstr, mul)
        rgb = tuple(min(1.0, int(hexstr[i:i + 2], 16) / 255.0 * mul) for i in (0, 2, 4))
        rgb = self.rgb(rgb)
        lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]
        return (*lin, 1.0)

    def seg(self, n, minimum=3):
        """Segment / kenar sayısı (poly yoğunluğu)."""
        if self.density == 1.0:
            return n
        return max(minimum, round(n * self.density))


class Ctx:
    """Aileye verilen bağlam: spec, stil, palet."""

    def __init__(self, spec, style):
        self.spec = spec
        self.asset = spec["asset"]
        self.style = style
        self.palette = spec.get("palette", {})

    def color(self, key_or_hex, mul=1.0):
        """Palet anahtarı ya da doğrudan hex."""
        return self.style.color(self.palette.get(key_or_hex, key_or_hex), mul)

    def material_name(self, name):
        return f"{self.asset['material_prefix']}_{name}"


# ---------------------------------------------------------------- üretim akışı

def run(spec_path, argv):
    """Spec'ten üret. argv: [--part ID|all] [--preview P] [--front] [--export] [--force] [--build]"""
    import bpy
    import propkit
    from meshkit import render_preview, tri_count

    ap = argparse.ArgumentParser(prog=os.path.basename(spec_path))
    ap.add_argument("--part", default=None, help="varyant id ya da all (varsayılan: son varyant)")
    ap.add_argument("--preview")
    ap.add_argument("--front", action="store_true", help="önizlemeyi tam önden çek")
    ap.add_argument("--export", action="store_true")
    ap.add_argument("--force", action="store_true", help="elle düzenlenmiş .blend'i yedekleyip üstüne yaz")
    ap.add_argument("--build", action="store_true", help="build_all sözleşmesi: --part all --export")
    ap.add_argument("--style", help="stili geçersiz kıl (yalnızca önizleme; --export ile kullanılamaz)")
    args = ap.parse_args(argv)

    spec, _ = load_spec(spec_path)
    asset = spec["asset"]
    variants = spec["variant"]
    tag = os.path.splitext(os.path.basename(spec_path))[0]
    if args.build:
        args.part, args.export = "all", True
    part = args.part or variants[-1]["id"]
    blend_path = os.path.join(PROPS_DIR, asset["blend"] + ".blend")

    if args.export:
        # .blend tüm varyantları birlikte tutar; tek varyantla kaydetmek diğerlerini silerdi
        if part != "all" or args.style:
            print(f"[{tag}] DURDU: --export yalnızca --part all ile ve spec'in kendi stiliyle kullanılabilir.")
            return []
        try:
            propkit.guard_overwrite(blend_path, args.force)
        except propkit.OverwriteRefused as e:
            print(f"[{tag}] DURDU:", e)
            return []

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.unit_settings.scale_length = 1.0

    style = Style(args.style or asset["style"])
    ctx = Ctx(spec, style)
    family = importlib.import_module("families." + asset["family"])
    chosen = variants if part == "all" else [v for v in variants if v["id"] == part]
    if not chosen:
        raise ValueError(f"varyant yok: {part!r} (var olanlar: {[v['id'] for v in variants]})")

    objs = []
    for i, variant in enumerate(chosen):
        coll = bpy.data.collections.new(variant["object"])
        scene.collection.children.link(coll)
        obj = family.build(ctx, variant, coll)
        # galeri bilgisi: glTF "extras" olarak Godot'a metadata diye gider (sıra korunur)
        obj["prop_name"] = variant["name"]
        obj["prop_style"] = style.godot
        obj["prop_placement"] = asset["placement"]
        if "budget" in variant:
            obj["prop_budget"] = variant["budget"]
        obj.location.x = (i - (len(chosen) - 1) / 2) * asset.get("spacing", 0.6)
        objs.append(obj)
        budget = f" (bütçe {variant['budget']})" if "budget" in variant else ""
        print(f"[{tag}] {obj.name}: {tri_count(obj)} üçgen{budget}")

    if args.export:
        propkit.save_generated(blend_path)
        propkit.export_props(objs)

    if args.preview:
        render_preview(args.preview, objs, args.front, tag=tag)
    return objs


def ensure_paths():
    for path in (LIB_DIR, BLENDER_DIR):
        if path not in sys.path:
            sys.path.insert(0, path)
