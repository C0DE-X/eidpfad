class_name DiceRoller3D
extends SubViewportContainer

signal roll_sequence_finished

const DIE_SIZE := 0.72
const PHI := 1.61803398875
const INV_PHI := 0.61803398875
const PURPOSE_COLORS := {
	"hit": Color("963f3f"),
	"enemy_hit": Color("a45535"),
	"block": Color("4c8e9d"),
	"player_block": Color("4c8e9d"),
	"magic": Color("785da7"),
	"ward": Color("77a291"),
	"trap": Color("b08745"),
}
const D12_MODEL := "res://assets/models/dice/d12.glb"

const D12_VERTICES := [
	Vector3(-1,-1,-1),Vector3(-1,-1,1),Vector3(-1,1,-1),Vector3(-1,1,1),
	Vector3(1,-1,-1),Vector3(1,-1,1),Vector3(1,1,-1),Vector3(1,1,1),
	Vector3(0,-INV_PHI,-PHI),Vector3(0,-INV_PHI,PHI),Vector3(0,INV_PHI,-PHI),Vector3(0,INV_PHI,PHI),
	Vector3(-INV_PHI,-PHI,0),Vector3(-INV_PHI,PHI,0),Vector3(INV_PHI,-PHI,0),Vector3(INV_PHI,PHI,0),
	Vector3(-PHI,0,-INV_PHI),Vector3(-PHI,0,INV_PHI),Vector3(PHI,0,-INV_PHI),Vector3(PHI,0,INV_PHI),
]
const D12_FACES := [
	[17,16,0,12,1],[10,8,0,16,2],[14,12,0,8,4],[3,17,1,9,11],
	[5,9,1,12,14],[3,13,2,16,17],[6,10,2,13,15],[15,13,3,11,7],
	[5,14,4,18,19],[6,18,4,8,10],[11,9,5,19,7],[19,18,6,15,7],
]

var _viewport: SubViewport
var _world_root: Node3D
var _purpose_label: Label
var _dice: Array[Node3D] = []
var _queue: Array[Dictionary] = []
var _rolling := false
var _visual_rng := RandomNumberGenerator.new()


func _ready() -> void:
	custom_minimum_size = Vector2(0, 190)
	stretch = true
	mouse_filter = Control.MOUSE_FILTER_IGNORE
	_viewport = SubViewport.new()
	_viewport.size = Vector2i(900, 220)
	_viewport.transparent_bg = true
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	add_child(_viewport)
	_world_root = Node3D.new()
	_viewport.add_child(_world_root)

	var camera := Camera3D.new()
	camera.position = Vector3(0, 4.0, 9.5)
	camera.look_at_from_position(camera.position, Vector3(0, 0.1, 0))
	_world_root.add_child(camera)
	var light := DirectionalLight3D.new()
	light.rotation_degrees = Vector3(-48, -28, 0)
	light.light_color = Color("d9e8ee")
	light.light_energy = 1.4
	_world_root.add_child(light)
	var fill := OmniLight3D.new()
	fill.position = Vector3(-3, 2, 3)
	fill.light_color = Color("d49a48")
	fill.omni_range = 12.0
	fill.light_energy = 2.0
	_world_root.add_child(fill)

	_purpose_label = Label.new()
	_purpose_label.position = Vector2(12, 8)
	_purpose_label.add_theme_font_size_override("font_size", 16)
	_purpose_label.add_theme_color_override("font_color", Color("d7c49a"))
	add_child(_purpose_label)


func enqueue_roll(values: Array, purpose: String) -> void:
	if values.is_empty():
		return
	_queue.append({"values": values.duplicate(), "purpose": purpose})
	if not _rolling:
		_play_queue()


func roll_to(values: Array, purpose: String = "hit") -> void:
	_queue.clear()
	enqueue_roll(values, purpose)


func _play_queue() -> void:
	_rolling = true
	while not _queue.is_empty():
		var entry: Dictionary = _queue.pop_front()
		_show_roll(entry["values"], str(entry["purpose"]))
		await get_tree().create_timer(1.45).timeout
	_rolling = false
	roll_sequence_finished.emit()


func _show_roll(values: Array, purpose: String) -> void:
	for old_die in _dice:
		old_die.queue_free()
	_dice.clear()
	_purpose_label.text = _purpose_name(purpose)
	var spacing := minf(1.75, 10.5 / maxf(1.0, float(values.size() - 1)))
	var start_x := -spacing * float(values.size() - 1) / 2.0
	var color: Color = PURPOSE_COLORS.get(purpose, Color("d5c49d"))
	for index in values.size():
		var die := _create_die(color)
		die.position = Vector3(start_x + index * spacing, 0, 0)
		die.rotation = Vector3(
			_visual_rng.randf_range(-PI, PI),
			_visual_rng.randf_range(-PI, PI),
			_visual_rng.randf_range(-PI, PI),
		)
		_world_root.add_child(die)
		_dice.append(die)
		_animate_die(die, clampi(int(values[index]), 1, 12), index)


func _create_die(color: Color) -> Node3D:
	var root := Node3D.new()
	var body_root: Node3D
	if ResourceLoader.exists(D12_MODEL):
		var packed := load(D12_MODEL) as PackedScene
		if packed != null:
			body_root = packed.instantiate() as Node3D
	if body_root == null:
		var fallback := MeshInstance3D.new()
		fallback.mesh = _create_d12_mesh()
		body_root = fallback
	_tint_model(body_root, color)
	body_root.scale = Vector3.ONE * 0.82
	root.add_child(body_root)
	for face_index in D12_FACES.size():
		var center := _face_center(face_index)
		_add_face(root, str(face_index + 1), center * 1.035, center.normalized(), color)
	return root


func _tint_model(node: Node, color: Color) -> void:
	if node is MeshInstance3D:
		var model_material := StandardMaterial3D.new()
		model_material.albedo_color = color
		model_material.metallic = 0.42
		model_material.roughness = 0.38
		(node as MeshInstance3D).material_override = model_material
	for child in node.get_children():
		_tint_model(child, color)


func _create_d12_mesh() -> ArrayMesh:
	var surface := SurfaceTool.new()
	surface.begin(Mesh.PRIMITIVE_TRIANGLES)
	for face in D12_FACES:
		var center := Vector3.ZERO
		for vertex_index in face:
			center += D12_VERTICES[vertex_index] * DIE_SIZE
		center /= float(face.size())
		var normal := center.normalized()
		for index in face.size():
			var first: Vector3 = D12_VERTICES[face[index]] * DIE_SIZE
			var second: Vector3 = D12_VERTICES[face[(index + 1) % face.size()]] * DIE_SIZE
			surface.set_normal(normal)
			surface.add_vertex(center)
			surface.set_normal(normal)
			surface.add_vertex(first)
			surface.set_normal(normal)
			surface.add_vertex(second)
	return surface.commit()


func _face_center(face_index: int) -> Vector3:
	var center := Vector3.ZERO
	for vertex_index in D12_FACES[face_index]:
		center += D12_VERTICES[vertex_index] * DIE_SIZE
	return center / float(D12_FACES[face_index].size())


func _add_face(root: Node3D, value: String, face_position: Vector3, normal: Vector3, color: Color) -> void:
	var label := Label3D.new()
	label.text = value
	label.position = face_position
	var up := Vector3.UP if abs(normal.dot(Vector3.UP)) < 0.95 else Vector3.FORWARD
	label.basis = Basis.looking_at(-normal, up)
	label.font_size = 68
	label.outline_size = 9
	label.modulate = Color("f2ead8")
	label.outline_modulate = color.darkened(0.45)
	root.add_child(label)


func _animate_die(die: Node3D, value: int, delay_index: int) -> void:
	var final_rotation := _rotation_for_value(value)
	var spins := Vector3(TAU * 3.0, TAU * 2.0, TAU * 2.0)
	var tween := create_tween()
	tween.set_trans(Tween.TRANS_QUINT).set_ease(Tween.EASE_OUT)
	tween.tween_interval(delay_index * 0.05)
	tween.tween_property(die, "rotation", final_rotation + spins, 1.05)
	tween.tween_callback(func() -> void: die.rotation = final_rotation)


func _rotation_for_value(value: int) -> Vector3:
	var normal := _face_center(value - 1).normalized()
	var axis := normal.cross(Vector3.UP)
	var angle := acos(clampf(normal.dot(Vector3.UP), -1.0, 1.0))
	if axis.length_squared() < 0.0001:
		return Vector3.ZERO if normal.y > 0 else Vector3(PI, 0, 0)
	return Quaternion(axis.normalized(), angle).get_euler()


func _purpose_name(purpose: String) -> String:
	return {
		"hit": "TREFFERWURF",
		"block": "GEGNERISCHER BLOCK",
		"enemy_hit": "GEGNERANGRIFF",
		"player_block": "VERTEIDIGUNG",
		"magic": "MAGIEWURF",
		"ward": "BANNWURF",
		"trap": "FALLENWURF",
	}.get(purpose, purpose.to_upper())
