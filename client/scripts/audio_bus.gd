class_name GameAudio
extends Node

const EVENT_CUES := {
	"ui_click": "ui_click",
	"card_played": "card_play",
	"dice_rolled": "dice_roll",
	"enemy_damaged": "hit",
	"player_damaged": "hit",
	"player_healed": "heal",
	"loot_offered": "loot",
	"scenario_completed": "victory",
	"rollback": "defeat",
	"block_dice_added": "block",
	"magic_resolved": "magic",
	"boss_stage_changed": "oath_gate",
	"boss_objective_destroyed": "anchor_break",
	"armor_broken": "armor_break",
	"boss_threat_changed": "threat",
	"oath_power_gained": "oath_power",
	"ending_resolved": "ending",
	"legacy_transfer_ready": "legacy",
	"new_game_plus_started": "new_game_plus",
}

var _players: Array[AudioStreamPlayer] = []
var _cursor := 0
var _music: AudioStreamPlayer
var _ambience: AudioStreamPlayer
var _music_name := ""
var _ambience_name := ""


func _ready() -> void:
	for _index in 6:
		var player := AudioStreamPlayer.new()
		player.volume_db = -8.0
		player.bus = "SFX"
		add_child(player)
		_players.append(player)
	_music = AudioStreamPlayer.new()
	_music.volume_db = -18.0
	_music.bus = "Music"
	add_child(_music)
	_ambience = AudioStreamPlayer.new()
	_ambience.volume_db = -22.0
	_ambience.bus = "Ambience"
	add_child(_ambience)
	_play_loop(_music, "music_menu")
	_music_name = "music_menu"


func play_event(event: Dictionary) -> void:
	var cue := str(EVENT_CUES.get(str(event.get("type", "")), ""))
	if cue.is_empty():
		return
	var path := "res://assets/audio/%s.wav" % cue
	if not ResourceLoader.exists(path):
		return
	var player := _players[_cursor]
	_cursor = (_cursor + 1) % _players.size()
	player.stream = load(path)
	player.play()


func set_context(state: Dictionary) -> void:
	var scenario: Dictionary = state.get("scenario", {})
	var ambience_name := "ambience_%s" % str(scenario.get("biome", "moor"))
	if ambience_name != _ambience_name:
		_ambience_name = ambience_name
		_play_loop(_ambience, ambience_name)
	var music_name := "music_world_echo" if not state.get("postgame", {}).is_empty() else "music_exploration" if bool(state.get("awaiting_scenario_choice", false)) else "music_finale" if bool(scenario.get("is_final", false)) else "music_boss" if bool(scenario.get("is_boss", false)) else "music_combat"
	if music_name != _music_name:
		_music_name = music_name
		_play_loop(_music, music_name)


func set_voice_active(active: bool) -> void:
	var tween := create_tween().set_parallel(true)
	tween.tween_property(_music, "volume_db", -27.0 if active else -18.0, 0.22)
	tween.tween_property(_ambience, "volume_db", -30.0 if active else -22.0, 0.22)


func play_ui_click() -> void:
	play_event({"type": "ui_click"})


func _play_loop(player: AudioStreamPlayer, loop_name: String) -> void:
	var path := "res://assets/audio/%s.wav" % loop_name
	if not ResourceLoader.exists(path):
		return
	var stream := load(path)
	if stream is AudioStreamWAV:
		(stream as AudioStreamWAV).loop_mode = AudioStreamWAV.LOOP_FORWARD
	player.stream = stream
	player.play()
