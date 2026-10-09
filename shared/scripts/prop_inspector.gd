class_name PropInspector
extends Node3D
## Bir propu yörünge kamerasıyla 360° inceleme modu.
## open() ile oyuncu kamerasından propun etrafına yumuşakça uçar; close() ile geri döner.
##
## Fare: döndür (aşağıdan bakmak dahil) · Tekerlek: yakınlaştır · R: görünümü sıfırla · Esc/E: çık

signal closed

const PITCH_MIN := deg_to_rad(-85.0)
const PITCH_MAX := deg_to_rad(85.0)
const START_PITCH := deg_to_rad(18.0)
const SMOOTHING := 10.0  # kamera hedefe ne hızla yaklaşır
const ZOOM_STEP := 0.88
const ACTIONS := {"inspect": [KEY_E], "inspect_reset": [KEY_R]}

@export var mouse_sensitivity := 0.005

var active := false
var camera: Camera3D

var _center := Vector3.ZERO
var _radius := 0.5
var _yaw := 0.0
var _pitch := START_PITCH
var _dist := 1.0
var _start_yaw := 0.0
var _return_camera: Camera3D  # kapanırken geri dönülecek kamera
var _closing := false
var _panel: PanelContainer
var _info_label: Label


func _ready() -> void:
	FpsPlayer.ensure_actions(ACTIONS)
	camera = Camera3D.new()
	camera.fov = 50.0
	camera.near = 0.01
	add_child(camera)
	_build_panel()


## model: incelenecek prop (kaidesiz). info: başlıkta gösterilecek bilgi sözlüğü.
func open(model: Node3D, info: Dictionary, from_camera: Camera3D) -> void:
	var box := model.global_transform * PropStyle.local_aabb(model)
	_center = box.get_center()
	_radius = maxf(box.size.length() * 0.5, 0.05)
	_dist = _fit_distance()
	var from := from_camera.global_position - _center
	_start_yaw = atan2(from.x, from.z)
	_yaw = _start_yaw
	_pitch = START_PITCH

	_return_camera = from_camera
	camera.global_transform = from_camera.global_transform
	camera.current = true
	_info_label.text = _info_text(info, box.size)
	_panel.visible = true
	active = true
	_closing = false


func close() -> void:
	if not active or _closing:
		return
	_closing = true
	_panel.visible = false


func _fit_distance() -> float:
	return _radius / sin(deg_to_rad(camera.fov * 0.5)) * 1.1


## Fare _input'ta: imleç ortadayken arayüz öğeleri olayı yutamasın (bkz. FpsPlayer._input).
func _input(event: InputEvent) -> void:
	if not active or _closing:
		return
	if event is InputEventMouseMotion:
		var rel := (event as InputEventMouseMotion).screen_relative  # pencere ölçeğinden bağımsız
		_yaw -= rel.x * mouse_sensitivity
		_pitch = clampf(_pitch + rel.y * mouse_sensitivity, PITCH_MIN, PITCH_MAX)
	elif event is InputEventMouseButton and (event as InputEventMouseButton).pressed:
		var button := (event as InputEventMouseButton).button_index
		if button == MOUSE_BUTTON_WHEEL_UP:
			_dist = maxf(_dist * ZOOM_STEP, _radius * 1.05)
		elif button == MOUSE_BUTTON_WHEEL_DOWN:
			_dist = minf(_dist / ZOOM_STEP, _radius * 8.0)
		else:
			return
	else:
		return
	get_viewport().set_input_as_handled()


func _unhandled_input(event: InputEvent) -> void:
	if not active or _closing:
		return
	if event.is_action_pressed("inspect_reset"):
		_yaw = _start_yaw
		_pitch = START_PITCH
		_dist = _fit_distance()
	elif event.is_action_pressed("ui_cancel") or event.is_action_pressed("inspect"):
		close()
	else:
		return
	get_viewport().set_input_as_handled()


func _process(delta: float) -> void:
	if not active:
		return
	var target: Transform3D
	if _closing:
		target = _return_camera.global_transform
	else:
		var offset := Vector3(sin(_yaw) * cos(_pitch), sin(_pitch), cos(_yaw) * cos(_pitch)) * _dist
		var pos := _center + offset
		target = Transform3D(Basis.looking_at(_center - pos), pos)
	var t := 1.0 - exp(-SMOOTHING * delta)
	camera.global_transform = camera.global_transform.interpolate_with(target, t)

	if _closing and camera.global_position.distance_to(target.origin) < 0.02:
		active = false
		_closing = false
		_return_camera.current = true
		closed.emit()


func _info_text(info: Dictionary, size: Vector3) -> String:
	var lines := PackedStringArray()
	lines.append(str(info.get("name", "?")))
	lines.append("%d üçgen · stil: %s · %s" % [
		info.get("triangles", 0), info.get("style", "?"),
		"kaide" if info.get("placement", "") == "pedestal" else "yer"])
	lines.append("Ölçü: %d × %d × %d cm (G×Y×D)" % [
		roundi(size.x * 100.0), roundi(size.y * 100.0), roundi(size.z * 100.0)])
	var issues: PackedStringArray = info.get("issues", PackedStringArray())
	lines.append("Kalite kontrolü: temiz" if issues.is_empty() else "Kalite kontrolü:")
	for issue in issues:
		lines.append("  • " + issue)
	lines.append("")
	lines.append("Fare: döndür · Tekerlek: yakınlaştır · R: sıfırla · Esc/E: çık")
	return "\n".join(lines)


func _build_panel() -> void:
	var layer := CanvasLayer.new()
	layer.layer = 2
	add_child(layer)
	_panel = PanelContainer.new()
	_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_panel.grow_horizontal = Control.GROW_DIRECTION_BEGIN  # metin uzayınca sola doğru büyüsün
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.08, 0.09, 0.11, 0.72)
	style.set_corner_radius_all(6)
	style.set_content_margin_all(12)
	_panel.add_theme_stylebox_override("panel", style)
	_info_label = Label.new()
	_info_label.add_theme_color_override("font_color", Color(0.93, 0.94, 0.96))
	_panel.add_child(_info_label)
	_panel.visible = false
	layer.add_child(_panel)
	_panel.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT, Control.PRESET_MODE_MINSIZE, 16)
