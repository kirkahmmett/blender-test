"""Asset kataloğu ve onay durumu.

    blender --background --factory-startup --python blender/tools/catalog.py

build_all her çalıştığında da yazar. Çıktı: repo kökünde CATALOG.md (GitHub'da görüntülü vitrin).
Deterministik: içerik değişmedikçe dosyaya dokunulmaz (tarih/saat yazılmaz).

Onay durumu: assets/asset_status.json (Godot galerisi yazar: incelemede 1–4 tuşları).
    {"<asset>": {"status": "draft|review|approved|rejected", "sha256": "<karar anındaki glb>",
                 "date": "YYYY-MM-DD", "note": "..."}}
Kaydı olmayan asset "taslak"tır. Onaylı asset'in glb'si karar anındakinden farklıysa durum
"değişti" olur: model onaydan sonra değişmiş, yeniden incelenmeli.
"""

import hashlib
import json
import os
import struct
import sys

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(TOOLS_DIR))
MODELS_DIR = os.path.join(PROJECT_DIR, "assets", "models")
STATUS_PATH = os.path.join(PROJECT_DIR, "assets", "asset_status.json")
MANIFEST_PATH = os.path.join(PROJECT_DIR, "blender", "build", "manifest.json")
GOLDEN_REL = "blender/build/golden"
CATALOG_PATH = os.path.join(PROJECT_DIR, "CATALOG.md")
EXCLUDE = ("test_cube",)
COLLISION_SUFFIX = "-convcolonly"

sys.path.insert(0, os.path.join(PROJECT_DIR, "blender", "lib"))
from propkit import BUDGETS  # noqa: E402  (stil başına üçgen bütçesi; Blender içinde çalışır)

# görünen ad, rozet; sıra = katalog özetindeki sıra
STATUSES = {
    "approved": ("onaylı", "🟢"),
    "changed": ("değişti — yeniden incele", "🟠"),
    "review": ("incelemede", "🟡"),
    "draft": ("taslak", "⚪"),
    "rejected": ("reddedildi", "🔴"),
}


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_status():
    if not os.path.isfile(STATUS_PATH):
        return {}
    with open(STATUS_PATH, encoding="utf-8") as f:
        return json.load(f)


def effective_status(record, glb_sha256):
    """Kayıttaki durum; onaylıyken model değiştiyse "changed"."""
    status = (record or {}).get("status", "draft")
    if status not in STATUSES or status == "changed":
        status = "draft"
    if status == "approved" and record.get("sha256") and record["sha256"] != glb_sha256:
        return "changed"
    return status


def read_glb(path):
    """glb'nin JSON bölümünden prop bilgisi: extras + ölçü (m; G×Y×D, çarpışma gövdesi hariç)."""
    with open(path, "rb") as f:
        data = f.read()
    length = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + length])
    for node in gltf.get("nodes", []):
        extras = node.get("extras", {})
        if "prop_style" not in extras or node.get("name", "").endswith(COLLISION_SUFFIX):
            continue
        lo, hi = [float("inf")] * 3, [float("-inf")] * 3
        for prim in gltf["meshes"][node["mesh"]]["primitives"]:
            acc = gltf["accessors"][prim["attributes"]["POSITION"]]
            lo = [min(a, b) for a, b in zip(lo, acc["min"])]
            hi = [max(a, b) for a, b in zip(hi, acc["max"])]
        return extras, [h - l for l, h in zip(lo, hi)]
    return {}, None


def collect():
    """Her asset için katalog satırı (ada göre sıralı), üretici (spec) bilgisiyle."""
    manifest = {"generators": {}}
    if os.path.isfile(MANIFEST_PATH):
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            manifest = json.load(f)
    owner = {}
    for gen, entry in manifest["generators"].items():
        for name, info in entry["assets"].items():
            owner[name] = (gen, info)
    status = load_status()

    rows = []
    for file in sorted(os.listdir(MODELS_DIR)):
        name, ext = os.path.splitext(file)
        if ext != ".glb" or name in EXCLUDE:
            continue
        path = os.path.join(MODELS_DIR, file)
        sha = file_sha256(path)
        extras, size = read_glb(path)
        gen, info = owner.get(name, ("(elle export)", {}))
        rows.append({
            "name": name, "title": extras.get("prop_name", name), "style": extras.get("prop_style", "?"),
            "budget": extras.get("prop_budget"), "size": size, "generator": gen,
            "triangles": info.get("triangles"), "issues": info.get("issues", []),
            "status": effective_status(status.get(name), sha), "record": status.get(name, {}),
        })
    return rows


def status_summary(rows):
    counts = {}
    for r in rows:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts


def _cell(text):
    return str(text).replace("|", "\\|").replace("\n", " ")


def render(rows):
    counts = status_summary(rows)
    out = ["# Asset kataloğu", "",
           "> `build_all` tarafından otomatik yazılır; elle düzenleme. Görseller oyundaki shader'larla "
           "alınmış görsel regresyon altın görüntüleridir (`shared/tests/visual_test.tscn`). "
           "Onay durumu: galeride propu incele (E), **1** taslak · **2** incelemede · **3** onaylı · "
           "**4** reddedildi.", "",
           f"**{len(rows)} asset** — " + " · ".join(
               f"{STATUSES[s][1]} {counts[s]} {STATUSES[s][0]}" for s in STATUSES if counts.get(s)), ""]
    changed = [r["name"] for r in rows if r["status"] == "changed"]
    if changed:
        out += [f"> ⚠️ Onaydan sonra değişenler (yeniden incele): {', '.join(changed)}", ""]

    by_gen = {}
    for r in rows:
        by_gen.setdefault(r["generator"], []).append(r)
    for gen in sorted(by_gen):
        out += [f"## {os.path.splitext(os.path.basename(gen))[0]}", "", f"Üretici: `{gen}`", "",
                "| Görünüm | Asset | Bilgi | Durum |", "|---|---|---|---|"]
        for r in by_gen[gen]:
            imgs = []
            for angle in ("on", "ust"):
                rel = f"{GOLDEN_REL}/{r['name']}_{angle}.png"
                if os.path.isfile(os.path.join(PROJECT_DIR, rel)):
                    imgs.append(f'<img src="{rel}" width="150">')
            view = " ".join(imgs) or "görüntü yok (`build_all --visual`)"
            tris = "?" if r["triangles"] is None else f"{r['triangles']:,}".replace(",", ".")
            budget = r["budget"] or BUDGETS.get(r["style"])
            if budget:
                tris += f" / {int(float(budget)):,}".replace(",", ".")
            size = (" × ".join(str(round(v * 100)) for v in r["size"]) + " cm") if r["size"] else "?"
            errors = sum(1 for i in r["issues"] if i.startswith("hata"))
            warns = len(r["issues"]) - errors
            qa = "temiz" if not r["issues"] else f"{errors} hata, {warns} uyarı"
            info = f"{tris} üçgen<br>{r['style']} · {size}<br>kalite: {qa}"
            label, badge = STATUSES[r["status"]]
            state = f"{badge} {label}"
            if r["record"].get("date"):
                state += f"<br>{r['record']['date']}"
            if r["record"].get("note"):
                state += f"<br><i>{_cell(r['record']['note'])}</i>"
            out.append(f"| {view} | **{_cell(r['title'])}**<br>`{r['name']}` | {info} | {state} |")
        out.append("")
    return "\n".join(out)


def write_catalog():
    """CATALOG.md'yi yaz (değiştiyse). (satırlar, yazıldı mı)."""
    rows = collect()
    text = render(rows)
    old = None
    if os.path.isfile(CATALOG_PATH):
        with open(CATALOG_PATH, encoding="utf-8") as f:
            old = f.read()
    if old != text:
        with open(CATALOG_PATH, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return rows, old != text


if __name__ == "__main__":
    rows, written = write_catalog()
    counts = status_summary(rows)
    print(f"[catalog] {len(rows)} asset, " + ", ".join(f"{STATUSES[s][0]} {counts[s]}" for s in STATUSES
                                                        if counts.get(s))
          + (" — CATALOG.md yazıldı" if written else " — CATALOG.md değişmedi"))
