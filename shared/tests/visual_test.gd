extends Node
## Görsel regresyon testi: her asset oyundaki shader'larıyla (PropStyle) sabit ışık ve sabit
## kameradan iki açıdan render edilir ve onaylı "altın" görüntülerle karşılaştırılır.
##   godot --path . res://shared/tests/visual_test.tscn [-- --update-golden]
## Pencereli çalıştır (GPU gerekir; fare kilitlenmez).
##
## Altın görüntüler: blender/build/golden/<asset>_<açı>.png (git'te). Altını olmayan yeni asset'in
## görüntüsü yazılır (git'te görsel fark = onay). Fark eşiği aşılırsa gerçek görüntü ve fark
## haritası blender/build/tmp/visual/'a yazılır, çıkış kodu 1. Tekrarlanabilirlik için sabit
## boyutlu SubViewport, gölge ve MSAA kapalı.

const MODELS_DIR := "res://assets/models/"
const GOLDEN_DIR := "res://blender/build/golden"
const OUT_DIR := "res://blender/build/tmp/visual"
const SIZE := Vector2i(384, 384)
const EXCLUDE := ["test_cube"]
## Eşikler: bir pikselin herhangi bir kanalı PIXEL_TOLERANCE'tan (0..255) fazla değişirse "değişmiş";
## değişmiş piksel oranı MAX_CHANGED'i ya da ortalama fark MAX_MEAN'i aşarsa fark sayılır.
## Aynı makinede render birebir tekrarlanıyor (fark 0); tolerans yalnızca sürücü/GPU farkları içindir.
## Kalibrasyon: olgun domates kırmızısında EE9585 → E8897A (ekranda kanal başına 4–8) yakalanır.
const PIXEL_TOLERANCE := 3
const MAX_CHANGED := 0.0005   # %0.05 ≈ 74 piksel (384²)
const MAX_MEAN := 0.5
const ANGLES := {
	"on": Vector3(0.35, 0.3, 1.0),       # 3/4 önden, hafif yukarıdan
	"ust": Vector3(-0.6, 1.4, 0.7),      # arkadan-yukarıdan (başka yüzleri de görsün)
}

var _viewport: SubViewport
var _camera: Camera3D
var _jobs: Array = []        # [glb yolu, açı adı]
var _current: Node3D
var _wait := 0
var _update := false
var _failed: Array[String] = []
var _new: Array[String] = []
var _passed := 0


func _ready() -> void:
	_update = "--update-golden" in OS.get_cmdline_user_args()
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(GOLDEN_DIR))
	DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(OUT_DIR))

	_viewport = SubViewport.new()
	_viewport.size = SIZE
	_viewport.msaa_3d = Viewport.MSAA_DISABLED
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_viewport.own_world_3d = true
	add_child(_viewport)

	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.background_color = Color(0.78, 0.8, 0.84)
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	env.ambient_light_color = Color(0.85, 0.86, 0.9)
	env.ambient_light_energy = 0.6
	var we := WorldEnvironment.new()
	we.environment = env
	_viewport.add_child(we)
	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50.0, 30.0, 0.0)
	sun.light_energy = 0.8
	sun.shadow_enabled = false
	_viewport.add_child(sun)
	_camera = Camera3D.new()
	_camera.fov = 40.0
	_viewport.add_child(_camera)
	_camera.current = true

	for path in _model_paths():
		for angle: String in ANGLES:
			_jobs.append([path, angle])
	print("[visual] %d asset × %d açı" % [_jobs.size() / ANGLES.size(), ANGLES.size()])
	_start_job()


func _model_paths() -> PackedStringArray:
	var paths := PackedStringArray()
	for file in DirAccess.get_files_at(MODELS_DIR):
		file = file.trim_suffix(".import")
		if file.get_extension() != "glb" or file.get_basename() in EXCLUDE:
			continue
		if MODELS_DIR + file not in paths:
			paths.append(MODELS_DIR + file)
	paths.sort()
	return paths


func _start_job() -> void:
	if _current:
		_current.queue_free()
		_current = null
	if _jobs.is_empty():
		_finish()
		return
	var path: String = _jobs[0][0]
	var angle: String = _jobs[0][1]
	_current = (load(path) as PackedScene).instantiate()
	_viewport.add_child(_current)
	PropStyle.apply(_current, PropStyle.extras(_current).get("prop_style", "ps1"))
	var box := PropStyle.local_aabb(_current)
	var center := box.get_center()
	var radius := maxf(box.size.length() * 0.5, 0.05)
	var dist := radius / sin(deg_to_rad(_camera.fov * 0.5)) * 1.05
	_camera.position = center + (ANGLES[angle] as Vector3).normalized() * dist
	_camera.look_at(center)
	_wait = 3   # shader derlemesi + birkaç kare otursun


func _process(_delta: float) -> void:
	if _current == null or _jobs.is_empty():
		return
	_wait -= 1
	if _wait > 0:
		return
	var path: String = _jobs[0][0]
	var angle: String = _jobs[0][1]
	var key := "%s_%s" % [path.get_file().get_basename(), angle]
	var shot := _viewport.get_texture().get_image()
	shot.convert(Image.FORMAT_RGB8)   # kayıt ve karşılaştırma aynı biçimde
	var golden_path := "%s/%s.png" % [GOLDEN_DIR, key]
	if _update or not FileAccess.file_exists(golden_path):
		if not _update:
			_new.append(key)
		shot.save_png(golden_path)
	else:
		var golden := Image.load_from_file(ProjectSettings.globalize_path(golden_path))
		golden.convert(Image.FORMAT_RGB8)
		var m: Dictionary = shot.compute_image_metrics(golden, false)
		# ortalama, küçük ama yerel değişikliği (ör. meyve rengi) gizler: değişen piksel oranına bak
		var changed := 0.0 if m.max <= PIXEL_TOLERANCE else _changed_fraction(shot, golden)
		if changed > MAX_CHANGED or m.mean > MAX_MEAN:
			_failed.append("%s (değişen piksel %%%.2f, ortalama %.2f, en büyük %d)"
					% [key, changed * 100.0, m.mean, m.max])
			shot.save_png("%s/%s.png" % [OUT_DIR, key])
			_diff_image(shot, golden).save_png("%s/%s_fark.png" % [OUT_DIR, key])
		else:
			_passed += 1
	_jobs.pop_front()
	_start_job()


## Herhangi bir kanalı PIXEL_TOLERANCE'tan fazla değişen piksellerin oranı (RGB8 bayt dizisi üzerinde).
func _changed_fraction(a: Image, b: Image) -> float:
	var da := a.get_data()
	var db := b.get_data()
	var changed := 0
	for i in range(0, da.size(), 3):
		if absi(da[i] - db[i]) > PIXEL_TOLERANCE or absi(da[i + 1] - db[i + 1]) > PIXEL_TOLERANCE \
				or absi(da[i + 2] - db[i + 2]) > PIXEL_TOLERANCE:
			changed += 1
	return changed / float(SIZE.x * SIZE.y)


## Fark haritası: farkın büyüklüğü kırmızı (×4), aynı pikseller soluk gri.
func _diff_image(a: Image, b: Image) -> Image:
	var out := Image.create(SIZE.x, SIZE.y, false, Image.FORMAT_RGB8)
	for y in SIZE.y:
		for x in SIZE.x:
			var ca := a.get_pixel(x, y)
			var cb := b.get_pixel(x, y)
			var d := maxf(maxf(absf(ca.r - cb.r), absf(ca.g - cb.g)), absf(ca.b - cb.b))
			out.set_pixel(x, y, Color(minf(d * 4.0, 1.0), 0, 0) if d > 0.01 else Color(ca.v * 0.3, ca.v * 0.3, ca.v * 0.3))
	return out


func _finish() -> void:
	if _update:
		print("[visual] altın görüntüler güncellendi")
	for key in _new:
		print("[visual] YENİ altın görüntü (git'te gözden geçir): %s" % key)
	for line in _failed:
		print("[visual] FARK: %s" % line)
	print("[visual] %d geçti, %d fark, %d yeni — %s" % [_passed, _failed.size(), _new.size(),
			"SORUN VAR" if not _failed.is_empty() else "tamam"])
	if not _failed.is_empty():
		print("[visual] gerçek görüntüler ve fark haritaları: %s" % ProjectSettings.globalize_path(OUT_DIR))
	get_tree().quit(1 if not _failed.is_empty() else 0)
