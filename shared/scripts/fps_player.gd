class_name FpsPlayer
extends CharacterBody3D
## Basit FPS karakter. Çarpışma şekli ve kamerayı kendisi kurar; sahneye boş bir
## CharacterBody3D olarak eklenip bu script verilmesi yeterli.
##
## WASD yürü · Shift koş · Space zıpla · F uçma (noclip) aç/kapa
## Uçarken Space yüksel, Ctrl/C alçal · Esc fareyi bırak, sol tık geri yakala.
## Tuşlar fiziksel konuma göre (Türkçe Q klavyede de aynı yerde).

const EYE_HEIGHT := 1.7
const FALL_LIMIT := -30.0

## Eylem -> fiziksel tuşlar. Proje ayarlarına dokunmadan çalışma anında eklenir.
const ACTIONS := {
	"move_forward": [KEY_W],
	"move_back": [KEY_S],
	"move_left": [KEY_A],
	"move_right": [KEY_D],
	"jump": [KEY_SPACE],
	"sprint": [KEY_SHIFT],
	"fly_toggle": [KEY_F],
	"fly_down": [KEY_CTRL, KEY_C],
}

@export var walk_speed := 4.0
@export var sprint_speed := 7.5
@export var fly_speed := 4.0
@export var jump_velocity := 4.5
@export var acceleration := 12.0
@export var mouse_sensitivity := 0.0025

var camera: Camera3D
var flying := false
## false iken karakter girdiye tepki vermez (ör. inceleme modunda).
var controls_enabled := true

var _gravity: float = ProjectSettings.get_setting("physics/3d/default_gravity")
var _collision: CollisionShape3D
var _spawn: Transform3D


static func ensure_actions(actions: Dictionary) -> void:
	for action: String in actions:
		if InputMap.has_action(action):
			continue
		InputMap.add_action(action)
		for key: Key in actions[action]:
			var ev := InputEventKey.new()
			ev.physical_keycode = key
			InputMap.action_add_event(action, ev)


func _ready() -> void:
	ensure_actions(ACTIONS)

	var capsule := CapsuleShape3D.new()
	capsule.radius = 0.3
	capsule.height = 1.8
	_collision = CollisionShape3D.new()
	_collision.shape = capsule
	_collision.position.y = capsule.height * 0.5
	add_child(_collision)

	camera = Camera3D.new()
	camera.position.y = EYE_HEIGHT
	camera.fov = 75.0
	camera.near = 0.03
	add_child(camera)
	camera.current = true

	_spawn = global_transform
	Input.mouse_mode = Input.MOUSE_MODE_CAPTURED


## Fare bakışı _input'ta: kilitli imleç ekranın ortasında durur ve oradaki bir arayüz
## öğesi (ör. nişangâh) hareketi _unhandled_input'a ulaşmadan yutabilir.
## Yatayda sınırsız (360°), dikeyde ±89°. screen_relative: hassasiyet pencere boyutuna
## (canvas_items ölçeklemesine) bağlı değişmesin.
func _input(event: InputEvent) -> void:
	if not controls_enabled or not event is InputEventMouseMotion \
			or Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		return
	var motion := event as InputEventMouseMotion
	rotate_y(-motion.screen_relative.x * mouse_sensitivity)
	camera.rotation.x = clampf(camera.rotation.x - motion.screen_relative.y * mouse_sensitivity, -1.55, 1.55)


func _unhandled_input(event: InputEvent) -> void:
	if not controls_enabled:
		return
	if event is InputEventMouseButton and (event as InputEventMouseButton).pressed \
			and Input.mouse_mode != Input.MOUSE_MODE_CAPTURED:
		Input.mouse_mode = Input.MOUSE_MODE_CAPTURED
	elif event.is_action_pressed("ui_cancel"):
		Input.mouse_mode = Input.MOUSE_MODE_VISIBLE
	elif event.is_action_pressed("fly_toggle"):
		set_flying(not flying)


func set_flying(value: bool) -> void:
	flying = value
	_collision.disabled = flying
	velocity = Vector3.ZERO


func _physics_process(delta: float) -> void:
	var input := Vector2.ZERO
	if controls_enabled:
		input = Input.get_vector("move_left", "move_right", "move_forward", "move_back")
	var sprinting := controls_enabled and Input.is_action_pressed("sprint")

	if flying:
		_fly(delta, input, sprinting)
		return

	if not is_on_floor():
		velocity.y -= _gravity * delta
	elif controls_enabled and Input.is_action_just_pressed("jump"):
		velocity.y = jump_velocity

	var dir := transform.basis * Vector3(input.x, 0.0, input.y)
	dir.y = 0.0
	var target := dir.normalized() * (sprint_speed if sprinting else walk_speed) * minf(dir.length(), 1.0)
	var t := minf(acceleration * delta, 1.0)
	velocity.x = lerpf(velocity.x, target.x, t)
	velocity.z = lerpf(velocity.z, target.z, t)
	move_and_slide()

	if global_position.y < FALL_LIMIT:
		global_transform = _spawn
		velocity = Vector3.ZERO


## Noclip: bakılan yöne uç, çarpışma yok.
func _fly(delta: float, input: Vector2, sprinting: bool) -> void:
	var dir := camera.global_basis * Vector3(input.x, 0.0, input.y)
	if controls_enabled:
		dir.y += float(Input.is_action_pressed("jump")) - float(Input.is_action_pressed("fly_down"))
	var speed := fly_speed * (2.5 if sprinting else 1.0)
	velocity = velocity.lerp(dir.limit_length(1.0) * speed, minf(acceleration * delta, 1.0))
	global_position += velocity * delta
