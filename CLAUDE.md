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
- exp02: **bonsai, 3 aşama** (`blender/props/make_bonsai.py`). **Stil istisnası**: PS1 kuralları dışında; med poly, smooth, pastel vertex color, `pastel_spatial.gdshader`. Han-kengai (yarı şelale), ardıç bulutları, seladon oval porselen saksı. Aşamalar aynı yolun (TRUNK_PATH) başını kullanır, yani aynı ağacın büyümesi. Üçgen: 2110 / 3640 / 5838 (kullanıcı 5.8k'yı onayladı). `--part pot|stage1|stage2|stage3|all [--export] [--preview p.png] [--front]`.
- Önizlemeler `blender/props/previews/` altında.
- `blender/.gdignore` var: Godot `.blend` kaynaklarını kendisi import etmeye çalışmasın.

## Bilinen tuzaklar

- **Vertex color + GL Compatibility**: glTF köşe renkleri lineer gelir. Compatibility renderer sRGB uzayında hesap yaptığından shader'da `linear_to_srgb` gerekir (`#if CURRENT_RENDERER == RENDERER_COMPATIBILITY`). İki shader da bunu yapıyor (8 Ekim 2026).
- **bmesh icosphere**: `bmesh.ops.create_icosphere(subdivisions=1)` bölünmemiş ikosahedron (20 yüz). 2 → 80, 3 → 320 üçgen (arayüzdekinden bir düzey eksik).
- Workbench önizlemesi vertex color'ı loş gösterir; pastel/smooth işler için EEVEE + `view_transform = "Standard"` kullan.
- Bash'te `python` çağırma: Windows Python yükleyicisini tetikleyip Python kuruyor (8 Ekim 2026'da 3.14.8 istemeden kuruldu). Dosya düzenlemeyi Edit/sed ile yap, Python gerekiyorsa Blender'ın kendi Python'unu kullan.

## Prop üretim akışı (kullanıcının seçimi: A)

Her prop kendi üretici script'iyle **arka plan Blender'ında** yapılır; açık Blender oturumuna dokunulmaz:

```
"<BLENDER_EXE>" --background --factory-startup --python blender/props/make_<ad>.py -- <scratchpad>/<ad>_preview.png
```

- Çıktılar: `blender/props/<ad>.blend` (kullanıcı açar ya da Append eder), `blender/props/textures/<ad>.png`, `assets/models/<ad>.glb`, önizleme PNG'si (Workbench render).
- Sonra `experiments/expNN_ad/expNN.tscn` sahnesi `shared/scripts/model_spinner.gd`'yi kullanır; `model_paths` (yan yana dizilir), `style` (0 = PS1, 1 = PASTEL; pastelde malzeme adı sonekine göre `PASTEL_PRESETS`), `spacing`, `spin_speed` ayarlanır. Pencereli `--write-movie` ile karelere bakıp doğrula.
- Örnek ve şablon: `blender/props/make_crate.py` (bmesh ile kutu parçaları, parça başına UV yönü, prosedürel piksel doku, vertex color ile ton + sahte AO).
- **Galeri bilgisi (zorunlu):** Her prop objesine custom property yaz: `obj["prop_name"]` (Türkçe görünen ad), `obj["prop_style"]` (`"ps1"` | `"pastel"`), `obj["prop_placement"]` (`"floor"` | `"pedestal"`). glTF extras olarak gider; Godot `MeshInstance3D`'nin `extras` metadata'sına koyar (`PropStyle.extras()` okur). Bilgisi olmayan model galeride PS1 + yere konur.

## Galeri (exp03) — FPS ile propları gezme

- `experiments/exp03_gallery/exp03.tscn`: `assets/models/*.glb`'yi tarar (`exclude` listesi hariç, varsayılan `test_cube`), bilgiye göre stil + yer/kaide (0.6×0.8×0.6 m) ile sıraya dizer, her mesh'e convex çarpışma ekler. Yeni .glb = galeride yeni sergi, ek iş yok.
- `shared/scripts/fps_player.gd` (`FpsPlayer`): çarpışma ve kamerayı kendisi kurar. WASD, Shift, Space, F uçma (Space/Ctrl), Esc fare. Eylemler çalışma anında `InputMap`'e eklenir (fiziksel tuş), `project.godot`'a dokunulmaz. `controls_enabled` ile kapatılabilir.
- `shared/scripts/prop_style.gd` (`PropStyle`): `apply(root, style)`, `extras(root)`, `local_aabb(root)`; spinner ve galeri ortak kullanır.
- Stüdyo ışığı Compatibility'de kolay patlar: sky ambient 0.45, güneş 0.75, zemin taban rengi ~0.56. Değerleri artırırken kareye bakarak doğrula.
- Test: geçici bir sahneden `Input.action_press` ve `InputEventMouseMotion` ile karakteri sür, `--write-movie` ile kaydet; geçici klasörü sonra sil.

## Klasör düzeni

```
blender-test/
├─ project.godot
├─ blender/export_glb.py        # Blender -> .glb export yardımcısı
├─ blender/props/               # make_<ad>.py üreticiler, <ad>.blend, textures/
├─ assets/models/               # Blender'dan gelen .glb dosyaları (elle düzenleme yok)
├─ shared/shaders/ps1_spatial.gdshader
├─ shared/shaders/pastel_spatial.gdshader   # PS1 dışı yumuşak/pastel stil
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
6. Galeri 2. kontrol noktası (onaylı plan): E ile inceleme modu (360° döndürme, tekerlekle yakınlaştırma, Esc çıkış), sergi etiketleri (ad, üçgen, stil), wireframe tuşu. İnsan silueti istenmedi.
7. Kullanıcı isterse affine UV / vertex titremesi değerlerini (`snap_grid`, `affine_amount`, `color_levels`) ayarla.

Not: `Desktop\godot-blender-lab` ilk kurulan iskelet. Aktif çalışma burada, bu klasörde.
