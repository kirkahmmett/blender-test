"""Tek komut: değişen propları üret, kontrol et, Godot'a al ve galeriyi dene.

    blender --background --factory-startup --python blender/tools/build_all.py -- [seçenekler]

Seçenekler:
    --only AD      yalnızca adında AD geçen üreticiler (ör. --only crate); tekrarlanabilir
    --full         manifesti yok say, hepsini yeniden üret
    --jobs N       paralel Blender işçisi sayısı (varsayılan: çekirdek/2, en fazla 4)
    --force        elle düzenlenmiş .blend'leri yedekleyip yeniden üret (dikkat!)
    --no-godot     Godot import ve galeri testini atla

Akış (bkz. blender/lib/buildkit.py):
  1. Artımlı: girdisi ve çıktıları değişmeyen üreticiler atlanır (blender/build/manifest.json).
  2. Paralel: kirli üreticiler işçilere bölünür; bu süreç de işçi olarak çalışır.
     Değişmeyen glb'lere dokunulmaz, Godot boşuna yeniden import etmez.
  3. Godot: yalnızca bir glb değiştiyse; proje bir editörde açıksa komut satırından import
     yapılmaz (editör değişen dosyaları kendisi alır).
Sorun (kalite "hata"sı, çöken üretici, Godot hatası) varsa çıkış kodu 1'dir.
"""

import argparse
import json
import os
import sys
import shutil
import tempfile
import time

import bpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import buildkit  # noqa: E402


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="build_all")
    ap.add_argument("--only", action="append", default=[])
    ap.add_argument("--full", action="store_true")
    ap.add_argument("--jobs", type=int, default=min(4, max(1, (os.cpu_count() or 2) // 2)))
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--no-godot", action="store_true")
    args = ap.parse_args(argv)

    t_start = time.perf_counter()
    version = bpy.app.version_string
    manifest = buildkit.load_manifest()
    gens = buildkit.generators(args.only)
    if not gens:
        print("[build_all] üretici bulunamadı")
        return 1
    if not args.only:   # silinmiş / taşınmış birimlerin kayıtları manifestte kalmasın
        for stale in sorted(set(manifest["generators"]) - set(gens)):
            print(f"[build_all] manifestten çıkarıldı (birim artık yok): {stale}")
            del manifest["generators"][stale]

    dirty = {}
    for g in gens:
        reason = "--full" if args.full else buildkit.dirty_reason(g, manifest, version)
        if reason:
            dirty[g] = reason
    print("\n== Plan ==")
    for g in gens:
        print(f"  {os.path.basename(g):<22}{dirty.get(g, 'değişmedi, atlanıyor')}")

    # ---- üretim: işçilere böl; ilk grubu bu süreç kendisi üretir
    extra = ["--force"] if args.force else []
    results = []
    if dirty:
        groups = buildkit.split_jobs(list(dirty), manifest, max(1, args.jobs))
        tmp = tempfile.mkdtemp(prefix="build_all_")
        procs = []
        for i, grp in enumerate(groups[1:], start=1):
            out = os.path.join(tmp, f"worker{i}.json")
            procs.append((buildkit.spawn_worker(grp, out, extra), out, grp))
        print(f"\n[build_all] {len(dirty)} üretici, {len(groups)} süreç", flush=True)
        for g in groups[0]:
            results.append(buildkit.run_generator(g, extra))
        for proc, out, grp in procs:
            proc.wait()
            with open(out + ".log", encoding="utf-8", errors="replace") as f:
                err = f.read()
            if os.path.isfile(out):
                with open(out, encoding="utf-8") as f:
                    results.extend(json.load(f))
            else:
                for g in grp:
                    results.append({"generator": g, "status": "ÇÖKTÜ", "seconds": 0.0, "events": [],
                                    "error": f"işçi sonuç yazmadı (kod {proc.returncode})\n{err[-2000:]}",
                                    "log": ""})
        shutil.rmtree(tmp, ignore_errors=True)
    t_build = time.perf_counter() - t_start

    failed = False
    changed_glbs = []
    for r in results:
        if r["status"] == "üretildi":
            manifest["generators"][r["generator"]] = buildkit.manifest_entry(r, r["generator"], version)
        failed |= r["status"] == "ÇÖKTÜ"
        changed_glbs += [ev["path"] for ev in r["events"] if ev["type"] == "glb" and ev["changed"]]
    buildkit.save_manifest(manifest)

    # ---- rapor: bu derlemede üretilenler + manifestteki (değişmeyen) asset'ler
    by_gen = {r["generator"]: r for r in results}
    print("\n== Kalite kontrolü ==")
    print(f"{'prop':<22}{'durum':<12}{'üçgen':>7}{'hata':>6}{'uyarı':>7}  glb")
    for g in gens:
        r = by_gen.get(g)
        if r and r["status"] != "üretildi":
            print(f"{os.path.basename(g):<22}{r['status']:<12}")
            if r["status"] == "ÇÖKTÜ":
                print("    " + (r["error"] or "").strip().replace("\n", "\n    ")[-2500:])
            for ev in r["events"]:
                if ev["type"] == "refused":
                    print(f"    {os.path.basename(ev['blend'])}: {ev['reason']}; üstüne yazılmadı "
                          f"(yalnızca export: blender/tools/export_props.py, yeniden üretim: --force)")
        entry = manifest["generators"].get(g)
        if not entry:
            continue
        glb_state = {ev["name"]: ev["changed"] for ev in r["events"] if ev["type"] == "glb"} if r else {}
        status = "üretildi" if r and r["status"] == "üretildi" else "değişmedi"
        for name, info in sorted(entry["assets"].items()):
            errors = sum(1 for i in info["issues"] if i.startswith("hata"))
            warns = len(info["issues"]) - errors
            note = ("yazıldı" if glb_state.get(name) else "aynı") if name in glb_state else "-"
            print(f"{name:<22}{status:<12}{info['triangles']:>7}{errors:>6}{warns:>7}  {note}")
            for issue in info["issues"]:
                print(f"    {name}: {issue}")
            failed |= errors > 0

    # ---- Godot
    t_godot = 0.0
    if args.no_godot:
        print("\n== Godot == atlandı (--no-godot)")
    elif not changed_glbs:
        print("\n== Godot == değişen model yok, import gerekmiyor")
    elif buildkit.godot_editor_open():
        print(f"\n== Godot == {len(changed_glbs)} model değişti; proje editörde açık, komut satırından "
              "import yapılmadı. Editör pencereye geçince yeniden import eder, galeri kendini yeniler.")
    else:
        print("\n== Godot ==")
        t0 = time.perf_counter()
        for label, seconds, errors in buildkit.godot_check():
            print(f"{label:<8}{'tamam' if not errors else f'{len(errors)} hata'}  ({seconds:.1f} s)")
            for line in errors[:10]:
                print("   ", line)
            failed |= bool(errors)
        t_godot = time.perf_counter() - t0

    total = time.perf_counter() - t_start
    print(f"\n[build_all] süre: üretim {t_build:.1f} s, Godot {t_godot:.1f} s, toplam {total:.1f} s "
          f"(+ bu sürecin Blender açılışı)")
    print("[build_all] SONUÇ:", "SORUN VAR" if failed else "temiz")
    return 1 if failed else 0


sys.exit(main())
