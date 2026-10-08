extends Node3D
## Model önizleme sahnesi (deneylerde ortak).
## model_paths'teki .glb'leri yan yana yükler, stile göre shader uygular, kamerayı
## hepsini görecek şekilde konumlar ve modelleri döndürür.
## Birden çok model varsa 1–9 tuşları tek modele odaklanır, 0 hepsine döner.
## Model yoksa yerine yer tutucu bir küp koyar.

enum Style { PS1, PASTEL }

const PS1_SHADER := preload("res://shared/shaders/ps1_spatial.gdshader")
const PASTEL_SHADER := preload("res://shared/shaders/pastel_spatial.gdshader")

## Malzeme adı soneki -> pastel shader parametreleri (Blender'daki malzeme adlarıyla eşleşir).
const PASTEL_PRESETS := {
	"porcelain": {"roughness": 0.22, "specular": 0.6, "rim": 0.0},
	"soil": {"roughness": 1.0, "specular": 0.1, "rim": 0.0},
	"bark": {"roughness": 0.9, "specular": 0.15, "rim": 0.0},
	"foliage": {"roughness": 0.85, "specular": 0.2, "rim": 0.35},
}

const VIEW_DIR := Vector3(0.0, 0.35, 1.0)
const FOCUS_TIME := 0.6

@export var model_paths: PackedStringArray = ["res://assets/models/test_cube.glb"]
@export var style: Style = Style.PS1
@export var spacing: float = 0.8
@export var spin_speed: float = 0.8

var _spinners: Array[Node3D] = []
var _spin_aabbs: Array[AABB] = []  # model başına, dönüşten bağımsız sınır kutusu
var _all_aabb: AABB
var _focus := -1  # -1 = hepsi
var _camera: Camera3D
var _tween: Tween


func _ready() -> void:
	_build_environment()

	for i in model_paths.size():
		var model := _load_model(model_paths[i])
		model.position.x = (i - (model_paths.size() - 1) * 0.5) * spacing
		add_child(model)
		_apply_style(model)
		_spinners.append(model)
		_spin_aabbs.append(_spin_aabb(model))

	if _spinners.is_empty():
		push_warning("model_paths boş.")
		return
	_all_aabb = _spin_aabbs[0]
	for box in _spin_aabbs:
		_all_aabb = _all_aabb.merge(box)
	_frame_camera(_all_aabb, false)
	if _spinners.size() > 1:
		_build_hint()


func _process(delta: float) -> void:
	for s in _spinners:
		s.rotate_y(delta * spin_speed)


func _unhandled_input(event: InputEvent) -> void:
	var key := event as InputEventKey
	if key == null or not key.pressed or key.echo or _spinners.size() < 2:
		return
	var digit := -1
	if key.keycode >= KEY_0 and key.keycode <= KEY_9:
		digit = key.keycode - KEY_0
	elif key.keycode >= KEY_KP_0 and key.keycode <= KEY_KP_9:
		digit = key.keycode - KEY_KP_0
	if digit == 0:
		focus(-1)
	elif digit >= 1 and digit <= _spinners.size():
		focus(digit - 1)


## index: odaklanılacak model (0'dan başlar), -1 = hepsi.
func focus(index: int) -> void:
	if index == _focus:
		return
	_focus = index
	for i in _spinners.size():
		_spinners[i].visible = index == -1 or i == index
	_frame_camera(_all_aabb if index == -1 else _spin_aabbs[index], true)


func _load_model(path: String) -> Node3D:
	if ResourceLoader.exists(path):
		var packed := load(path) as PackedScene
		return packed.instantiate() as Node3D
	push_warning("Model bulunamadı: %s — blender/export_glb.py ile export et." % path)
	return _make_placeholder()


func _build_environment() -> void:
	_camera = Camera3D.new()
	_camera.fov = 40.0
	add_child(_camera)
	_camera.current = true

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-50.0, 30.0, 0.0)
	add_child(sun)

	var env := Environment.new()
	env.background_mode = Environment.BG_COLOR
	env.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	if style == Style.PASTEL:
		env.background_color = Color(0.78, 0.8, 0.84)
		env.ambient_light_color = Color(0.85, 0.86, 0.9)
		env.ambient_light_energy = 0.75
		sun.light_color = Color(1.0, 0.97, 0.92)
		sun.light_energy = 0.9
	else:
		env.background_color = Color(0.08, 0.07, 0.1)
		env.ambient_light_color = Color(0.45, 0.45, 0.5)
	var we := WorldEnvironment.new()
	we.environment = env
	add_child(we)


func _build_hint() -> void:
	var layer := CanvasLayer.new()
	add_child(layer)
	var label := Label.new()
	label.text = "1–%d: tek model   0: hepsi" % _spinners.size()
	label.position = Vector2(16.0, 12.0)
	var dark_text := style == Style.PASTEL
	label.add_theme_color_override("font_color", Color(0.25, 0.27, 0.3) if dark_text else Color(0.8, 0.8, 0.85))
	layer.add_child(label)


## Kamerayı sınır kutusunun merkezine baktır, boyutuna göre uzaklaştır.
func _frame_camera(aabb: AABB, animate: bool) -> void:
	var center := aabb.get_center()
	var half_v := tan(deg_to_rad(_camera.fov * 0.5))
	var viewport := get_viewport().get_visible_rect().size
	var half_h := half_v * viewport.x / maxf(viewport.y, 1.0)
	# genişlik ya da ekrandaki yükseklik (kamera yukarıdan baktığı için derinlik de katkı verir),
	# hangisi sığmazsa ona göre; yakın yüz için derinliğin bir kısmı kadar pay
	var elev := atan2(VIEW_DIR.y, VIEW_DIR.z)
	var extent_v := (aabb.size.y * cos(elev) + aabb.size.z * sin(elev)) * 0.5
	var dist := maxf(aabb.size.x * 0.5 / half_h, extent_v / half_v) * 1.1 + aabb.size.z * 0.35
	dist = maxf(dist, 0.3)
	var pos := center + VIEW_DIR.normalized() * dist
	var rot := Basis.looking_at(center - pos).get_rotation_quaternion()

	if _tween:
		_tween.kill()
	if not animate:
		_camera.position = pos
		_camera.quaternion = rot
		return
	_tween = create_tween().set_parallel().set_trans(Tween.TRANS_SINE).set_ease(Tween.EASE_IN_OUT)
	_tween.tween_property(_camera, "position", pos, FOCUS_TIME)
	_tween.tween_property(_camera, "quaternion", rot, FOCUS_TIME)


func _mesh_instances(root: Node3D) -> Array[MeshInstance3D]:
	var out: Array[MeshInstance3D] = []
	if root is MeshInstance3D:
		out.append(root)
	for node in root.find_children("*", "MeshInstance3D", true, false):
		out.append(node as MeshInstance3D)
	return out


## Model kendi ekseninde dönerken kapladığı alan: dikey eksen etrafında silindir.
func _spin_aabb(model: Node3D) -> AABB:
	var radius := 0.0
	var y_min := INF
	var y_max := -INF
	var origin := model.global_position
	for mi in _mesh_instances(model):
		var box := mi.global_transform * mi.get_aabb()
		for i in 8:
			var c := box.get_endpoint(i)
			radius = maxf(radius, Vector2(c.x - origin.x, c.z - origin.z).length())
			y_min = minf(y_min, c.y)
			y_max = maxf(y_max, c.y)
	if radius == 0.0:
		return AABB(origin - Vector3.ONE * 0.5, Vector3.ONE)
	return AABB(Vector3(origin.x - radius, y_min, origin.z - radius),
		Vector3(radius * 2.0, y_max - y_min, radius * 2.0))


func _apply_style(root: Node) -> void:
	for node in root.find_children("*", "MeshInstance3D", true, false):
		var mi := node as MeshInstance3D
		if mi.mesh == null:
			continue
		for i in mi.mesh.get_surface_count():
			var src := mi.mesh.surface_get_material(i) as BaseMaterial3D
			var mat := ShaderMaterial.new()
			if style == Style.PASTEL:
				mat.shader = PASTEL_SHADER
				var preset: Dictionary = _pastel_preset(src.resource_name if src else "")
				for key: String in preset:
					mat.set_shader_parameter(key, preset[key])
			else:
				mat.shader = PS1_SHADER
				if src:
					mat.set_shader_parameter("albedo_color", src.albedo_color)
					if src.albedo_texture:
						mat.set_shader_parameter("albedo_texture", src.albedo_texture)
						mat.set_shader_parameter("use_texture", true)
			mi.set_surface_override_material(i, mat)


func _pastel_preset(material_name: String) -> Dictionary:
	for suffix: String in PASTEL_PRESETS:
		if material_name.ends_with(suffix):
			return PASTEL_PRESETS[suffix]
	return {}


func _make_placeholder() -> MeshInstance3D:
	var mi := MeshInstance3D.new()
	mi.mesh = BoxMesh.new()
	var mat := ShaderMaterial.new()
	mat.shader = PS1_SHADER
	mat.set_shader_parameter("albedo_color", Color(0.9, 0.5, 0.3))
	mi.material_override = mat
	return mi
