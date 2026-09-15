extends Node

signal status_changed(text: String)

var request := HTTPRequest.new()
var cancellation := HTTPRequest.new()
var microphone := AudioStreamPlayer.new()
var speaker := AudioStreamPlayer.new()
var recorder := AudioEffectRecord.new()
var recording := false
var busy := false
var elapsed := 0.0
var capture_view := SubViewport.new()
var capture_camera := Camera3D.new()
var eye: Camera3D
var source_name := ""
var voice_url := OS.get_environment("ARRIETTY_VOICE_URL")
var token := OS.get_environment("ARRIETTY_VOICE_TOKEN")
var microphone_bus := ""
var monitor_bus := ""
var selection_error := ""
var selected_microphone := "Default"
var meter_elapsed := 0.0
var level_db := -100.0
var peak_db := -100.0
var last_recording: Dictionary = {}
var stage := "idle"

func _ready() -> void:
	request.use_threads = true
	request.timeout = 190.0
	request.body_size_limit = 24 * 1024 * 1024
	add_child(request)
	add_child(cancellation)
	request.request_completed.connect(_completed)
	# Meter/record before the muted output bus. No microphone feedback is audible.
	monitor_bus = "Arrietty silent %s" % get_instance_id()
	var monitor := AudioServer.bus_count
	AudioServer.add_bus()
	AudioServer.set_bus_name(monitor, monitor_bus)
	AudioServer.set_bus_mute(monitor, true)
	var bus := AudioServer.bus_count
	AudioServer.add_bus()
	microphone_bus = "Arrietty microphone %s" % get_instance_id()
	AudioServer.set_bus_name(bus, microphone_bus)
	AudioServer.set_bus_send(bus, monitor_bus)
	recorder.format = AudioStreamWAV.FORMAT_16_BITS
	AudioServer.add_bus_effect(bus, recorder)
	microphone.bus = microphone_bus
	microphone.stream = AudioStreamMicrophone.new()
	add_child(microphone)
	add_child(speaker)
	select_microphone(OS.get_environment("ARRIETTY_MICROPHONE"))
	capture_view.size = Vector2i(1024, 768)
	capture_view.mesh_lod_threshold = 0.0
	capture_view.render_target_update_mode = SubViewport.UPDATE_DISABLED
	capture_view.world_3d = get_viewport().world_3d
	add_child(capture_view)
	capture_view.add_child(capture_camera)
	capture_camera.current = true

func _process(delta: float) -> void:
	if recording:
		elapsed += delta
		meter_elapsed += delta
		var bus := AudioServer.get_bus_index(microphone_bus)
		level_db = maxf(-100.0, maxf(AudioServer.get_bus_peak_volume_left_db(bus, 0), AudioServer.get_bus_peak_volume_right_db(bus, 0)))
		peak_db = maxf(peak_db, level_db)
		if meter_elapsed >= 0.1:
			meter_elapsed = 0.0
			status_changed.emit("録音中 %.1f秒 · 入力 %.0f dB\nXを離すと送信 / Bで中止" % [elapsed, level_db])
		if elapsed >= 30.0:
			finish()

static func match_microphone(devices: PackedStringArray, requested: String) -> String:
	if requested.is_empty():
		return "Default"
	if requested in devices:
		return requested
	var matches: Array[String] = []
	for device in devices:
		if device.to_lower().contains(requested.to_lower()):
			matches.append(device)
	return matches[0] if matches.size() == 1 else ""

func select_microphone(requested: String) -> void:
	var selected := match_microphone(AudioServer.get_input_device_list(), requested)
	selection_error = ""
	if selected.is_empty():
		selection_error = "指定マイクが見つからないか、複数あります。Yで選んでください。"
		return
	AudioServer.input_device = selected
	# WASAPI applies the requested device when capture starts; the getter can still
	# report the previous device while idle. Keep selection separate from that state.
	selected_microphone = selected

func cycle_microphone() -> void:
	if recording or busy:
		status_changed.emit("マイク切替はBで中止してからYを押してください。")
		return
	var devices := AudioServer.get_input_device_list()
	if devices.size() > 1 and "Default" in devices:
		devices.remove_at(devices.find("Default"))
	if devices.is_empty():
		status_changed.emit("入力マイクが見つかりません。")
		return
	var index := devices.find(selected_microphone)
	select_microphone(devices[(index + 1) % devices.size()])
	status_changed.emit("マイクを切り替えました。Xを押しながら話してください。")

func microphone_label() -> String:
	return "マイク: %s (Yで切替)" % selected_microphone if selection_error.is_empty() else selection_error

func diagnostics() -> Dictionary:
	return {"device": selected_microphone, "engine_device": AudioServer.input_device, "devices": AudioServer.get_input_device_list(),
		"selection_error": selection_error, "stage": stage, "recording": recording,
		"level_db": level_db, "peak_db": peak_db, "elapsed": elapsed, "last_recording": last_recording}

func begin() -> void:
	if busy or recording:
		return
	if not selection_error.is_empty():
		status_changed.emit(selection_error)
		return
	if voice_url.is_empty():
		status_changed.emit("音声サービスがありません。start.ps1 から起動してください。")
		return
	speaker.stop()
	elapsed = 0.0
	meter_elapsed = 0.0
	level_db = -100.0
	peak_db = -100.0
	recorder.set_recording_active(true)
	microphone.play()
	recording = true
	stage = "recording"
	status_changed.emit("録音中… Xを離すと質問と目線画像を送信")

func finish() -> void:
	if not recording:
		return
	recording = false
	recorder.set_recording_active(false)
	microphone.stop()
	var audio := recorder.get_recording()
	stage = "idle"
	if elapsed < 0.2 or audio == null or audio.data.is_empty():
		stage = "no_recording"
		status_changed.emit("録音が短いか、マイクの音声データがありません。Xを押しながら話してください。")
		return
	last_recording = {"device": AudioServer.input_device, "bytes": audio.data.size(),
		"seconds": float(audio.data.size()) / (audio.mix_rate * (2 if audio.stereo else 1) * 2),
		"peak_db": peak_db, "mix_rate": audio.mix_rate}
	submit(audio)

func submit(audio: AudioStreamWAV) -> void:
	busy = true
	stage = "submitted"
	status_changed.emit("景色を見ながら回答を考えています…")
	# One centre-eye image per question; this viewport is idle during normal rendering.
	capture_camera.global_transform = eye.global_transform
	capture_camera.near = eye.near
	capture_camera.far = eye.far
	capture_camera.fov = 85.0
	var position := eye.global_position
	var forward := -eye.global_basis.z
	capture_view.render_target_update_mode = SubViewport.UPDATE_ONCE
	await RenderingServer.frame_post_draw
	if not busy:
		return
	var screenshot := capture_view.get_texture().get_image()
	if screenshot == null or screenshot.is_empty():
		busy = false
		status_changed.emit("目線画像を取得できませんでした。")
		return
	var payload := {"audio": Marshalls.raw_to_base64(wav_bytes(audio)),
		"image": Marshalls.raw_to_base64(screenshot.save_jpg_to_buffer(0.85)),
		"context": {"scene": source_name, "position_metres": [position.x, position.y, position.z],
		"forward": [forward.x, forward.y, forward.z]}}
	var err := request.request(voice_url + "/ask", headers(), HTTPClient.METHOD_POST, JSON.stringify(payload))
	if err != OK:
		busy = false
		status_changed.emit("音声サービスへ接続できませんでした。")

func headers() -> PackedStringArray:
	return PackedStringArray(["Content-Type: application/json", "Authorization: Bearer " + token])

func cancel() -> void:
	recording = false
	recorder.set_recording_active(false)
	microphone.stop()
	speaker.stop()
	if busy:
		request.cancel_request()
		cancellation.cancel_request()
		cancellation.request(voice_url + "/cancel", headers(), HTTPClient.METHOD_POST, "{}")
	busy = false
	stage = "cancelled"
	status_changed.emit("音声案内を中止しました。")

func _completed(result: int, code: int, _headers: PackedStringArray, body: PackedByteArray) -> void:
	busy = false
	stage = "error"
	var response = JSON.parse_string(body.get_string_from_utf8())
	if result != HTTPRequest.RESULT_SUCCESS or not response is Dictionary:
		status_changed.emit("音声サービスと通信できませんでした。")
		return
	if response.get("recording", null) is Dictionary:
		last_recording.merge(response.recording, true)
	if code != 200:
		status_changed.emit(str(response.get("error", "音声処理に失敗しました。")))
		return
	var audio := AudioStreamWAV.load_from_buffer(Marshalls.base64_to_raw(response.get("audio", "")))
	if audio == null:
		status_changed.emit("回答の音声を再生できませんでした。")
		return
	speaker.stream = audio
	speaker.play()
	stage = "answered"
	status_changed.emit(str(response.get("answer", "")))

func _exit_tree() -> void:
	microphone.stop()
	recorder.set_recording_active(false)
	for bus_name in [microphone_bus, monitor_bus]:
		var index := AudioServer.get_bus_index(bus_name)
		if index > 0:
			AudioServer.remove_bus(index)

static func wav_bytes(audio: AudioStreamWAV) -> PackedByteArray:
	var data := audio.data
	var channels := 2 if audio.stereo else 1
	var bytes := PackedByteArray()
	bytes.resize(44)
	for entry in [[0, "RIFF"], [8, "WAVE"], [12, "fmt "], [36, "data"]]:
		var text_bytes: PackedByteArray = entry[1].to_ascii_buffer()
		for i in 4:
			bytes[entry[0] + i] = text_bytes[i]
	bytes.encode_u32(4, data.size() + 36)
	bytes.encode_u32(16, 16)
	bytes.encode_u16(20, 1)
	bytes.encode_u16(22, channels)
	bytes.encode_u32(24, audio.mix_rate)
	bytes.encode_u32(28, audio.mix_rate * channels * 2)
	bytes.encode_u16(32, channels * 2)
	bytes.encode_u16(34, 16)
	bytes.encode_u32(40, data.size())
	bytes.append_array(data)
	return bytes
