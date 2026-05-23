extends Node
class_name MqttClient

signal message_received(topic: String, payload: PackedByteArray)
signal connection_changed(connected: bool)

@export var host: String = "127.0.0.1"
@export var port: int = 1883
@export var client_id: String = "godot_airfreight"
@export var keep_alive_sec: int = 60

var _tcp: StreamPeerTCP
var _connected := false
var _connect_requested := false
var _session_ready := false
var _connect_packet_sent := false
var _subscriptions: Dictionary = {}
var _pending_packet_id := 1
var _buffer := PackedByteArray()
var _last_ping_sent_ms := 0


func connect_to_broker() -> void:
	_connect_requested = true
	_session_ready = false
	_connect_packet_sent = false
	_set_connected(false)
	if _tcp == null:
		_tcp = StreamPeerTCP.new()
	_tcp.disconnect_from_host()
	var err := _tcp.connect_to_host(host, port)
	if err != OK and err != ERR_ALREADY_IN_USE:
		push_warning("MQTT connect_to_host failed: %s" % error_string(err))


func subscribe(topic: String, qos: int = 0) -> void:
	_subscriptions[topic] = qos
	if _connected:
		_send_subscribe(topic, qos)


func poll() -> void:
	if _tcp == null:
		return

	_tcp.poll()
	var status := _tcp.get_status()
	if status == StreamPeerTCP.STATUS_CONNECTED:
		if _connect_requested and not _session_ready and not _connect_packet_sent:
			_send_connect()
			_connect_packet_sent = true
	elif status == StreamPeerTCP.STATUS_ERROR or status == StreamPeerTCP.STATUS_NONE:
		if _connect_packet_sent or _session_ready or _connected:
			_reset_session()
			if _connect_requested:
				_tcp.disconnect_from_host()
				var err := _tcp.connect_to_host(host, port)
				if err != OK and err != ERR_ALREADY_IN_USE:
					push_warning("MQTT reconnect failed: %s" % error_string(err))
	elif status == StreamPeerTCP.STATUS_CONNECTING:
		return

	if status != StreamPeerTCP.STATUS_CONNECTED:
		return

	var available := _tcp.get_available_bytes()
	if available > 0:
		var chunk := _tcp.get_data(available)
		if chunk[0] == OK:
			_buffer.append_array(chunk[1])
			_parse_packets()

	if _connected:
		_send_keepalive()


func _reset_session() -> void:
	_connect_packet_sent = false
	_session_ready = false
	_buffer.clear()
	_set_connected(false)


func _set_connected(value: bool) -> void:
	if _connected == value:
		return
	_connected = value
	connection_changed.emit(value)
	if value:
		for topic in _subscriptions.keys():
			_send_subscribe(topic, int(_subscriptions[topic]))


func _send_connect() -> void:
	var protocol_name := _encode_string("MQTT")
	var payload := protocol_name
	payload.append(4) # MQTT 3.1.1
	payload.append(0x02) # clean session
	payload.append_array(_encode_uint16(keep_alive_sec))
	payload.append_array(_encode_string(client_id))
	_send_packet(0x10, payload)
	_last_ping_sent_ms = Time.get_ticks_msec()


func _send_subscribe(topic: String, qos: int) -> void:
	var packet_id := _next_packet_id()
	var payload := _encode_uint16(packet_id)
	payload.append_array(_encode_string(topic))
	payload.append(qos & 0x03)
	_send_packet(0x82, payload)


func _send_ping() -> void:
	_send_packet(0xC0, PackedByteArray())


func _send_keepalive() -> void:
	if not _connected:
		return
	var now := Time.get_ticks_msec()
	if now - _last_ping_sent_ms >= keep_alive_sec * 500:
		_send_ping()
		_last_ping_sent_ms = now


func _send_packet(packet_type: int, payload: PackedByteArray) -> void:
	if _tcp == null or _tcp.get_status() != StreamPeerTCP.STATUS_CONNECTED:
		return
	var packet := PackedByteArray()
	packet.append(packet_type)
	packet.append_array(_encode_remaining_length(payload.size()))
	packet.append_array(payload)
	_tcp.put_data(packet)


func _parse_packets() -> void:
	while _buffer.size() > 0:
		var header_byte := int(_buffer[0])
		var packet_type := header_byte & 0xF0
		var offset := 1
		var remaining := _decode_remaining_length(_buffer, offset)
		if remaining["length"] < 0:
			return
		offset = remaining["offset"]
		var length: int = remaining["length"]
		if _buffer.size() < offset + length:
			return
		var body := _buffer.slice(offset, offset + length)
		_buffer = _buffer.slice(offset + length)
		_handle_packet(packet_type, body, header_byte)


func _handle_packet(packet_type: int, body: PackedByteArray, header_byte: int) -> void:
	match packet_type:
		0x30, 0x31, 0x32, 0x33:
			_handle_publish(body, header_byte)
		0xD0:
			pass # PINGRESP
		0x90:
			pass # SUBACK
		0x20:
			if body.size() >= 2 and body[1] != 0:
				push_warning("MQTT CONNACK rejected with code %d" % int(body[1]))
				_reset_session()
				return
			_session_ready = true
			_set_connected(true)


func _handle_publish(body: PackedByteArray, header_byte: int) -> void:
	if body.size() < 2:
		return
	var topic_len := _decode_uint16(body, 0)
	var offset := 2
	if topic_len < 0 or body.size() < offset + topic_len:
		return
	var topic := body.slice(offset, offset + topic_len).get_string_from_utf8()
	offset += topic_len
	var qos := (header_byte >> 1) & 0x03
	if qos > 0:
		offset += 2
	if offset > body.size():
		return
	var payload := body.slice(offset, body.size())
	message_received.emit(topic, payload)


func _encode_string(value: String) -> PackedByteArray:
	var bytes := value.to_utf8_buffer()
	var encoded := _encode_uint16(bytes.size())
	encoded.append_array(bytes)
	return encoded


func _encode_uint16(value: int) -> PackedByteArray:
	var encoded := PackedByteArray()
	encoded.append((value >> 8) & 0xFF)
	encoded.append(value & 0xFF)
	return encoded


func _decode_uint16(data: PackedByteArray, offset: int) -> int:
	if data.size() < offset + 2:
		return -1
	return (int(data[offset]) << 8) | int(data[offset + 1])


func _encode_remaining_length(length: int) -> PackedByteArray:
	var encoded := PackedByteArray()
	var value := length
	while true:
		var byte := value % 128
		value = value >> 7
		if value > 0:
			byte |= 0x80
		encoded.append(byte)
		if value == 0:
			break
	return encoded


func _decode_remaining_length(data: PackedByteArray, offset: int) -> Dictionary:
	var multiplier := 1
	var value := 0
	var index := offset
	while index < data.size():
		var encoded_byte := int(data[index])
		index += 1
		value += (encoded_byte & 127) * multiplier
		if (encoded_byte & 128) == 0:
			return {"length": value, "offset": index}
		multiplier *= 128
		if multiplier > 128 * 128 * 128:
			break
	return {"length": -1, "offset": offset}


func _next_packet_id() -> int:
	_pending_packet_id += 1
	if _pending_packet_id > 65535:
		_pending_packet_id = 1
	return _pending_packet_id
