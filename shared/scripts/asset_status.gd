class_name AssetStatus
extends RefCounted
## Asset onay durumu: res://assets/asset_status.json (Python tarafı: blender/tools/catalog.py).
##   {"<asset>": {"status": "draft|review|approved|rejected", "sha256": "<karar anındaki glb>",
##                "date": "YYYY-MM-DD", "note": "..."}}
## Kaydı olmayan asset taslaktır. Onaylı asset'in glb'si karar anındakinden farklıysa durum
## "changed" olur (model onaydan sonra değişti, yeniden incele).
## Yazma yalnızca proje klasöründen çalışırken (editör / geliştirme) mümkündür.

const PATH := "res://assets/asset_status.json"
const ORDER := ["draft", "review", "approved", "rejected"]   # galeride 1–4 tuşları
const LABELS := {
	"draft": "taslak",
	"review": "incelemede",
	"approved": "onaylı",
	"rejected": "reddedildi",
	"changed": "değişti — yeniden incele",
}
const COLORS := {
	"draft": Color(0.45, 0.47, 0.5),
	"review": Color(0.8, 0.6, 0.0),
	"approved": Color(0.15, 0.55, 0.25),
	"rejected": Color(0.75, 0.15, 0.15),
	"changed": Color(0.85, 0.42, 0.0),
}


static func load_all() -> Dictionary:
	if not FileAccess.file_exists(PATH):
		return {}
	var data: Variant = JSON.parse_string(FileAccess.get_file_as_string(PATH))
	return data if data is Dictionary else {}


## Asset'in geçerli durumu (model_path: glb'nin res:// yolu, değişiklik kontrolü için).
static func effective(record: Dictionary, model_path: String) -> String:
	var status: String = record.get("status", "draft")
	if status not in ORDER:
		status = "draft"
	if status == "approved" and record.get("sha256", "") != "" and FileAccess.file_exists(model_path):
		if FileAccess.get_sha256(model_path) != record.sha256:
			return "changed"
	return status


## Durumu yaz (not korunur). Yeni kayıt sözlüğünü döner.
static func set_status(asset: String, model_path: String, status: String) -> Dictionary:
	var all := load_all()
	var record: Dictionary = all.get(asset, {})
	record["status"] = status
	record["sha256"] = FileAccess.get_sha256(model_path) if FileAccess.file_exists(model_path) else ""
	record["date"] = Time.get_date_string_from_system()
	if not record.has("note"):
		record["note"] = ""
	all[asset] = record
	var file := FileAccess.open(PATH, FileAccess.WRITE)
	if file == null:
		push_error("AssetStatus: %s yazılamadı (%s)" % [PATH, error_string(FileAccess.get_open_error())])
		return record
	file.store_string(JSON.stringify(all, "  ", true) + "\n")
	return record
