class_name CinematicPlayer
extends Control

signal cinematic_started(cinematic_id: String)
signal cinematic_finished(cinematic_id: String, skipped: bool)

const CINEMATICS_PATH := "res://assets/narrative/cinematics.json"
const VOICE_PATH := "res://assets/narrative/voice_manifest.de-DE.json"
const LOCALE_PATH := "res://assets/narrative/de-DE.json"

var subtitles_enabled := true
var voice_enabled := true

var _cinematics: Dictionary = {}
var _lines: Dictionary = {}
var _localized_strings: Dictionary = {}
var _seen: Dictionary = {}
var _playing := false
var _skip_requested := false
var _current_id := ""

var _plate: TextureRect
var _shade: ColorRect
var _speaker: Label
var _subtitle: Label
var _skip_button: Button
var _voice: AudioStreamPlayer


func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	mouse_filter = Control.MOUSE_FILTER_STOP
	z_index = 200
	_load_manifests()
	_build_surface()
	hide()


func play_id(cinematic_id: String, context: Dictionary = {}) -> void:
	if _playing or not _cinematics.has(cinematic_id):
		return
	var definition: Dictionary = _cinematics[cinematic_id]
	var scope := str(definition.get("scope", "repeatable"))
	var seen_key := _scope_key(cinematic_id, scope, context)
	if scope != "repeatable" and _seen.has(seen_key):
		return
	_seen[seen_key] = true
	_playing = true
	_skip_requested = false
	_current_id = cinematic_id
	show()
	modulate.a = 0.0
	var appear := create_tween()
	appear.tween_property(self, "modulate:a", 1.0, 0.35)
	await appear.finished
	cinematic_started.emit(cinematic_id)
	for shot_value in definition.get("shots", []):
		if _skip_requested:
			break
		if shot_value is Dictionary:
			await _play_shot(shot_value, context)
	_voice.stop()
	_speaker.text = ""
	_subtitle.text = ""
	var skipped := _skip_requested
	var disappear := create_tween()
	disappear.tween_property(self, "modulate:a", 0.0, 0.28)
	await disappear.finished
	hide()
	_current_id = ""
	_playing = false
	cinematic_finished.emit(cinematic_id, skipped)


func play_authoritative(cinematic_id: String, context: Dictionary = {}) -> void:
	"""Play a server-owned campaign cinematic even if another campaign saw it locally."""
	if _playing or not _cinematics.has(cinematic_id):
		return
	var definition: Dictionary = _cinematics[cinematic_id]
	_seen.erase(_scope_key(cinematic_id, str(definition.get("scope", "repeatable")), context))
	await play_id(cinematic_id, context)


func is_playing() -> bool:
	return _playing


func _play_shot(shot: Dictionary, context: Dictionary) -> void:
	var plate_path := str(shot.get("plate", ""))
	if plate_path == "$scenario_background":
		plate_path = str(context.get("background", "res://assets/backgrounds/rift.png"))
	if ResourceLoader.exists(plate_path):
		_plate.texture = load(plate_path)
	_plate.position = Vector2.ZERO
	_plate.scale = Vector2.ONE * 1.04
	var duration := float(shot.get("duration", 6.0))
	var motion := str(shot.get("motion", "push_in"))
	var target_scale := Vector2.ONE * (1.12 if motion == "push_in" else 1.02)
	var target_position := Vector2.ZERO
	if motion == "pan_left":
		target_position = Vector2(-36, 0)
	elif motion == "pan_right":
		target_position = Vector2(36, 0)
	elif motion == "shake":
		target_position = Vector2(12, -5)
	var camera_tween := create_tween().set_parallel(true)
	camera_tween.tween_property(_plate, "scale", target_scale, duration).set_trans(Tween.TRANS_SINE)
	camera_tween.tween_property(_plate, "position", target_position, duration).set_trans(Tween.TRANS_SINE)
	for line_id_value in shot.get("lines", []):
		if _skip_requested:
			break
		await _play_line(str(line_id_value))
	if not _skip_requested and shot.get("lines", []).is_empty():
		await get_tree().create_timer(duration).timeout
	if camera_tween.is_running():
		camera_tween.kill()


func _play_line(line_id: String) -> void:
	if not _lines.has(line_id):
		return
	var line: Dictionary = _lines[line_id]
	_speaker.text = _speaker_name(str(line.get("speaker", ""))) if subtitles_enabled else ""
	_subtitle.text = str(_localized_strings.get(line_id, line.get("text", ""))) if subtitles_enabled else ""
	var duration := maxf(1.1, float(line.get("duration_ms", 1800)) / 1000.0)
	var path := str(line.get("asset", ""))
	if voice_enabled and ResourceLoader.exists(path):
		_voice.stream = load(path)
		_voice.play()
	var elapsed := 0.0
	while elapsed < duration and not _skip_requested:
		await get_tree().create_timer(minf(0.08, duration - elapsed)).timeout
		elapsed += 0.08
	_voice.stop()


func _build_surface() -> void:
	_shade = ColorRect.new()
	_shade.color = Color("05070a")
	_shade.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(_shade)
	_plate = TextureRect.new()
	_plate.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_plate.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	_plate.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	_plate.pivot_offset = Vector2(800, 450)
	_plate.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_plate)
	var letterbox_top := ColorRect.new()
	letterbox_top.color = Color("050608")
	letterbox_top.set_anchors_and_offsets_preset(Control.PRESET_TOP_WIDE)
	letterbox_top.custom_minimum_size.y = 58
	add_child(letterbox_top)
	var letterbox_bottom := ColorRect.new()
	letterbox_bottom.color = Color(0.015, 0.018, 0.022, 0.96)
	letterbox_bottom.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_WIDE)
	letterbox_bottom.position.y = -170
	letterbox_bottom.custom_minimum_size.y = 170
	add_child(letterbox_bottom)
	_speaker = Label.new()
	_speaker.position = Vector2(110, -145)
	_speaker.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	_speaker.add_theme_font_size_override("font_size", 20)
	_speaker.add_theme_color_override("font_color", Color("d2b56f"))
	add_child(_speaker)
	_subtitle = Label.new()
	_subtitle.position = Vector2(110, -112)
	_subtitle.size = Vector2(1320, 88)
	_subtitle.set_anchors_and_offsets_preset(Control.PRESET_BOTTOM_LEFT)
	_subtitle.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_subtitle.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_subtitle.add_theme_font_size_override("font_size", 27)
	_subtitle.add_theme_color_override("font_color", Color("f0e8d7"))
	add_child(_subtitle)
	_skip_button = Button.new()
	_skip_button.text = "ÜBERSPRINGEN"
	_skip_button.position = Vector2(-185, 22)
	_skip_button.set_anchors_and_offsets_preset(Control.PRESET_TOP_RIGHT)
	_skip_button.custom_minimum_size = Vector2(160, 42)
	_skip_button.pressed.connect(_request_skip)
	add_child(_skip_button)
	_voice = AudioStreamPlayer.new()
	_voice.bus = "Voice"
	add_child(_voice)


func _load_manifests() -> void:
	var cinematic_doc := _read_json(CINEMATICS_PATH)
	for value in cinematic_doc.get("cinematics", []):
		if value is Dictionary:
			_cinematics[str(value.get("id", ""))] = value
	var voice_doc := _read_json(VOICE_PATH)
	for value in voice_doc.get("lines", []):
		if value is Dictionary:
			_lines[str(value.get("id", ""))] = value
	_localized_strings = _read_json(LOCALE_PATH).get("strings", {})


func _read_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		return {}
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(path))
	return parsed if parsed is Dictionary else {}


func _request_skip() -> void:
	_skip_requested = true
	_voice.stop()


func _scope_key(cinematic_id: String, scope: String, context: Dictionary) -> String:
	if scope == "country_once":
		return "%s:%s" % [cinematic_id, context.get("country_id", "")]
	if scope == "scenario_once":
		return "%s:%s" % [cinematic_id, context.get("id", "")]
	return cinematic_id


func _speaker_name(value: String) -> String:
	if value == "pathfinder":
		return "PFADFINDERIN"
	if value == "vanguard":
		return "VORHUT"
	if value == "duelist":
		return "DUELLANTIN"
	if value == "arbalist":
		return "ARBALESTER"
	if value == "narrator":
		return "CHRONIST"
	if value == "mentor":
		return "WEGSTEIN"
	if value.begins_with("boss_"):
		return "HÜTER"
	return "GEGNER"
