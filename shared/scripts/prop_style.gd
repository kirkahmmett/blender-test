@tool
class_name PropStyle
## Proplara stil shader'ı uygular ve Blender'dan gelen prop bilgisini okur.
## model_spinner ve galeri ortak kullanır.
##
## Blender'da objeye yazılan custom property'ler (prop_name, prop_style, prop_placement)
## glTF "extras" olarak gelir; Godot bunları MeshInstance3D'nin "extras" metadata'sına koyar.

const PS1_SHADER := preload("res://shared/shaders/ps1_spatial.gdshader")
const PASTEL_SHADER := preload("res://shared/shaders/pastel_spatial.gdshader")
## Çift taraflı pastel: yaprak/taç yaprağı gibi ince yüzeyler (preset'te "double_sided").
const PASTEL_LEAF_SHADER := preload("res://shared/shaders/pastel_leaf.gdshader")

## Malzeme adı soneki -> pastel shader parametreleri (Blender'daki malzeme adlarıyla eşleşir).
## "double_sided": true olanlar PASTEL_LEAF_SHADER kullanır; parametre değildir.
const PASTEL_PRESETS := {
	"porcelain": {"roughness": 0.22, "specular": 0.6, "rim": 0.0},
	"terracotta": {"roughness": 0.75, "specular": 0.2, "rim": 0.0},
	"soil": {"roughness": 1.0, "specular": 0.1, "rim": 0.0},
	"bark": {"roughness": 0.9, "specular": 0.15, "rim": 0.0},
	"stem": {"roughness": 0.8, "specular": 0.2, "rim": 0.15},
	"stake": {"roughness": 0.7, "specular": 0.25, "rim": 0.0},
	# açık pastel yeşiller güneş + parlama + rim toplamında beyaza taşar: hepsi kısık
	"foliage": {"roughness": 0.9, "specular": 0.1, "rim": 0.15, "albedo_tint": Color(0.9, 0.9, 0.9)},
	"leaf": {"roughness": 0.9, "specular": 0.08, "rim": 0.1, "albedo_tint": Color(0.86, 0.86, 0.86),
			"double_sided": true},
	"petal": {"roughness": 0.7, "specular": 0.2, "rim": 0.25, "double_sided": true},
	"fruit": {"roughness": 0.3, "specular": 0.55, "rim": 0.2},
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
				var preset: Dictionary = _pastel_preset(src.resource_name if src else "")
				mat.shader = PASTEL_LEAF_SHADER if preset.get("double_sided", false) else PASTEL_SHADER
				for key: String in preset:
					if key != "double_sided":
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
