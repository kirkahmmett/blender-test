extends Node3D
## exp03 — prop galerisi. assets/models/ içindeki her .glb'yi tarar ve bir sıra halinde dizer.
## Stil ve yerleşim Blender'dan gelen bilgiden okunur (PropStyle.extras):
##   prop_style: "ps1" | "pastel"   prop_placement: "floor" | "pedestal"   prop_name: görünen ad
## Bilgisi olmayan model PS1 stiliyle yere konur. Yeni bir .glb eklemek galeriye eklemek demektir.

const MODELS_DIR := "res://assets/models/"
const GRID_SHADER := preload("res://shared/shaders/grid_floor.gdshader")
const PEDESTAL_SIZE := Vector3(0.6, 0.8, 0.6)
const GAP := 1.6  # sergiler arası boşluk (m)
const PLAYER_START := Vector3(0.0, 0.0, 4.5)

## Galeriye alınmayacak modeller (dosya adı, uzantısız).
@export var exclude: PackedStringArray = ["test_cube"]

var player: FpsPlayer
var exhibits: Array[Node3D] = []


func _ready() -> void:
	_build_studio()
	_place_props(_model_paths())
	_build_hud()

	player = FpsPlayer.new()
	player.position = PLAYER_START
	add_child(player)


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
		add_child(exhibit)
		exhibits.append(exhibit)
		var box := PropStyle.local_aabb(exhibit)
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

	exhibit.set_meta("prop_info", {
		"name": extras.get("prop_name", exhibit.name),
		"style": style,
		"placement": placement,
		"triangles": _triangle_count(model),
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
	add_child(floor_body)

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
	add_child(world_env)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-55.0, 35.0, 0.0)
	sun.light_color = Color(1.0, 0.97, 0.92)
	sun.light_energy = 0.75
	sun.shadow_enabled = true
	sun.directional_shadow_max_distance = 30.0
	add_child(sun)


func _build_hud() -> void:
	var layer := CanvasLayer.new()
	layer.name = "Hud"
	add_child(layer)

	var dot := ColorRect.new()
	dot.color = Color(1, 1, 1, 0.8)
	dot.size = Vector2(4, 4)
	dot.set_anchors_preset(Control.PRESET_CENTER)
	dot.position -= dot.size * 0.5
	layer.add_child(dot)

	var help := Label.new()
	help.text = "WASD yürü · Shift koş · Space zıpla · F uç (Space/Ctrl yüksel/alçal) · Esc fareyi bırak"
	help.add_theme_color_override("font_color", Color(0.15, 0.17, 0.2))
	help.position = Vector2(16, 12)
	layer.add_child(help)
