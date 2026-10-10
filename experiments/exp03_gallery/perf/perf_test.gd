extends Node
## Galeri performans testi: gerçek GPU ile, karakter olmadan (fare kilitlenmez) galeriyi kurar ve
## sabit bakış noktalarından ölçer. Pencereli çalıştır (headless GPU ölçemez):
##   godot --path . res://experiments/exp03_gallery/perf/perf_test.tscn [-- --out rapor.json]
## Çıktı: "[perf]" satırları + JSON rapor (varsayılan blender/build/perf_report.json).
##
## Ölçülenler (bakış noktası başına, 90 karelik ortalama; vsync kapalı):
##   kare süresi (ms), çizim çağrısı, ekrandaki üçgen (LOD etkisi), görünür obje, video bellek.
## Ayrıca galerinin kurulum süresi (glb yükleme + çarpışma + etiket).

const GALLERY := preload("res://experiments/exp03_gallery/exp03.tscn")
const WARMUP := 30
const SAMPLES := 90
const SHOTS_DIR := "res://blender/build/tmp/perf"   # bakış noktası başına ekran görüntüsü (git dışı)

var _gallery: Node3D
var _camera: Camera3D
var _views: Array[Dictionary] = []
var _report := {}
var _view := -1
var _frame := 0
var _sum := {}
var _t_last := 0


func _ready() -> void:
	DisplayServer.window_set_vsync_mode(DisplayServer.VSYNC_DISABLED)
	Engine.max_fps = 0

	var t0 := Time.get_ticks_usec()
	_gallery = GALLERY.instantiate()
	_gallery.spawn_player = false
	add_child(_gallery)
	var build_ms := (Time.get_ticks_usec() - t0) / 1000.0

	_camera = Camera3D.new()
	_camera.fov = 75.0
	add_child(_camera)
	_camera.current = true

	var exhibits: Array = _gallery.exhibits
	var first: Node3D = exhibits[0]
	var last: Node3D = exhibits[-1]
	var mid_x := (first.position.x + last.position.x) * 0.5
	var biggest: Node3D = exhibits[0]
	for e: Node3D in exhibits:
		if e.get_meta("prop_info").triangles > biggest.get_meta("prop_info").triangles:
			biggest = e
	_views = [
		{"name": "genel", "pos": Vector3(mid_x, 2.2, 6.0), "look": Vector3(mid_x, 0.6, 0.0)},
		{"name": "yakın", "pos": biggest.position + Vector3(0.0, 1.5, 1.4),
			"look": biggest.position + Vector3(0.0, 1.1, 0.0)},
		{"name": "uzak", "pos": Vector3(mid_x, 4.0, 40.0), "look": Vector3(mid_x, 0.6, 0.0)},
	]
	var total_tris := 0
	for e: Node3D in exhibits:
		total_tris += e.get_meta("prop_info").triangles
	_report = {"build_ms": snappedf(build_ms, 0.1), "exhibits": exhibits.size(),
			"model_triangles": total_tris, "renderer": RenderingServer.get_current_rendering_method(),
			"gpu": RenderingServer.get_video_adapter_name(), "views": {}}
	print("[perf] galeri kurulumu: %.1f ms, %d sergi, modellerde %d üçgen" % [build_ms, exhibits.size(), total_tris])
	_next_view()


func _next_view() -> void:
	_view += 1
	if _view >= _views.size():
		_finish()
		return
	var v: Dictionary = _views[_view]
	_camera.position = v.pos
	_camera.look_at(v.look)
	_frame = 0
	_sum = {"ms": 0.0, "draw": 0.0, "prims": 0.0, "objects": 0.0}


func _process(_delta: float) -> void:
	if _view < 0 or _view >= _views.size():
		return
	var now := Time.get_ticks_usec()
	_frame += 1
	if _frame > WARMUP:
		_sum.ms += (now - _t_last) / 1000.0
		_sum.draw += Performance.get_monitor(Performance.RENDER_TOTAL_DRAW_CALLS_IN_FRAME)
		_sum.prims += Performance.get_monitor(Performance.RENDER_TOTAL_PRIMITIVES_IN_FRAME)
		_sum.objects += Performance.get_monitor(Performance.RENDER_TOTAL_OBJECTS_IN_FRAME)
	_t_last = now
	if _frame >= WARMUP + SAMPLES:
		var v: Dictionary = _views[_view]
		var r := {}
		for k: String in _sum:
			r[k] = snappedf(_sum[k] / SAMPLES, 0.01)
		r["vram_mb"] = snappedf(Performance.get_monitor(Performance.RENDER_VIDEO_MEM_USED) / 1048576.0, 0.1)
		_report.views[v.name] = r
		# görsel karşılaştırma için kare (optimizasyon görüntüyü değiştirmemeli)
		DirAccess.make_dir_recursive_absolute(ProjectSettings.globalize_path(SHOTS_DIR))
		get_viewport().get_texture().get_image().save_png("%s/%s.png" % [SHOTS_DIR, v.name])
		print("[perf] %-6s kare %.2f ms | çizim çağrısı %d | ekranda üçgen %d | obje %d | VRAM %.1f MB"
				% [v.name, r.ms, r.draw, r.prims, r.objects, r.vram_mb])
		_next_view()


func _finish() -> void:
	var out := "res://blender/build/perf_report.json"
	var args := OS.get_cmdline_user_args()
	var i := args.find("--out")
	if i >= 0 and i + 1 < args.size():
		out = args[i + 1]
	var f := FileAccess.open(out, FileAccess.WRITE)
	if f:
		f.store_string(JSON.stringify(_report, "  ", true) + "\n")
	print("[perf] rapor: ", ProjectSettings.globalize_path(out) if out.begins_with("res://") else out)
	get_tree().quit(1 if _regressed() else 0)


## Taban çizgisiyle (blender/build/perf_baseline.json, git'te) karşılaştır. Gerileme: aynı sayıda
## sergide çizim çağrısı %10'dan fazla arttı ya da kurulum süresi 2 katını aştı (makine gürültüsü
## için geniş). Kare süresi gürültülü olduğundan yalnızca raporlanır. --update-baseline tabanı yazar.
func _regressed() -> bool:
	var path := "res://blender/build/perf_baseline.json"
	if "--update-baseline" in OS.get_cmdline_user_args() or not FileAccess.file_exists(path):
		var f := FileAccess.open(path, FileAccess.WRITE)
		f.store_string(JSON.stringify(_report, "  ", true) + "\n")
		print("[perf] taban çizgisi yazıldı")
		return false
	var base: Dictionary = JSON.parse_string(FileAccess.get_file_as_string(path))
	if int(base.exhibits) != int(_report.exhibits):
		print("[perf] sergi sayısı değişmiş (%d → %d): karşılaştırma yok, tabanı güncelle: --update-baseline"
				% [base.exhibits, _report.exhibits])
		return false
	var bad := false
	for view: String in _report.views:
		var b: float = base.views[view].draw
		var now: float = _report.views[view].draw
		if now > b * 1.10:
			print("[perf] GERİLEME %s: çizim çağrısı %d → %d" % [view, b, now])
			bad = true
	if _report.build_ms > base.build_ms * 2.0 + 20.0:
		print("[perf] GERİLEME: galeri kurulumu %.0f → %.0f ms" % [base.build_ms, _report.build_ms])
		bad = true
	print("[perf] taban çizgisine göre: %s" % ("GERİLEME VAR" if bad else "tamam"))
	return bad
