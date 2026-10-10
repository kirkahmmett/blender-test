# Blender_Test — Godot 4.7 × Blender 5.2 × Claude

Sıfırdan deneyler için kum havuzu. Bu klasör bir Godot 4.7 projesinin kökü (`project.godot` burada, renderer: GL Compatibility). Kullanıcının gerçek oyun projelerinden bağımsızdır; `Desktop\Godot` altındaki oyun projesine (morningwillwait) dokunma.

Kullanıcı Türkçe konuşur; yanıtları Türkçe ver.

## Durum (8 Ekim 2026)

- Blender 5.2.2 LTS kurulu. Resmi Blender Lab MCP eklentisi kurulu. Canlı bağlantı için Blender açık olmalı ve eklentinin sunucusu başlatılmış olmalı; `Cannot connect to Blender at localhost:9876` hatası sunucunun kapalı olduğunu gösterir.
- Blender'dan `assets/models/test_cube.glb` (vertex color'lı, 12 üçgen) export edildi. Export hattı çalışıyor.
- `shared/shaders/ps1_spatial.gdshader` ve `experiments/exp00_hello/` **doğrulandı**: headless import/check/run hatasız; pencereli çalıştırmada (OpenGL 3.3, RTX 4060) shader derleniyor, vertex color'lı küp PS1 snap'iyle dönüyor, hata/uyarı yok.
- `GODOT_EXE = "C:\Users\pc\Desktop\Godot_v4.7.1-stable_win64.exe"` (exe'nin kendi bildirdiği sürüm 4.7.1.stable).
- Görsel doğrulama için pencereli çalıştırıp kareleri kaydet, sonra PNG'ye bak:
  `<GODOT_EXE> --path . res://experiments/exp00_hello/exp00.tscn --write-movie <scratchpad>/f.png --fixed-fps 30 --quit-after 60`

- `BLENDER_EXE = "C:\Program Files (x86)\Steam\steamapps\common\Blender\blender.exe"` (5.2.2 LTS, Steam kurulumu).
- exp01: `wooden_crate` (204 üçgen, 64 px tahta dokusu + vertex color tonu) üretildi, Godot'ta doğrulandı.
- exp02: **bonsai, 3 aşama** (`blender/specs/bonsai.toml`, aile `families/bonsai.py`). **Stil istisnası**: PS1 kuralları dışında; med poly, smooth, pastel vertex color, `pastel_spatial.gdshader`. Han-kengai (yarı şelale), ardıç bulutları, seladon oval porselen saksı. Aşamalar aynı yolun (TRUNK_PATH) başını kullanır, yani aynı ağacın büyümesi. Üçgen: 2110 / 3640 / 5838 (kullanıcı 5.8k'yı onayladı). `--part pot|stage1|stage2|stage3|all [--export] [--preview p.png] [--front]`.
- **Domates fidanı, 4 aşama** (`blender/specs/tomato.toml`, aile `families/tomato.py`, 10 Ekim 2026): pastel, med-high poly; fide → genç (bambu çubuk + ip) → çiçekli (sarı çiçek salkımları, tomurcuk, minik yeşil meyve) → olgun (alt salkım pastel kırmızı, orta turuncu-yeşil, üst çiçek). Terakota saksı. Aynı bitkinin büyümesi: düğüm azimutları (137.5°), gövde kıvrımı, salkım düğümleri (6, 8, 11) sabit; boy, yaprak sayı/boyu, olgunluk değişir. Kullanıcı onaylı bütçe `prop_budget`: 2200 / 5500 / 10000 / 13200; şu an 1602 / 3971 / 7370 / 11912. Bileşik yaprak: sap + 1–3 yaprakçık çifti + ara minik yaprakçıklar + uç yaprakçık (tırtıklı, hafif çanak). Malzemeler: tomato_terracotta/soil/stem/leaf/fruit/petal/stake.
- Önizlemeler `blender/props/previews/` altında.
- `blender/.gdignore` var: Godot `.blend` kaynaklarını kendisi import etmeye çalışmasın.

## Bilinen tuzaklar

- **Vertex color + GL Compatibility**: glTF köşe renkleri lineer gelir. Compatibility renderer sRGB uzayında hesap yaptığından shader'da `linear_to_srgb` gerekir (`#if CURRENT_RENDERER == RENDERER_COMPATIBILITY`). İki shader da bunu yapıyor (8 Ekim 2026).
- **bmesh icosphere**: `bmesh.ops.create_icosphere(subdivisions=1)` bölünmemiş ikosahedron (20 yüz). 2 → 80, 3 → 320 üçgen (arayüzdekinden bir düzey eksik).
- Workbench önizlemesi vertex color'ı loş gösterir; pastel/smooth işler için EEVEE + `view_transform = "Standard"` kullan.
- Bash'te `python` çağırma: Windows Python yükleyicisini tetikleyip Python kuruyor (8 Ekim 2026'da 3.14.8 istemeden kuruldu). Dosya düzenlemeyi Edit/sed ile yap, Python gerekiyorsa Blender'ın kendi Python'unu kullan.

## Prop üretim akışı (kullanıcının seçimi: A)

Her şey **arka plan Blender'ında** üretilir; açık Blender oturumuna dokunulmaz.

**Asset = veri + aile + parça + stil (Sprint 2, 10 Ekim 2026; `blender/lib/assetkit.py`):**
- `blender/specs/<ad>.toml`: asset'in tüm verisi (ölçüler, palet, aşama/varyantlar, adlar, bütçeler). Biçim `assetkit.py` başındaki açıklamada. Her `[[variant]]` bir obje = bir glb.
- `blender/lib/families/<aile>.py`: algoritma, `build(ctx, variant, collection) -> obj`. Şu an: `crate`, `bonsai`, `tomato` (otsu çubuklu bitki).
- `blender/lib/parts/`: birden çok ailenin kullandığı parçalar. `pots.py`: tornalanmış saksı + toprak, renk modları `glaze` / `terracotta`, toprak `moss` / `plain`. Saksı verileri `blender/specs/parts/*.toml`; spec'te `pot = "@parts/pot_terracotta"` (kök anahtar, ilk `[tablo]`dan önce yaz — sonra yazılırsa o tabloya girer).
- `blender/styles/<ad>.toml`: `godot` (galeri shader'ı: ps1/pastel), `[color]` saturation/value/lift, `[mesh]` density. Varsayılanlar (1/1/0/1) hiçbir hesap yapmaz → çıktı bayt bayt aynı. Aileler renkleri `ctx.color(palet_anahtarı)`, segment sayılarını `ctx.style.seg(n)` ile almalı ki stil etkili olsun.
- Taşıma kanıtı: eski `make_*.py` script'lerinin ürettiği 8 glb, spec'lerden bayt bayt aynı üretildi (manifest "aynı"); `.blend`'ler yeniden kaydedilmedi.
- **Yeni asset:** mevcut ailedeyse yalnızca yeni bir TOML (ör. sarı çeri domates denemesi: palet + salkımlar + `@parts/pot_celadon_oval`; `previews/demo_spec_cherry_celadon.png`). Yeni bir biçimse yeni aile modülü. Kodla özel durum hâlâ mümkün: `blender/props/make_<ad>.py` (`--build`/`--force` sözleşmesi, propkit akışı) da birim sayılır.

Tek spec'i denemek / önizlemek:

```
"<BLENDER_EXE>" --background --factory-startup --python blender/tools/make.py -- blender/specs/<ad>.toml [--part <id>|all] [--preview p.png] [--front] [--style <stil>]
```

`--style` yalnızca önizleme içindir (export spec'in stiliyle; ör. `previews/demo_style_muted.png`: doygunluk 0.7, yoğunluk 0.6 → domates 11912 → 9927 üçgen). `--export` yalnızca `--part all` ile (`.blend` tüm varyantları tutar).

**Tek komut (her değişiklikten sonra çalıştır):**

```
"<BLENDER_EXE>" --background --factory-startup --python blender/tools/build_all.py -- [--only <ad>] [--full] [--jobs N] [--no-godot]
```

Üretim birimlerini kendisi bulur: `blender/specs/*.toml` + varsa `blender/props/make_*.py`. **Artımlı** (Sprint 1, 10 Ekim 2026): `blender/build/manifest.json` (git'te izlenir) her birim için girdi özetini (şema + Blender sürümü + birim + spec'in `@` başvuruları ve stili + `blender/lib/**/*.py` (buildkit hariç) + `export_glb.py`) ve çıktı sha256'larını tutar; girdi ve çıktılar aynıysa atlanır, çıktı silinmiş/dışarıdan değişmişse yeniden derler. Kirli üreticiler **paralel** işçilere bölünür (`blender/tools/worker.py`; ana süreç de işçi; önceki sürelere göre dağıtım); üreticiler süreç içinde `runpy` ile çalışır (`buildkit.run_generator`), sonuçlar `propkit.EVENTS`'ten okunur. Değişmeyen glb'ye dokunulmaz (geçici klasöre export + bayt karşılaştırma) → Godot boşuna import etmez; hiçbir glb değişmediyse Godot adımı atlanır; proje editörde açıksa CLI import yapılmaz. Kalite tablosu manifestteki tüm asset'leri gösterir. Sorun varsa çıkış kodu 1. Ölçümler: değişiklik yok 1.7 s (yalnızca Blender açılışı), tam paralel derleme 3.6 s, tek üretici + Godot ~11 s (Godot import ~5–6 s sabit). Godot yolu `blender/tools/paths.json` (ya da `GODOT_EXE`).

**İzleme modu (günlük çalışma için):**

```
"<BLENDER_EXE>" --background --factory-startup --python blender/tools/watch.py -- [--no-godot]
```

Blender açık kalır; üretici/kit kaydedilince yalnızca etkilenen üretici süreç içinde yeniden üretilir (kaydet → yeni glb ~1 s). Editör açıksa editör kendisi import eder ve galeri (`gallery.gd`, `resources_reimported` / `filesystem_changed`) kendini yeniler; editör kapalıysa `godot --import` arka planda çalışır, izleyici beklemez. Manifesti build_all ile aynı anda iki süreç yazmasın: izleme açıkken build_all çalıştırma.

**Oyun içi optimizasyon (Sprint 3, 10 Ekim 2026; `propkit.optimize`, `assetkit.run` her objeye uygular):**
- **Malzeme birleştirme (pastel):** parçalar `<önek>_solid` (arka yüz çizilmez) + `<önek>_thin` (çift taraflı; `propkit.THIN_MATERIALS` = leaf, petal) olarak ikiye iner → prop başına ≤2 çizim çağrısı (bonsai 4→1, domates 7→2). Parçanın asıl malzeme kimliği **köşe renginin alfa kanalında** (id/255; alfa zaten kullanılmıyordu, Godot 8 bit saklar, ≤16 parça), adları `obj["prop_materials"]` (virgüllü, kimlik sırası) extras ile Godot'a gider. `pastel_common.gdshaderinc` `use_lut` ile `lut_roughness/specular/rim/tint[16]` dizilerinden okur; `PropStyle._pastel_lut` dizileri `PASTEL_PRESETS`'ten doldurur (ince ayar yine Godot'ta). Eski (parça başına malzeme) glb'ler eski yoldan çalışır. Yeni ince yüzey parçası: `THIN_MATERIALS`'a ekle. QA: >2 malzeme uyarı.
- **Çarpışma:** modelin dışbükey zarfı `<obje>-convcolonly` çocuk objesi (Blender'da tel kafes, render'da gizli) → Godot import'ta StaticBody3D + ConvexPolygonShape3D (sandık 8, bonsai 176, domates 122 nokta). Galeri bu varsa açılışta çarpışma hesaplamaz. `export_props` objeyi çocuklarıyla seçer.
- **LOD:** Godot'un otomatik LOD'u (`meshes/generate_lods=true`, varsayılan) Compatibility'de çalışıyor: uzak bakışta ekrandaki üçgen 38k → 3.6k. Ek iş yok.
- **Import varsayılanı:** `project.godot` `[importer_defaults] scene = {"meshes/ensure_tangents": false}` (normal map yok). Ölçüm: Godot sıkıştırmalı mesh'te teğeti yine tutuyor, VRAM değişmedi (16.8 MB) — zararsız, kazancı yok.
- **Performans testi:** `experiments/exp03_gallery/perf/perf_test.tscn` (pencereli; galeri `spawn_player=false`, fare kilitlenmez). 3 bakış noktası (genel / yakın / uzak) × 90 kare: kare süresi, çizim çağrısı, ekrandaki üçgen, obje, VRAM + galeri kurulum süresi; ekran görüntüleri `blender/build/tmp/perf/`. `blender/build/perf_baseline.json` (git'te) ile karşılaştırır: çizim çağrısı >%10 ya da kurulum >2×+20 ms artarsa GERİLEME, çıkış kodu 1. `-- --update-baseline` tabanı yazar (sergi sayısı değişince gerekir). `build_all --perf` bunu çalıştırır.
- Sprint 3 ölçümü (RTX 4060, 8 sergi): galeri kurulumu ~560 → ~35 ms; çizim çağrısı genel 193 → 97, yakın 96 → 48, uzak 64 → 40; görüntü önce/sonra piksel farkı ortalama 0.02/255 (yalnızca ince kenarlarda çizim sırası farkı).
- Gizli iç yüz temizliği yapılmadı: tek örnek sandığın iç içe kirişleri (toplam 204 üçgen), kazanç ölçülemeyecek kadar küçük; kaynak paylaşımlı köşeleri birleştirmek gölgelendirmeyi değiştirirdi.

- **Alt süreç tuzağı:** `Popen(stdout=PIPE)` ile başlatılıp bitene kadar okunmayan süreç, boru dolunca kilitlenir (izleme modunda Godot import'u takıldı). Uzun süren alt süreçlerin çıktısını dosyaya yönlendir.

- **Kod üreticisi sözleşmesi (özel durumlar):** `make_<ad>.py` `--build` (her şeyi üret + export) ve `--force` kabul etmeli; `propkit.guard_overwrite` → üret → `propkit.save_generated` → `propkit.export_props` sırasını izlemeli (`assetkit.run` aynı akışı uygular).
- **Kalite kontrolü (`propkit.check_object`):** hata = prop_name/style/placement eksik ya da geçersiz, üçgen bütçesi aşımı (`BUDGETS`: ps1 500, pastel 6000), merkez noktası tabanda değil (±1 cm). uyarı = isim snake_case değil, ölçek/dönüş uygulanmamış, merkez izdüşüm dışında, ölçü 2 cm–10 m dışında, doku kare/2'nin kuvveti değil, PS1 dokuda >256 px ya da nearest değil. Sonuç glb'ye `qa` extras'ı olarak gömülür; galeride hata kırmızı, uyarı turuncu etiket; inceleme paneli listeler. `qa` anahtarı hiç yoksa "kontrolden geçmemiş" uyarısı.
- `save_generated` içerik değişmediyse `.blend`'i yeniden kaydetmez (git'te ikili fark oluşmasın). glb export'u deterministik.

- Çıktılar: `blender/props/<blend>.blend` (kullanıcı açar ya da Append eder), `blender/props/textures/<ad>.png`, `assets/models/<obje>.glb`, önizleme PNG'si (EEVEE, `meshkit.render_preview`).
- Galeri (exp03) yeni glb'leri kendiliğinden gösterir. Tek modeli döndürerek görmek için `shared/scripts/model_spinner.gd` (`model_paths`, `style`, `spacing`, `spin_speed`).
- **Elle düzenleme koruması (`blender/lib/propkit.py`):** Üretici script'ler `.blend`'i `propkit.save_generated()` ile kaydeder; içerik parmak izi "propkit_fingerprint" Text bloğuna yazılır (scene property değil: glTF'e sızar). Üretimden önce `propkit.guard_overwrite()` dosyayı açıp karşılaştırır; içerik değiştiyse **durur**. Yalnızca açıp kaydetmek uyarı vermez. `--force` eskisini `blender/props/_backup/`'a (git dışı) yedekleyip üstüne yazar; **`--force`'u kullanıcıya sormadan kullanma.** Elle düzenlenmiş dosyayı Godot'a göndermek için yeniden üretme, yalnızca export et: `"<BLENDER_EXE>" --background blender/props/<ad>.blend --python blender/tools/export_props.py` (`prop_style` olan her obje orijinde `assets/models/<obje adı>.glb`).
- Üretmeden önce MCP ile (ya da süreç listesinden) kullanıcının Blender'ında aynı `.blend`'in açık olmadığını kontrol et; açıksa kullanıcı sonra kaydedince bizim yazdığımızı ezer.
- **Galeri bilgisi (zorunlu; spec'ten `assetkit.run` yazar):** Her prop objesinde custom property: `obj["prop_name"]` (Türkçe görünen ad), `obj["prop_style"]` (`"ps1"` | `"pastel"`), `obj["prop_placement"]` (`"floor"` | `"pedestal"`). glTF extras olarak gider; Godot `MeshInstance3D`'nin `extras` metadata'sına koyar (`PropStyle.extras()` okur). Bilgisi olmayan model galeride PS1 + yere konur.

## Galeri (exp03) — FPS ile propları gezme

- `experiments/exp03_gallery/exp03.tscn`: `assets/models/*.glb`'yi tarar (`exclude` listesi hariç, varsayılan `test_cube`), bilgiye göre stil + yer/kaide (0.6×0.8×0.6 m) ile sıraya dizer, her mesh'e convex çarpışma ekler. Yeni .glb = galeride yeni sergi, ek iş yok.
- `shared/scripts/fps_player.gd` (`FpsPlayer`): çarpışma ve kamerayı kendisi kurar. WASD, Shift, Space, F uçma (Space/Ctrl), Esc fare. Eylemler çalışma anında `InputMap`'e eklenir (fiziksel tuş), `project.godot`'a dokunulmaz. `controls_enabled` ile kapatılabilir.
- `shared/scripts/prop_style.gd` (`PropStyle`): `apply(root, style)`, `extras(root)`, `local_aabb(root)`; spinner ve galeri ortak kullanır.
- Stüdyo ışığı Compatibility'de kolay patlar: sky ambient 0.45, güneş 0.75, zemin taban rengi ~0.56. Değerleri artırırken kareye bakarak doğrula.
- Test: geçici bir sahneden `Input.action_press` ve `InputEventMouseMotion` ile karakteri sür, `--write-movie` ile kaydet; geçici klasörü sonra sil.
- **Fare bakışı tuzakları (9 Ekim 2026'da düzeltildi):** (1) Kilitli imleç ekran ortasındadır; oradaki bir Control (varsayılan `MOUSE_FILTER_STOP` olan ColorRect nişangâh) fare hareketini yutar ve `_unhandled_input`'a hiç ulaşmaz. Bakış/yörünge `_input`'ta, HUD öğeleri `MOUSE_FILTER_IGNORE`. (2) `canvas_items` ölçeklemesinde `relative` pencere boyutuyla ölçeklenir; bakış için `screen_relative` kullan. Testte sentetik fare olayının `position`'ını ekran ortasına ver, yoksa (1) gizlenir.
- **Galeri @tool:** `gallery.gd` editörde de stüdyo + sergileri kurar (sahipsiz "Generated" düğümü, sahneye kaydedilmez); karakter/HUD/inceleme yalnızca oyunda. Inspector'da "Galeriyi yenile" düğmesi (`@export_tool_button`). `PropStyle` da `@tool`. Editörde çalışan koda `Engine.is_editor_hint()` koruması koy; editör açıkken ikinci bir editör örneği açma.
- **Pastel malzeme eşlemesi (`PropStyle.PASTEL_PRESETS`):** Blender malzeme adı sonekine göre (porcelain, terracotta, soil, bark, stem, stake, foliage, leaf, petal, fruit). `"double_sided": true` → `pastel_leaf` shader; yeni ince yüzey malzemesi eklerken bunu unutma. Açık pastel yeşiller galeri ışığında beyaza taşar: foliage/leaf için specular/rim düşük, `albedo_tint` ~0.86–0.9. Blender tarafında ince yüzey malzemelerinde `use_backface_culling = False`, kapalı gövdelerde True (glTF doubleSided buna göre).
- İnceleme sırasında sergi kaidesi gizlenir (alttan 360° bakış için), çıkışta geri gelir.
- Testte pencereli kayıt gerçek fareyi kilitleyebilir: test sahnesinde `player.controls_enabled = false` ve `inspector.mouse_sensitivity = 0` yap, yönü elle ver.
- Pencereli testler gerçek fareyi kısa süre kilitler ve kullanıcının fare hareketi değerleri bozar; kesin değer gerekiyorsa headless çalıştır (headless'ta fare kilitlenmez, FpsPlayer bakışı test edilemez).
- Test tuzakları: sentetik `InputEventKey`'de hem `keycode` hem `physical_keycode` doldur (`ui_cancel` keycode ile eşleşir, bizim eylemler fiziksel). Kayıt modunda sentetik fare hareketi FpsPlayer'a her zaman ulaşmayabilir; bakış açısını testte doğrudan `camera.rotation.x` ile ver.

## Klasör düzeni

```
blender-test/
├─ project.godot
├─ blender/export_glb.py        # Blender -> .glb export yardımcısı
├─ blender/lib/propkit.py       # ortak prop kiti: parmak izi koruması, kalite kontrolü, export
├─ blender/lib/meshkit.py       # ortak geometri: srgb, MeshBuilder, tube, catmull_rom, render_preview
├─ blender/tools/export_props.py # elle düzenlenmiş .blend için yalnızca export
├─ blender/tools/build_all.py    # tek komut: artımlı + paralel üretim, kalite kontrolü, Godot testi
├─ blender/tools/watch.py        # izleme modu: kaydet → yeniden üret (~1 s)
├─ blender/tools/worker.py       # paralel derleme işçisi (build_all başlatır)
├─ blender/lib/buildkit.py       # derleme çekirdeği: girdi özeti, manifest, süreç içi çalıştırma, Godot
├─ blender/build/manifest.json   # derleme kaydı (izlenir); perf_baseline.json (izlenir); tmp/, perf_report.json git dışı
├─ experiments/exp03_gallery/perf/  # performans testi (pencereli)
├─ blender/tools/paths.json      # Godot exe yolu
├─ blender/specs/               # asset spec'leri (TOML); parts/ ortak parça verileri (saksılar)
├─ blender/styles/              # stil tokenları (pastel, ps1)
├─ blender/lib/assetkit.py      # spec → asset üretim akışı, Style, Ctx
├─ blender/lib/families/        # aileler: crate, bonsai, tomato
├─ blender/lib/parts/           # ortak parçalar: pots (saksı + toprak)
├─ blender/tools/make.py        # tek spec'i üret / önizle (--style)
├─ blender/props/               # <ad>.blend kaynakları, textures/, previews/, _backup/ (git dışı)
├─ assets/models/               # Blender'dan gelen .glb dosyaları (elle düzenleme yok)
├─ shared/shaders/ps1_spatial.gdshader
├─ shared/shaders/pastel_common.gdshaderinc # pastel gövdesi (iki shader include eder)
├─ shared/shaders/pastel_spatial.gdshader   # pastel, cull_back (kapalı gövdeler)
├─ shared/shaders/pastel_leaf.gdshader      # pastel, çift taraflı (yaprak, taç yaprak)
├─ shared/shaders/grid_floor.gdshader   # 1 m / 5 m ızgaralı zemin
├─ shared/scripts/model_spinner.gd   # model önizleme sahnesi (model_paths, style)
├─ shared/scripts/fps_player.gd      # FpsPlayer
├─ shared/scripts/prop_style.gd      # PropStyle: stil, extras, aabb
└─ experiments/expNN_ad/        # her deney kendi klasöründe
```

## Blender'dan export

Blender'a MCP üzerinden şu kodu gönder (kullanıcının açık sahnesini bozma; seçili objeleri export eder ve seçimi geri yükler):

```python
import sys, importlib
sys.path.insert(0, r"C:\Users\pc\Documents\blender-test\blender")
import export_glb; importlib.reload(export_glb)
export_glb.export_glb("exp01_ad", source="selection",
                      project_dir=r"C:\Users\pc\Documents\blender-test")
```

- Kullanıcının açık sahnesine test objesi ekleme. Gerekirse geçici bir sahne aç (`bpy.data.scenes.new`, `window.scene = tmp`), işin bitince sahneyi, objeyi ve mesh'i sil, `window.scene`'i eski haline getir.
- Eklenti kodu `exec` ile çalıştırır; sonucu `result = {...}` ile döndür.
- Dosyayı değiştirdikten sonra Blender'daki modül önbelleği için `importlib.reload` şart.

## Kurallar

- 1 Blender birimi = 1 metre = 1 Godot birimi. Export +Y Up. Godot'ta elle döndürme/ölçekleme ile telafi etme.
- İsimlendirme: `snake_case`. Collider için obje adına `-col`, `-convcol`, `-colonly` ekle.
- PS1 bütçesi: prop ≤ 500 üçgen, karakter ≤ 1500. Dokular kare, 64–256 px, nearest. Normal map yok, mümkünse vertex color.
- Godot kodu: GDScript, tipli, tab girinti. Ortak şeyler `shared/` altına.
- Git: `main` dalı, ilk commit 51920be (8 Ekim 2026). Kimlik yalnızca repo için ayarlı (ahmetenes058). `.gitignore`: `.godot/`, `__pycache__/`, `*.blend1`.
- **Otomatik commit + push (kullanıcı isteği, 8 Ekim 2026):** Her commit'ten hemen sonra `git push` da yap (kullanıcı onayladı, ayrıca sorma). Push başarısız olursa (ağ, giriş, çakışma) zorlamadan (`--force` yok) dur ve kullanıcıya bildir. Kullanıcı bir adımı onayladığında ("tamam", "evet", "böyle kalsın", "geç" gibi) ya da bir iş doğrulanıp bittiğinde, sormadan commit at. Mesaj Türkçe, ne yapıldığını özetlesin. Yalnızca o adımın dosyalarını ekle; yarım kalmış ya da onay bekleyen işi commit etme. Uzak repo: `origin` = https://github.com/kirkahmmett/blender-test (private, 8 Ekim 2026'da bağlandı; giriş Git Credential Manager'da kayıtlı). Commit'ten sonra kısa hash'i kullanıcıya söyle.

## Test komutları (GODOT_EXE bilindikten sonra)

```
<GODOT_EXE> --headless --path . --import
<GODOT_EXE> --headless --path . --quit-after 5
<GODOT_EXE> --headless --path . --check-only --script res://shared/scripts/model_spinner.gd
```

## Sıradaki işler

1. ~~exp00 doğrulaması~~ ve ~~headless kontroller~~ — tamam (8 Ekim 2026).
2. Prop'larda origin tabanın ortasında olsun (sahneye y=0 ile konur). model_spinner kamerayı AABB'ye göre ortalar.
3. ~~İlk PS1 prop~~ — wooden_crate tamam. Sıradaki prop'ları kullanıcı seçer.
4. ~~ps1_spatial renk dönüşümü~~ — tamam.
5. ~~Tuşla odaklanma~~ — tamam: model_spinner'de 1–9 tek modele (kamera tween, diğerleri gizlenir), 0 hepsine. Kadraj dönüşten bağımsız silindir kutusuyla hesaplanır.
6. ~~Galeri 2. kontrol noktası~~ — tamam (9 Ekim 2026): `shared/scripts/prop_inspector.gd` (`PropInspector`): E ile yörünge kamerası (fare döndür, tekerlek yakınlaştır, R sıfırla, Esc/E çık; kamera yumuşak geçişle gider/döner), sağ üst panelde ad/üçgen/stil/ölçü (cm). Galeride Label3D etiketler (L), wireframe (G; `RenderingServer.set_debug_generate_wireframes(true)` mesh'ler yüklenmeden önce çağrılmalı). İnceleme sırasında etiket, nişangâh ve yardım gizlenir. İnsan silueti istenmedi.
7. Kullanıcı isterse affine UV / vertex titremesi değerlerini (`snap_grid`, `affine_amount`, `color_levels`) ayarla.

Not: `Desktop\godot-blender-lab` ilk kurulan iskelet. Aktif çalışma burada, bu klasörde.
