"""Derleme işçisi: verilen üreticileri bu Blender sürecinde art arda çalıştırır, sonuçları JSON yazar.
build_all.py paralel derlemede bunu ayrı süreçler olarak başlatır; elle çalıştırmak gerekmez.

    blender --background --factory-startup --python blender/tools/worker.py -- --out sonuç.json gen1 gen2 ...
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import buildkit  # noqa: E402

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
ap = argparse.ArgumentParser(prog="worker")
ap.add_argument("--out", required=True)
ap.add_argument("--extra", default="")
ap.add_argument("gens", nargs="+")
args = ap.parse_args(argv)

results = [buildkit.run_generator(g, args.extra.split()) for g in args.gens]
with open(args.out, "w", encoding="utf-8") as f:
    json.dump(results, f, ensure_ascii=False)
