extends Node2D

const STATE_IDLE := "IDLE"
const STATE_IN_FLIGHT := "IN_FLIGHT"
const STATE_UNLOADING := "UNLOADING"
const STATE_RETURNING := "RETURNING"
const STATE_MAINTENANCE := "MAINTENANCE"
const ROUTE_OUTBOUND := 0
const ROUTE_RETURN := 1

var config := {
	"pallet_interval_sec": 6.0,
	"pallet_expiration_sec": 120.0,
	"loading_sec": 0.0,
	"flight_sec": 30.0,
	"unload_sec": 2.0,
	"return_sec": 30.0,
	"maintenance_sec": 10.0,
	"total_duration_sec": 300.0,
	"aircraft_count": 2,
	"time_scale": 5.0
}

@export var use_mqtt_events: bool = true
@export var mqtt_host: String = "127.0.0.1"
@export var mqtt_port: int = 1883
@export var mqtt_topic: String = "sa/airfreight/events"
@export var mqtt_playback_rate: float = 1.0

var mqtt_client: MqttClient
var external_pallet_deadlines: Dictionary = {}
var external_pallet_generation_times: Dictionary = {}
var use_local_simulation: bool = false
var _mqtt_anchor_sim_time: float = 0.0
var _mqtt_anchor_usec: int = 0
var _mqtt_last_message_usec: int = 0
var _mqtt_stream_stalled: bool = false

var sim_time_sec := 0.0
var next_generation_sec := 0.0
var pallet_counter := 11
var queue: Array = []
var aircraft: Array = []
var events: Array[String] = []
var latencies: Array[float] = []
var delivered_list: Array[String] = []

var generated := 0
var expired := 0
var delivered := 0
var sim_finished := false
@export var curve_height: float = 170.0
@export var origin_marker: Marker2D
@export var dest_marker: Marker2D

var origin_pos := Vector2(400, 650)
var dest_pos := Vector2(1500, 500)
var warehouse_pos := Vector2(280, 640)
var queue_world_pos := Vector2(390, 600)
var plane_texture: Texture2D = null
var pallet_texture: Texture2D = null
var facility_texture: Texture2D = null
var destination_texture: Texture2D = null
var scene_rect := Rect2()
var aircraft_sprites: Array[Sprite2D] = []
var facility_sprite: Sprite2D = null
var destination_sprite: Sprite2D = null
var chroma_shader: Shader = null
var route_line_outbound: Line2D
var route_line_return: Line2D
var outbound_path: Path2D
var return_path: Path2D
@export var outbound_lateral_offset := 178.0
@export var return_lateral_offset := -204.0
@export var outbound_height_offset := 138.0
@export var return_height_scale := 0.34
@export var use_manual_route_markers := true
@export var stage_anchor_margin := Vector2(56, 52)
@export var auto_fit_background_to_stage := false
@export var background_bleed_px := 1.0
var queue_cards: Dictionary = {}
var queue_progress: Dictionary = {}
var queue_countdowns: Dictionary = {}
var aircraft_state_labels: Array[Label] = []
var aircraft_cargo_labels: Array[Label] = []
var aircraft_world_tag_labels: Array[Label] = []
var aircraft_popup_labels: Array[Label] = []
var top_sim_time_label: Label
var top_avg_latency_label: Label
var visual_loading_delay_sec := 0.5
var scene_background: TextureRect

var title_label: Label
var subtitle_label: Label
var stats_values := {}
var queue_list: VBoxContainer
var delivered_list_ui: VBoxContainer
var event_log_label: RichTextLabel
var system_info_label: RichTextLabel
var queue_world_text_label: Label
var destination_hub_text_label: Label

@onready var ui_title_block: PanelContainer = %TitleBlock
@onready var ui_stats_strip: PanelContainer = %StatsStrip
@onready var ui_dashboard_row: HBoxContainer = %DashboardRow
@onready var ui_top_bar: HBoxContainer = get_node_or_null("../../UILayer/UIRoot/SafeArea/RootVBox/TopBar") as HBoxContainer
@onready var ui_origin_column: PanelContainer = %OriginColumn
@onready var ui_destination_column: PanelContainer = %DestinationColumn
@onready var ui_bottom_panel: HBoxContainer = get_node_or_null("../../UILayer/UIRoot/SafeArea/RootVBox/BottomPanel") as HBoxContainer
@onready var ui_event_log_panel: PanelContainer = %EventLogPanel
@onready var ui_system_info_panel: PanelContainer = %SystemInfoPanel
@onready var ui_card_generated: PanelContainer = %CardGenerated
@onready var ui_card_queued: PanelContainer = %CardQueued
@onready var ui_card_delivered: PanelContainer = %CardDelivered
@onready var ui_card_expired: PanelContainer = %CardExpired
@onready var ui_fleet_coordinator_panel: PanelContainer = %FleetCoordinatorPanel
@onready var ui_aircraft1_card: PanelContainer = %Aircraft1Card
@onready var ui_aircraft2_card: PanelContainer = %Aircraft2Card
@onready var ui_title_label: Label = %TitleLabel
@onready var ui_subtitle_label: Label = %SubtitleLabel
@onready var ui_generated_value: Label = %LabelGeneratedValue
@onready var ui_queued_value: Label = %LabelQueuedValue
@onready var ui_delivered_value: Label = %LabelDeliveredValue
@onready var ui_expired_value: Label = %LabelExpiredValue
@onready var ui_generated_icon: TextureRect = get_node_or_null("../../UILayer/UIRoot/SafeArea/RootVBox/TopBar/StatsStrip/DashboardRow/CardGenerated/CardGeneratedVBox/GeneratedTitleRow/GeneratedIcon") as TextureRect
@onready var ui_queued_icon: TextureRect = get_node_or_null("../../UILayer/UIRoot/SafeArea/RootVBox/TopBar/StatsStrip/DashboardRow/CardQueued/CardQueuedVBox/QueuedTitleRow/QueuedIcon") as TextureRect
@onready var ui_delivered_icon: TextureRect = get_node_or_null("../../UILayer/UIRoot/SafeArea/RootVBox/TopBar/StatsStrip/DashboardRow/CardDelivered/CardDeliveredVBox/DeliveredTitleRow/DeliveredIcon") as TextureRect
@onready var ui_expired_icon: TextureRect = get_node_or_null("../../UILayer/UIRoot/SafeArea/RootVBox/TopBar/StatsStrip/DashboardRow/CardExpired/CardExpiredVBox/ExpiredTitleRow/ExpiredIcon") as TextureRect
@onready var ui_aircraft1_state_label: Label = %Aircraft1StateLabel
@onready var ui_aircraft1_cargo_label: Label = %Aircraft1CargoLabel
@onready var ui_aircraft2_state_label: Label = %Aircraft2StateLabel
@onready var ui_aircraft2_cargo_label: Label = %Aircraft2CargoLabel
@onready var ui_queue_list: VBoxContainer = %QueueList
@onready var ui_delivered_list: VBoxContainer = %DeliveredList
@onready var ui_queue_world_panel: PanelContainer = %QueueWorldPanel
@onready var ui_queue_world_text: Label = %QueueWorldText
@onready var ui_destination_hub_panel: PanelContainer = %DestinationHubPanel
@onready var ui_destination_hub_text: Label = %DestinationHubText
@onready var ui_event_log_text: RichTextLabel = %EventLogText
@onready var ui_system_info_text: RichTextLabel = %SystemInfoText
@onready var ui_origin_title: Label = get_node_or_null("../../UILayer/UIRoot/SafeArea/RootVBox/CenterArea/OriginColumn/OriginVBox/OriginTitle") as Label
@onready var ui_queue_world_title: Label = get_node_or_null("../../UILayer/UIRoot/SafeArea/RootVBox/CenterArea/OriginColumn/OriginVBox/QueueWorldPanel/QueueWorldVBox/QueueWorldTitle") as Label
@onready var ui_fleet_coordinator_title: Label = get_node_or_null("../../UILayer/UIRoot/SafeArea/RootVBox/CenterArea/OriginColumn/OriginVBox/FleetCoordinatorPanel/FleetCoordinatorVBox/FleetCoordinatorTitle") as Label
@onready var ui_delivered_title: Label = get_node_or_null("../../UILayer/UIRoot/SafeArea/RootVBox/CenterArea/DestinationColumn/DestinationVBox/DeliveredTitle") as Label
@onready var ui_destination_hub_title: Label = get_node_or_null("../../UILayer/UIRoot/SafeArea/RootVBox/CenterArea/DestinationColumn/DestinationVBox/DestinationHubPanel/DestinationHubVBox/DestinationHubTitle") as Label
@onready var ui_event_log_title: Label = get_node_or_null("../../UILayer/UIRoot/SafeArea/RootVBox/BottomPanel/EventLogPanel/EventLogVBox/EventLogTitle") as Label
@onready var ui_system_info_title: Label = get_node_or_null("../../UILayer/UIRoot/SafeArea/RootVBox/BottomPanel/SystemInfoPanel/SystemInfoVBox/SystemInfoTitle") as Label
@onready var ui_stage_viewport: Control = %StageViewport
@onready var flight_camera: Camera2D = %FlightCamera
@onready var scene_origin_marker: Marker2D = %OriginMarker
@onready var scene_warehouse_marker: Marker2D = get_node_or_null("WarehouseMarker") as Marker2D
@onready var scene_queue_marker: Marker2D = %QueueMarker
@onready var scene_dest_marker: Marker2D = %DestMarker
@onready var scene_outbound_path: Path2D = %OutboundPath
@onready var scene_return_path: Path2D = %ReturnPath
var scene_outbound_control_marker: Marker2D
var scene_return_control_marker: Marker2D


func _ready() -> void:
	DisplayServer.window_set_mode(DisplayServer.WINDOW_MODE_FULLSCREEN)
	var root_node := get_tree().current_scene
	if root_node != null:
		scene_background = root_node.get_node_or_null("Background") as TextureRect
	if scene_background == null:
		scene_background = get_node_or_null("../../Background") as TextureRect
	plane_texture = load_texture_safe("res://design/aircraft.png")
	if plane_texture == null:
		plane_texture = load_texture_safe("res://design/plane_icon.png")
	pallet_texture = load_texture_safe("res://design/pallet.png")
	if pallet_texture == null:
		pallet_texture = load_texture_safe("res://design/pallet_icon.png")
	facility_texture = load_texture_safe("res://design/facility.png")
	destination_texture = load_texture_safe("res://design/destination.png")
	if origin_marker == null:
		origin_marker = scene_origin_marker
	if dest_marker == null:
		dest_marker = scene_dest_marker
	scene_outbound_control_marker = resolve_route_marker("OutboundControlMarker")
	scene_return_control_marker = resolve_route_marker("ReturnControlMarker")
	chroma_shader = load("res://shaders/chroma_key.gdshader")
	update_layout()
	update_stage_anchors()
	setup_route_lines()
	setup_paths()
	setup_world_landmarks()
	setup_ui_theme()
	setup_ui_content()
	for i in range(config.aircraft_count):
		aircraft.append({
			"name": "Aircraft-%d" % (i + 1),
			"state": STATE_IDLE,
			"cargo": null,
			"position": origin_pos + Vector2(0, i * 32),
			"phase_start": 0.0,
			"state_until": 0.0,
			"flight_tween": null,
			"active_follow": null,
			"out_follow": null,
			"ret_follow": null
		})
		var craft_sprite := Sprite2D.new()
		craft_sprite.name = "Aircraft%d" % (i + 1)
		craft_sprite.texture = plane_texture
		craft_sprite.centered = true
		fit_sprite_to_width(craft_sprite, 88.0)
		craft_sprite.z_index = 5
		add_child(craft_sprite)
		apply_chroma_material(craft_sprite, 0.20, 0.05)

		var tag_panel := PanelContainer.new()
		tag_panel.name = "AircraftTagPanel"
		tag_panel.position = Vector2(-88, -64)
		tag_panel.mouse_filter = Control.MOUSE_FILTER_IGNORE
		tag_panel.add_theme_stylebox_override("panel", make_world_tag_style())
		craft_sprite.add_child(tag_panel)
		var tag_label := Label.new()
		tag_label.name = "AircraftTagLabel"
		tag_label.add_theme_color_override("font_color", Color("e2e8f0"))
		tag_label.add_theme_font_size_override("font_size", 11)
		tag_panel.add_child(tag_label)
		aircraft_world_tag_labels.append(tag_label)
		var popup := Label.new()
		popup.name = "LoadPopup"
		popup.visible = false
		popup.position = Vector2(-44, -84)
		popup.add_theme_color_override("font_color", Color("fde68a"))
		popup.add_theme_font_size_override("font_size", 12)
		craft_sprite.add_child(popup)
		aircraft_popup_labels.append(popup)

		var out_follow := PathFollow2D.new()
		out_follow.rotates = false
		outbound_path.add_child(out_follow)
		aircraft[i]["out_follow"] = out_follow
		var ret_follow := PathFollow2D.new()
		ret_follow.rotates = false
		return_path.add_child(ret_follow)
		aircraft[i]["ret_follow"] = ret_follow

		aircraft_sprites.append(craft_sprite)
	sync_aircraft_sprites()
	use_local_simulation = not use_mqtt_events
	if use_mqtt_events:
		setup_mqtt_client()
		append_event("Waiting for MQTT simulation events on %s..." % mqtt_topic)
	else:
		append_event("Simulation started.")


func _process(delta: float) -> void:
	if mqtt_client != null:
		mqtt_client.poll()

	update_layout()
	update_stage_anchors()
	if flight_camera != null:
		flight_camera.position = scene_rect.position + scene_rect.size * 0.5

	if not use_local_simulation:
		advance_mqtt_display_clock()
		sync_aircraft_sprites()
		update_aircraft_world_tags()
		update_fleet_coordinator_ui()
		update_ui_texts()
		queue_redraw()
		return

	if sim_finished:
		update_ui_texts()
		queue_redraw()
		return

	sim_time_sec += delta * config.time_scale

	if sim_time_sec <= config.total_duration_sec:
		while sim_time_sec >= next_generation_sec:
			var pallet := {
				"id": "P-%03d" % pallet_counter,
				"generation_time": next_generation_sec,
				"deadline_time": next_generation_sec + config.pallet_expiration_sec
			}
			pallet_counter += 1
			queue.push_back(pallet)
			add_queue_card(pallet)
			generated += 1
			append_event("pallet_generated: %s deadline=%.1fs" % [pallet.id, pallet.deadline_time])
			next_generation_sec += config.pallet_interval_sec

	expire_due()
	assign_available()
	update_aircraft()
	sync_aircraft_sprites()

	if sim_time_sec >= config.total_duration_sec:
		sim_finished = true
		append_event("Simulation finished at t=%.1fs" % sim_time_sec)

	update_ui_texts()
	queue_redraw()


func expire_due() -> void:
	while queue.size() > 0 and sim_time_sec >= queue[0].deadline_time:
		var p: Dictionary = queue.pop_front()
		remove_queue_card(p.id)
		expired += 1
		append_event("pallet_expired: %s" % p.id)


func assign_available() -> void:
	for idx in range(aircraft.size()):
		var craft: Dictionary = aircraft[idx]
		if craft.state != STATE_IDLE or craft.cargo != null:
			continue
		if queue.is_empty():
			return
		var p: Dictionary = queue.pop_front()
		remove_queue_card(p.id)
		craft.cargo = p
		craft.state = STATE_IN_FLIGHT
		craft.phase_start = sim_time_sec
		craft.state_until = sim_time_sec + config.flight_sec
		craft.position = origin_pos
		start_path_flight(idx, true, config.flight_sec, visual_loading_delay_sec)
		show_loading_popup(idx, p.id)
		append_event("%s assigned %s, departing." % [craft.name, p.id])


func update_aircraft() -> void:
	for idx in range(aircraft.size()):
		var craft: Dictionary = aircraft[idx]
		match craft.state:
			STATE_IDLE:
				craft.position = origin_pos
			STATE_IN_FLIGHT:
				if sim_time_sec >= craft.state_until:
					stop_flight_tween(idx)
					craft.position = dest_pos
					craft.state = STATE_UNLOADING
					craft.phase_start = sim_time_sec
					craft.state_until = sim_time_sec + config.unload_sec
					append_event("%s arrived destination, unloading %s." % [craft.name, craft.cargo.id])
			STATE_UNLOADING:
				craft.position = dest_pos
				if sim_time_sec >= craft.state_until:
					if craft.cargo != null:
						delivered += 1
						var latency: float = sim_time_sec - craft.cargo.generation_time
						latencies.push_back(latency)
						delivered_list.push_front("%s @ %.1fs" % [craft.cargo.id, sim_time_sec])
						if delivered_list.size() > 8:
							delivered_list.resize(8)
						append_event("delivery_completed: %s latency=%.1fs" % [craft.cargo.id, latency])
					craft.state = STATE_RETURNING
					craft.phase_start = sim_time_sec
					craft.state_until = sim_time_sec + config.return_sec
					start_path_flight(idx, false, config.return_sec, 0.0)
					append_event("%s unload complete, returning." % craft.name)
			STATE_RETURNING:
				if sim_time_sec >= craft.state_until:
					stop_flight_tween(idx)
					craft.position = origin_pos
					craft.cargo = null
					craft.state = STATE_MAINTENANCE
					craft.phase_start = sim_time_sec
					craft.state_until = sim_time_sec + config.maintenance_sec
					append_event("%s at origin, maintenance." % craft.name)
			STATE_MAINTENANCE:
				craft.position = origin_pos
				if sim_time_sec >= craft.state_until:
					craft.state = STATE_IDLE
					append_event("%s maintenance complete, idle." % craft.name)


func append_event(evt: String) -> void:
	events.push_back("%6.1fs | %s" % [sim_time_sec, evt])
	if events.size() > 30:
		events.pop_front()


func setup_mqtt_client() -> void:
	mqtt_client = MqttClient.new()
	mqtt_client.host = mqtt_host
	mqtt_client.port = mqtt_port
	mqtt_client.client_id = "godot_airfreight_%d" % randi()
	mqtt_client.message_received.connect(_on_mqtt_message)
	mqtt_client.connection_changed.connect(_on_mqtt_connection_changed)
	add_child(mqtt_client)
	mqtt_client.subscribe(mqtt_topic)
	mqtt_client.connect_to_broker()


func _on_mqtt_connection_changed(connected: bool) -> void:
	if connected:
		append_event("MQTT connected. Listening on %s" % mqtt_topic)
	else:
		append_event("MQTT disconnected from %s:%d" % [mqtt_host, mqtt_port])
	update_ui_texts()


func _on_mqtt_message(_topic: String, payload: PackedByteArray) -> void:
	_mqtt_last_message_usec = Time.get_ticks_usec()
	_mqtt_stream_stalled = false
	var text := payload.get_string_from_utf8()
	var parsed: Variant = JSON.parse_string(text)
	if parsed == null or not parsed is Dictionary:
		push_warning("Ignoring invalid MQTT payload: %s" % text)
		return
	apply_external_event(parsed as Dictionary)


func apply_external_event(evt: Dictionary) -> void:
	sync_mqtt_time_anchor(evt)
	var event_name := str(evt.get("event", ""))
	var payload: Dictionary = evt.get("payload", {}) as Dictionary
	match event_name:
		"pallet_generated":
			_handle_pallet_generated(payload)
		"pallet_queued":
			_handle_pallet_queued(payload)
		"pallet_expired":
			_handle_pallet_expired(payload)
		"assignment_created":
			_handle_assignment_created(payload)
		"depart":
			_handle_depart(payload)
		"pallet_delivered":
			_handle_pallet_delivered(payload)
		"return":
			_handle_return(payload)
		"maintenance_start":
			_handle_maintenance_start(payload)
		"maintenance_end":
			_handle_maintenance_end(payload)
		_:
			return
	sync_aircraft_sprites()
	append_event("%s/%s %s" % [evt.get("entity", ""), event_name, str(payload)])
	update_ui_texts()
	queue_redraw()


func sync_mqtt_time_anchor(evt: Dictionary) -> void:
	var anchor_time: Variant = evt.get("time", evt.get("_sim_time", null))
	if anchor_time == null:
		return
	_mqtt_anchor_sim_time = float(anchor_time)
	_mqtt_anchor_usec = Time.get_ticks_usec()
	sim_time_sec = _mqtt_anchor_sim_time


func advance_mqtt_display_clock() -> void:
	if _mqtt_anchor_usec <= 0:
		return
	if _mqtt_last_message_usec > 0:
		var stall_wall_sec := (Time.get_ticks_usec() - _mqtt_last_message_usec) / 1_000_000.0
		if stall_wall_sec > 2.0:
			_mqtt_stream_stalled = true
			sim_time_sec = _mqtt_anchor_sim_time
			return
	_mqtt_stream_stalled = false
	var elapsed_sec := (Time.get_ticks_usec() - _mqtt_anchor_usec) / 1_000_000.0
	sim_time_sec = _mqtt_anchor_sim_time + elapsed_sec * maxf(0.01, mqtt_playback_rate)


func visual_playback_scale() -> float:
	if use_local_simulation:
		return maxf(0.01, float(config.time_scale))
	return maxf(0.01, mqtt_playback_rate)


func pallet_label(pallet_id: int) -> String:
	return "P-%03d" % pallet_id


func aircraft_index(aircraft_id: int) -> int:
	return maxi(0, aircraft_id - 1)


func _handle_pallet_generated(payload: Dictionary) -> void:
	var pallet_id := int(payload.get("pallet_id", 0))
	external_pallet_deadlines[pallet_id] = float(payload.get("expiration_time", sim_time_sec))
	external_pallet_generation_times[pallet_id] = sim_time_sec
	generated += 1


func pallet_expiration_window(pallet: Dictionary) -> float:
	return maxf(1.0, float(pallet.deadline_time) - float(pallet.generation_time))


func _handle_pallet_queued(payload: Dictionary) -> void:
	var pallet_id := int(payload.get("pallet_id", 0))
	var pallet := {
		"id": pallet_label(pallet_id),
		"generation_time": float(external_pallet_generation_times.get(pallet_id, sim_time_sec)),
		"deadline_time": float(external_pallet_deadlines.get(pallet_id, sim_time_sec + config.pallet_expiration_sec))
	}
	queue.push_back(pallet)
	add_queue_card(pallet)


func _handle_pallet_expired(payload: Dictionary) -> void:
	var pallet_id := int(payload.get("pallet_id", 0))
	var pallet_key := pallet_label(pallet_id)
	for i in range(queue.size()):
		if queue[i].id == pallet_key:
			queue.remove_at(i)
			break
	remove_queue_card(pallet_key)
	external_pallet_deadlines.erase(pallet_id)
	external_pallet_generation_times.erase(pallet_id)
	expired += 1


func _handle_assignment_created(payload: Dictionary) -> void:
	var pallet_id := int(payload.get("pallet_id", 0))
	var pallet_key := pallet_label(pallet_id)
	for i in range(queue.size()):
		if queue[i].id == pallet_key:
			queue.remove_at(i)
			break
	remove_queue_card(pallet_key)
	var idx := aircraft_index(int(payload.get("aircraft_id", 1)))
	if idx >= aircraft.size():
		return
	var craft: Dictionary = aircraft[idx]
	craft.cargo = {
		"id": pallet_key,
		"generation_time": sim_time_sec,
		"deadline_time": float(external_pallet_deadlines.get(pallet_id, sim_time_sec))
	}
	craft.state = STATE_IDLE
	craft.position = origin_pos
	show_loading_popup(idx, pallet_key)


func _handle_depart(payload: Dictionary) -> void:
	var idx := aircraft_index(int(payload.get("aircraft_id", 1)))
	if idx >= aircraft.size():
		return
	var craft: Dictionary = aircraft[idx]
	craft.state = STATE_IN_FLIGHT
	craft.phase_start = sim_time_sec
	craft.state_until = sim_time_sec + config.flight_sec
	craft.position = origin_pos
	start_path_flight(idx, true, config.flight_sec, visual_loading_delay_sec)


func _handle_pallet_delivered(payload: Dictionary) -> void:
	var idx := aircraft_index(int(payload.get("aircraft_id", 1)))
	if idx >= aircraft.size():
		return
	var craft: Dictionary = aircraft[idx]
	complete_path_flight(idx)
	craft.position = dest_pos
	delivered += 1
	var latency := float(payload.get("latency", 0.0))
	latencies.push_back(latency)
	delivered_list.push_front("%s @ %.1fs" % [pallet_label(int(payload.get("pallet_id", 0))), sim_time_sec])
	if delivered_list.size() > 8:
		delivered_list.resize(8)
	craft.state = STATE_RETURNING
	craft.phase_start = sim_time_sec
	craft.state_until = sim_time_sec + config.return_sec
	start_path_flight(idx, false, config.return_sec, 0.0)


func _handle_return(payload: Dictionary) -> void:
	var idx := aircraft_index(int(payload.get("aircraft_id", 1)))
	if idx >= aircraft.size():
		return
	var craft: Dictionary = aircraft[idx]
	complete_path_flight(idx)
	craft.position = origin_pos
	craft.state = STATE_RETURNING


func _handle_maintenance_start(payload: Dictionary) -> void:
	var idx := aircraft_index(int(payload.get("aircraft_id", 1)))
	if idx >= aircraft.size():
		return
	var craft: Dictionary = aircraft[idx]
	complete_path_flight(idx)
	craft.position = origin_pos
	craft.cargo = null
	craft.state = STATE_MAINTENANCE
	craft.phase_start = sim_time_sec
	craft.state_until = sim_time_sec + config.maintenance_sec


func _handle_maintenance_end(payload: Dictionary) -> void:
	var idx := aircraft_index(int(payload.get("aircraft_id", 1)))
	if idx >= aircraft.size():
		return
	var craft: Dictionary = aircraft[idx]
	craft.state = STATE_IDLE
	craft.position = origin_pos
	craft.cargo = null


func avg_latency() -> float:
	if latencies.is_empty():
		return 0.0
	var total := 0.0
	for x in latencies:
		total += x
	return total / float(latencies.size())


func utilization() -> float:
	if aircraft.is_empty():
		return 0.0
	var busy := 0
	for craft in aircraft:
		if craft.state != STATE_IDLE:
			busy += 1
	return 100.0 * float(busy) / float(aircraft.size())


func _draw() -> void:
	draw_status_ribbon()
	draw_aircraft()


func draw_aircraft() -> void:
	for craft in aircraft:
		var c := Color("d4e6f8")
		if craft.state == STATE_IN_FLIGHT:
			c = Color("96f7b3")
		elif craft.state == STATE_RETURNING:
			c = Color("9db8ff")
		elif craft.state == STATE_UNLOADING:
			c = Color("f7e39e")
		elif craft.state == STATE_MAINTENANCE:
			c = Color("d7a3ff")

		var p: Vector2 = craft.position
		draw_circle(p + Vector2(1, 6), 15, Color(0, 0, 0, 0.25))
		draw_cargo_marker(p + Vector2(0, 24), c)
		var status := "%s %s" % [craft.name, craft.state]
		if craft.cargo != null:
			status = "%s %s (%s)" % [craft.name, craft.state, craft.cargo.id]
		draw_string(ThemeDB.fallback_font, p + Vector2(-40, -14), status, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color.WHITE)


func draw_cargo_marker(marker_pos: Vector2, tint: Color) -> void:
	if pallet_texture != null:
		var icon_size := Vector2(12, 12)
		var rect := Rect2(marker_pos - icon_size * 0.5, icon_size)
		draw_texture_rect(pallet_texture, rect, false, tint)
		return
	draw_circle(marker_pos, 3.5, tint)




func draw_status_ribbon() -> void:
	var vp := get_viewport_rect().size
	var ribbon := Rect2(Vector2(vp.x * 0.28, 20), Vector2(vp.x * 0.44, 34))
	draw_rect(ribbon, Color(0.02, 0.05, 0.08, 0.72), true)
	draw_rect(ribbon, Color("7dd3fc"), false, 1.0)
	var busy := 0
	for craft in aircraft:
		if craft.state != STATE_IDLE:
			busy += 1
	var text := "SIM %.1fs   QUEUE %d   ACTIVE %d/%d   DELIVERED %d" % [sim_time_sec, queue.size(), busy, aircraft.size(), delivered]
	draw_string(ThemeDB.fallback_font, ribbon.position + Vector2(12, 22), text, HORIZONTAL_ALIGNMENT_LEFT, -1, 13, Color("e0f2fe"))


func draw_route_labels() -> void:
	var out_controls := route_controls(origin_pos, dest_pos, curve_height + outbound_height_offset, outbound_lateral_offset, ROUTE_OUTBOUND)
	var ret_controls := route_controls(dest_pos, origin_pos, curve_height * return_height_scale, return_lateral_offset, ROUTE_RETURN)
	var out_label_pos := (out_controls["mid"] as Vector2) + Vector2(-56, 34)
	var ret_label_pos := (ret_controls["mid"] as Vector2) + Vector2(-56, -42)
	draw_pill_label(out_label_pos, "OUTBOUND %.0fs" % config.flight_sec, Color(0.10, 0.26, 0.16, 0.80), Color("86efac"), Color("dcfce7"))
	draw_pill_label(ret_label_pos, "RETURN %.0fs" % config.return_sec, Color(0.08, 0.16, 0.28, 0.80), Color("93c5fd"), Color("dbeafe"))


func draw_pill_label(label_pos: Vector2, text: String, bg_color: Color, border_color: Color, text_color: Color) -> void:
	var width := maxf(92.0, float(text.length()) * 7.2 + 16.0)
	var rect := Rect2(label_pos, Vector2(width, 24))
	draw_rect(rect, bg_color, true)
	draw_rect(rect, border_color, false, 1.0)
	draw_string(ThemeDB.fallback_font, rect.position + Vector2(8, 16), text, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, text_color)


func draw_loading_visual(craft: Dictionary) -> void:
	var craft_pos: Vector2 = craft.position
	var elapsed := maxf(0.0, sim_time_sec - float(craft.phase_start))
	var ratio := clampf(elapsed / config.loading_sec, 0.0, 1.0)
	var steps := 5
	var loaded_steps := int(floor(ratio * steps))
	var label_text := "LOADING %d/%d" % [loaded_steps, steps]
	draw_string(ThemeDB.fallback_font, craft_pos + Vector2(-34, -30), label_text, HORIZONTAL_ALIGNMENT_LEFT, -1, 12, Color("fde68a"))

	var bar_rect := Rect2(craft_pos + Vector2(-36, -23), Vector2(72, 6))
	draw_rect(bar_rect, Color(0.08, 0.10, 0.15, 0.85), true)
	draw_rect(Rect2(bar_rect.position, Vector2(bar_rect.size.x * ratio, bar_rect.size.y)), Color("fbbf24"), true)
	draw_rect(bar_rect, Color("fef3c7"), false, 1.0)

	var move_phase := fmod(ratio * float(steps), 1.0)
	if loaded_steps < steps:
		var from_pos := queue_world_pos + Vector2(22, -8)
		var to_pos := craft_pos + Vector2(-22, 8)
		var moving := from_pos.lerp(to_pos, move_phase)
		draw_rect(Rect2(moving + Vector2(-5, -5), Vector2(10, 10)), Color("fcd34d"), true)
		draw_rect(Rect2(moving + Vector2(-5, -5), Vector2(10, 10)), Color("f59e0b"), false, 1.0)

	for i in range(loaded_steps):
		var loaded_pos := craft_pos + Vector2(-18 + i * 8, 10)
		draw_rect(Rect2(loaded_pos + Vector2(-3, -3), Vector2(6, 6)), Color("facc15"), true)
	draw_line(craft_pos + Vector2(-30, 14), craft_pos + Vector2(30, 14), Color("f59e0b"), 1.0)


func bezier_control_point(from: Vector2, to: Vector2, arc_height: float) -> Vector2:
	var mid_point := (from + to) / 2.0
	return mid_point + Vector2(0, -arc_height)


func route_control_point(from: Vector2, to: Vector2, arc_height: float, lateral_offset: float) -> Vector2:
	var control := bezier_control_point(from, to, arc_height)
	var direction := (to - from).normalized()
	var normal := Vector2(-direction.y, direction.x)
	return control + normal * lateral_offset


func route_controls(from: Vector2, to: Vector2, arc_height: float, lateral_offset: float, route_kind: int) -> Dictionary:
	var mid := route_control_point(from, to, arc_height, lateral_offset)
	if use_manual_route_markers:
		if route_kind == ROUTE_OUTBOUND and scene_outbound_control_marker != null:
			mid = scene_outbound_control_marker.global_position
		elif route_kind == ROUTE_RETURN and scene_return_control_marker != null:
			mid = scene_return_control_marker.global_position
	var direction := (to - from).normalized()
	var dist := maxf(1.0, from.distance_to(to))
	var pull := clampf(dist * 0.24, 90.0, 220.0)
	var c1 := from.lerp(mid, 0.56) + direction * pull * 0.35
	var c2 := to.lerp(mid, 0.56) - direction * pull * 0.35
	return {
		"mid": mid,
		"c1": c1,
		"c2": c2,
	}


func resolve_route_marker(marker_name: String) -> Marker2D:
	var direct := get_node_or_null(marker_name) as Marker2D
	if direct != null:
		return direct
	var nested := find_child(marker_name, true, false) as Marker2D
	return nested


func start_path_flight(idx: int, is_outbound: bool, duration: float, visual_delay: float) -> void:
	stop_flight_tween(idx)
	if idx >= 0 and idx < aircraft_sprites.size():
		aircraft_sprites[idx].flip_h = not is_outbound
	var follow: PathFollow2D = aircraft[idx]["out_follow"] if is_outbound else aircraft[idx]["ret_follow"]
	if follow == null:
		return
	follow.progress_ratio = 0.0
	aircraft[idx]["active_follow"] = follow
	var move_duration := maxf(0.05, duration - visual_delay)
	var real_delay := maxf(0.0, visual_delay / visual_playback_scale())
	var real_duration := maxf(0.01, move_duration / visual_playback_scale())
	var tween := create_tween()
	tween.set_trans(Tween.TRANS_LINEAR)
	tween.set_ease(Tween.EASE_IN_OUT)
	if real_delay > 0.0:
		tween.tween_interval(real_delay)
	tween.tween_property(follow, "progress_ratio", 1.0, real_duration)
	aircraft[idx]["flight_tween"] = tween


func stop_flight_tween(idx: int) -> void:
	if idx < 0 or idx >= aircraft.size():
		return
	var tw: Tween = aircraft[idx].get("flight_tween")
	if tw != null and tw.is_running():
		tw.kill()
	aircraft[idx]["flight_tween"] = null
	aircraft[idx]["active_follow"] = null


func complete_path_flight(idx: int) -> void:
	if idx < 0 or idx >= aircraft.size():
		return
	var follow: PathFollow2D = aircraft[idx].get("active_follow")
	if follow != null:
		follow.progress_ratio = 1.0
	stop_flight_tween(idx)


func show_loading_popup(idx: int, pallet_id: String) -> void:
	if idx < 0 or idx >= aircraft_popup_labels.size():
		return
	var popup: Label = aircraft_popup_labels[idx]
	if popup == null:
		return
	popup.text = "+ Pallet %s" % pallet_id
	popup.visible = true
	popup.modulate = Color(1, 1, 1, 1)
	popup.position = Vector2(-44, -84)
	var tw := create_tween()
	tw.set_trans(Tween.TRANS_SINE)
	tw.tween_property(popup, "position", Vector2(-44, -112), 0.45)
	tw.parallel().tween_property(popup, "modulate:a", 0.0, 0.45)
	tw.finished.connect(func() -> void:
		popup.visible = false
	)


func load_texture_safe(path: String) -> Texture2D:
	if not ResourceLoader.exists(path):
		return null
	var res := load(path)
	if res is Texture2D:
		return res as Texture2D
	return null


func apply_chroma_material(sprite: Sprite2D, similarity: float, smoothness: float) -> void:
	if sprite == null or chroma_shader == null:
		return
	var mat := ShaderMaterial.new()
	mat.shader = chroma_shader
	mat.set_shader_parameter("key_color", Color(0, 1, 0, 1))
	mat.set_shader_parameter("similarity", similarity)
	mat.set_shader_parameter("smoothness", smoothness)
	mat.set_shader_parameter("spill_strength", 1.35)
	mat.set_shader_parameter("alpha_cutoff", 0.04)
	sprite.material = mat


func fit_sprite_to_width(sprite: Sprite2D, target_width: float) -> void:
	if sprite == null or sprite.texture == null:
		return
	var tex_size := sprite.texture.get_size()
	if tex_size.x <= 0.0:
		return
	var s := target_width / tex_size.x
	sprite.scale = Vector2(s, s)


func update_layout() -> void:
	var vp := get_viewport_rect().size
	scene_rect = Rect2(Vector2.ZERO, vp)
	if ui_stage_viewport != null:
		scene_rect = ui_stage_viewport.get_global_rect()
	if auto_fit_background_to_stage:
		sync_background_to_stage()


func sync_background_to_stage() -> void:
	if scene_background == null:
		return
	var bleed := maxf(0.0, background_bleed_px)
	var left := floorf(scene_rect.position.x) - bleed
	var top := floorf(scene_rect.position.y) - bleed
	var right := ceilf(scene_rect.position.x + scene_rect.size.x) + bleed
	var bottom := ceilf(scene_rect.position.y + scene_rect.size.y) + bleed
	scene_background.set_anchors_preset(Control.PRESET_TOP_LEFT)
	scene_background.offset_left = left
	scene_background.offset_top = top
	scene_background.offset_right = right
	scene_background.offset_bottom = bottom


func update_stage_anchors() -> void:
	var stage := scene_rect.grow_individual(-stage_anchor_margin.x, -stage_anchor_margin.y, -stage_anchor_margin.x, -stage_anchor_margin.y)
	if stage.size.x <= 0.0 or stage.size.y <= 0.0:
		stage = scene_rect
	var origin_default := stage.position + Vector2(stage.size.x * 0.17, stage.size.y * 0.78)
	var dest_default := stage.position + Vector2(stage.size.x * 0.83, stage.size.y * 0.30)
	var warehouse_default := origin_default + Vector2(-118, -18)
	var queue_default := warehouse_default + Vector2(98, -74)
	origin_pos = clamp_point_to_rect(origin_marker.global_position if origin_marker != null else origin_default, stage)
	dest_pos = clamp_point_to_rect(dest_marker.global_position if dest_marker != null else dest_default, stage)
	warehouse_pos = clamp_point_to_rect(scene_warehouse_marker.global_position if scene_warehouse_marker != null else warehouse_default, stage)
	queue_world_pos = clamp_point_to_rect(scene_queue_marker.global_position if scene_queue_marker != null else queue_default, stage)

	for i in range(min(aircraft.size(), aircraft_sprites.size())):
		aircraft_sprites[i].position = aircraft[i].position
	sync_world_landmarks()
	update_route_lines()
	update_paths()


func sync_aircraft_sprites() -> void:
	for i in range(min(aircraft.size(), aircraft_sprites.size())):
		var craft: Dictionary = aircraft[i]
		var active_follow: PathFollow2D = craft.get("active_follow")
		if active_follow != null:
			aircraft_sprites[i].global_position = active_follow.global_position
			craft.position = active_follow.global_position
		else:
			aircraft_sprites[i].position = craft.position


func setup_world_landmarks() -> void:
	if facility_texture != null:
		facility_sprite = Sprite2D.new()
		facility_sprite.texture = facility_texture
		facility_sprite.centered = true
		facility_sprite.z_index = 2
		fit_sprite_to_width(facility_sprite, 210.0)
		apply_chroma_material(facility_sprite, 0.22, 0.06)
		add_child(facility_sprite)
	if destination_texture != null:
		destination_sprite = Sprite2D.new()
		destination_sprite.texture = destination_texture
		destination_sprite.centered = true
		destination_sprite.z_index = 2
		fit_sprite_to_width(destination_sprite, 240.0)
		apply_chroma_material(destination_sprite, 0.22, 0.06)
		add_child(destination_sprite)
	sync_world_landmarks()


func sync_world_landmarks() -> void:
	if facility_sprite != null:
		facility_sprite.position = warehouse_pos + Vector2(6, 22)
	if destination_sprite != null:
		destination_sprite.position = dest_pos + Vector2(0, 36)


func setup_route_lines() -> void:
	route_line_outbound = make_route_line(Color(0.29, 0.98, 0.72, 0.15), Color(0.29, 0.98, 0.72, 0.95))
	route_line_return = make_route_line(Color(0.37, 0.72, 1.0, 0.15), Color(0.37, 0.72, 1.0, 0.95))
	add_child(route_line_outbound)
	add_child(route_line_return)
	route_line_outbound.z_index = 3
	route_line_return.z_index = 3
	update_route_lines()


func setup_paths() -> void:
	outbound_path = scene_outbound_path
	return_path = scene_return_path
	update_paths()


func update_paths() -> void:
	if outbound_path != null:
		var out_controls := route_controls(origin_pos, dest_pos, curve_height + outbound_height_offset, outbound_lateral_offset, ROUTE_OUTBOUND)
		var curve1 := Curve2D.new()
		curve1.add_point(origin_pos, Vector2.ZERO, (out_controls["c1"] as Vector2) - origin_pos)
		curve1.add_point(dest_pos, (out_controls["c2"] as Vector2) - dest_pos, Vector2.ZERO)
		outbound_path.curve = curve1
	if return_path != null:
		var ret_controls := route_controls(dest_pos, origin_pos, curve_height * return_height_scale, return_lateral_offset, ROUTE_RETURN)
		var curve2 := Curve2D.new()
		curve2.add_point(dest_pos, Vector2.ZERO, (ret_controls["c1"] as Vector2) - dest_pos)
		curve2.add_point(origin_pos, (ret_controls["c2"] as Vector2) - origin_pos, Vector2.ZERO)
		return_path.curve = curve2


func make_route_line(start_color: Color, end_color: Color) -> Line2D:
	var line := Line2D.new()
	line.width = 4.4
	line.antialiased = true
	line.joint_mode = Line2D.LINE_JOINT_ROUND
	line.begin_cap_mode = Line2D.LINE_CAP_ROUND
	line.end_cap_mode = Line2D.LINE_CAP_ROUND
	var gradient := Gradient.new()
	gradient.offsets = PackedFloat32Array([0.0, 0.08, 0.50, 0.92, 1.0])
	gradient.colors = PackedColorArray([
		Color(start_color.r, start_color.g, start_color.b, 0.02),
		Color(start_color.r, start_color.g, start_color.b, start_color.a * 0.62),
		Color((start_color.r + end_color.r) * 0.5, (start_color.g + end_color.g) * 0.5, (start_color.b + end_color.b) * 0.5, 0.98),
		Color(end_color.r, end_color.g, end_color.b, end_color.a * 0.64),
		Color(end_color.r, end_color.g, end_color.b, 0.03),
	])
	line.gradient = gradient
	return line


func build_route_points(from: Vector2, to: Vector2, arc_height: float, lateral_offset: float = 0.0, route_kind: int = ROUTE_OUTBOUND) -> PackedVector2Array:
	var curve := Curve2D.new()
	var samples := 72
	var controls := route_controls(from, to, arc_height, lateral_offset, route_kind)
	var c1: Vector2 = controls["c1"]
	var c2: Vector2 = controls["c2"]
	for i in range(samples + 1):
		var t := float(i) / float(samples)
		curve.add_point(from.bezier_interpolate(c1, c2, to, t))
	return curve.get_baked_points()


func update_route_lines() -> void:
	if route_line_outbound != null:
		route_line_outbound.points = build_route_points(origin_pos, dest_pos, curve_height + outbound_height_offset, outbound_lateral_offset, ROUTE_OUTBOUND)
	if route_line_return != null:
		route_line_return.points = build_route_points(dest_pos, origin_pos, curve_height * return_height_scale, return_lateral_offset, ROUTE_RETURN)


func clamp_point_to_rect(point: Vector2, rect: Rect2) -> Vector2:
	return Vector2(
		clampf(point.x, rect.position.x, rect.end.x),
		clampf(point.y, rect.position.y, rect.end.y)
	)


func setup_ui_theme() -> void:
	for panel in [
		ui_title_block,
		ui_stats_strip,
		ui_origin_column,
		ui_destination_column,
		ui_event_log_panel,
		ui_system_info_panel,
	]:
		if panel != null:
			panel.add_theme_stylebox_override("panel", make_panel_style())

	for edge_panel in [
		ui_origin_column,
		ui_destination_column,
		ui_event_log_panel,
		ui_stats_strip,
	]:
		if edge_panel != null:
			var edge_style := make_panel_style()
			edge_style.shadow_size = 0
			edge_style.shadow_offset = Vector2.ZERO
			edge_panel.add_theme_stylebox_override("panel", edge_style)

	for pair in [
		{"node": ui_card_generated, "color": Color("3b82f6")},
		{"node": ui_card_queued, "color": Color("facc15")},
		{"node": ui_card_delivered, "color": Color("22c55e")},
		{"node": ui_card_expired, "color": Color("ef4444")},
	]:
		var card: PanelContainer = pair.node
		if card != null:
			var s := make_panel_style()
			s.border_color = pair.color
			s.set_border_width_all(2)
			card.add_theme_stylebox_override("panel", s)


func make_panel_style() -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.05, 0.08, 0.13, 0.88)
	style.border_color = Color(0.62, 0.79, 0.98, 0.92)
	style.set_border_width_all(2)
	style.shadow_color = Color(0, 0, 0, 0.35)
	style.shadow_size = 6
	style.shadow_offset = Vector2(0, 2)
	style.corner_radius_top_left = 8
	style.corner_radius_top_right = 8
	style.corner_radius_bottom_left = 8
	style.corner_radius_bottom_right = 8
	style.content_margin_left = 10
	style.content_margin_top = 8
	style.content_margin_right = 10
	style.content_margin_bottom = 8
	return style


func make_world_tag_style() -> StyleBoxFlat:
	var style := StyleBoxFlat.new()
	style.bg_color = Color(0.02, 0.03, 0.05, 0.78)
	style.border_color = Color(0.55, 0.70, 0.88, 0.75)
	style.set_border_width_all(1)
	style.corner_radius_top_left = 4
	style.corner_radius_top_right = 4
	style.corner_radius_bottom_left = 4
	style.corner_radius_bottom_right = 4
	style.content_margin_left = 6
	style.content_margin_top = 3
	style.content_margin_right = 6
	style.content_margin_bottom = 3
	return style


func state_label_color(state: String) -> Color:
	match state:
		STATE_IDLE:
			return Color("22c55e")
		STATE_IN_FLIGHT:
			return Color("facc15")
		STATE_UNLOADING:
			return Color("a855f7")
		STATE_RETURNING:
			return Color("7dd3fc")
		STATE_MAINTENANCE:
			return Color("fb923c")
		_:
			return Color("e2e8f0")


func state_short_text(state: String) -> String:
	match state:
		STATE_IN_FLIGHT:
			return "IN FLIGHT"
		STATE_RETURNING:
			return "RETURN"
		STATE_UNLOADING:
			return "UNLOADING"
		STATE_MAINTENANCE:
			return "MAINTENANCE"
		_:
			return "IDLE"


func craft_remaining_time(craft: Dictionary) -> float:
	return maxf(0.0, float(craft.state_until) - sim_time_sec)


func setup_ui_content() -> void:
	title_label = ui_title_label
	title_label.add_theme_color_override("font_color", Color("e9f2ff"))
	title_label.add_theme_font_size_override("font_size", 24)
	subtitle_label = ui_subtitle_label
	subtitle_label.add_theme_color_override("font_color", Color("8ec5ff"))
	subtitle_label.add_theme_font_size_override("font_size", 12)
	stats_values["gen"] = ui_generated_value
	stats_values["q"] = ui_queued_value
	stats_values["d"] = ui_delivered_value
	stats_values["e"] = ui_expired_value
	if ui_dashboard_row != null:
		top_sim_time_label = create_top_metric_card("SIM TIME", "0.0s", Color("38bdf8"), 0, "res://design/icon_clock.png")
		top_avg_latency_label = create_top_metric_card("AVG LATENCY", "0.0s", Color("a78bfa"), ui_dashboard_row.get_child_count(), "res://design/icon_latency_purple.png")
	for key in stats_values.keys():
		stats_values[key].add_theme_color_override("font_color", Color("f8fafc"))
		stats_values[key].add_theme_font_size_override("font_size", 20)

	queue_list = ui_queue_list
	delivered_list_ui = ui_delivered_list
	event_log_label = ui_event_log_text
	system_info_label = ui_system_info_text
	queue_world_text_label = ui_queue_world_text
	destination_hub_text_label = ui_destination_hub_text
	queue_cards.clear()
	queue_progress.clear()
	queue_countdowns.clear()
	aircraft_state_labels = [ui_aircraft1_state_label, ui_aircraft2_state_label]
	aircraft_cargo_labels = [ui_aircraft1_cargo_label, ui_aircraft2_cargo_label]
	for lbl in aircraft_state_labels:
		if lbl != null:
			lbl.add_theme_font_size_override("font_size", 12)
			lbl.add_theme_color_override("font_color", Color("bfdbfe"))
	for lbl in aircraft_cargo_labels:
		if lbl != null:
			lbl.add_theme_color_override("font_color", Color("cbd5e1"))
			lbl.add_theme_font_size_override("font_size", 11)
	if ui_fleet_coordinator_panel != null:
		ui_fleet_coordinator_panel.add_theme_stylebox_override("panel", make_panel_style())
	if ui_queue_world_panel != null:
		var queue_style := make_panel_style()
		queue_style.border_color = Color("60a5fa")
		queue_style.set_border_width_all(2)
		ui_queue_world_panel.add_theme_stylebox_override("panel", queue_style)
	if ui_destination_hub_panel != null:
		var dest_style := make_panel_style()
		dest_style.border_color = Color("22c55e")
		dest_style.set_border_width_all(2)
		ui_destination_hub_panel.add_theme_stylebox_override("panel", dest_style)
	if ui_aircraft1_card != null:
		var s1 := make_panel_style()
		s1.bg_color = Color(0.07, 0.12, 0.20, 0.94)
		ui_aircraft1_card.add_theme_stylebox_override("panel", s1)
	if ui_aircraft2_card != null:
		var s2 := make_panel_style()
		s2.bg_color = Color(0.07, 0.12, 0.20, 0.94)
		ui_aircraft2_card.add_theme_stylebox_override("panel", s2)
	if queue_world_text_label != null:
		queue_world_text_label.add_theme_color_override("font_color", Color("bfdbfe"))
		queue_world_text_label.add_theme_font_size_override("font_size", 11)
	if destination_hub_text_label != null:
		destination_hub_text_label.add_theme_color_override("font_color", Color("bbf7d0"))
		destination_hub_text_label.add_theme_font_size_override("font_size", 11)
	apply_custom_ui_icons()


func create_top_metric_card(title: String, initial_value: String, border_color: Color, insert_index: int, icon_path: String = "") -> Label:
	var card := PanelContainer.new()
	card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var style := make_panel_style()
	style.border_color = border_color
	style.set_border_width_all(2)
	card.add_theme_stylebox_override("panel", style)
	var vb := VBoxContainer.new()
	card.add_child(vb)
	var title_row := HBoxContainer.new()
	title_row.add_theme_constant_override("separation", 4)
	vb.add_child(title_row)
	if icon_path != "":
		var icon_tex := load_texture_safe(icon_path)
		if icon_tex != null:
			var icon := TextureRect.new()
			icon.texture = icon_tex
			icon.custom_minimum_size = Vector2(16, 16)
			icon.expand_mode = TextureRect.EXPAND_FIT_WIDTH
			icon.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
			title_row.add_child(icon)
	var title_l := Label.new()
	title_l.text = title
	title_l.add_theme_color_override("font_color", Color("bfdbfe"))
	title_l.add_theme_font_size_override("font_size", 11)
	title_row.add_child(title_l)
	var value_l := Label.new()
	value_l.text = initial_value
	value_l.add_theme_color_override("font_color", Color("f8fafc"))
	value_l.add_theme_font_size_override("font_size", 20)
	vb.add_child(value_l)
	ui_dashboard_row.add_child(card)
	ui_dashboard_row.move_child(card, insert_index)
	return value_l


func apply_custom_ui_icons() -> void:
	set_texture_rect_icon(ui_generated_icon, "res://design/icon_package_yellow.png", Vector2(44, 44))
	set_texture_rect_icon(ui_queued_icon, "res://design/icon_queue_blue.png", Vector2(44, 44))
	set_texture_rect_icon(ui_delivered_icon, "res://design/icon_destination_green.png", Vector2(44, 44))
	set_texture_rect_icon(ui_expired_icon, "res://design/icon_warning_red.png", Vector2(44, 44))
	decorate_title_with_icon(ui_origin_title, "res://design/icon_warehouse_blue.png", 18.0)
	decorate_title_with_icon(ui_queue_world_title, "res://design/icon_queue_blue.png", 18.0)
	decorate_title_with_icon(ui_fleet_coordinator_title, "res://design/badge_fleet_blue.png", 18.0)
	decorate_title_with_icon(ui_delivered_title, "res://design/icon_package_yellow.png", 18.0)
	decorate_title_with_icon(ui_destination_hub_title, "res://design/badge_delivery_green.png", 18.0)
	decorate_title_with_icon(ui_event_log_title, "res://design/icon_eventlog_cyan.png", 18.0)
	decorate_title_with_icon(ui_system_info_title, "res://design/icon_metrics_teal.png", 18.0)


func set_texture_rect_icon(target: TextureRect, path: String, size: Vector2) -> void:
	if target == null:
		return
	var tex := load_texture_safe(path)
	if tex == null:
		return
	target.texture = tex
	target.custom_minimum_size = size
	target.expand_mode = TextureRect.EXPAND_FIT_WIDTH
	target.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED


func decorate_title_with_icon(target_label: Label, icon_path: String, icon_size: float) -> void:
	if target_label == null:
		return
	var icon_tex := load_texture_safe(icon_path)
	if icon_tex == null:
		return
	var parent := target_label.get_parent()
	if parent == null:
		return
	var existing_row := parent.get_node_or_null("%sRow" % target_label.name) as HBoxContainer
	if existing_row == null:
		existing_row = HBoxContainer.new()
		existing_row.name = "%sRow" % target_label.name
		existing_row.add_theme_constant_override("separation", 6)
		var at_index := target_label.get_index()
		parent.add_child(existing_row)
		parent.move_child(existing_row, at_index)
		parent.remove_child(target_label)
		existing_row.add_child(target_label)
	var icon_rect := existing_row.get_node_or_null("Icon") as TextureRect
	if icon_rect == null:
		icon_rect = TextureRect.new()
		icon_rect.name = "Icon"
		existing_row.add_child(icon_rect)
		existing_row.move_child(icon_rect, 0)
	icon_rect.texture = icon_tex
	icon_rect.custom_minimum_size = Vector2(icon_size, icon_size)
	icon_rect.expand_mode = TextureRect.EXPAND_FIT_WIDTH
	icon_rect.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED


func update_ui_texts() -> void:
	if stats_values.has("gen"):
		stats_values["gen"].text = str(generated)
		stats_values["q"].text = str(queue.size())
		stats_values["d"].text = str(delivered)
		stats_values["e"].text = str(expired)
	if top_sim_time_label != null:
		top_sim_time_label.text = "%.1fs" % sim_time_sec
	if top_avg_latency_label != null:
		top_avg_latency_label.text = "%.1fs" % avg_latency()

	update_queue_cards()

	if delivered_list_ui != null:
		for c in delivered_list_ui.get_children():
			c.queue_free()
		for line in delivered_list:
			var card := PanelContainer.new()
			card.custom_minimum_size = Vector2(0, 34)
			var s2 := make_panel_style()
			s2.bg_color = Color(0.06, 0.16, 0.12, 1.0)
			s2.border_color = Color("22c55e")
			s2.set_border_width_all(1)
			card.add_theme_stylebox_override("panel", s2)
			delivered_list_ui.add_child(card)
			var l := Label.new()
			l.text = line
			l.add_theme_color_override("font_color", Color("dcfce7"))
			card.add_child(l)

	if event_log_label != null:
		var etxt := ""
		for i in range(events.size() - 1, max(-1, events.size() - 12), -1):
			etxt += "%s\n" % events[i]
		event_log_label.text = etxt

	if system_info_label != null:
		system_info_label.text = (
			"Generated: %d\nQueued: %d\nDelivered: %d\nExpired: %d\n"
			+ "Avg Latency: %.1fs\nUtilization: %.0f%%\n"
			+ "Load/Flight/Unload/Return/Maintain: %.0f/%.0f/%.0f/%.0f/%.0fs\n"
			+ "Legend: IN FLIGHT=Yellow, RETURNING=Blue, IDLE=Green"
		) % [
			generated, queue.size(), delivered, expired,
			avg_latency(), utilization(),
			config.loading_sec, config.flight_sec, config.unload_sec, config.return_sec, config.maintenance_sec
		]
	if queue_world_text_label != null:
		var queue_summary := "Waiting: %d pallets" % queue.size()
		if queue.size() > 0:
			var next_pallet: Dictionary = queue[0]
			var next_remain := maxf(0.0, next_pallet.deadline_time - sim_time_sec)
			queue_summary += "\nNext: %s (T-%.1fs)" % [next_pallet.id, next_remain]
		else:
			queue_summary += "\nNext: -"
		queue_world_text_label.text = queue_summary
	if destination_hub_text_label != null:
		destination_hub_text_label.text = "Delivered: %d pallets\nAvg Latency: %.1fs" % [delivered, avg_latency()]

	update_fleet_coordinator_ui()
	update_aircraft_world_tags()


func add_queue_card(pallet: Dictionary) -> void:
	if queue_list == null or queue_cards.has(pallet.id):
		return
	var card := PanelContainer.new()
	card.custom_minimum_size = Vector2(0, 56)
	card.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	var s := make_panel_style()
	s.bg_color = Color(0.09, 0.14, 0.21, 1.0)
	s.border_color = Color("60a5fa")
	card.add_theme_stylebox_override("panel", s)
	queue_list.add_child(card)
	queue_cards[pallet.id] = card

	var vb := VBoxContainer.new()
	vb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	card.add_child(vb)
	var row := HBoxContainer.new()
	vb.add_child(row)

	var id_l := Label.new()
	id_l.text = pallet.id
	id_l.add_theme_color_override("font_color", Color("f8fafc"))
	row.add_child(id_l)
	row.add_spacer(false)

	var countdown := Label.new()
	countdown.name = "Countdown"
	countdown.text = "T-%.1fs" % maxf(0.0, pallet.deadline_time - sim_time_sec)
	countdown.add_theme_color_override("font_color", Color("e2e8f0"))
	row.add_child(countdown)

	var bar := ProgressBar.new()
	bar.name = "TimerBar"
	var window := pallet_expiration_window(pallet)
	bar.max_value = window
	bar.value = clampf(maxf(0.0, pallet.deadline_time - sim_time_sec), 0.0, window)
	bar.show_percentage = false
	bar.custom_minimum_size = Vector2(0, 10)
	vb.add_child(bar)
	queue_progress[pallet.id] = bar
	queue_countdowns[pallet.id] = countdown
	apply_progress_style(bar, bar.value, window)


func remove_queue_card(pallet_id: String) -> void:
	if not queue_cards.has(pallet_id):
		return
	var card: PanelContainer = queue_cards[pallet_id]
	queue_cards.erase(pallet_id)
	queue_progress.erase(pallet_id)
	queue_countdowns.erase(pallet_id)
	if is_instance_valid(card):
		card.queue_free()


func apply_progress_style(bar: ProgressBar, remain: float, window: float) -> void:
	var fill := StyleBoxFlat.new()
	fill.corner_radius_top_left = 2
	fill.corner_radius_top_right = 2
	fill.corner_radius_bottom_left = 2
	fill.corner_radius_bottom_right = 2
	var warn_threshold := maxf(5.0, window * 0.2)
	var danger_threshold := maxf(2.0, window * 0.1)
	if remain <= 0.0:
		fill.bg_color = Color("ef4444")
	elif remain < danger_threshold:
		fill.bg_color = Color("ef4444")
	elif remain < warn_threshold:
		fill.bg_color = Color("facc15")
	else:
		fill.bg_color = Color("38bdf8")
	bar.add_theme_stylebox_override("fill", fill)

	var bg := StyleBoxFlat.new()
	bg.bg_color = Color(0.06, 0.08, 0.12, 1.0)
	bg.corner_radius_top_left = 2
	bg.corner_radius_top_right = 2
	bg.corner_radius_bottom_left = 2
	bg.corner_radius_bottom_right = 2
	bar.add_theme_stylebox_override("background", bg)


func update_queue_cards() -> void:
	if queue_list == null:
		return
	for item in queue:
		if not queue_cards.has(item.id):
			add_queue_card(item)
	var stale_ids: Array[String] = []
	for pallet_id in queue_cards.keys():
		var found := false
		for item in queue:
			if item.id == pallet_id:
				found = true
				break
		if not found:
			stale_ids.append(pallet_id)
	for stale_id in stale_ids:
		remove_queue_card(stale_id)
	var desired_order: Array[String] = []
	for item in queue:
		desired_order.append(item.id)
	for i in range(desired_order.size()):
		var pid := desired_order[i]
		if queue_cards.has(pid):
			var card: PanelContainer = queue_cards[pid]
			if card.get_parent() == queue_list:
				queue_list.move_child(card, i)
	for item in queue:
		var pid: String = item.id
		if not queue_cards.has(pid):
			continue
		var card: PanelContainer = queue_cards[pid]
		var window := pallet_expiration_window(item)
		var remain := maxf(0.0, item.deadline_time - sim_time_sec)
		var s := make_panel_style()
		s.bg_color = Color(0.09, 0.14, 0.21, 1.0)
		var warn_threshold := maxf(5.0, window * 0.2)
		var danger_threshold := maxf(2.0, window * 0.1)
		if remain <= 0.0:
			s.border_color = Color("f87171")
		elif remain < danger_threshold:
			s.border_color = Color("f87171")
		elif remain < warn_threshold:
			s.border_color = Color("facc15")
		else:
			s.border_color = Color("60a5fa")
		card.add_theme_stylebox_override("panel", s)
		var countdown: Label = queue_countdowns.get(pid)
		if countdown != null:
			countdown.text = "T-%.1fs" % remain
		var bar: ProgressBar = queue_progress.get(pid)
		if bar != null:
			bar.max_value = window
			bar.value = clampf(remain, 0.0, window)
			apply_progress_style(bar, remain, window)


func update_fleet_coordinator_ui() -> void:
	for i in range(min(aircraft.size(), aircraft_state_labels.size(), aircraft_cargo_labels.size())):
		var craft: Dictionary = aircraft[i]
		var state_label: Label = aircraft_state_labels[i]
		var cargo_label: Label = aircraft_cargo_labels[i]
		if state_label != null:
			var remain := craft_remaining_time(craft)
			var remain_text := ""
			if craft.state != STATE_IDLE:
				remain_text = " (%.1fs)" % remain
			state_label.text = "State: %s%s" % [craft.state, remain_text]
			state_label.add_theme_color_override("font_color", state_label_color(craft.state))
		if cargo_label != null:
			var cargo_text := "-"
			if craft.cargo != null:
				cargo_text = str(craft.cargo.id)
			cargo_label.text = "Cargo: %s" % cargo_text


func update_aircraft_world_tags() -> void:
	for i in range(min(aircraft.size(), aircraft_world_tag_labels.size())):
		var craft: Dictionary = aircraft[i]
		var lbl: Label = aircraft_world_tag_labels[i]
		if lbl == null:
			continue
		var cargo_text := ""
		if craft.cargo != null:
			cargo_text = " Cargo: %s" % craft.cargo.id
		var remain_text := ""
		if craft.state != STATE_IDLE:
			remain_text = " %.1fs" % craft_remaining_time(craft)
		lbl.text = "%s [%s%s]%s" % [craft.name, state_short_text(craft.state), remain_text, cargo_text]
