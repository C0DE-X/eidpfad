extends SceneTree

const STEP_TIMEOUT_SECONDS := 30.0

var _main: Control


func _initialize() -> void:
	call_deferred("_run")


func _run() -> void:
	var server_url := _argument_value("--server-url", "http://127.0.0.1:8080")
	var packed_scene := load("res://scenes/main.tscn") as PackedScene
	if packed_scene == null:
		_fail("Hauptszene konnte nicht geladen werden")
		return
	_main = packed_scene.instantiate() as Control
	root.add_child(_main)
	await process_frame
	await process_frame
	if _main.game_screen.visible or _main.submenu_panel.visible:
		_fail("Hauptmenue startet nicht in der geschlossenen Ausgangsansicht")
		return
	var solo_button := _find_button(_main, "EINZELSPIELER")
	if solo_button == null:
		_fail("Einzelspieler-Schaltflaeche fehlt im Hauptmenue")
		return
	solo_button.emit_signal("pressed")
	if not _main.submenu_panel.visible or not _main.submenu_views["profile"].visible:
		_fail("Einzelspieler oeffnet ohne Profil nicht das Profil-Untermenue")
		return

	_main.server_edit.text = server_url
	_main.options_server_edit.text = server_url
	_main.settings.server_url = server_url
	_main.name_edit.text = "Smoke-%s" % Time.get_ticks_msec()
	var profile_button := _find_button(_main, "Profil anlegen und weiter")
	if profile_button == null:
		_fail("Profil-Schaltflaeche fehlt")
		return
	profile_button.emit_signal("pressed")
	if not await _wait_until(func() -> bool: return not _main.network.device_token.is_empty(), "Profilanlage"):
		return

	if not _main.submenu_views["campaign"].visible:
		_fail("Profilanlage fuehrt nicht in das Einzelspieler-Untermenue")
		return
	_main.weapon_select.select(4)
	_main.magic_select.select(0)
	_main.length_select.select(0)
	_main.seed_edit.text = "20260804"
	_main.campaign_start_button.emit_signal("pressed")
	if not await _wait_until(
		func() -> bool: return not _main.current_state.is_empty() and _main.game_screen.visible,
		"Singleplayer-Start",
	):
		return
	var campaign_id: String = str(_main.network.campaign_id)
	if campaign_id.is_empty() or _main.network.game_mode != "singleplayer":
		_fail("Singleplayer-Kampagne wurde nicht korrekt uebernommen")
		return
	await _finish_presentation()

	_main.network.disconnect_campaign()
	if not await _wait_until(
		func() -> bool: return _main.network._socket.get_ready_state() == WebSocketPeer.STATE_CLOSED,
		"Trennen der Kampagne",
	):
		return
	_main.current_state = {}
	_main._presentation_queue.clear()
	_main._show_gameplay(false)
	var continue_button := _find_button(_main, "FORTSETZEN")
	if continue_button == null:
		_fail("Fortsetzen-Schaltflaeche fehlt im Hauptmenue")
		return
	continue_button.emit_signal("pressed")
	if not await _wait_until(
		func() -> bool: return not _main.continue_campaign_button.disabled,
		"Laden der Kampagnenliste",
	):
		return

	var resume_index := -1
	for index in _main.campaign_select.item_count:
		var campaign = _main.campaign_select.get_item_metadata(index)
		if campaign is Dictionary and str(campaign.get("campaign_id", "")) == campaign_id:
			resume_index = index
			break
	if resume_index < 0:
		_fail("Erstellte Kampagne fehlt im Fortsetzen-Menue")
		return
	_main.campaign_select.select(resume_index)
	_main._select_campaign(resume_index)
	_main.continue_campaign_button.emit_signal("pressed")
	if not await _wait_until(
		func() -> bool: return not _main.current_state.is_empty() and _main.game_screen.visible,
		"Fortsetzen der Singleplayer-Kampagne",
	):
		return
	if _main.network.campaign_id != campaign_id:
		_fail("Fortsetzen hat eine andere Kampagne geladen")
		return

	await _finish_presentation()
	_main.network.disconnect_campaign()
	await _wait_until(
		func() -> bool: return _main.network._socket.get_ready_state() == WebSocketPeer.STATE_CLOSED,
		"Abschlusstrennung",
	)
	print("CLIENT_MENU_FLOW_OK campaign_id=%s" % campaign_id)
	quit(0)


func _finish_presentation() -> void:
	if _main.cinematic != null and _main.cinematic.is_playing():
		_main.cinematic._request_skip()
	await _wait_until(func() -> bool: return not _main._presenting, "Cinematic-Abschluss")


func _wait_until(predicate: Callable, label: String) -> bool:
	var deadline := Time.get_ticks_msec() + int(STEP_TIMEOUT_SECONDS * 1000.0)
	while Time.get_ticks_msec() < deadline:
		if bool(predicate.call()):
			return true
		await create_timer(0.05).timeout
	_fail("Zeitueberschreitung: %s" % label)
	return false


func _argument_value(name: String, fallback: String) -> String:
	var arguments := OS.get_cmdline_user_args()
	for index in arguments.size():
		if arguments[index] == name and index + 1 < arguments.size():
			return arguments[index + 1]
	return fallback


func _find_button(node: Node, caption: String) -> Button:
	if node is Button and node.text == caption:
		return node as Button
	for child in node.get_children():
		var result := _find_button(child, caption)
		if result != null:
			return result
	return null


func _fail(message: String) -> void:
	push_error("CLIENT_MENU_FLOW_FAILED: %s" % message)
	quit(1)
