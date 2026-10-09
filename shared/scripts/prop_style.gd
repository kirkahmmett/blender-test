class_name PropStyle
## Proplara stil shader'ı uygular ve Blender'dan gelen prop bilgisini okur.
## model_spinner ve galeri ortak kullanır.
##
## Blender'da objeye yazılan custom property'ler (prop_name, prop_style, prop_placement)
## glTF "extras" olarak gelir; Godot bunları MeshInstance3D'nin "extras" metadata'sına koyar.

const PS1_SHADER := preload("res://shared/shaders/ps1_spatial.gdshader")
const PASTEL_SHADER := preload("res://shared/shaders/pastel_spatial.gdshader")

## Malzeme adı soneki -> pastel shader parametreleri (Blender'daki malzeme adlarıyla eşleşir).
const PASTEL_PRESETS := {
	"porcelain": {"roughness": 0.22, "specular": 0.6, "rim": 0.0},
	"soil": {"roughness": 1.0, "specular": 0.1, "rim": 0.0},
	"bark": {"roughness": 0.9, "specular": 0.15, "rim": 0.0},
	"foliage": {"roughness": 0.85, "specular": 0.2, "rim": 0.35},
}


## style: "ps1" ya da "pastel".
static func apply(root: Node, style: String) -> void:
	for node in root.find_children("*", "MeshInstance3D", true, false):
		var mi := node as MeshInstance3D
		if mi.mesh == null:
			continue
		for i in mi.mesh.get_surface_count():
			var src := mi.mesh.surface_get_material(i) as BaseMaterial3D
			var mat := ShaderMaterial.new()
			if style == "pastel":
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


## Modeldeki ilk "extras" sözlüğü (yoksa boş).
static func extras(root: Node) -> Dictionary:
	for node in root.find_children("*", "MeshInstance3D", true, false):
		if node.has_meta("extras"):
			return node.get_meta("extras")
	return {}


## Modelin kendi koordinatlarında sınır kutusu (root'un dönüşümü hariç).
static func local_aabb(root: Node3D) -> AABB:
	var result := AABB()
	var first := true
	var inv := root.global_transform.affine_inverse()
	for node in root.find_children("*", "MeshInstance3D", true, false):
		var mi := node as MeshInstance3D
		var box := inv * mi.global_transform * mi.get_aabb()
		result = box if first else result.merge(box)
		first = false
	return result


static func _pastel_preset(material_name: String) -> Dictionary:
	for suffix: String in PASTEL_PRESETS:
		if material_name.ends_with(suffix):
			return PASTEL_PRESETS[suffix]
	return {}
