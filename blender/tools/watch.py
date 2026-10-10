"""İzleme modu: dosya kaydedildiği anda yalnızca etkilenen propları yeniden üret.

    blender --background --factory-startup --python blender/tools/watch.py -- [--no-godot] [--max-seconds N]

Blender açık kalır (açılış maliyeti bir kez ödenir); üreticiler bu süreçte çalışır ve kit
modülleri her çalıştırmada yeniden yüklenir. İzlenen dosyalar: blender/props/make_*.py ve
ortak kit (blender/lib/*.py, blender/export_glb.py). Ortak kit değişirse hepsi derlenir.

Godot: proje editörde açıksa hiçbir şey yapılmaz; editör pencereye geçince değişen glb'leri
import eder ve galeri (exp03, @tool) kendini yeniler. Editör kapalıysa `godot --import` çalışır.
Çıkış: Ctrl+C (ya da test için --max-seconds).
"""

import argparse
import os
import subprocess
import tempfile
import sys
import time

import bpy

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import buildkit  # noqa: E402

POLL = 0.5       # s: dosya tarihlerine bakma aralığı
DEBOUNCE = 0.3   # s: editör kaydı birden çok yazma yapabilir; durulmasını bekle


def snapshot():
    stamps = {}
    for path in buildkit.watched_files():
        try:
            stamps[path] = os.path.getmtime(buildkit.absolute(path))
        except OSError:
            pass
    return stamps


def stamp():
    return time.strftime("%H:%M:%S")


def build_dirty(version):
    """Kirli üreticileri bu süreçte üret; yazılan glb yollarını döndür."""
    manifest = buildkit.load_manifest()
    dirty = [(g, r) for g in buildkit.generators()
             if (r := buildkit.dirty_reason(g, manifest, version))]
    if not dirty:
        return []
    t0 = time.perf_counter()
    changed = []
    for gen, reason in dirty:
        r = buildkit.run_generator(gen)
        name = os.path.basename(gen)
        if r["status"] == "üretildi":
            manifest["generators"][gen] = buildkit.manifest_entry(r, gen, version)
            glbs = [ev for ev in r["events"] if ev["type"] == "glb"]
            written = [ev["name"] for ev in glbs if ev["changed"]]
            changed += [ev["path"] for ev in glbs if ev["changed"]]
            issues = [f"{ev['name']}: {i}" for ev in glbs for i in ev["issues"]]
            print(f"[watch {stamp()}] {name}: üretildi ({r['seconds']:.1f} s) — "
                  f"{len(written)}/{len(glbs)} model yazıldı{': ' + ', '.join(written) if written else ''}",
                  flush=True)
            for issue in issues:
                print(f"    {issue}", flush=True)
        elif r["status"] == "atlandı":
            print(f"[watch {stamp()}] {name}: atlandı — .blend elle düzenlenmiş, üstüne yazılmadı",
                  flush=True)
        else:
            print(f"[watch {stamp()}] {name}: ÇÖKTÜ ({reason})\n{(r['error'] or '').strip()[-2500:]}",
                  flush=True)
    buildkit.save_manifest(manifest)
    print(f"[watch {stamp()}] tamam: {time.perf_counter() - t0:.1f} s", flush=True)
    return changed


class GodotImporter:
    """Editör kapalıyken `godot --import`'u arka planda çalıştırır: izleme döngüsü beklemez.
    Import sürerken yeni model gelirse, bitince bir tur daha yapılır."""

    def __init__(self):
        self.proc = None
        self.started = 0.0
        self.pending = False

    def request(self):
        if buildkit.godot_editor_open():
            print(f"[watch {stamp()}] editör açık: pencereye geçince import eder, galeri yenilenir",
                  flush=True)
            return
        self.pending = True
        self.poll()

    def poll(self):
        if self.proc and self.proc.poll() is not None:
            self.log.close()
            with open(self.log.name, encoding="utf-8", errors="replace") as f:
                errors = [ln for ln in f.read().splitlines() if ln.startswith(("ERROR", "SCRIPT ERROR"))]
            os.remove(self.log.name)
            print(f"[watch {stamp()}] Godot import: {'tamam' if not errors else f'{len(errors)} hata'} "
                  f"({time.perf_counter() - self.started:.1f} s)", flush=True)
            for line in errors[:10]:
                print("    " + line, flush=True)
            self.proc = None
        if self.pending and self.proc is None:
            self.pending = False
            self.started = time.perf_counter()
            # çıktı boruya değil dosyaya: süreç bitmeden okunmayan boru dolunca Godot kilitlenir
            self.log = tempfile.NamedTemporaryFile("w", suffix=".log", delete=False)
            self.proc = subprocess.Popen([buildkit.godot_exe(), "--headless", "--path",
                                          buildkit.PROJECT_DIR, "--import"], stdout=self.log,
                                         stderr=subprocess.STDOUT)

    def finish(self):
        while self.proc or self.pending:
            if self.proc:
                self.proc.wait()
            self.poll()


def main():
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    ap = argparse.ArgumentParser(prog="watch")
    ap.add_argument("--no-godot", action="store_true")
    ap.add_argument("--max-seconds", type=float, default=0.0, help="test için: bu süre sonra çık")
    args = ap.parse_args(argv)

    version = bpy.app.version_string
    importer = None if args.no_godot else GodotImporter()
    print(f"[watch {stamp()}] izleniyor: {len(buildkit.watched_files())} dosya (Ctrl+C ile çık)", flush=True)
    if build_dirty(version) and importer:          # açılışta eşitle
        importer.request()
    seen = snapshot()
    started = time.monotonic()
    try:
        while not args.max_seconds or time.monotonic() - started < args.max_seconds:
            time.sleep(POLL)
            if importer:
                importer.poll()
            now = snapshot()
            if now == seen:
                continue
            time.sleep(DEBOUNCE)
            now = snapshot()
            changed = sorted(p for p in set(now) | set(seen) if now.get(p) != seen.get(p))
            print(f"[watch {stamp()}] değişti: {', '.join(os.path.basename(p) for p in changed)}",
                  flush=True)
            seen = now
            if build_dirty(version) and importer:
                importer.request()
    except KeyboardInterrupt:
        pass
    if importer:
        importer.finish()
    print(f"[watch {stamp()}] çıkılıyor", flush=True)


main()
