class_name ScenarioStage
extends Control

var world_view: WorldDiorama3D
var _backdrop: TextureRect
var _current_background := ""
var _vfx_overlay: TextureRect


func _ready() -> void:
	custom_minimum_size = Vector2(0, 330)
	clip_contents = true
	_backdrop = TextureRect.new()
	_backdrop.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_backdrop.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_backdrop.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	_backdrop.modulate = Color(0.72, 0.72, 0.72, 0.82)
	add_child(_backdrop)
	var shade := ColorRect.new()
	shade.color = Color(0.02, 0.03, 0.035, 0.28)
	shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(shade)
	world_view = WorldDiorama3D.new()
	world_view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(world_view)
	_vfx_overlay = TextureRect.new()
	_vfx_overlay.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_vfx_overlay.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_vfx_overlay.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	_vfx_overlay.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_vfx_overlay.modulate = Color(1, 1, 1, 0)
	add_child(_vfx_overlay)


func set_game_state(state: Dictionary) -> void:
	var scenario: Dictionary = state.get("scenario", {})
	var has_loot := not state.get("pending_loot", []).is_empty()
	var path := "res://assets/backgrounds/loot_reveal.png" if has_loot else str(scenario.get("background", ""))
	if path != _current_background:
		var image := UIFactory.texture(path)
		if image != null:
			_backdrop.texture = image
			_current_background = path
	world_view.set_game_state(state)


func set_render_scale(value: float) -> void:
	if world_view != null:
		world_view.set_render_scale(value)


func play_event_vfx(event: Dictionary) -> void:
	var effect: String = str({
		"enemy_damaged": "hit", "player_damaged": "hit", "block_dice_added": "block",
		"magic_resolved": "magic", "player_healed": "heal", "loot_offered": "loot",
		"status_damage": "burn", "player_status_damage": "bleed",
		"player_ward_resolved": "ward", "enemy_status": "burn",
	}.get(str(event.get("type", "")), ""))
	if effect.is_empty():
		world_view.play_combat_event(event)
		return
	var texture := UIFactory.texture("res://assets/vfx/%s.svg" % effect)
	if texture != null:
		_vfx_overlay.texture = texture
		_vfx_overlay.modulate = Color(1, 1, 1, 0)
		var tween := create_tween()
		tween.tween_property(_vfx_overlay, "modulate:a", 0.72, 0.10)
		tween.tween_property(_vfx_overlay, "modulate:a", 0.0, 0.34)
	world_view.play_combat_event(event)
