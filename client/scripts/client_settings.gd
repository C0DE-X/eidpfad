class_name ClientSettings
extends RefCounted

const SETTINGS_PATH := "user://eidpfad-client.cfg"

var server_url := "http://127.0.0.1:8080"
var profile_id := ""
var display_name := ""
var device_token := ""
var campaign_id := ""
var invite_code := ""
var master_db := 0.0
var music_db := -4.0
var voice_db := 1.0
var subtitles_enabled := true
var render_scale := 1.0


func load_from_disk() -> void:
	var config := ConfigFile.new()
	if config.load(SETTINGS_PATH) != OK:
		return
	server_url = str(config.get_value("network", "server_url", server_url))
	profile_id = str(config.get_value("session", "profile_id", ""))
	display_name = str(config.get_value("session", "display_name", ""))
	device_token = str(config.get_value("session", "device_token", ""))
	campaign_id = str(config.get_value("session", "campaign_id", ""))
	invite_code = str(config.get_value("session", "invite_code", ""))
	master_db = float(config.get_value("audio", "master_db", master_db))
	music_db = float(config.get_value("audio", "music_db", music_db))
	voice_db = float(config.get_value("audio", "voice_db", voice_db))
	subtitles_enabled = bool(config.get_value("accessibility", "subtitles_enabled", subtitles_enabled))
	render_scale = float(config.get_value("graphics", "render_scale", render_scale))


func save_to_disk() -> Error:
	var config := ConfigFile.new()
	config.set_value("network", "server_url", server_url)
	config.set_value("session", "profile_id", profile_id)
	config.set_value("session", "display_name", display_name)
	config.set_value("session", "device_token", device_token)
	config.set_value("session", "campaign_id", campaign_id)
	config.set_value("session", "invite_code", invite_code)
	config.set_value("audio", "master_db", master_db)
	config.set_value("audio", "music_db", music_db)
	config.set_value("audio", "voice_db", voice_db)
	config.set_value("accessibility", "subtitles_enabled", subtitles_enabled)
	config.set_value("graphics", "render_scale", render_scale)
	return config.save(SETTINGS_PATH)


func clear_session() -> Error:
	profile_id = ""
	display_name = ""
	device_token = ""
	campaign_id = ""
	invite_code = ""
	return save_to_disk()
