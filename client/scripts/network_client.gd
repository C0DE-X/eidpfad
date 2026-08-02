class_name NetworkClient
extends Node

signal api_succeeded(action: String, payload: Variant)
signal api_failed(action: String, message: String)
signal socket_event(payload: Dictionary)
signal connection_changed(connected: bool)
signal lobby_changed(payload: Dictionary)
signal ready_changed(ready: bool)
signal campaign_status_changed(status: String)

const PROTOCOL_VERSION := 2

var server_url := "http://127.0.0.1:8080"
var profile_id := ""
var device_token := ""
var campaign_id := ""
var invite_code := ""
var campaign_status := ""
var game_mode := ""
var local_ready := false

var _http: HTTPRequest
var _socket := WebSocketPeer.new()
var _pending_action := ""
var _last_socket_state := WebSocketPeer.STATE_CLOSED
var _ready_request_pending := false
var _requested_game_mode := ""


func _ready() -> void:
	_http = HTTPRequest.new()
	_http.timeout = 15.0
	add_child(_http)
	_http.request_completed.connect(_on_request_completed)
	set_process(true)


func _process(_delta: float) -> void:
	var before := _socket.get_ready_state()
	if before != WebSocketPeer.STATE_CLOSED:
		_socket.poll()
	var state := _socket.get_ready_state()
	if state != _last_socket_state:
		_last_socket_state = state
		if state == WebSocketPeer.STATE_OPEN:
			connection_changed.emit(true)
		elif state == WebSocketPeer.STATE_CLOSED:
			_ready_request_pending = false
			_set_local_ready(false)
			connection_changed.emit(false)
	if state == WebSocketPeer.STATE_OPEN:
		while _socket.get_available_packet_count() > 0:
			var text := _socket.get_packet().get_string_from_utf8()
			var parsed = JSON.parse_string(text)
			if parsed is Dictionary:
				_track_socket_event(parsed)
				socket_event.emit(parsed)


func configure(url: String) -> bool:
	var normalized := url.strip_edges().trim_suffix("/")
	if not normalized.begins_with("http://") and not normalized.begins_with("https://"):
		api_failed.emit("configure", "Die Serveradresse muss mit http:// oder https:// beginnen")
		return false
	var host := _url_host(normalized)
	if host.is_empty() or "@" in normalized.get_slice("://", 1).get_slice("/", 0):
		api_failed.emit("configure", "Die Serveradresse enthaelt keinen gueltigen Host")
		return false
	if normalized.begins_with("http://") and not _is_loopback_host(host):
		api_failed.emit("configure", "Ausserhalb von localhost ist HTTPS erforderlich")
		return false
	server_url = normalized
	return true


func restore_session(
	url: String,
	stored_profile_id: String,
	stored_token: String,
	stored_campaign_id: String,
	stored_invite_code: String,
) -> void:
	if not configure(url):
		# Never copy a bearer token into a session whose transport validation
		# failed; otherwise an automatic profile check could leak it.
		profile_id = ""
		device_token = ""
		campaign_id = ""
		invite_code = ""
		return
	profile_id = stored_profile_id
	device_token = stored_token
	campaign_id = stored_campaign_id
	invite_code = stored_invite_code


func create_profile(display_name: String) -> void:
	_request("create_profile", "/api/v1/profiles", HTTPClient.METHOD_POST, {"display_name": display_name}, false)


func recover_profile(display_name: String, recovery_code: String) -> void:
	_request(
		"recover_profile",
		"/api/v1/profiles/recover",
		HTTPClient.METHOD_POST,
		{"display_name": display_name, "recovery_code": recovery_code},
		false,
	)


func validate_profile() -> void:
	_request("validate_profile", "/api/v1/profiles/me", HTTPClient.METHOD_GET, null, true)


func rotate_device_token() -> void:
	disconnect_campaign()
	_request("rotate_device_token", "/api/v1/profiles/me/token", HTTPClient.METHOD_POST, null, true)


func rotate_recovery_code() -> void:
	_request("rotate_recovery_code", "/api/v1/profiles/me/recovery-code", HTTPClient.METHOD_POST, null, true)


func list_campaigns() -> void:
	_request("list_campaigns", "/api/v1/campaigns", HTTPClient.METHOD_GET, null, true)


func create_campaign(weapon: String, magic: String, campaign_length: String, selected_game_mode: String, campaign_seed: Variant = null) -> void:
	_requested_game_mode = selected_game_mode
	var body := {"weapon": weapon, "magic": magic, "campaign_length": campaign_length, "game_mode": selected_game_mode}
	if campaign_seed != null:
		body["seed"] = campaign_seed
	_request("create_campaign", "/api/v1/campaigns", HTTPClient.METHOD_POST, body, true)


func join_campaign(code: String, weapon: String, magic: String) -> void:
	_requested_game_mode = "multiplayer"
	_request(
		"join_campaign",
		"/api/v1/campaigns/join",
		HTTPClient.METHOD_POST,
		{"invite_code": code.to_upper(), "weapon": weapon, "magic": magic},
		true,
	)


func connect_campaign() -> void:
	if campaign_id.is_empty() or device_token.is_empty():
		api_failed.emit("connect", "Profil oder Kampagne fehlt")
		return
	if _socket.get_ready_state() != WebSocketPeer.STATE_CLOSED:
		api_failed.emit("connect", "Die Verbindung wird bereits aufgebaut")
		return
	_socket = WebSocketPeer.new()
	_socket.handshake_headers = PackedStringArray(["Authorization: Bearer %s" % device_token])
	_socket.heartbeat_interval = 15.0
	_socket.max_queued_packets = 256
	var ws_url := ""
	if server_url.begins_with("https://"):
		ws_url = "wss://" + server_url.trim_prefix("https://")
	else:
		ws_url = "ws://" + server_url.trim_prefix("http://")
	ws_url += "/ws/campaigns/%s" % campaign_id
	_last_socket_state = WebSocketPeer.STATE_CONNECTING
	var error := _socket.connect_to_url(ws_url)
	if error != OK:
		_last_socket_state = WebSocketPeer.STATE_CLOSED
		api_failed.emit("connect", "WebSocket konnte nicht gestartet werden: %s" % error_string(error))


func disconnect_campaign() -> void:
	if _socket.get_ready_state() == WebSocketPeer.STATE_OPEN:
		_socket.close(1000, "Client closed")


func send_ready(value: bool) -> void:
	# Ready is an explicit, acknowledged lobby choice. Suppress duplicate local
	# requests; the server independently guarantees idempotence as well.
	if _ready_request_pending or local_ready == value:
		return
	if _send({"type": "ready", "protocol_version": PROTOCOL_VERSION, "ready": value}):
		_ready_request_pending = true


func play_card(card_id: String, target_id: String = "", target_ids: Array[String] = []) -> void:
	var selected: Array[String] = target_ids.duplicate()
	if selected.is_empty() and not target_id.is_empty():
		selected.append(target_id)
	_send({
		"type": "play_card",
		"protocol_version": PROTOCOL_VERSION,
		"card_id": card_id,
		"target_ids": selected,
	})


func pass_phase() -> void:
	_send({"type": "pass_phase", "protocol_version": PROTOCOL_VERSION})


func claim_loot(item_id: String) -> void:
	_send({"type": "claim_loot", "protocol_version": PROTOCOL_VERSION, "item_id": item_id})


func react(card_id: String = "", target_ids: Array[String] = []) -> void:
	var selected_card_id: Variant = null
	if not card_id.is_empty():
		selected_card_id = card_id
	_send({
		"type": "react",
		"protocol_version": PROTOCOL_VERSION,
		"card_id": selected_card_id,
		"target_ids": target_ids,
	})


func confirm_cooperation(accepted: bool) -> void:
	_send({"type": "confirm_cooperation", "protocol_version": PROTOCOL_VERSION, "accepted": accepted})


func choose_scenario(scenario_id: String) -> void:
	_send({"type": "choose_scenario", "protocol_version": PROTOCOL_VERSION, "scenario_id": scenario_id})


func equip_item(item_id: String) -> void:
	_send({"type": "equip_item", "protocol_version": PROTOCOL_VERSION, "item_id": item_id})


func perform_scenario_action(action: String) -> void:
	_send({"type": "scenario_action", "protocol_version": PROTOCOL_VERSION, "action": action})


func commit_final_oath() -> void:
	_send({"type": "commit_final_oath", "protocol_version": PROTOCOL_VERSION})


func submit_ending(choice: String) -> void:
	_send({"type": "ending_choice", "protocol_version": PROTOCOL_VERSION, "choice": choice})


func select_legacy(item_id: String) -> void:
	_send({"type": "select_legacy", "protocol_version": PROTOCOL_VERSION, "item_id": item_id})


func confirm_new_game_plus() -> void:
	_send({"type": "confirm_new_game_plus", "protocol_version": PROTOCOL_VERSION})


func cinematic_ack(cinematic_id: String, skipped: bool) -> void:
	_send({
		"type": "cinematic_ack",
		"protocol_version": PROTOCOL_VERSION,
		"cinematic_id": cinematic_id,
		"skipped": skipped,
	})


func select_campaign(campaign: Dictionary) -> void:
	campaign_id = str(campaign.get("campaign_id", ""))
	invite_code = str(campaign.get("invite_code", ""))
	campaign_status = str(campaign.get("status", ""))
	game_mode = str(campaign.get("game_mode", ""))


func clear_campaign_selection() -> void:
	disconnect_campaign()
	campaign_id = ""
	invite_code = ""
	campaign_status = ""
	game_mode = ""


func _request(
	action: String,
	path: String,
	method: HTTPClient.Method,
	body: Variant,
	authenticated: bool,
) -> void:
	if _pending_action != "":
		api_failed.emit(action, "Es laeuft bereits eine Anfrage")
		return
	var headers := PackedStringArray(["Content-Type: application/json", "Accept: application/json"])
	if authenticated:
		if device_token.is_empty():
			api_failed.emit(action, "Es ist kein lokales Profil gespeichert")
			return
		headers.append("Authorization: Bearer %s" % device_token)
	_pending_action = action
	var body_text := "" if body == null else JSON.stringify(body)
	var error := _http.request(server_url + path, headers, method, body_text)
	if error != OK:
		_pending_action = ""
		api_failed.emit(action, "HTTP-Anfrage konnte nicht gestartet werden: %s" % error_string(error))


func _send(payload: Dictionary) -> bool:
	if _socket.get_ready_state() != WebSocketPeer.STATE_OPEN:
		api_failed.emit("socket", "Keine aktive Kampagnenverbindung")
		return false
	var error := _socket.send_text(JSON.stringify(payload))
	if error != OK:
		api_failed.emit("socket", "Nachricht konnte nicht gesendet werden: %s" % error_string(error))
		return false
	return true


func _on_request_completed(
	result: int,
	response_code: int,
	_headers: PackedStringArray,
	body: PackedByteArray,
) -> void:
	var action := _pending_action
	_pending_action = ""
	var parsed = JSON.parse_string(body.get_string_from_utf8())
	var payload: Variant = parsed if parsed != null else {}
	if result != HTTPRequest.RESULT_SUCCESS:
		_requested_game_mode = ""
		api_failed.emit(action, "Der Server ist nicht erreichbar (Netzwerkfehler %s)" % result)
		return
	if response_code < 200 or response_code >= 300:
		_requested_game_mode = ""
		var detail := "HTTP %s" % response_code
		if payload is Dictionary:
			detail = str(payload.get("detail", detail))
		api_failed.emit(action, detail)
		return

	if payload is Dictionary:
		if action == "create_campaign" or action == "join_campaign":
			var returned_mode := str(payload.get("game_mode", ""))
			if returned_mode != _requested_game_mode:
				var requested_mode := _requested_game_mode
				_requested_game_mode = ""
				api_failed.emit(
					action,
					"Servermodus %s stimmt nicht mit der Auswahl %s überein; Kampagne nicht übernommen" % [returned_mode, requested_mode],
				)
				return
		if action == "create_profile" or action == "recover_profile":
			profile_id = str(payload.get("profile_id", ""))
			device_token = str(payload.get("device_token", ""))
			if action == "recover_profile":
				campaign_id = ""
				invite_code = ""
		elif action == "rotate_device_token":
			device_token = str(payload.get("device_token", ""))
		elif action == "create_campaign" or action == "join_campaign":
			campaign_id = str(payload.get("campaign_id", ""))
			invite_code = str(payload.get("invite_code", ""))
			campaign_status = str(payload.get("status", ""))
			game_mode = str(payload.get("game_mode", ""))
			_requested_game_mode = ""
	api_succeeded.emit(action, payload)


func _track_socket_event(payload: Dictionary) -> void:
	var new_status := str(payload.get("campaign_status", campaign_status))
	if new_status != campaign_status:
		campaign_status = new_status
		campaign_status_changed.emit(campaign_status)
	if str(payload.get("type", "")) == "lobby":
		game_mode = str(payload.get("game_mode", game_mode))
		_ready_request_pending = false
		var ready_members: Array = payload.get("ready", [])
		_set_local_ready(profile_id in ready_members)
		lobby_changed.emit(payload)


func _set_local_ready(value: bool) -> void:
	if local_ready == value:
		return
	local_ready = value
	ready_changed.emit(local_ready)


func _url_host(url: String) -> String:
	var authority := url.get_slice("://", 1).get_slice("/", 0)
	if authority.begins_with("["):
		var closing := authority.find("]")
		if closing <= 1:
			return ""
		return authority.substr(1, closing - 1).to_lower()
	return authority.get_slice(":", 0).to_lower()


func _is_loopback_host(host: String) -> bool:
	var normalized := host.trim_suffix(".").to_lower()
	if normalized == "localhost" or normalized.ends_with(".localhost") or normalized == "::1":
		return true
	if normalized.begins_with("127."):
		for part in normalized.split("."):
			if not part.is_valid_int() or int(part) < 0 or int(part) > 255:
				return false
		return normalized.split(".").size() == 4
	return false
