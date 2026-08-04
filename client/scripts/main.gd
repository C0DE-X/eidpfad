extends Control

const PHASE_NAMES := {
	"attack": "ANGRIFF",
	"defense": "VERTEIDIGUNG",
	"magic": "MAGIE",
	"utility": "VORBEREITUNG",
}

var network: NetworkClient
var game_audio: GameAudio
var voice_director: VoiceDirector
var settings := ClientSettings.new()
var current_state: Dictionary = {}
var cinematic: CinematicPlayer
var _presentation_queue: Array[Dictionary] = []
var _presenting := false

var server_edit: LineEdit
var options_server_edit: LineEdit
var name_edit: LineEdit
var recovery_edit: LineEdit
var invite_edit: LineEdit
var seed_edit: LineEdit
var weapon_select: OptionButton
var magic_select: OptionButton
var length_select: OptionButton
var campaign_view_title: Label
var campaign_view_description: Label
var campaign_start_button: Button
var multiplayer_join_box: Control
var campaign_label: Label
var campaign_select: OptionButton
var continue_campaign_button: Button
var ready_button: Button
var lobby_label: Label
var status_label: Label
var scenario_label: Label
var enemy_label: Label
var phase_label: Label
var phase_labels: Dictionary = {}
var action_box: HFlowContainer
var pass_button: Button
var portrait_texture: TextureRect
var portrait_stats: Label
var partner_stats: Label
var partner_panel: PanelContainer
var country_icon: TextureRect
var enemy_icon: TextureRect
var log_view: RichTextLabel
var dice_view: DiceRoller3D
var world_view: ScenarioStage
var connection_screen: Control
var game_screen: Control
var submenu_panel: PanelContainer
var submenu_views: Dictionary = {}
var _selected_mode := ""
var _pending_menu_after_profile := ""
var _auto_ready_after_connect := false
var _campaigns: Array[Dictionary] = []


func _ready() -> void:
	settings.load_from_disk()
	network = NetworkClient.new()
	add_child(network)
	game_audio = GameAudio.new()
	add_child(game_audio)
	voice_director = VoiceDirector.new()
	add_child(voice_director)
	voice_director.voice_active_changed.connect(game_audio.set_voice_active)
	voice_director.subtitle_requested.connect(func(speaker: String, text: String) -> void:
		if settings.subtitles_enabled:
			_append_log("[color=#d2b56f]%s:[/color] %s" % [speaker.to_upper(), text])
	)
	network.api_succeeded.connect(_on_api_succeeded)
	network.api_failed.connect(_on_api_failed)
	network.socket_event.connect(_on_socket_event)
	network.connection_changed.connect(_on_connection_changed)
	network.lobby_changed.connect(_on_lobby_changed)
	network.ready_changed.connect(_on_ready_changed)
	network.restore_session(
		settings.server_url,
		settings.profile_id,
		settings.device_token,
		settings.campaign_id,
		settings.invite_code,
	)
	_build_ui()
	world_view.set_render_scale(settings.render_scale)
	cinematic = CinematicPlayer.new()
	add_child(cinematic)
	cinematic.cinematic_started.connect(func(_id: String) -> void: game_audio.set_voice_active(true))
	cinematic.cinematic_finished.connect(func(cinematic_id: String, skipped: bool) -> void:
		game_audio.set_voice_active(false)
		var cinematic_state := _as_dictionary(current_state.get("cinematics", {}))
		var active := _as_dictionary(cinematic_state.get("active", {}))
		if str(active.get("cinematic_id", "")) == cinematic_id:
			network.cinematic_ack(cinematic_id, skipped)
	)
	cinematic.subtitles_enabled = settings.subtitles_enabled
	_apply_audio_settings()
	if not settings.device_token.is_empty():
		network.validate_profile()


func _notification(what: int) -> void:
	if what == NOTIFICATION_WM_CLOSE_REQUEST and network != null:
		network.disconnect_campaign()
		get_tree().quit()


func _build_ui() -> void:
	var background := TextureRect.new()
	background.texture = UIFactory.texture("res://assets/backgrounds/main_menu.png")
	background.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	background.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	background.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(background)
	move_child(background, 0)
	var veil := ColorRect.new()
	veil.color = Color(0.015, 0.020, 0.025, 0.22)
	veil.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(veil)
	move_child(veil, 1)

	var margin := MarginContainer.new()
	margin.add_theme_constant_override("margin_left", 24)
	margin.add_theme_constant_override("margin_right", 24)
	margin.add_theme_constant_override("margin_top", 20)
	margin.add_theme_constant_override("margin_bottom", 20)
	margin.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(margin)

	var root := HBoxContainer.new()
	root.add_theme_constant_override("separation", 20)
	margin.add_child(root)
	connection_screen = _build_main_menu()
	game_screen = _build_game_panel()
	root.add_child(connection_screen)
	root.add_child(game_screen)
	game_screen.hide()


func _build_main_menu() -> Control:
	var screen := HBoxContainer.new()
	screen.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	screen.size_flags_vertical = Control.SIZE_EXPAND_FILL
	screen.add_theme_constant_override("separation", 20)

	var navigation := PanelContainer.new()
	navigation.custom_minimum_size = Vector2(350, 0)
	navigation.add_theme_stylebox_override("panel", UIFactory.panel_style(Color(0.035, 0.045, 0.050, 0.88)))
	var nav_margin := MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		nav_margin.add_theme_constant_override("margin_%s" % side, 26)
	navigation.add_child(nav_margin)
	var nav_column := VBoxContainer.new()
	nav_column.add_theme_constant_override("separation", 10)
	nav_margin.add_child(nav_column)

	var logo := TextureRect.new()
	logo.texture = UIFactory.texture("res://assets/logo/eidpfad.svg")
	logo.custom_minimum_size = Vector2(96, 96)
	logo.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	logo.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	nav_column.add_child(logo)
	var title := UIFactory.heading("EIDPFAD", 42)
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	nav_column.add_child(title)
	var subtitle := Label.new()
	subtitle.text = "DIE KRONE OHNE NAMEN"
	subtitle.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	subtitle.add_theme_color_override("font_color", Color("89979d"))
	nav_column.add_child(subtitle)
	var title_separator := HSeparator.new()
	title_separator.custom_minimum_size.y = 18
	nav_column.add_child(title_separator)

	var solo_button := _menu_button("EINZELSPIELER", "res://assets/ui/character.svg")
	solo_button.pressed.connect(_open_mode_menu.bind("singleplayer"))
	nav_column.add_child(solo_button)
	var multiplayer_button := _menu_button("MEHRSPIELER", "res://assets/ui/connection.svg")
	multiplayer_button.pressed.connect(_open_mode_menu.bind("multiplayer"))
	nav_column.add_child(multiplayer_button)
	var resume_button := _menu_button("FORTSETZEN", "res://assets/ui/campaign.svg")
	resume_button.pressed.connect(_open_continue_menu)
	nav_column.add_child(resume_button)
	var options_button := _menu_button("OPTIONEN", "res://assets/ui/armor.svg")
	options_button.pressed.connect(_show_submenu.bind("options"))
	nav_column.add_child(options_button)
	var quit_button := _menu_button("BEENDEN", "res://assets/ui/threat.svg")
	quit_button.pressed.connect(func() -> void: get_tree().quit())
	nav_column.add_child(quit_button)

	var nav_spacer := Control.new()
	nav_spacer.size_flags_vertical = Control.SIZE_EXPAND_FILL
	nav_column.add_child(nav_spacer)
	status_label = Label.new()
	status_label.text = "Bereit"
	status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	status_label.add_theme_color_override("font_color", Color("c8b98e"))
	nav_column.add_child(status_label)
	log_view = RichTextLabel.new()
	log_view.bbcode_enabled = true
	log_view.scroll_following = true
	log_view.custom_minimum_size = Vector2(0, 92)
	log_view.add_theme_color_override("default_color", Color("8c989c"))
	nav_column.add_child(log_view)
	screen.add_child(navigation)

	submenu_panel = PanelContainer.new()
	submenu_panel.custom_minimum_size = Vector2(510, 0)
	submenu_panel.add_theme_stylebox_override("panel", UIFactory.panel_style(Color(0.055, 0.070, 0.075, 0.94)))
	var scroll := ScrollContainer.new()
	scroll.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	scroll.vertical_scroll_mode = ScrollContainer.SCROLL_MODE_AUTO
	scroll.follow_focus = true
	submenu_panel.add_child(scroll)
	var submenu_margin := MarginContainer.new()
	for side in ["left", "right", "top", "bottom"]:
		submenu_margin.add_theme_constant_override("margin_%s" % side, 26)
	submenu_margin.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	scroll.add_child(submenu_margin)
	var submenu_host := VBoxContainer.new()
	submenu_host.add_theme_constant_override("separation", 12)
	submenu_margin.add_child(submenu_host)

	for entry in [
		["profile", _build_profile_view()],
		["campaign", _build_campaign_view()],
		["continue", _build_continue_view()],
		["options", _build_options_view()],
		["lobby", _build_lobby_view()],
	]:
		var view: Control = entry[1]
		view.hide()
		submenu_views[entry[0]] = view
		submenu_host.add_child(view)
	submenu_panel.hide()
	screen.add_child(submenu_panel)

	var open_space := Control.new()
	open_space.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	screen.add_child(open_space)
	_append_log("Client bereit.")
	return screen


func _menu_button(caption: String, icon_path: String) -> Button:
	var button := UIFactory.button(caption)
	button.icon = UIFactory.texture(icon_path)
	button.custom_minimum_size = Vector2(0, 56)
	button.alignment = HORIZONTAL_ALIGNMENT_LEFT
	button.add_theme_font_size_override("font_size", 20)
	button.add_theme_color_override("font_color", Color("d8d0bb"))
	button.add_theme_color_override("font_hover_color", Color("f0d990"))
	button.add_theme_stylebox_override("normal", UIFactory.panel_style(Color(0.02, 0.03, 0.035, 0.12)))
	button.add_theme_stylebox_override("hover", UIFactory.panel_style(Color(0.20, 0.16, 0.10, 0.64)))
	return button


func _view_column(title: String, description: String) -> VBoxContainer:
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 12)
	column.add_child(UIFactory.heading(title, 28))
	var copy := Label.new()
	copy.text = description
	copy.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	copy.add_theme_color_override("font_color", Color("aab3b5"))
	column.add_child(copy)
	column.add_child(HSeparator.new())
	return column


func _build_profile_view() -> Control:
	var column := _view_column("PROFIL", "Ein lokales Profil verbindet deinen Fortschritt sicher mit dem Spielserver.")
	server_edit = UIFactory.line_edit("http://127.0.0.1:8080", settings.server_url)
	server_edit.tooltip_text = "Lokal: http://127.0.0.1:8080 · VPS: HTTPS-Adresse mit gueltigem Zertifikat"
	column.add_child(server_edit)
	name_edit = UIFactory.line_edit("Spielername", settings.display_name)
	column.add_child(name_edit)
	var profile_button := UIFactory.button("Profil anlegen und weiter")
	profile_button.icon = UIFactory.texture("res://assets/ui/server.svg")
	profile_button.pressed.connect(_create_profile)
	column.add_child(profile_button)
	column.add_child(UIFactory.heading("PROFIL WIEDERHERSTELLEN", 16))
	recovery_edit = UIFactory.line_edit("Wiederherstellungscode", "")
	recovery_edit.secret = true
	column.add_child(recovery_edit)
	var recover_button := UIFactory.button("Profil wiederherstellen")
	recover_button.icon = UIFactory.texture("res://assets/ui/legacy.svg")
	recover_button.pressed.connect(_recover_profile)
	column.add_child(recover_button)
	return column


func _build_campaign_view() -> Control:
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 12)
	campaign_view_title = UIFactory.heading("NEUE KAMPAGNE", 28)
	column.add_child(campaign_view_title)
	campaign_view_description = Label.new()
	campaign_view_description.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	campaign_view_description.add_theme_color_override("font_color", Color("aab3b5"))
	column.add_child(campaign_view_description)
	column.add_child(HSeparator.new())

	var choices := HBoxContainer.new()
	choices.add_theme_constant_override("separation", 8)
	column.add_child(choices)
	weapon_select = OptionButton.new()
	for value in ["Zwei Klingen", "Axt", "Langbogen", "Armbrust", "Langschwert"]:
		weapon_select.add_item(value)
	weapon_select.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	choices.add_child(weapon_select)
	magic_select = OptionButton.new()
	for value in ["Runenmagie", "Glutmagie", "Schleiermagie", "Blutmagie"]:
		magic_select.add_item(value)
	magic_select.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	choices.add_child(magic_select)
	length_select = OptionButton.new()
	length_select.add_item("Expedition · 6 Laender")
	length_select.add_item("Feldzug · 9 Laender")
	length_select.add_item("Saga · 13 Laender")
	length_select.select(1)
	column.add_child(length_select)
	seed_edit = UIFactory.line_edit("Seed (optional)", "")
	column.add_child(seed_edit)
	campaign_start_button = UIFactory.button("Kampagne starten")
	campaign_start_button.icon = UIFactory.texture("res://assets/ui/ready.svg")
	campaign_start_button.custom_minimum_size.y = 48
	campaign_start_button.pressed.connect(_create_campaign)
	column.add_child(campaign_start_button)

	multiplayer_join_box = VBoxContainer.new()
	multiplayer_join_box.add_theme_constant_override("separation", 10)
	multiplayer_join_box.add_child(HSeparator.new())
	multiplayer_join_box.add_child(UIFactory.heading("LOBBY BEITRETEN", 16))
	invite_edit = UIFactory.line_edit("Einladungscode", settings.invite_code)
	multiplayer_join_box.add_child(invite_edit)
	var join_button := UIFactory.button("Kampagne beitreten")
	join_button.icon = UIFactory.texture("res://assets/ui/connection.svg")
	join_button.pressed.connect(_join_campaign)
	multiplayer_join_box.add_child(join_button)
	column.add_child(multiplayer_join_box)
	return column


func _build_continue_view() -> Control:
	var column := _view_column("FORTSETZEN", "Waehle eine gespeicherte Kampagne. Singleplayer wird automatisch verbunden und fortgesetzt.")
	campaign_select = OptionButton.new()
	campaign_select.add_item("Kampagnen werden geladen …")
	campaign_select.set_item_metadata(0, {})
	campaign_select.item_selected.connect(_select_campaign)
	column.add_child(campaign_select)
	continue_campaign_button = UIFactory.button("Ausgewaehlte Kampagne fortsetzen")
	continue_campaign_button.icon = UIFactory.texture("res://assets/ui/connection.svg")
	continue_campaign_button.disabled = true
	continue_campaign_button.pressed.connect(_continue_campaign)
	column.add_child(continue_campaign_button)
	var refresh_button := UIFactory.button("Liste aktualisieren")
	refresh_button.pressed.connect(func() -> void: network.list_campaigns())
	column.add_child(refresh_button)
	return column


func _build_options_view() -> Control:
	var column := _view_column("OPTIONEN", "Netzwerk, Audio, Untertitel und Darstellungsqualitaet.")
	options_server_edit = UIFactory.line_edit("http://127.0.0.1:8080", settings.server_url)
	column.add_child(options_server_edit)
	var save_server_button := UIFactory.button("Serveradresse speichern")
	save_server_button.pressed.connect(_save_server_settings)
	column.add_child(save_server_button)
	column.add_child(UIFactory.heading("AUDIO & ZUGAENGLICHKEIT", 16))
	column.add_child(_audio_slider("Master", "Master", settings.master_db))
	column.add_child(_audio_slider("Musik", "Music", settings.music_db))
	column.add_child(_audio_slider("Stimmen", "Voice", settings.voice_db))
	var subtitle_toggle := CheckButton.new()
	subtitle_toggle.text = "Deutsche Untertitel"
	subtitle_toggle.button_pressed = settings.subtitles_enabled
	subtitle_toggle.toggled.connect(func(enabled: bool) -> void:
		settings.subtitles_enabled = enabled
		if cinematic != null:
			cinematic.subtitles_enabled = enabled
		settings.save_to_disk()
	)
	column.add_child(subtitle_toggle)
	var quality_select := OptionButton.new()
	quality_select.add_item("3D-Qualitaet: Performance · 75 %")
	quality_select.add_item("3D-Qualitaet: Hoch · 100 %")
	quality_select.add_item("3D-Qualitaet: Ultra · 125 %")
	quality_select.select(0 if settings.render_scale < 0.9 else 2 if settings.render_scale > 1.1 else 1)
	quality_select.item_selected.connect(func(index: int) -> void:
		settings.render_scale = [0.75, 1.0, 1.25][index]
		if world_view != null:
			world_view.set_render_scale(settings.render_scale)
		settings.save_to_disk()
	)
	column.add_child(quality_select)
	var profile_button := UIFactory.button("Profil verwalten")
	profile_button.pressed.connect(_show_submenu.bind("profile"))
	column.add_child(profile_button)
	return column


func _build_lobby_view() -> Control:
	var column := _view_column("LOBBY", "Singleplayer startet automatisch. Im Multiplayer muessen beide Spieler verbunden und bereit sein.")
	campaign_label = Label.new()
	campaign_label.text = _campaign_text()
	campaign_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	campaign_label.add_theme_color_override("font_color", Color("d7c49a"))
	column.add_child(campaign_label)
	lobby_label = Label.new()
	lobby_label.text = "Lobby: nicht verbunden"
	lobby_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	column.add_child(lobby_label)
	ready_button = UIFactory.button("Bereit")
	ready_button.icon = UIFactory.texture("res://assets/ui/ready.svg")
	ready_button.disabled = true
	ready_button.pressed.connect(func() -> void: network.send_ready(not network.local_ready))
	column.add_child(ready_button)
	var disconnect_button := UIFactory.button("Verbindung trennen")
	disconnect_button.pressed.connect(func() -> void:
		network.disconnect_campaign()
		_auto_ready_after_connect = false
		_show_submenu("continue")
	)
	column.add_child(disconnect_button)
	return column


func _show_submenu(name: String) -> void:
	if not submenu_views.has(name):
		return
	for view_value in submenu_views.values():
		var view: Control = view_value
		view.visible = view == submenu_views[name]
	submenu_panel.show()


func _open_mode_menu(mode: String) -> void:
	_selected_mode = mode
	if network.device_token.is_empty():
		_pending_menu_after_profile = "campaign"
		_show_submenu("profile")
		status_label.text = "Bitte zuerst ein Profil anlegen oder wiederherstellen."
		return
	campaign_view_title.text = "EINZELSPIELER" if mode == "singleplayer" else "MEHRSPIELER"
	campaign_view_description.text = (
		"Erstelle eine eigene Kampagne. Verbindung und Bereitschaft erfolgen beim Start automatisch."
		if mode == "singleplayer"
		else "Erstelle eine Lobby oder tritt mit einem Einladungscode bei. Der Modus bleibt fuer diese Kampagne fest."
	)
	campaign_start_button.text = "Einzelspieler starten" if mode == "singleplayer" else "Multiplayer-Lobby erstellen"
	multiplayer_join_box.visible = mode == "multiplayer"
	_show_submenu("campaign")


func _open_continue_menu() -> void:
	if network.device_token.is_empty():
		_pending_menu_after_profile = "continue"
		_show_submenu("profile")
		status_label.text = "Zum Fortsetzen wird dein Profil benoetigt."
		return
	_show_submenu("continue")
	if network.configure(settings.server_url):
		status_label.text = "Kampagnen werden geladen …"
		network.list_campaigns()


func _save_server_settings() -> void:
	if network.configure(options_server_edit.text):
		settings.server_url = network.server_url
		server_edit.text = settings.server_url
		settings.save_to_disk()
		status_label.text = "Serveradresse gespeichert."


func _recover_profile() -> void:
	if name_edit.text.strip_edges().is_empty() or recovery_edit.text.strip_edges().is_empty():
		_on_api_failed("recover_profile", "Spielername und Wiederherstellungscode fehlen")
		return
	if network.configure(server_edit.text):
		network.recover_profile(name_edit.text, recovery_edit.text)


func _audio_slider(label_text: String, bus_name: String, value: float) -> Control:
	var row := HBoxContainer.new()
	var label := Label.new()
	label.text = label_text
	label.custom_minimum_size.x = 72
	row.add_child(label)
	var slider := HSlider.new()
	slider.min_value = -40.0
	slider.max_value = 6.0
	slider.step = 1.0
	slider.value = value
	slider.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	slider.value_changed.connect(func(db: float) -> void:
		var bus_index := AudioServer.get_bus_index(bus_name)
		if bus_index >= 0:
			AudioServer.set_bus_volume_db(bus_index, db)
		if bus_name == "Master": settings.master_db = db
		elif bus_name == "Music": settings.music_db = db
		elif bus_name == "Voice": settings.voice_db = db
		settings.save_to_disk()
	)
	row.add_child(slider)
	return row


func _apply_audio_settings() -> void:
	for entry in [["Master", settings.master_db], ["Music", settings.music_db], ["Voice", settings.voice_db]]:
		var bus_index := AudioServer.get_bus_index(str(entry[0]))
		if bus_index >= 0:
			AudioServer.set_bus_volume_db(bus_index, float(entry[1]))


func _build_game_panel() -> Control:
	var column := VBoxContainer.new()
	column.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	column.add_theme_constant_override("separation", 8)

	var header := HBoxContainer.new()
	header.add_theme_constant_override("separation", 14)
	column.add_child(header)
	var lobby_button := UIFactory.button("LOBBY")
	lobby_button.icon = UIFactory.texture("res://assets/ui/campaign.svg")
	lobby_button.pressed.connect(func() -> void:
		_show_gameplay(false)
		_show_submenu("lobby")
	)
	header.add_child(lobby_button)
	country_icon = TextureRect.new()
	country_icon.custom_minimum_size = Vector2(46, 46)
	country_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	country_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	header.add_child(country_icon)
	scenario_label = UIFactory.heading("Warte auf Kampagne", 22)
	scenario_label.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	header.add_child(scenario_label)
	enemy_label = Label.new()
	enemy_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_RIGHT
	enemy_label.add_theme_color_override("font_color", Color("d58d80"))
	header.add_child(enemy_label)
	enemy_icon = TextureRect.new()
	enemy_icon.custom_minimum_size = Vector2(46, 46)
	enemy_icon.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	enemy_icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
	header.add_child(enemy_icon)

	var phase_bar := HBoxContainer.new()
	phase_bar.alignment = BoxContainer.ALIGNMENT_CENTER
	phase_bar.add_theme_constant_override("separation", 18)
	column.add_child(phase_bar)
	for phase in ["attack", "defense", "magic", "utility"]:
		var label := Label.new()
		label.text = PHASE_NAMES[phase]
		label.add_theme_color_override("font_color", Color("5e6a70"))
		phase_labels[phase] = label
		phase_bar.add_child(label)
	phase_label = Label.new()
	phase_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	phase_bar.add_child(phase_label)

	world_view = ScenarioStage.new()
	world_view.size_flags_vertical = Control.SIZE_EXPAND_FILL
	column.add_child(world_view)
	dice_view = DiceRoller3D.new()
	column.add_child(dice_view)

	var lower := HBoxContainer.new()
	lower.custom_minimum_size = Vector2(0, 190)
	lower.add_theme_constant_override("separation", 10)
	column.add_child(lower)

	partner_panel = PanelContainer.new()
	partner_panel.custom_minimum_size = Vector2(155, 0)
	partner_panel.add_theme_stylebox_override("panel", UIFactory.panel_style(Color("1c292f")))
	partner_stats = Label.new()
	partner_stats.text = "PARTNER\nNoch nicht verbunden"
	partner_stats.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	partner_stats.vertical_alignment = VERTICAL_ALIGNMENT_CENTER
	partner_panel.add_child(partner_stats)
	lower.add_child(partner_panel)

	var actions_panel := PanelContainer.new()
	actions_panel.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	actions_panel.add_theme_stylebox_override("panel", UIFactory.panel_style(Color("171e22")))
	var action_margin := MarginContainer.new()
	action_margin.add_theme_constant_override("margin_left", 10)
	action_margin.add_theme_constant_override("margin_right", 10)
	action_margin.add_theme_constant_override("margin_top", 10)
	action_margin.add_theme_constant_override("margin_bottom", 10)
	actions_panel.add_child(action_margin)
	var action_column := VBoxContainer.new()
	action_margin.add_child(action_column)
	action_box = HFlowContainer.new()
	action_box.size_flags_vertical = Control.SIZE_EXPAND_FILL
	action_box.add_theme_constant_override("h_separation", 7)
	action_box.add_theme_constant_override("v_separation", 7)
	action_column.add_child(action_box)
	pass_button = UIFactory.button("Phase passen")
	pass_button.pressed.connect(func() -> void: network.pass_phase())
	action_column.add_child(pass_button)
	lower.add_child(actions_panel)

	var portrait_panel := PanelContainer.new()
	portrait_panel.custom_minimum_size = Vector2(230, 0)
	portrait_panel.add_theme_stylebox_override("panel", UIFactory.panel_style(Color("2a2220")))
	var portrait_column := VBoxContainer.new()
	portrait_column.alignment = BoxContainer.ALIGNMENT_CENTER
	portrait_panel.add_child(portrait_column)
	portrait_texture = TextureRect.new()
	portrait_texture.custom_minimum_size = Vector2(220, 118)
	portrait_texture.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
	portrait_texture.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	portrait_texture.texture = UIFactory.texture("res://assets/portraits/vanguard.png")
	portrait_column.add_child(portrait_texture)
	portrait_stats = Label.new()
	portrait_stats.text = "EIGENER SOELDNER\nNicht verbunden"
	portrait_stats.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	portrait_column.add_child(portrait_stats)
	lower.add_child(portrait_panel)
	return column


func _create_profile() -> void:
	if name_edit.text.strip_edges().is_empty():
		_on_api_failed("create_profile", "Bitte einen Spielernamen eingeben")
		return
	if network.configure(server_edit.text):
		settings.server_url = network.server_url
		network.create_profile(name_edit.text)


func _create_campaign() -> void:
	if network.device_token.is_empty():
		_pending_menu_after_profile = "campaign"
		_show_submenu("profile")
		return
	if not network.configure(settings.server_url):
		return
	if _game_mode().is_empty():
		_on_api_failed("create_campaign", "Bitte zuerst Singleplayer oder Multiplayer auswählen")
		return
	var campaign_seed: Variant = null
	if not seed_edit.text.strip_edges().is_empty():
		if not seed_edit.text.strip_edges().is_valid_int():
			_on_api_failed("create_campaign", "Der Seed muss eine ganze Zahl sein")
			return
		campaign_seed = int(seed_edit.text)
	status_label.text = "Kampagne wird erstellt …"
	campaign_start_button.disabled = true
	network.create_campaign(_weapon_id(), _magic_id(), _campaign_length(), _game_mode(), campaign_seed)


func _join_campaign() -> void:
	if invite_edit.text.strip_edges().is_empty():
		_on_api_failed("join_campaign", "Bitte einen Einladungscode eingeben")
		return
	if network.configure(settings.server_url):
		_selected_mode = "multiplayer"
		status_label.text = "Lobby wird gesucht …"
		network.join_campaign(invite_edit.text, _weapon_id(), _magic_id())


func _connect_campaign() -> void:
	if network.configure(settings.server_url):
		_sync_settings()
		status_label.text = "Verbindung wird aufgebaut …"
		network.connect_campaign()


func _continue_campaign() -> void:
	if campaign_select == null or campaign_select.selected < 0:
		return
	var value = campaign_select.get_item_metadata(campaign_select.selected)
	if not value is Dictionary or value.is_empty():
		_on_api_failed("continue", "Bitte eine Kampagne auswaehlen")
		return
	network.select_campaign(value)
	_set_selected_campaign_mode(str(value.get("game_mode", "multiplayer")))
	_auto_ready_after_connect = network.game_mode == "singleplayer"
	_sync_settings()
	_show_submenu("lobby")
	_connect_campaign()


func _select_campaign(index: int) -> void:
	if campaign_select == null or index < 0 or index >= campaign_select.item_count:
		return
	var value = campaign_select.get_item_metadata(index)
	if value is Dictionary and not value.is_empty():
		network.select_campaign(value)
		if invite_edit != null:
			invite_edit.text = network.invite_code
		_set_selected_campaign_mode(str(value.get("game_mode", "multiplayer")))
		_sync_settings()


func _set_selected_campaign_mode(selected_mode: String) -> void:
	_selected_mode = selected_mode
	if campaign_label != null:
		campaign_label.text = _campaign_text()


func _weapon_id() -> String:
	return ["dual_blades", "axe", "bow", "crossbow", "longsword"][weapon_select.selected]


func _game_mode() -> String:
	return _selected_mode


func _magic_id() -> String:
	return ["rune", "ember", "veil", "blood"][magic_select.selected]


func _campaign_length() -> String:
	return ["expedition", "fieldzug", "saga"][length_select.selected]


func _on_api_succeeded(action: String, payload: Variant) -> void:
	_append_log("[color=#9bbf8a]%s erfolgreich[/color]" % action)
	if (action == "create_profile" or action == "recover_profile") and payload is Dictionary:
		settings.display_name = str(payload.get("display_name", name_edit.text))
		var recovery_code := str(payload.get("recovery_code", ""))
		if not recovery_code.is_empty():
			_append_log("[color=#e2c27b]Wiederherstellungscode – jetzt sicher notieren:[/color] %s" % recovery_code)
			recovery_edit.text = ""
		_sync_settings()
		status_label.text = "Profil %s ist bereit." % settings.display_name
		var next_menu := _pending_menu_after_profile
		_pending_menu_after_profile = ""
		if next_menu == "campaign":
			_open_mode_menu(_selected_mode)
		elif next_menu == "continue":
			_open_continue_menu()
	elif action == "validate_profile" and payload is Dictionary:
		settings.display_name = str(payload.get("display_name", settings.display_name))
		name_edit.text = settings.display_name
		status_label.text = "Profil %s verbunden." % settings.display_name
	elif action == "list_campaigns" and payload is Array:
		_campaigns.clear()
		campaign_select.clear()
		var selected_index := 0
		for campaign_value in payload:
			var campaign: Dictionary = campaign_value
			_campaigns.append(campaign)
			var index := campaign_select.item_count
			campaign_select.add_item("%s · %s · Rang %s · %s" % [
				_mode_name(str(campaign.get("game_mode", "multiplayer"))),
				campaign.get("campaign_length", ""),
				campaign.get("world_tier", 1),
				campaign.get("status", ""),
			])
			campaign_select.set_item_metadata(index, campaign)
			if str(campaign.get("campaign_id", "")) == network.campaign_id:
				selected_index = index
		if _campaigns.is_empty():
			campaign_select.add_item("Keine gespeicherte Kampagne")
			campaign_select.set_item_metadata(0, {})
			campaign_select.set_item_disabled(0, true)
			continue_campaign_button.disabled = true
			status_label.text = "Noch keine Kampagne vorhanden."
		else:
			campaign_select.select(selected_index)
			_select_campaign(selected_index)
			continue_campaign_button.disabled = false
			status_label.text = "%s Kampagne(n) geladen." % _campaigns.size()
	elif action == "create_campaign" or action == "join_campaign":
		if payload is Dictionary:
			campaign_label.text = "%s · Kampagne %s\nEinladung: %s" % [
				_mode_name(str(payload.get("game_mode", "multiplayer"))),
				payload.get("campaign_id", ""),
				payload.get("invite_code", ""),
			]
			invite_edit.text = str(payload.get("invite_code", ""))
			_set_selected_campaign_mode(str(payload.get("game_mode", "multiplayer")))
			_sync_settings()
			campaign_start_button.disabled = false
			_auto_ready_after_connect = network.game_mode == "singleplayer"
			_show_submenu("lobby")
			_connect_campaign()


func _on_api_failed(action: String, message: String) -> void:
	_append_log("[color=#cf7068]%s: %s[/color]" % [action, message])
	status_label.text = message
	if campaign_start_button != null:
		campaign_start_button.disabled = false
	if action == "validate_profile":
		settings.clear_session()
		network.profile_id = ""
		network.device_token = ""
		network.campaign_id = ""
		network.invite_code = ""
		status_label.text = "Gespeichertes Profil ist nicht mehr gueltig"


func _on_socket_event(payload: Dictionary) -> void:
	var message_type := str(payload.get("type", ""))
	if message_type == "error":
		_on_api_failed("server", str(payload.get("message", "Unbekannter Fehler")))
		return
	if message_type == "game_started" or message_type == "state":
		var state = payload.get("state", {})
		if state is Dictionary:
			_presentation_queue.append({"kind": message_type, "state": state, "events": payload.get("events", [])})
			_drain_presentation_queue()
	elif message_type == "lobby":
		_on_lobby_changed(payload)


func _on_connection_changed(connected: bool) -> void:
	status_label.text = (
		("Verbunden · Solo-Kampagne" if network.game_mode == "singleplayer" else "Verbunden · warte auf Partner")
		if connected else "Nicht verbunden"
	)
	if ready_button != null:
		ready_button.disabled = not connected or network.campaign_status == "completed"
	if not connected:
		_show_gameplay(false)
	elif network.game_mode == "multiplayer":
		_show_submenu("lobby")


func _on_lobby_changed(payload: Dictionary) -> void:
	var lines: Array[String] = []
	for value in payload.get("players", []):
		var player: Dictionary = value
		lines.append("%s · %s · %s" % [
			player.get("display_name", "Spieler"),
			"verbunden" if player.get("connected", false) else "offline",
			"bereit" if player.get("ready", false) else "wartet",
		])
	var mode := str(payload.get("game_mode", network.game_mode))
	lobby_label.text = "%s\n%s" % [_mode_name(mode), "\n".join(lines)]
	ready_button.disabled = (
		network.campaign_status == "completed"
		or (not bool(payload.get("can_ready", false)) and not network.local_ready)
	)
	if mode == "singleplayer" and _auto_ready_after_connect and bool(payload.get("can_ready", false)) and not network.local_ready:
		status_label.text = "Singleplayer wird gestartet …"
		network.send_ready(true)


func _on_ready_changed(value: bool) -> void:
	ready_button.text = "Bereitschaft zurücknehmen" if value else "Bereit"


func _drain_presentation_queue() -> void:
	if _presenting:
		return
	_presenting = true
	while not _presentation_queue.is_empty():
		var packet: Dictionary = _presentation_queue.pop_front()
		var incoming: Dictionary = packet.get("state", {})
		current_state = incoming
		_render_state()
		_set_interaction_enabled(false)
		await _play_authoritative_cinematic(incoming)
		for event_value in packet.get("events", []):
			if event_value is Dictionary:
				await _present_event(event_value)
		current_state = incoming
		_render_state()
		_set_interaction_enabled(true)
	_presenting = false


func _present_event(event: Dictionary) -> void:
	game_audio.play_event(event)
	voice_director.play_event(event, current_state, network.profile_id, cinematic.is_playing())
	world_view.play_event_vfx(event)
	var event_type := str(event.get("type", ""))
	if event_type == "dice_rolled":
		dice_view.roll_to(event.get("values", []), str(event.get("purpose", "hit")))
		await dice_view.roll_sequence_finished
		return
	if event_type == "rollback":
		await cinematic.play_id("rollback", current_state.get("scenario", {}))
	else:
		var delay: float = float({
			"card_played": 0.42, "enemy_damaged": 0.32, "player_damaged": 0.32,
			"enemy_defeated": 1.25, "enemy_spawned": 0.75, "enemy_attack_resolved": 0.52,
			"boss_phase_changed": 0.82, "scenario_completed": 1.0,
		}.get(event_type, 0.10))
		await get_tree().create_timer(delay).timeout


func _play_authoritative_cinematic(state: Dictionary) -> void:
	var cinematic_state := _as_dictionary(state.get("cinematics", {}))
	var active := _as_dictionary(cinematic_state.get("active", {}))
	var cinematic_id := str(active.get("cinematic_id", ""))
	if not cinematic_id.is_empty() and not cinematic.is_playing():
		await cinematic.play_authoritative(cinematic_id, state.get("scenario", {}))


func _set_interaction_enabled(enabled: bool) -> void:
	if enabled:
		return
	if pass_button != null:
		pass_button.disabled = true
	if action_box != null:
		for child in action_box.get_children():
			if child is BaseButton:
				(child as BaseButton).disabled = true


func _render_state() -> void:
	_show_gameplay(true)
	world_view.set_game_state(current_state)
	game_audio.set_context(current_state)
	var scenario: Dictionary = current_state.get("scenario", {})
	scenario_label.text = "%s · %s" % [scenario.get("country", "Welt"), scenario.get("title", "Szenario")]
	var objective_state: Dictionary = current_state.get("scenario_objective", {})
	var objective: Dictionary = objective_state.get("objective", {})
	if not objective.is_empty():
		scenario_label.text += "\nZiel: %s/%s · %s" % [objective.get("current", 0), objective.get("maximum", 0), objective_state.get("status", "active")]
	var weather_effect: Dictionary = current_state.get("weather_effect", {})
	if not weather_effect.is_empty():
		scenario_label.tooltip_text = "%s: %s" % [weather_effect.get("weather", "Wetter"), weather_effect.get("text", "")]
	country_icon.texture = UIFactory.texture(str(scenario.get("art", "")))
	var enemy: Dictionary = current_state.get("enemy", {})
	var boss_value = current_state.get("boss_contract", {})
	var boss: Dictionary = boss_value if boss_value is Dictionary else {}
	if boss.is_empty():
		enemy_label.text = "%s  %s/%s LP  ·  Rüstung %s  ·  %s verbleibend" % [
			enemy.get("name", "Gegner"), enemy.get("hp", 0), enemy.get("max_hp", 0), enemy.get("armor", 0),
			int(current_state.get("enemy_queue", []).size()),
		]
	else:
		enemy_label.text = "%s · Eidkraft %s/%s · Bedrohung %s" % [
			str(boss.get("stage", "")).to_upper(), boss.get("oath_power", 0),
			boss.get("oath_power_required", 12), boss.get("threat", 0),
		]
	enemy_icon.texture = UIFactory.texture(str(enemy.get("art", "")))
	var phase := str(current_state.get("phase", "attack"))
	phase_label.text = "Runde %s" % current_state.get("round_number", 1)
	for phase_id in phase_labels:
		var label: Label = phase_labels[phase_id]
		label.add_theme_color_override("font_color", Color("e2c27b") if phase_id == phase else Color("5e6a70"))

	var players: Dictionary = current_state.get("players", {})
	var me: Dictionary = players.get(network.profile_id, {})
	var partner: Dictionary = {}
	for player_id in players:
		if player_id != network.profile_id:
			partner = players[player_id]
			break
	portrait_texture.texture = UIFactory.texture({
		"dual_blades": "res://assets/portraits/duelist.png",
		"axe": "res://assets/portraits/vanguard.png",
		"bow": "res://assets/portraits/pathfinder.png",
		"crossbow": "res://assets/portraits/arbalist.png",
		"longsword": "res://assets/portraits/swordmaster.png",
	}.get(str(me.get("weapon", "")), "res://assets/portraits/vanguard.png"))
	portrait_stats.text = "%s\n%s/%s LP  ·  %s AP\n%s + %s" % [
		settings.display_name if not settings.display_name.is_empty() else "EIGENER SOELDNER",
		me.get("hp", 0), me.get("max_hp", 0), me.get("action_points", 0),
		_weapon_name(str(me.get("weapon", ""))), _magic_name(str(me.get("magic", ""))),
	]
	var solo := _is_singleplayer()
	partner_panel.visible = not solo
	if not solo:
		partner_stats.text = "PARTNER\n%s/%s LP\n%s AP" % [
			partner.get("hp", 0), partner.get("max_hp", 0), partner.get("action_points", 0)
		]
	_rebuild_actions(me, phase)


func _show_gameplay(enabled: bool) -> void:
	if connection_screen == null or game_screen == null:
		return
	connection_screen.visible = not enabled
	game_screen.visible = enabled


func _rebuild_actions(me: Dictionary, phase: String) -> void:
	for child in action_box.get_children():
		child.queue_free()
	var cinematic_state: Dictionary = current_state.get("cinematics", {})
	if bool(cinematic_state.get("gameplay_blocked", false)):
		_add_action_button("Warte auf Cinematic-Bestätigung" if _is_singleplayer() else "Warte auf beide Cinematic-Bestätigungen", Callable(), true)
		pass_button.disabled = true
		return

	var postgame_value = current_state.get("postgame", {})
	var postgame: Dictionary = postgame_value if postgame_value is Dictionary else {}
	if not postgame.is_empty():
		_build_postgame_actions(postgame)
		return

	if bool(current_state.get("awaiting_scenario_choice", false)):
		_add_equipment_menu(me)
		for scenario_value in current_state.get("available_scenarios", []):
			var option: Dictionary = scenario_value
			_add_action_button("%s\n%s" % [option.get("title", "Pfad"), option.get("kind", "")], network.choose_scenario.bind(str(option.get("id", ""))))
		pass_button.disabled = true
		pass_button.text = "Pfad wählen" if _is_singleplayer() else "Pfad gemeinsam wählen"
		return

	var combat := _as_dictionary(current_state.get("combat", {}))
	var cooperation := _as_dictionary(combat.get("cooperation", {}))
	if not cooperation.is_empty():
		if str(cooperation.get("actor", "")) != network.profile_id:
			_add_action_button("Kooperation bestätigen", network.confirm_cooperation.bind(true))
			_add_action_button("Ablehnen", network.confirm_cooperation.bind(false))
		else:
			_add_action_button("Warte auf Partnerbestätigung", Callable(), true)
		pass_button.disabled = true
		return
	var reaction := _as_dictionary(combat.get("reaction_window", {}))
	if not reaction.is_empty():
		var responded: Array = reaction.get("responded", [])
		if network.profile_id in responded:
			_add_action_button("Reaktion bestätigt – warte auf Partner", Callable(), true)
		else:
			_add_action_button("Keine Reaktion", network.react.bind("", []))
			var reaction_definitions: Dictionary = current_state.get("card_definitions", {})
			for card_id in me.get("hand", []):
				var card: Dictionary = reaction_definitions.get(card_id, {})
				if str(card.get("kind", "")) == "reaction":
					_add_action_button("Reaktion: %s" % card.get("name", card_id), _play_reaction.bind(str(card_id), card))
		pass_button.disabled = true
		return

	if bool(current_state.get("final_oath_available", false)):
		_add_action_button("DER LETZTE EID · 5 AP", network.commit_final_oath, int(me.get("action_points", 0)) < 5)
		pass_button.disabled = true
		return

	var pending_loot: Array = current_state.get("pending_loot", [])
	if not pending_loot.is_empty():
		var loot_definitions: Dictionary = current_state.get("item_definitions", {})
		var loot_claims: Dictionary = current_state.get("loot_claims", {})
		var already_claimed: bool = network.profile_id in loot_claims
		if already_claimed:
			_add_equipment_menu(me)
		for item_id in pending_loot:
			var item: Dictionary = loot_definitions.get(item_id, {})
			var button := _add_action_button("%s\n%s" % [item.get("name", item_id), str(item.get("rarity", "")).to_upper()], network.claim_loot.bind(str(item_id)), already_claimed)
			button.icon = UIFactory.texture(str(item.get("art", "")))
			button.expand_icon = true
			button.tooltip_text = _item_tooltip(item)
		pass_button.disabled = true
		pass_button.text = ("Beute übernommen" if _is_singleplayer() else "Warte auf Partner") if already_claimed else "Beute wählen"
		return

	var card_definitions: Dictionary = current_state.get("card_definitions", {})
	var active := str(current_state.get("active_player", "")) == network.profile_id
	var objective_state: Dictionary = current_state.get("scenario_objective", {})
	var objective: Dictionary = objective_state.get("objective", {})
	if active and str(objective.get("kind", "")) == "prepare_hunt" and int(objective.get("current", 0)) < 1 and phase == "utility":
		_add_action_button("Fährte vorbereiten · 1 AP", network.perform_scenario_action.bind("prepare_hunt"), int(me.get("action_points", 0)) < 1)
	for card_id in me.get("hand", []):
		var card: Dictionary = card_definitions.get(card_id, {})
		var cost := int(card.get("action_point_cost", 0))
		var button := _add_action_button("%s  [%s AP]" % [card.get("name", card_id), cost], _play_card.bind(str(card_id), card))
		button.icon = UIFactory.texture(str(card.get("art", "")))
		button.expand_icon = true
		button.tooltip_text = str(card.get("text", ""))
		button.disabled = not active or str(card.get("phase", "")) != phase or int(me.get("action_points", 0)) < cost
	pass_button.disabled = not active
	pass_button.text = "%s passen" % PHASE_NAMES.get(phase, "Phase")
	pass_button.icon = UIFactory.texture("res://assets/ui/%s.svg" % phase)


func _build_postgame_actions(postgame: Dictionary) -> void:
	pass_button.disabled = true
	var postgame_phase := str(postgame.get("phase", ""))
	if postgame_phase == "ending_vote":
		for choice in ["seal", "destroy", "bind", "dominate"]:
			_add_action_button({"seal":"Versiegeln", "destroy":"Vernichten", "bind":"Binden", "dominate":"Beherrschen"}[choice], network.submit_ending.bind(choice))
	elif postgame_phase == "legacy_selection":
		var legacy_definitions: Dictionary = current_state.get("item_definitions", {})
		for item_id in postgame.get("legacy_options", []):
			var item: Dictionary = legacy_definitions.get(item_id, {})
			_add_action_button("Vermächtnis: %s" % item.get("name", item_id), network.select_legacy.bind(str(item_id)))
	elif postgame_phase == "new_game_plus":
		_add_action_button("New Game+ · Weltrang %s" % postgame.get("next_world_tier", 2), network.confirm_new_game_plus)
	else:
		_add_action_button("Kampagne abgeschlossen", Callable(), true)


func _play_card(card_id: String, card: Dictionary) -> void:
	var targets: Array[String] = []
	var enemy_targets: Array = current_state.get("combat", {}).get("targets", [])
	var area_cards := ["tausend_schnitte", "sturm_des_henkers", "pfeilregen", "sonnenhagel", "bolzenhagel", "salve", "feuersturm", "mondlose_nacht", "purpurflut"]
	var effects_text := JSON.stringify(card.get("effects", []))
	if not enemy_targets.is_empty() and ("dice_attack" in effects_text or "dice_magic_damage" in effects_text or "armor_break" in effects_text or "enemy_status" in effects_text or "set_trap" in effects_text):
		var maximum := 3 if card_id in area_cards else 1
		for target_value in enemy_targets.slice(0, maximum):
			var target: Dictionary = target_value
			targets.append(str(target.get("id", "")))
	network.play_card(card_id, "", targets)


func _play_reaction(card_id: String, card: Dictionary) -> void:
	var targets: Array[String] = []
	var enemy_targets: Array = current_state.get("combat", {}).get("targets", [])
	if not enemy_targets.is_empty() and "enemy" in JSON.stringify(card.get("effects", [])):
		var target: Dictionary = enemy_targets[0]
		targets.append(str(target.get("id", "")))
	network.react(card_id, targets)


func _add_action_button(text: String, callback: Callable, disabled: bool = false) -> Button:
	var button := UIFactory.button(text)
	button.custom_minimum_size = Vector2(160, 46)
	button.disabled = disabled
	if callback.is_valid():
		button.pressed.connect(game_audio.play_ui_click)
		button.pressed.connect(callback)
	action_box.add_child(button)
	return button


func _add_equipment_menu(me: Dictionary) -> void:
	var inventory: Array = me.get("inventory", [])
	if inventory.is_empty():
		return
	var equipment_definitions: Dictionary = current_state.get("item_definitions", {})
	var equipped: Dictionary = me.get("equipment", {})
	var menu := MenuButton.new()
	menu.text = "Ausrüstung"
	menu.icon = UIFactory.texture("res://assets/ui/armor.svg")
	menu.custom_minimum_size = Vector2(170, 46)
	var item_ids: Array[String] = []
	for item_id_value in inventory:
		var item_id := str(item_id_value)
		var item: Dictionary = equipment_definitions.get(item_id, {})
		var is_equipped := item_id in equipped.values()
		var label := "%s%s · %s" % ["✓ " if is_equipped else "", item.get("name", item_id), item.get("slot", "")]
		menu.get_popup().add_item(label)
		item_ids.append(item_id)
	menu.get_popup().id_pressed.connect(func(index: int) -> void:
		if index >= 0 and index < item_ids.size():
			game_audio.play_ui_click()
			network.equip_item(item_ids[index])
	)
	action_box.add_child(menu)


func _item_tooltip(item: Dictionary) -> String:
	var bonus_parts: Array[String] = []
	for key in item.get("bonuses", {}):
		bonus_parts.append("%s %+d" % [str(key).replace("_", " "), int(item.get("bonuses", {})[key])])
	var bonus_text := ", ".join(bonus_parts)
	return "%s\n%s%s" % [item.get("description", ""), "Boni: " if not bonus_text.is_empty() else "", bonus_text]


func _sync_settings() -> void:
	settings.server_url = network.server_url
	settings.profile_id = network.profile_id
	settings.device_token = network.device_token
	settings.campaign_id = network.campaign_id
	settings.invite_code = network.invite_code
	settings.save_to_disk()
	campaign_label.text = _campaign_text()


func _campaign_text() -> String:
	if settings.campaign_id.is_empty():
		return "Noch keine Kampagne"
	return "%s · Kampagne %s\nEinladung: %s" % [
		_mode_name(network.game_mode), settings.campaign_id, settings.invite_code
	]


func _mode_name(value: String) -> String:
	return "Singleplayer" if value == "singleplayer" else "Multiplayer"


func _as_dictionary(value: Variant) -> Dictionary:
	return value if value is Dictionary else {}


func _is_singleplayer() -> bool:
	return str(current_state.get("game_mode", network.game_mode)) == "singleplayer"


func _weapon_name(value: String) -> String:
	return {"dual_blades":"Zwillingsklingen","axe":"Axt","bow":"Langbogen","crossbow":"Armbrust","longsword":"Langschwert"}.get(value, value)


func _magic_name(value: String) -> String:
	return {"rune":"Runenmagie","ember":"Glutmagie","veil":"Schleiermagie","blood":"Blutmagie"}.get(value, value)


func _append_log(message: String) -> void:
	log_view.append_text(message + "\n")
