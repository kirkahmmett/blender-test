"""Derleme kiti: artımlı derleme, manifest, üreticileri süreç içinde çalıştırma, Godot adımı.

build_all.py (tek komut) ve watch.py (izleme modu) bunu kullanır.

Artımlı derleme
---------------
İş birimi ("üretici"): asset spec'i (blender/specs/*.toml, bkz. assetkit) ya da özel durumlar için
kod (blender/props/make_*.py); biri birden çok asset üretebilir. Girdi özeti = şema sürümü +
Blender sürümü + birim dosyası + spec'in başvurduğu dosyalar (saksı spec'leri, stil) + ortak
kod (blender/lib/**/*.py, buildkit hariç; blender/export_glb.py). Manifest (blender/build/manifest.json) her üretici için girdi özetini
ve çıktıların (glb + blend) sha256'sını tutar. Girdi aynı ve çıktılar diskte aynıysa üretici
atlanır. Çıktı elle değiştirildiyse (ör. export_props ile) yeniden derlenir; .blend elle
düzenlendiyse propkit koruması üretimi durdurur ve "atlandı" raporlanır.

Süreç içi çalıştırma
--------------------
Blender'ın açılışı (~1.7 s) üretimden pahalı. run_generator() bir üreticiyi açık Blender
sürecinin içinde runpy ile çalıştırır; böylece bir süreç birçok üreticiyi art arda üretir.
Kit modülleri her çalıştırmadan önce yeniden yüklenir (izleme modunda kod değişikliği görünsün).
Sonuçlar metinden değil propkit.EVENTS'ten okunur.
"""

import contextlib
import glob
import hashlib
import io
import json
import os
import runpy
import subprocess
import sys
import time
import traceback

LIB_DIR = os.path.dirname(os.path.abspath(__file__))
BLENDER_DIR = os.path.dirname(LIB_DIR)
PROJECT_DIR = os.path.dirname(BLENDER_DIR)
PROPS_DIR = os.path.join(BLENDER_DIR, "props")
SPECS_DIR = os.path.join(BLENDER_DIR, "specs")
STYLES_DIR = os.path.join(BLENDER_DIR, "styles")
BUILD_DIR = os.path.join(BLENDER_DIR, "build")
MANIFEST_PATH = os.path.join(BUILD_DIR, "manifest.json")
TOOLS_DIR = os.path.join(BLENDER_DIR, "tools")
GALLERY_SCENE = "res://experiments/exp03_gallery/exp03.tscn"

SCHEMA = 1  # artırılırsa her şey yeniden derlenir (çıktı biçimi değiştiğinde)
KIT_MODULES = ("propkit", "meshkit", "export_glb")


def rel(path):
    return os.path.relpath(path, PROJECT_DIR).replace("\\", "/")


def absolute(relpath):
    return os.path.join(PROJECT_DIR, relpath)


def file_hash(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- girdiler ve manifest

def generators(only=()):
    """Üretim birimleri: asset spec'leri (blender/specs/*.toml) + kod üreticileri (make_*.py)."""
    gens = sorted(glob.glob(os.path.join(SPECS_DIR, "*.toml")))
    gens += sorted(glob.glob(os.path.join(PROPS_DIR, "make_*.py")))
    if only:
        gens = [g for g in gens if any(o in os.path.basename(g) for o in only)]
    return [rel(g) for g in gens]


def common_inputs():
    """Üreticilerin kullandığı ortak kod (aileler, parçalar dahil). buildkit'in kendisi hariç:
    derleme aracını değiştirmek asset'leri yeniden ürettirmesin."""
    files = sorted(f for f in glob.glob(os.path.join(LIB_DIR, "**", "*.py"), recursive=True)
                   if os.path.basename(f) != "buildkit.py" and "__pycache__" not in f)
    files.append(os.path.join(BLENDER_DIR, "export_glb.py"))
    return [rel(f) for f in files]


def unit_deps(gen):
    """Spec'in başvurduğu dosyalar (saksı spec'leri, stil); kod üreticisi için boş."""
    if not gen.endswith(".toml"):
        return []
    import assetkit
    _, deps = assetkit.load_spec(absolute(gen))
    return sorted({rel(d) for d in deps})


def watched_files():
    """İzleme modunun baktığı dosyalar: birimler + tüm spec/stil dosyaları + ortak kod."""
    data = glob.glob(os.path.join(SPECS_DIR, "**", "*.toml"), recursive=True)
    data += glob.glob(os.path.join(STYLES_DIR, "*.toml"))
    return sorted(set(generators()) | {rel(f) for f in data}) + common_inputs()


def input_hash(gen, blender_version):
    h = hashlib.sha256(f"schema={SCHEMA}\nblender={blender_version}\n".encode())
    for path in [gen] + unit_deps(gen) + common_inputs():
        h.update(path.encode() + b"\0")
        with open(absolute(path), "rb") as f:
            h.update(f.read())
    return h.hexdigest()


def load_manifest():
    if not os.path.isfile(MANIFEST_PATH):
        return {"schema": SCHEMA, "generators": {}}
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        data = json.load(f)
    if data.get("schema") != SCHEMA:
        return {"schema": SCHEMA, "generators": {}}
    return data


def save_manifest(manifest):
    """Deterministik yazım (sıralı anahtarlar, zaman damgası yok): git'te yalnızca gerçek fark."""
    os.makedirs(BUILD_DIR, exist_ok=True)
    text = json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    if os.path.isfile(MANIFEST_PATH):
        with open(MANIFEST_PATH, encoding="utf-8") as f:
            if f.read() == text:
                return False
    with open(MANIFEST_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return True


def dirty_reason(gen, manifest, blender_version):
    """Üretici yeniden derlenmeli mi? Gerekmiyorsa None, gerekiyorsa nedeni."""
    entry = manifest["generators"].get(gen)
    if entry is None:
        return "yeni (manifestte yok)"
    try:
        current = input_hash(gen, blender_version)
    except Exception as e:  # bozuk TOML / eksik başvuru: derlemede hatasıyla görünsün
        return f"girdi okunamadı: {e}"
    if entry["input"] != current:
        return "girdi değişti (spec, kod ya da Blender sürümü)"
    for path, digest in entry["outputs"].items():
        if not os.path.isfile(absolute(path)):
            return f"çıktı eksik: {path}"
        if file_hash(absolute(path)) != digest:
            return f"çıktı dışarıdan değişmiş: {path}"
    return None


def manifest_entry(result, gen, blender_version):
    outputs, assets = {}, {}
    for ev in result["events"]:
        if ev["type"] == "glb":
            outputs[rel(ev["path"])] = ev["sha256"]
            assets[ev["name"]] = {"triangles": ev["triangles"], "issues": ev["issues"]}
        elif ev["type"] == "blend" and os.path.isfile(ev["path"]):
            outputs[rel(ev["path"])] = file_hash(ev["path"])
    return {"input": input_hash(gen, blender_version), "blender": blender_version,
            "outputs": outputs, "assets": assets, "seconds": round(result["seconds"], 2)}


# ---------------------------------------------------------------- çalıştırma

def run_generator(gen, extra_args=()):
    """Üreticiyi bu Blender sürecinin içinde '--build' ile çalıştır. Sonuç sözlüğü döner:
    status: "üretildi" | "atlandı" (elle düzenlenmiş .blend korundu) | "ÇÖKTÜ"."""
    import bpy

    # ortak kodun taze kopyası (aileler, parçalar dahil): izleme modunda düzenleme görünsün
    for name, mod in list(sys.modules.items()):
        path = getattr(mod, "__file__", None) or ""
        if name in KIT_MODULES or (path and os.path.abspath(path).startswith(LIB_DIR) and name != "buildkit"):
            sys.modules.pop(name, None)
    for path in (LIB_DIR, BLENDER_DIR):
        if path not in sys.path:
            sys.path.insert(0, path)
    import propkit  # noqa: F401  (taze kopya; üretici aynı modülü alır)

    saved_argv = sys.argv
    sys.argv = [bpy.app.binary_path, "--", "--build", *extra_args]
    buf = io.StringIO()
    error = None
    t0 = time.perf_counter()
    try:
        with contextlib.redirect_stdout(buf):
            if gen.endswith(".toml"):
                import assetkit
                assetkit.run(absolute(gen), ["--build", *extra_args])
            else:
                runpy.run_path(absolute(gen), run_name="__main__")
    except BaseException:  # SystemExit dahil: üretici süreci düşürmesin
        error = traceback.format_exc()
    finally:
        sys.argv = saved_argv
    seconds = time.perf_counter() - t0

    events = list(sys.modules["propkit"].EVENTS) if "propkit" in sys.modules else []
    if error:
        status = "ÇÖKTÜ"
    elif any(ev["type"] == "refused" for ev in events):
        status = "atlandı"
    else:
        status = "üretildi"
    return {"generator": gen, "status": status, "seconds": seconds, "events": events,
            "error": error, "log": buf.getvalue()[-4000:]}


def spawn_worker(gens, out_path, extra_args=()):
    """Ayrı bir Blender sürecinde worker.py ile üreticileri çalıştır (paralel derleme)."""
    import bpy
    cmd = [bpy.app.binary_path, "--background", "--factory-startup", "--python-exit-code", "1",
           "--python", os.path.join(TOOLS_DIR, "worker.py"), "--", "--out", out_path,
           *([f"--extra={' '.join(extra_args)}"] if extra_args else []), *gens]
    # çıktı dosyaya: ana süreç kendi işini bitirene dek boruyu okumaz, dolarsa işçi duraklar
    log = open(out_path + ".log", "w", encoding="utf-8")
    try:
        return subprocess.Popen(cmd, cwd=PROJECT_DIR, stdout=log, stderr=subprocess.STDOUT)
    finally:
        log.close()  # alt süreç kendi kopyasını tutar


def split_jobs(gens, manifest, workers):
    """Önceki sürelere göre açgözlü dağıtım: en uzun işler önce, en boş işçiye."""
    cost = {g: manifest["generators"].get(g, {}).get("seconds", 3.0) for g in gens}
    groups = [[] for _ in range(workers)]
    loads = [0.0] * workers
    for g in sorted(gens, key=lambda g: -cost[g]):
        i = loads.index(min(loads))
        groups[i].append(g)
        loads[i] += cost[g]
    return [grp for grp in groups if grp]


# ---------------------------------------------------------------- Godot

def godot_exe():
    if os.environ.get("GODOT_EXE"):
        return os.environ["GODOT_EXE"]
    with open(os.path.join(TOOLS_DIR, "paths.json"), encoding="utf-8") as f:
        return json.load(f)["godot"]


def expected_versions():
    with open(os.path.join(TOOLS_DIR, "paths.json"), encoding="utf-8") as f:
        return json.load(f).get("versions", {})


def check_versions(blender_version, need_godot=True):
    """Beklenen araç sürümleri (paths.json "versions") ile çalışanları karşılaştır; uyarı listesi.
    Blender sürümü girdi özetine de girer: farklı sürüm her şeyi yeniden derler ve çıktıyı
    değiştirebilir. Godot sürümü import sonucunu (mesh biçimi, LOD) etkiler."""
    want = expected_versions()
    warnings = []
    if want.get("blender") and blender_version != want["blender"]:
        warnings.append(f"Blender {blender_version} çalışıyor, beklenen {want['blender']} "
                        "(çıktılar değişebilir; paths.json'u bilerek güncelle)")
    if need_godot and want.get("godot"):
        try:
            out = subprocess.run([godot_exe(), "--version"], capture_output=True, text=True,
                                 encoding="utf-8", errors="replace", timeout=30).stdout.strip()
        except (OSError, subprocess.TimeoutExpired) as e:
            out = f"çalıştırılamadı ({e})"
        if not out.startswith(want["godot"]):
            warnings.append(f"Godot {out or '?'} bulundu, beklenen {want['godot']}")
    return warnings


def godot_editor_open():
    """Bu proje bir Godot editöründe açık mı? Açıksa komut satırından import yapılmaz:
    iki süreç aynı .godot önbelleğine yazmasın, editör değişen dosyaları kendisi alır."""
    if sys.platform != "win32":
        return False
    # hızlı ön kontrol: Godot hiç çalışmıyorsa yavaş PowerShell sorgusuna gerek yok
    try:
        tasks = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, text=True,
                               encoding="utf-8", errors="replace", timeout=10).stdout
    except (OSError, subprocess.TimeoutExpired):
        tasks = "godot"
    if "godot" not in tasks.lower():
        return False
    ps = ("Get-CimInstance Win32_Process -Filter \"Name LIKE 'Godot%'\" | "
          "ForEach-Object { $_.CommandLine }")
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True,
                             text=True, encoding="utf-8", errors="replace", timeout=20).stdout
    except (OSError, subprocess.TimeoutExpired):
        return False
    project = PROJECT_DIR.replace("\\", "/").lower()
    for line in out.splitlines():
        line_n = line.replace("\\", "/").lower()
        if project in line_n and ("--editor" in line_n or " -e " in f"{line_n} "):
            return True
    return False


PERF_SCENE = "res://experiments/exp03_gallery/perf/perf_test.tscn"
VISUAL_SCENE = "res://shared/tests/visual_test.tscn"


def _godot_windowed(scene, prefix):
    """Pencereli Godot testi (GPU gerekir; fare kilitlenmez). (geçti mi, ilgili satırlar)."""
    proc = subprocess.run([godot_exe(), "--path", PROJECT_DIR, scene], cwd=PROJECT_DIR,
                          capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
    lines = [ln for ln in (proc.stdout + proc.stderr).splitlines()
             if ln.startswith((prefix, "ERROR", "SCRIPT ERROR"))]
    return proc.returncode == 0, lines


def godot_perf():
    """Galeri performans testi + taban çizgisi karşılaştırması."""
    return _godot_windowed(PERF_SCENE, "[perf]")


def godot_visual():
    """Görsel regresyon testi: her asset altın görüntüsüyle karşılaştırılır."""
    return _godot_windowed(VISUAL_SCENE, "[visual]")


def godot_check():
    """import + galeri açılış testi; [(adım, saniye, hata satırları)]."""
    exe = godot_exe()
    steps = []
    for label, args in [("import", ["--import"]), ("galeri", [GALLERY_SCENE, "--quit-after", "30"])]:
        t0 = time.perf_counter()
        proc = subprocess.run([exe, "--headless", "--path", PROJECT_DIR] + args, cwd=PROJECT_DIR,
                              capture_output=True, text=True, encoding="utf-8", errors="replace")
        out = proc.stdout + proc.stderr
        errors = [ln for ln in out.splitlines() if ln.startswith(("ERROR", "SCRIPT ERROR"))]
        if proc.returncode != 0 and not errors:
            errors = [f"çıkış kodu {proc.returncode}"]
        steps.append((label, time.perf_counter() - t0, errors))
    return steps
