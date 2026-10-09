"""Tek komut: bütün propları üret, kontrol et, Godot'a al ve galeriyi dene.

    blender --background --factory-startup --python blender/tools/build_all.py -- [seçenekler]

Seçenekler:
    --only AD      yalnızca adında AD geçen üreticiler (ör. --only crate); tekrarlanabilir
    --force        elle düzenlenmiş .blend'leri yedekleyip yeniden üret (dikkat!)
    --no-godot     Godot import ve galeri testini atla

Adımlar:
  1. blender/props/make_*.py üreticilerini (kendiliğinden bulunur) ayrı Blender süreçlerinde
     "--build" ile çalıştırır. Elle düzenlenmiş .blend'ler korunur ve "atlandı" diye raporlanır.
  2. Her prop kalite kontrolünden geçer (propkit.check_object); sonuç glb'ye gömülür.
  3. Godot: --import, sonra galeri sahnesi headless açılır; hata satırları sayılır.
Hata (kalite "hata"sı, üretici çökmesi, Godot hatası) varsa çıkış kodu 1'dir.
"""

import argparse
import glob
import json
import os
import re
import subprocess
import sys

import bpy

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(os.path.dirname(TOOLS_DIR))
PROPS_DIR = os.path.join(PROJECT_DIR, "blender", "props")
GALLERY_SCENE = "res://experiments/exp03_gallery/exp03.tscn"

GLB_RE = re.compile(r"\[propkit\] glb: (.+?\.glb) (\d+) üçgen, (\d+) hata, (\d+) uyarı")
QA_RE = re.compile(r"\[qa\] (\S+): (hata|uyarı): (.*)")
GODOT_ERR_RE = re.compile(r"^(SCRIPT )?ERROR", re.MULTILINE)


def run(cmd):
    proc = subprocess.run(cmd, cwd=PROJECT_DIR, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, proc.stdout + proc.stderr


def godot_exe():
    if os.environ.get("GODOT_EXE"):
        return os.environ["GODOT_EXE"]
    with open(os.path.join(TOOLS_DIR, "paths.json"), encoding="utf-8") as f:
        return json.load(f)["godot"]


def build_generator(path, force):
    """Bir üreticiyi çalıştır; (durum, [prop sonuçları], qa satırları, çıktı) döner."""
    cmd = [bpy.app.binary_path, "--background", "--factory-startup", "--python-exit-code", "1",
           "--python", path, "--", "--build"] + (["--force"] if force else [])
    code, out = run(cmd)
    props = [dict(name=os.path.splitext(os.path.basename(m[0]))[0], tris=int(m[1]),
                  errors=int(m[2]), warnings=int(m[3])) for m in GLB_RE.findall(out)]
    qa = QA_RE.findall(out)
    if code != 0 or "Traceback" in out:
        status = "ÇÖKTÜ"
    elif "DURDU" in out:
        status = "atlandı"
    else:
        status = "üretildi"
    return status, props, qa, out


def godot_check():
    exe = godot_exe()
    results = []
    for label, args in [("import", ["--import"]),
                        ("galeri", [GALLERY_SCENE, "--quit-after", "30"])]:
        code, out = run([exe, "--headless", "--path", PROJECT_DIR] + args)
        errors = [line for line in out.splitlines() if GODOT_ERR_RE.match(line)]
        results.append((label, code, errors))
    return results


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="build_all")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-godot", action="store_true")
    args = ap.parse_args(argv)

    gens = sorted(glob.glob(os.path.join(PROPS_DIR, "make_*.py")))
    if args.only:
        gens = [g for g in gens if any(o in os.path.basename(g) for o in args.only)]
    if not gens:
        print("[build_all] üretici bulunamadı")
        return 1

    failed = False
    rows = []
    for gen in gens:
        name = os.path.basename(gen)
        print(f"[build_all] {name} çalışıyor...", flush=True)
        status, props, qa, out = build_generator(gen, args.force)
        if status == "ÇÖKTÜ":
            failed = True
            print(out[-3000:])
        elif status == "atlandı":
            for line in out.splitlines():
                if "DURDU" in line or line.startswith("  - "):
                    print("   ", line.strip())
        rows.append((name, status, props, qa))

    print("\n== Kalite kontrolü ==")
    print(f"{'prop':<22}{'durum':<11}{'üçgen':>7}{'hata':>6}{'uyarı':>7}")
    for name, status, props, qa in rows:
        if not props:
            print(f"{name:<22}{status:<11}")
        for p in props:
            print(f"{p['name']:<22}{status:<11}{p['tris']:>7}{p['errors']:>6}{p['warnings']:>7}")
            failed |= p["errors"] > 0
        for obj, level, msg in qa:
            print(f"    {obj}: {level}: {msg}")

    if not args.no_godot:
        print("\n== Godot ==")
        for label, code, errors in godot_check():
            print(f"{label:<8}{'tamam' if code == 0 and not errors else f'{len(errors)} hata'}")
            for line in errors[:10]:
                print("   ", line)
            failed |= code != 0 or bool(errors)

    print("\n[build_all] SONUÇ:", "SORUN VAR" if failed else "temiz")
    return 1 if failed else 0


sys.exit(main())
