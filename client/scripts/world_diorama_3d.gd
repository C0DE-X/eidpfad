class_name WorldDiorama3D
extends SubViewportContainer

const CHARACTER_MODELS := {
	"axe": "res://assets/models/characters/vanguard.glb",
	"bow": "res://assets/models/characters/pathfinder.glb",
	"dual_blades": "res://assets/models/characters/duelist.glb",
	"crossbow": "res://assets/models/characters/arbalist.glb",
	"longsword": "res://assets/models/characters/swordmaster.glb",
}
const FIGURE_PROFILE_PATH := "res://assets/animations/figure_profiles.json"

var _viewport: SubViewport
var _world: Node3D
var _party: Node3D
var _party_figures: Array[Node3D] = []
var _player_ids: Array[String] = []
var _party_signature := ""
var _enemy_figure: Node3D
var _enemy_figures: Dictionary = {}
var _enemy_signature := ""
var _country_landmark: Node3D
var _scenario_props: Node3D
var _loot_root: Node3D
var _current_enemy_id := ""
var _current_country_id := ""
var _current_prop_signature := ""
var _current_loot_signature := ""
var _markers: Array[Node3D] = []
var _scenario_markers: Dictionary = {}
var _scenario_label: Label
var _animation_time := 0.0
var _render_scale := 1.0
var _animation_profile: Dictionary = {}


func _ready() -> void:
	custom_minimum_size = Vector2(0, 330)
	stretch = true
	_animation_profile = _read_json(FIGURE_PROFILE_PATH)
	_build_viewport()
	_build_diorama()
	set_process(true)


func _process(delta: float) -> void:
	_animation_time += delta
	if _loot_root != null and _loot_root.visible:
		for index in _loot_root.get_child_count():
			var model := _loot_root.get_child(index) as Node3D
			model.rotation.y += delta * (0.35 + float(index) * 0.08)
			model.position.y = 0.7 + sin(_animation_time * 1.8 + float(index)) * 0.08


func set_render_scale(value: float) -> void:
	_render_scale = clampf(value, 0.65, 1.5)


func set_game_state(state: Dictionary) -> void:
	_ensure_party(state)
	var index := int(state.get("scenario_index", 0))
	var route: Array = state.get("world", {}).get("route", [])
	if route.size() != _markers.size():
		_rebuild_route(route)
	var scenario: Dictionary = state.get("scenario", {})
	_scenario_label.text = "%s · %s" % [scenario.get("country", ""), scenario.get("title", "")]
	if not _markers.is_empty():
		var local_index := clampi(index, 0, _markers.size() - 1)
		var selected_marker: Node3D = _scenario_markers.get(str(scenario.get("id", "")), _markers[local_index])
		_party.position = selected_marker.position + Vector3(0, 0.24, 0)
		for marker_index in _markers.size():
			_set_marker_color(_markers[marker_index], marker_index, local_index)
	_set_country_scene(scenario)
	var targets: Array = state.get("combat", {}).get("targets", [])
	if targets.is_empty() and not state.get("enemy", {}).is_empty():
		targets = [state.get("enemy", {})]
	_set_enemy_figures(targets)
	_set_loot(state)


func play_combat_event(event: Dictionary) -> void:
	var event_type := str(event.get("type", ""))
	if event_type == "card_played":
		var actor := _actor_for(str(event.get("actor", "")))
		var phase := str(event.get("phase", "attack"))
		_play_clip(actor, {"attack":"attack","defense":"guard","magic":"cast","utility":"cast"}.get(phase, "attack"))
	elif event_type in ["enemy_damaged", "boss_objective_damaged", "throneless_damaged"]:
		_play_clip(_enemy_figures.get(str(event.get("target", event.get("target_id", "throneless"))), _enemy_figure), "hit")
	elif event_type == "player_damaged":
		_play_clip(_actor_for(str(event.get("player", ""))), "hit")
	elif event_type in ["enemy_defeated", "boss_objective_destroyed"]:
		_play_clip(_enemy_figures.get(str(event.get("enemy", event.get("target_id", ""))), _enemy_figure), "defeat")
	elif event_type == "enemy_spawned":
		preview_enemy(event.get("enemy", {}))
		_play_clip(_enemy_figure, "spawn")
	elif event_type == "enemy_attack_resolved":
		_play_clip(_enemy_figure, "attack")
	elif event_type == "enemy_intent":
		var intent := str(event.get("intent", "strike"))
		_play_clip(_enemy_figure, "guard" if intent == "guard" else "cast" if intent == "hex" else "combat_idle")
	elif event_type == "boss_phase_changed":
		_play_clip(_enemy_figure, "heavy_attack" if int(event.get("phase", 1)) >= 3 else "cast")
	elif event_type == "scenario_completed":
		for actor in _party_figures:
			_play_clip(actor, "victory")


func preview_enemy(enemy: Dictionary) -> void:
	_set_enemy_figures([enemy])


func _build_viewport() -> void:
	_viewport = SubViewport.new()
	_viewport.size = Vector2i(1100, 520)
	_viewport.transparent_bg = true
	_viewport.render_target_update_mode = SubViewport.UPDATE_ALWAYS
	_viewport.msaa_3d = Viewport.MSAA_4X
	add_child(_viewport)
	_world = Node3D.new()
	_viewport.add_child(_world)

	var environment := WorldEnvironment.new()
	var settings := Environment.new()
	settings.background_mode = Environment.BG_COLOR
	settings.background_color = Color(0.08, 0.10, 0.11, 0.0)
	settings.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	settings.ambient_light_color = Color("9fae9b")
	settings.ambient_light_energy = 0.62
	settings.tonemap_mode = Environment.TONE_MAPPER_FILMIC
	environment.environment = settings
	_world.add_child(environment)

	var camera := Camera3D.new()
	camera.projection = Camera3D.PROJECTION_ORTHOGONAL
	camera.size = 13.5
	camera.position = Vector3(8.7, 9.6, 10.8)
	camera.look_at_from_position(camera.position, Vector3(0, 0, 0))
	_world.add_child(camera)

	var sun := DirectionalLight3D.new()
	sun.rotation_degrees = Vector3(-52, -28, 0)
	sun.light_color = Color("d8caa5")
	sun.light_energy = 1.15
	sun.shadow_enabled = true
	_world.add_child(sun)

	var rim := DirectionalLight3D.new()
	rim.rotation_degrees = Vector3(-28, 142, 0)
	rim.light_color = Color("7895a1")
	rim.light_energy = 0.48
	_world.add_child(rim)

	_scenario_label = Label.new()
	_scenario_label.position = Vector2(18, 16)
	_scenario_label.add_theme_font_size_override("font_size", 22)
	_scenario_label.add_theme_color_override("font_color", Color("e4d3a9"))
	add_child(_scenario_label)


func _build_diorama() -> void:
	_add_box(Vector3(0, -0.5, 0), Vector3(12, 0.8, 8), Color("28372f"))
	_add_box(Vector3(-3.8, 0.05, -1.8), Vector3(3.8, 0.45, 2.6), Color("414d3c"))
	_add_box(Vector3(3.4, 0.25, 1.4), Vector3(3.4, 0.8, 2.9), Color("504836"))
	_add_river()
	_add_mountains()

	_party = Node3D.new()
	_world.add_child(_party)
	_party.position = Vector3(-4.8, 0.28, 2.7)

	_scenario_props = Node3D.new()
	_world.add_child(_scenario_props)
	_loot_root = Node3D.new()
	_loot_root.visible = false
	_world.add_child(_loot_root)


func _rebuild_route(route: Array) -> void:
	for marker_value in _scenario_markers.values():
		var old_marker: Node3D = marker_value
		old_marker.queue_free()
	_markers.clear()
	_scenario_markers.clear()
	if route.is_empty():
		return
	var columns := 7
	var rows := ceili(float(route.size()) / columns)
	for index in route.size():
		var row := int(index / columns)
		var offset := index % columns
		var column := offset if row % 2 == 0 else columns - 1 - offset
		var x := -4.8 + float(column) * 1.6
		var z := 2.7 if rows <= 1 else 2.7 - float(row) * (5.4 / float(rows - 1))
		var scenario: Dictionary = route[index]
		var marker := _create_marker(bool(scenario.get("is_boss", false)))
		marker.position = Vector3(x, 0.12 + sin(float(index) * 1.7) * 0.08, z)
		_world.add_child(marker)
		_markers.append(marker)
		_scenario_markers[str(scenario.get("id", index))] = marker
		var alternatives: Array = scenario.get("alternatives", [])
		for alternative_index in alternatives.size():
			var alternative: Dictionary = alternatives[alternative_index]
			var branch_marker := _create_marker(false)
			branch_marker.scale = Vector3.ONE * 0.72
			branch_marker.position = marker.position + Vector3(0.48 + alternative_index * 0.32, 0.04, -0.46)
			_world.add_child(branch_marker)
			_scenario_markers[str(alternative.get("id", ""))] = branch_marker


func _set_country_scene(scenario: Dictionary) -> void:
	var country_id := str(scenario.get("country_id", ""))
	if country_id != _current_country_id:
		_current_country_id = country_id
		if _country_landmark != null:
			_country_landmark.queue_free()
		_country_landmark = _instantiate_model(str(scenario.get("landmark_model", "")))
		if _country_landmark != null:
			_country_landmark.position = Vector3(-3.7, 0.3, -2.05)
			_country_landmark.scale = Vector3.ONE * 0.62
			_world.add_child(_country_landmark)

	var prop_paths: Array = scenario.get("prop_models", [])
	var signature := str(prop_paths)
	if signature == _current_prop_signature:
		return
	_current_prop_signature = signature
	for child in _scenario_props.get_children():
		child.queue_free()
	for index in prop_paths.size():
		var prop := _instantiate_model(str(prop_paths[index]))
		if prop != null:
			prop.position = Vector3(2.6 + float(index) * 1.35, 0.42, 2.1 - float(index) * 0.65)
			prop.scale = Vector3.ONE * (0.55 if index == 0 else 0.42)
			prop.rotation.y = -0.45 + float(index) * 0.7
			_scenario_props.add_child(prop)


func _set_enemy_figure(enemy: Dictionary) -> void:
	_set_enemy_figures([enemy])


func _set_enemy_figures(targets: Array) -> void:
	var identifiers: Array[String] = []
	for value in targets:
		var target: Dictionary = value
		identifiers.append(str(target.get("id", target.get("enemy_id", ""))))
	var signature := ",".join(identifiers)
	if signature == _enemy_signature:
		return
	_enemy_signature = signature
	for figure_value in _enemy_figures.values():
		var old_figure: Node3D = figure_value
		old_figure.queue_free()
	_enemy_figures.clear()
	_enemy_figure = null
	_current_enemy_id = identifiers[0] if not identifiers.is_empty() else ""
	for index in targets.size():
		var enemy: Dictionary = targets[index]
		var enemy_id := str(enemy.get("id", enemy.get("enemy_id", "")))
		if enemy_id.is_empty():
			continue
		var figure := _instantiate_model(str(enemy.get("model", "")))
		if figure == null:
			figure = _create_fallback_figure(Color("8d3f45"))
		var scale_factor := (0.76 if bool(enemy.get("boss", false)) else 0.62 if bool(enemy.get("elite", false)) else 0.52) * float(enemy.get("scale", 1.0))
		figure.scale = Vector3.ONE * scale_factor
		figure.position = Vector3(3.25 + float(index) * 1.05, 0.52, -1.80 + float(index % 2) * 0.85)
		var role_speed: Dictionary = _animation_profile.get("role_speed", {})
		figure.set_meta("animation_speed", float(role_speed.get(str(enemy.get("role", "")), 1.0)))
		_world.add_child(figure)
		_enemy_figures[enemy_id] = figure
		if _enemy_figure == null:
			_enemy_figure = figure
		_play_clip(figure, "spawn")


func _set_loot(state: Dictionary) -> void:
	var pending: Array = state.get("pending_loot", [])
	var signature := str(pending)
	if signature == _current_loot_signature:
		return
	_current_loot_signature = signature
	for child in _loot_root.get_children():
		child.queue_free()
	_loot_root.visible = not pending.is_empty()
	for figure_value in _enemy_figures.values():
		var figure: Node3D = figure_value
		figure.visible = pending.is_empty()
	if pending.is_empty():
		return
	var definitions: Dictionary = state.get("item_definitions", {})
	for index in mini(3, pending.size()):
		var definition: Dictionary = definitions.get(pending[index], {})
		var item := _instantiate_model(str(definition.get("model", "")))
		if item != null:
			item.position = Vector3(2.4 + float(index) * 1.35, 0.7, -1.45)
			item.scale = Vector3.ONE * 0.46
			_loot_root.add_child(item)
			_play_clip(item, "loot_hover")


func _ensure_party(state: Dictionary) -> void:
	var players: Dictionary = state.get("players", {})
	var signature_parts: Array[String] = []
	for player_id_value in players:
		var player: Dictionary = players[player_id_value]
		signature_parts.append("%s:%s" % [player_id_value, player.get("weapon", "axe")])
	var signature := ",".join(signature_parts)
	if signature == _party_signature:
		return
	_party_signature = signature
	_player_ids.clear()
	_party_figures.clear()
	for child in _party.get_children():
		child.queue_free()
	var index := 0
	var used_weapons: Dictionary = {}
	for player_id_value in players:
		var player_id := str(player_id_value)
		var player: Dictionary = players[player_id_value]
		var model_path := str(CHARACTER_MODELS.get(str(player.get("weapon", "axe")), CHARACTER_MODELS["axe"]))
		var figure := _instantiate_model(model_path)
		if figure == null:
			figure = _create_fallback_figure(Color("983f3d") if index == 0 else Color("4c8494"))
		figure.position = Vector3(-0.22 if index == 0 else 0.22, 0, 0)
		figure.scale = Vector3.ONE * 0.22
		var weapon := str(player.get("weapon", "axe"))
		if int(used_weapons.get(weapon, 0)) > 0:
			_apply_team_variant(figure, Color(0.22, 0.55, 0.78, 0.24))
		used_weapons[weapon] = int(used_weapons.get(weapon, 0)) + 1
		_party.add_child(figure)
		_party_figures.append(figure)
		_player_ids.append(player_id)
		_play_clip(figure, "idle")
		index += 1


func _actor_for(player_id: String) -> Node3D:
	var index := _player_ids.find(player_id)
	if index >= 0 and index < _party_figures.size():
		return _party_figures[index]
	return _party_figures[0] if not _party_figures.is_empty() else null


func _play_clip(model: Node, clip: String) -> void:
	if model == null:
		return
	var animator := _find_animation_player(model)
	if animator == null:
		return
	var selected := StringName(clip)
	if not animator.has_animation(selected):
		for candidate in animator.get_animation_list():
			if str(candidate).get_file() == clip or str(candidate).ends_with("/" + clip):
				selected = candidate
				break
	if animator.has_animation(selected):
		var clip_profile: Dictionary = _animation_profile.get("clips", {}).get(clip, {})
		var animation := animator.get_animation(selected)
		if animation != null:
			animation.loop_mode = Animation.LOOP_LINEAR if bool(clip_profile.get("loop", false)) else Animation.LOOP_NONE
		animator.speed_scale = float(model.get_meta("animation_speed", 1.0))
		animator.play(selected)


func _apply_team_variant(node: Node, color: Color) -> void:
	if node is MeshInstance3D:
		var overlay := StandardMaterial3D.new()
		overlay.transparency = BaseMaterial3D.TRANSPARENCY_ALPHA
		overlay.shading_mode = BaseMaterial3D.SHADING_MODE_UNSHADED
		overlay.albedo_color = color
		(node as MeshInstance3D).material_overlay = overlay
	for child in node.get_children():
		_apply_team_variant(child, color)


func _read_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}


func _find_animation_player(node: Node) -> AnimationPlayer:
	if node is AnimationPlayer:
		return node as AnimationPlayer
	for child in node.get_children():
		var found := _find_animation_player(child)
		if found != null:
			return found
	return null


func _instantiate_model(path: String) -> Node3D:
	if path.is_empty() or not ResourceLoader.exists(path):
		return null
	var packed := load(path) as PackedScene
	if packed == null:
		return null
	return packed.instantiate() as Node3D


func _add_box(position: Vector3, size: Vector3, color: Color) -> void:
	var mesh := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = size
	mesh.mesh = box
	mesh.position = position
	mesh.material_override = _material(color, 0.92)
	_world.add_child(mesh)


func _add_river() -> void:
	var river := MeshInstance3D.new()
	var box := BoxMesh.new()
	box.size = Vector3(11.5, 0.08, 0.7)
	river.mesh = box
	river.position = Vector3(0, 0.02, -1.0)
	river.rotation_degrees.y = -12
	river.material_override = _material(Color("284b55"), 0.28)
	_world.add_child(river)


func _add_mountains() -> void:
	for entry in [
		[Vector3(-4.5, 0.5, -2.7), 1.7], [Vector3(-3.2, 0.45, -3.0), 1.3],
		[Vector3(4.4, 0.75, 2.4), 1.9], [Vector3(3.2, 0.7, 2.9), 1.4],
	]:
		var mountain := MeshInstance3D.new()
		var cone := CylinderMesh.new()
		cone.top_radius = 0.0
		cone.bottom_radius = float(entry[1])
		cone.height = float(entry[1]) * 1.6
		mountain.mesh = cone
		mountain.position = entry[0]
		mountain.material_override = _material(Color("596058"), 0.95)
		_world.add_child(mountain)


func _create_marker(boss: bool) -> Node3D:
	var root := Node3D.new()
	var mesh := MeshInstance3D.new()
	var cylinder := CylinderMesh.new()
	cylinder.top_radius = 0.22 if not boss else 0.34
	cylinder.bottom_radius = 0.28 if not boss else 0.42
	cylinder.height = 0.18 if not boss else 0.3
	mesh.mesh = cylinder
	mesh.material_override = _material(Color("6d6654"), 0.55)
	root.add_child(mesh)
	return root


func _create_fallback_figure(color: Color) -> Node3D:
	var root := Node3D.new()
	var body := MeshInstance3D.new()
	var capsule := CapsuleMesh.new()
	capsule.radius = 0.24
	capsule.height = 0.82
	body.mesh = capsule
	body.position.y = 0.42
	body.material_override = _material(color, 0.62)
	root.add_child(body)
	var head := MeshInstance3D.new()
	var sphere := SphereMesh.new()
	sphere.radius = 0.15
	sphere.height = 0.3
	head.mesh = sphere
	head.position.y = 0.96
	head.material_override = _material(Color("b58c6c"), 0.78)
	root.add_child(head)
	return root


func _set_marker_color(marker: Node3D, marker_index: int, active_index: int) -> void:
	var mesh := marker.get_child(0) as MeshInstance3D
	if marker_index < active_index:
		mesh.material_override = _material(Color("586e58"), 0.65)
	elif marker_index == active_index:
		mesh.material_override = _material(Color("c79a4a"), 0.38)
	else:
		mesh.material_override = _material(Color("5b5a56"), 0.82)


func _material(color: Color, roughness: float) -> StandardMaterial3D:
	var material := StandardMaterial3D.new()
	material.albedo_color = color
	material.roughness = roughness
	return material
