class_name VoiceDirector
extends Node

signal subtitle_requested(speaker: String, text: String)
signal voice_active_changed(active: bool)

const MANIFEST_PATH := "res://assets/narrative/voice_manifest.de-DE.json"

var enabled := true
var _lines: Dictionary = {}
var _player: AudioStreamPlayer
var _cooldown_until := 0


func _ready() -> void:
	_player = AudioStreamPlayer.new()
	_player.bus = "Voice"
	_player.finished.connect(func() -> void: voice_active_changed.emit(false))
	add_child(_player)
	var parsed = JSON.parse_string(FileAccess.get_file_as_string(MANIFEST_PATH))
	if parsed is Dictionary:
		for value in parsed.get("lines", []):
			if value is Dictionary:
				_lines[str(value.get("id", ""))] = value


func play_event(event: Dictionary, state: Dictionary, local_profile_id: String, cinematic_active: bool) -> void:
	if not enabled or cinematic_active or Time.get_ticks_msec() < _cooldown_until:
		return
	var event_type := str(event.get("type", ""))
	var line_id := ""
	if event_type in ["card_played", "player_damaged", "player_healed", "loot_claimed", "scenario_completed"]:
		var actor_id := str(event.get("actor", event.get("player", local_profile_id)))
		var actor: Dictionary = state.get("players", {}).get(actor_id, {})
		var speaker: String = str({"axe":"vanguard", "bow":"pathfinder", "dual_blades":"duelist", "crossbow":"arbalist"}.get(str(actor.get("weapon", "axe")), "vanguard"))
		var ranges := {"card_played":[1,15], "player_damaged":[16,18], "player_healed":[17,18], "loot_claimed":[19,20], "scenario_completed":[23,24]}
		var range_value: Array = ranges.get(event_type, [1,24])
		line_id = "bark_%s_%02d" % [speaker, _select(event, int(range_value[0]), int(range_value[1]))]
	elif event_type in ["enemy_intent", "enemy_attack_resolved", "enemy_spawned"]:
		var role := str(state.get("enemy", {}).get("role", "skirmisher"))
		if event_type == "enemy_spawned":
			role = str(event.get("enemy", {}).get("role", role))
		line_id = "enemy_%s_%d" % [role, _select(event, 1, 6)]
	if not line_id.is_empty():
		_play_line(line_id)


func _play_line(line_id: String) -> void:
	if not _lines.has(line_id):
		return
	var line: Dictionary = _lines[line_id]
	var path := str(line.get("asset", ""))
	if not ResourceLoader.exists(path):
		return
	_player.stream = load(path)
	_player.play()
	_cooldown_until = Time.get_ticks_msec() + int(line.get("duration_ms", 1600)) + 900
	voice_active_changed.emit(true)
	subtitle_requested.emit(str(line.get("speaker", "")), str(line.get("text", "")))


func _select(event: Dictionary, minimum: int, maximum: int) -> int:
	var material := str(event)
	return minimum + abs(material.hash()) % (maximum - minimum + 1)
