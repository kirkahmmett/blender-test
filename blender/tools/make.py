"""Tek bir asset spec'ini üret (geliştirme ve önizleme için; toplu derleme build_all.py'de).

    blender --background --factory-startup --python blender/tools/make.py -- blender/specs/tomato.toml \
        [--part stage4|all] [--preview out.png] [--front] [--style pastel] [--export [--force]]

--style yalnızca önizleme içindir (ör. başka bir stilin kataloğa etkisini görmek); export
spec'in kendi stiliyle yapılır. Varsayılan --part son varyanttır.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "lib"))
import assetkit  # noqa: E402

assetkit.ensure_paths()
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if not argv or not argv[0].endswith(".toml"):
    print("kullanım: ... make.py -- blender/specs/<ad>.toml [--part ...] [--preview ...]")
    sys.exit(2)
assetkit.run(argv[0], argv[1:])
