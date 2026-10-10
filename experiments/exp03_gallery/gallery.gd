@tool
extends Node3D
## exp03 — prop galerisi. assets/models/ içindeki her .glb'yi tarar ve bir sıra halinde dizer.
## Stil ve yerleşim Blender'dan gelen bilgiden okunur (PropStyle.extras):
##   prop_style: "ps1" | "pastel"   prop_placement: "floor" | "pedestal"   prop_name: görünen ad
## Bilgisi olmayan model PS1 stiliyle yere konur. Yeni bir .glb eklemek galeriye eklemek demektir.
##
## @tool: stüdyo ve sergiler editörde de kurulur (karakter, HUD ve inceleme yalnızca oyunda).
## Hepsi sahibi (owner) olmayan "Generated" düğümünün altındadır, yani sahne dosyasına
## kaydedilmez; her açılışta yeniden kurulur. Yeni .glb sonrası Inspector'daki
## "Galeriyi yenile" düğmesi yeter.

const MODELS_DIR := "res://assets/models/"
const GRID_SHADER := preload("res://shared/shaders/grid_floor.gdshader")
const PEDESTAL_SIZE := Vector3(0.6, 0.8, 0.6)
const GAP := 1.6  # sergiler arası boşluk (m)
const PLAYER_START := Vector3(0.0, 0.0, 4.5)
const AIM_RANGE := 5.0  # E ile incelemek için en fazla uzaklık (m)

const ACTIONS := {
	"inspect": [KEY_E],
	"inspect_reset": [KEY_R],
	"toggle_wireframe": [KEY_G],
	"toggle_labels": [KEY_L],
}

## Galeriye alınmayacak modeller (dosya adı, uzantısız).
@export var exclude: PackedStringArray = ["test_cube"]:
	set(value):
		exclude = value
		if is_node_ready():
			_rebuild()

@export_tool_button("Galeriyi yenile", "Reload") var rebuild_button := _rebuild

## false: yalnızca stüdyo + sergiler (karakter, HUD, inceleme yok). Performans testi kullanır.
@export var spawn_player := true

var player: FpsPlayer
var inspector: PropInspector
var exhibits: Array[Node3D] = []

var _generated: Node3D  # stüdyo + sergiler; kaydedilmez

var _aimed: Node3D  # nişangâhın üstünde olduğu sergi
var _hidden_pedestal: Node3D  # inceleme sırasında gizlenen kaide
var _inspected: Node3D  # incelenen sergi (durum değişikliği için)
var _status: Dictionary  # assets/asset_status.json (AssetStatus)
var _labels: Array[Label3D] = []
var _labels_on := true
var _aim_label: Label
var _crosshair: ColorRect
var _help: Label


func _ready() -> void:
	if Engine.is_editor_hint():
		_rebuild()
		set_physics_process(false)
		_watch_editor_imports()
		return

	# wireframe görünümü, mesh'ler yüklenmeden önce açılmalı
	RenderingServer.set_debug_generate_wireframes(true)
	FpsPlayer.ensure_actions(ACTIONS)

	_rebuild()
	if not spawn_player:   # ör. performans testi: kendi kamerası var, fare kilitlenmez
		set_physics_process(false)
		return
	_build_hud()

	player = FpsPlayer.new()
	player.position = PLAYER_START
	add_child(player)

	inspector = PropInspector.new()
	add_child(inspector)
	inspector.closed.connect(_on_inspector_closed)
	inspector.status_requested.connect(_on_status_requested)


## Editörde: model klasörüne yeni ya da yeniden import edilmiş glb gelince galeriyi yenile
## (blender/tools/watch.py ile birlikte: kaydet → üret → editör import eder → galeri güncellenir).
## EditorInterface'e adla erişilir: doğrudan yazılsa dışa aktarılmış oyunda derlenmez.
func _watch_editor_imports() -> void:
	var editor: Object = Engine.get_singleton("EditorInterface")
	if editor == null:
		return
	var fs: Object = editor.get_resource_filesystem()
	if not fs.resources_reimported.is_connected(_on_resources_reimported):
		fs.resources_reimported.connect(_on_resources_reimported)
		fs.filesystem_changed.connect(_on_filesystem_changed)


func _exit_tree() -> void:
	var editor: Object = Engine.get_singleton("EditorInterface") if Engine.is_editor_hint() else null
	if editor:
		var fs: Object = editor.get_resource_filesystem()
		if fs.resources_reimported.is_connected(_on_resources_reimported):
			fs.resources_reimported.disconnect(_on_resources_reimported)
			fs.filesystem_changed.disconnect(_on_filesystem_changed)


func _on_resources_reimported(paths: PackedStringArray) -> void:
	for p in paths:
		if p.begins_with(MODELS_DIR) and p.get_extension() == "glb":
			_rebuild.call_deferred()
			return


## Yeni eklenen ya da silinen model (yeniden import olmadan da galeri değişmeli).
func _on_filesystem_changed() -> void:
	var shown := PackedStringArray()
	for e in exhibits:
		shown.append(e.get_meta("prop_info").path)
	if shown != _model_paths():
		_rebuild.call_deferred()


## Stüdyoyu ve sergileri (yeniden) kur.
func _rebuild() -> void:
	if _generated:
		_generated.free()
	exhibits.clear()
	_labels.clear()
	_generated = Node3D.new()
	_generated.name = "Generated"
	add_child(_generated)
	_status = AssetStatus.load_all()
	_build_studio()
	_place_props(_model_paths())
	if not Engine.is_editor_hint() and _help:
		_refresh_overlay()


func _unhandled_input(event: InputEvent) -> void:
	if Engine.is_editor_hint() or player == null:
		return
	if event.is_action_pressed("toggle_wireframe"):
		var vp := get_viewport()
		vp.debug_draw = Viewport.DEBUG_DRAW_DISABLED if vp.debug_draw == Viewport.DEBUG_DRAW_WIREFRAME \
				else Viewport.DEBUG_DRAW_WIREFRAME
	elif event.is_action_pressed("toggle_labels") and not inspector.active:
		_labels_on = not _labels_on
		_refresh_overlay()
	elif event.is_action_pressed("inspect") and _aimed and not inspector.active:
		var info: Dictionary = _aimed.get_meta("prop_info")
		player.controls_enabled = false
		# kaide alttan bakışı kapatmasın: inceleme boyunca gizle (prop havada kalır)
		_hidden_pedestal = _aimed.get_node_or_null("Pedestal")
		if _hidden_pedestal:
			_hidden_pedestal.visible = false
		inspector.open(info.model, info, player.camera)
		_inspected = _aimed
		_set_aim(null)
		_refresh_overlay()
	else:
		return
	get_viewport().set_input_as_handled()


func _physics_process(_delta: float) -> void:
	if inspector.active:
		return
	var cam := player.camera
	var from := cam.global_position
	var query := PhysicsRayQueryParameters3D.create(from, from - cam.global_basis.z * AIM_RANGE)
	query.exclude = [player.get_rid()]
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	_set_aim(_exhibit_of(hit.collider) if hit else null)


## Çarpışma gövdesinden yukarı çıkıp ait olduğu sergiyi bul.
func _exhibit_of(node: Object) -> Node3D:
	var n := node as Node
	while n and n != self:
		if n.has_meta("prop_info"):
			return n as Node3D
		n = n.get_parent()
	return null


func _set_aim(exhibit: Node3D) -> void:
	_aimed = exhibit
	if exhibit:
		_aim_label.text = "E — İncele: %s" % exhibit.get_meta("prop_info").name
	_aim_label.visible = exhibit != null
	_crosshair.color = Color(1.0, 0.85, 0.3) if exhibit else Color(1, 1, 1, 0.8)


## İncelemede 1–4: onay durumu assets/asset_status.json'a yazılır (karar anındaki glb özetiyle).
func _on_status_requested(status: String) -> void:
	if _inspected == null:
		return
	var info: Dictionary = _inspected.get_meta("prop_info")
	var record := AssetStatus.set_status(info.asset, info.path, status)
	_status[info.asset] = record
	info.status = AssetStatus.effective(record, info.path)
	info.record = record
	_update_badge(_inspected)
	inspector.refresh(info)


func _on_inspector_closed() -> void:
	_inspected = null
	player.controls_enabled = true
	if _hidden_pedestal:
		_hidden_pedestal.visible = true
		_hidden_pedestal = null
	_refresh_overlay()


## İnceleme sırasında nişangâh, yürüme yardımı ve 3D etiketler gizlenir
## (etiketler incelenen propun önüne düşer; panel aynı bilgiyi verir).
func _refresh_overlay() -> void:
	var walking := not inspector.active
	_crosshair.visible = walking
	_help.visible = walking
	for label in _labels:
		label.visible = walking and _labels_on


func _model_paths() -> PackedStringArray:
	var paths := PackedStringArray()
	for file in DirAccess.get_files_at(MODELS_DIR):
		# dışa aktarılmış oyunda yalnızca .import dosyaları kalır
		file = file.trim_suffix(".import")
		if file.get_extension() != "glb" or file.get_basename() in exclude:
			continue
		var path := MODELS_DIR + file
		if path not in paths and ResourceLoader.exists(path):
			paths.append(path)
	paths.sort()
	return paths


func _place_props(paths: PackedStringArray) -> void:
	# önce hepsini kur ve genişliklerini ölç, sonra sırayı ortala
	var spans: Array[Vector2] = []  # sergi başına (sol, sağ) x sınırı
	for path in paths:
		var exhibit := _make_exhibit(path)
		_generated.add_child(exhibit)
		exhibits.append(exhibit)
		var box := PropStyle.local_aabb(exhibit)
		_add_label(exhibit, box)
		var left := minf(box.position.x, -PEDESTAL_SIZE.x * 0.5)
		var right := maxf(box.end.x, PEDESTAL_SIZE.x * 0.5)
		spans.append(Vector2(left, right))

	var total := 0.0
	for s in spans:
		total += s.y - s.x
	total += GAP * maxf(spans.size() - 1, 0)
	var x := -total * 0.5
	for i in exhibits.size():
		exhibits[i].position.x = x - spans[i].x
		x += spans[i].y - spans[i].x + GAP


## Sergi üstünde, kameraya dönük ad + üçgen + stil etiketi (L ile aç/kapa).
func _add_label(exhibit: Node3D, box: AABB) -> void:
	var info: Dictionary = exhibit.get_meta("prop_info")
	var issues: PackedStringArray = info.issues
	var label := Label3D.new()
	label.text = "%s\n%d üçgen · %s" % [info.name, info.triangles, info.style]
	if not issues.is_empty():
		label.text += "\n(!) %d sorun — E ile incele" % issues.size()
	label.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	label.font_size = 40
	label.pixel_size = 0.0022
	label.outline_size = 10
	label.modulate = _issue_color(issues)
	label.outline_modulate = Color(1, 1, 1, 0.85)
	label.vertical_alignment = VERTICAL_ALIGNMENT_BOTTOM   # satır sayısı ne olursa olsun yukarı büyür
	label.position = Vector3(box.get_center().x, box.end.y + 0.12, box.get_center().z)
	exhibit.add_child(label)
	_labels.append(label)

	# onay rozeti: ad etiketinin hemen altında, durum rengiyle
	var badge := Label3D.new()
	badge.name = "StatusBadge"
	badge.billboard = BaseMaterial3D.BILLBOARD_ENABLED
	badge.font_size = 34
	badge.pixel_size = 0.0022
	badge.outline_size = 10
	badge.outline_modulate = Color(1, 1, 1, 0.85)
	badge.vertical_alignment = VERTICAL_ALIGNMENT_TOP
	badge.position = label.position - Vector3(0, 0.01, 0)
	exhibit.add_child(badge)
	_labels.append(badge)
	_update_badge(exhibit)


func _update_badge(exhibit: Node3D) -> void:
	var badge := exhibit.get_node_or_null("StatusBadge") as Label3D
	if badge == null:
		return
	var status: String = exhibit.get_meta("prop_info").status
	badge.text = "● " + AssetStatus.LABELS[status]
	badge.modulate = AssetStatus.COLORS[status]


## Kalite durumuna göre etiket rengi: hata kırmızı, uyarı turuncu, temiz koyu gri.
static func _issue_color(issues: PackedStringArray) -> Color:
	for line in issues:
		if line.begins_with("hata"):
			return Color(0.78, 0.1, 0.1)
	return Color(0.82, 0.45, 0.05) if not issues.is_empty() else Color(0.12, 0.14, 0.18)


## Blender'daki kalite kontrolünün (propkit.check_object) glb'ye gömdüğü sorunlar.
static func _qa_issues(extras: Dictionary) -> PackedStringArray:
	if not extras.has("qa"):
		return PackedStringArray(["uyarı: kalite kontrolünden geçmemiş (propkit ile export edilmedi)"])
	return str(extras.qa).split("\n", false)


## Bir sergi: (gerekirse) kaide + model + çarpışma. Bilgiler "prop_info" metadata'sında.
func _make_exhibit(path: String) -> Node3D:
	var model := (load(path) as PackedScene).instantiate() as Node3D
	var extras := PropStyle.extras(model)
	var style: String = extras.get("prop_style", "ps1")
	var placement: String = extras.get("prop_placement", "floor")

	var exhibit := Node3D.new()
	exhibit.name = path.get_file().get_basename()
	if placement == "pedestal":
		exhibit.add_child(_make_pedestal())
		model.position.y = PEDESTAL_SIZE.y
	exhibit.add_child(model)
	PropStyle.apply(model, style)
	_add_collision(model)

	var record: Dictionary = _status.get(exhibit.name, {})
	exhibit.set_meta("prop_info", {
		"asset": exhibit.name,
		"status": AssetStatus.effective(record, path),
		"record": record,
		"name": extras.get("prop_name", exhibit.name),
		"style": style,
		"placement": placement,
		"triangles": _triangle_count(model),
		"issues": _qa_issues(extras),
		"path": path,
		"model": model,
	})
	return exhibit


func _make_pedestal() -> StaticBody3D:
	var body := StaticBody3D.new()
	body.name = "Pedestal"
	body.position.y = PEDESTAL_SIZE.y * 0.5
	var mesh := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = PEDESTAL_SIZE
	var mat := StandardMaterial3D.new()
	mat.albedo_color = Color(0.7, 0.69, 0.67)
	mat.roughness = 0.85
	box.material = mat
	mesh.mesh = box
	body.add_child(mesh)
	var shape := CollisionShape3D.new()
	var box_shape := BoxShape3D.new()
	box_shape.size = PEDESTAL_SIZE
	shape.shape = box_shape
	body.add_child(shape)
	return body


## Her mesh'e dışbükey (convex) çarpışma: içinden geçilmez, hesap ucuz kalır.
func _add_collision(model: Node3D) -> void:
	# model kendi sade çarpışma gövdesiyle geldiyse (Blender'da "-convcolonly") hesaplama yok
	if not model.find_children("*", "StaticBody3D", true, false).is_empty():
		return
	for node in model.find_children("*", "MeshInstance3D", true, false):
		var mi := node as MeshInstance3D
		if mi.mesh == null:
			continue
		var body := StaticBody3D.new()
		var shape := CollisionShape3D.new()
		shape.shape = mi.mesh.create_convex_shape(true, true)
		body.add_child(shape)
		mi.add_child(body)


func _triangle_count(model: Node3D) -> int:
	var tris := 0
	for node in model.find_children("*", "MeshInstance3D", true, false):
		var mesh := (node as MeshInstance3D).mesh
		if mesh == null:
			continue
		for i in mesh.get_surface_count():
			var arrays := mesh.surface_get_arrays(i)
			var indices: PackedInt32Array = arrays[Mesh.ARRAY_INDEX]
			tris += indices.size() / 3 if indices.size() > 0 \
					else (arrays[Mesh.ARRAY_VERTEX] as PackedVector3Array).size() / 3
	return tris


## Nötr stüdyo: 1 m ızgaralı sonsuz zemin, yumuşak gökyüzü, gölgeli güneş.
func _build_studio() -> void:
	var floor_body := StaticBody3D.new()
	floor_body.name = "Floor"
	var floor_shape := CollisionShape3D.new()
	floor_shape.shape = WorldBoundaryShape3D.new()
	floor_body.add_child(floor_shape)
	var floor_mesh := MeshInstance3D.new()
	var plane := PlaneMesh.new()
	plane.size = Vector2(200.0, 200.0)
	var floor_mat := ShaderMaterial.new()
	floor_mat.shader = GRID_SHADER
	plane.material = floor_mat
	floor_mesh.mesh = plane
	floor_body.add_child(floor_mesh)
	_generated.add_child(floor_body)

	var sky_mat := ProceduralSkyMaterial.new()
	sky_mat.sky_top_color = Color(0.6, 0.67, 0.76)
	sky_mat.sky_horizon_color = Color(0.83, 0.85, 0.87)
	sky_mat.ground_horizon_color = Color(0.83, 0.85, 0.87)
	sky_mat.ground_bottom_color = Color(0.55, 0.56, 0.58)
	var sky := Sky.new()
	sky.sky_material = sky_mat
	var env := Environment.new()
	env.background_mode = Environment.BG_SKY
	env.sky = sky
	env.ambient_light_source = Environment.AMBIENT_SOURCE_SKY
	env.ambient_light_energy = 0.45
	var world_env := WorldEnvironment.new()
	world_env.environment = env
	_generated.add_child(world_env)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55.0, 35.0, 0.0)
	sun.light_color = Color(1.0, 0.97, 0.92)
	sun.light_energy = 0.75
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 30.0
	_generated.add_child(sun)


func _build_hud() -> void:
	var layer := CanvasLayer.new()
	layer.name = "Hud"
	add_child(layer)

	_crosshair = ColorRect.new()
	_crosshair.mouse_filter = Control.MOUSE_FILTER_IGNORE  # ekran ortasında; fareyi yutmasın
	_crosshair.color = Color(1, 1, 1, 0.8)
	_crosshair.size = Vector2(4, 4)
	_crosshair.set_anchors_preset(Control.PRESET_CENTER)
	_crosshair.position -= _crosshair.size * 0.5
	layer.add_child(_crosshair)

	_aim_label = Label.new()
	_aim_label.add_theme_color_override("font_color", Color(1, 1, 1))
	_aim_label.add_theme_color_override("font_outline_color", Color(0.1, 0.11, 0.14))
	_aim_label.add_theme_constant_override("outline_size", 6)
	_aim_label.add_theme_font_size_override("font_size", 20)
	_aim_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_aim_label.visible = false
	layer.add_child(_aim_label)
	_aim_label.set_anchors_and_offsets_preset(Control.PRESET_CENTER_BOTTOM, Control.PRESET_MODE_KEEP_SIZE, 0)
	_aim_label.offset_left = -400
	_aim_label.offset_right = 400
	_aim_label.offset_top = -120
	_aim_label.offset_bottom = -90

	_help = Label.new()
	_help.text = "WASD yürü · Shift koş · Space zıpla · F uç (Space/Ctrl yüksel/alçal) · Esc fareyi bırak\n" \
			+ "E incele · G wireframe · L etiketler"
	_help.add_theme_color_override("font_color", Color(0.15, 0.17, 0.2))
	_help.position = Vector2(16, 12)
	layer.add_child(_help)
