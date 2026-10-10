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
## Birleştirilmiş modellerde (prop_materials) bu ayarlar köşe kimliğiyle lut_* dizilerinden okunur;
## "double_sided" yalnızca eski (parça başına malzeme) düzende kullanılır; birleştirilmiş düzende
## çift taraflılığı malzeme adının "_thin" soneki belirler (Blender'da propkit.THIN_MATERIALS).
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
		# birleştirilmiş malzemeler (propkit.merge_materials): kimlik sırasıyla parça adları
		var merged := str(mi.get_meta("extras", {}).get("prop_materials", ""))
		var lut := _pastel_lut(merged.split(",")) if style == "pastel" and merged != "" else {}
		for i in mi.mesh.get_surface_count():
			var src := mi.mesh.surface_get_material(i) as BaseMaterial3D
			var src_name := src.resource_name if src else ""
			var mat := ShaderMaterial.new()
			if style == "pastel" and not lut.is_empty():
				# "<önek>_thin" ince yüzeyler (çift taraflı), "<önek>_solid" kapalı gövdeler
				mat.shader = PASTEL_LEAF_SHADER if src_name.ends_with("_thin") else PASTEL_SHADER
				mat.set_shader_parameter("use_lut", true)
				for key: String in lut:
					mat.set_shader_parameter(key, lut[key])
			elif style == "pastel":
				# eski düzen: parça başına ayrı malzeme
				var preset: Dictionary = _pastel_preset(src_name)
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


## Parça adlarından (kimlik sırasıyla) shader'ın lut_* dizileri; tanımsız parça varsayılan alır.
static func _pastel_lut(names: PackedStringArray) -> Dictionary:
	var roughness := PackedFloat32Array()
	var specular := PackedFloat32Array()
	var rim := PackedFloat32Array()
	var tint := PackedFloat32Array()
	for i in 16:
		var p: Dictionary = _pastel_preset(names[i]) if i < names.size() else {}
		roughness.append(p.get("roughness", 0.8))
		specular.append(p.get("specular", 0.3))
		rim.append(p.get("rim", 0.0))
		tint.append((p.get("albedo_tint", Color.WHITE) as Color).r)
	return {"lut_roughness": roughness, "lut_specular": specular, "lut_rim": rim, "lut_tint": tint}


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
