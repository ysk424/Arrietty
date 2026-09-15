extends Node3D

const Walker = preload("res://walker.gd")
const Voice = preload("res://voice.gd")
const WorldCollision = preload("res://world_collision.gd")
var walker: Node3D
var collision_info: Dictionary = {}
var voice: Node
var info := Label.new()
var status := "X: 話す  /  View長押し: 高さ・正面調整"
var head_label := Label3D.new()
var metadata: Dictionary
var ready_to_walk := false
var xr: XRInterface
var xr_active := false
var recenter_hold := 0.0
var recenter_done := false
var turn_ready := true
var talk_was_down := false
var cancel_was_down := false
var microphone_was_down := false
var active_pad := -1
var calibration_time := 0.0
var metrics_time := 0.0
var runtime := 0.0
var benchmark_seconds := 0
var samples: Array[Dictionary] = []
var scene_meshes := 0
var scene_triangles := 0
var desktop := false
var captured_preview := false

func _ready() -> void:
	get_viewport().mesh_lod_threshold = 0.0
	var args := OS.get_cmdline_user_args()
	desktop = "--desktop" in args
	var height := 1.5
	for i in range(args.size() - 1):
		if args[i] == "--height":
			height = args[i + 1].to_float()
		if args[i] == "--benchmark-seconds":
			benchmark_seconds = args[i + 1].to_int()
	if desktop and benchmark_seconds == 0:
		Engine.max_fps = 60
	if not is_finite(height) or height < 0.01 or height > 1000.0:
		push_error("Eye height must be 0.01–1000 m")
		get_tree().quit(1)
		return
	var layer := CanvasLayer.new()
	add_child(layer)
	layer.add_child(info)
	info.position = Vector2(20, 16)
	info.size = Vector2(1100, 160)
	info.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	info.add_theme_color_override("font_shadow_color", Color.BLACK)
	info.add_theme_constant_override("shadow_offset_x", 2)
	info.add_theme_constant_override("shadow_offset_y", 2)
	var font := SystemFont.new()
	font.font_names = PackedStringArray(["Yu Gothic", "Meiryo", "sans-serif"])
	info.add_theme_font_override("font", font)
	info.text = "Arrietty — 世界を読み込み中…"
	await get_tree().process_frame
	if not FileAccess.file_exists("res://scene.json") or not ResourceLoader.exists("res://world.glb"):
		fatal("start.ps1 にBlenderファイルを渡して起動してください。")
		return
	metadata = JSON.parse_string(FileAccess.get_file_as_string("res://scene.json"))
	var world := load("res://world.glb").instantiate() as Node3D
	add_child(world)
	for node in world.find_children("*", "Camera3D", true, false):
		node.current = false
	for mesh in world.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null:
			continue
		scene_meshes += 1
		for surface in mesh.mesh.get_surface_count():
			var count: int = mesh.mesh.surface_get_array_index_len(surface)
			if count == 0:
				count = mesh.mesh.surface_get_array_len(surface)
			scene_triangles += count / 3
	collision_info = WorldCollision.prepare(world)
	var environment := WorldEnvironment.new()
	environment.environment = Environment.new()
	environment.environment.background_mode = Environment.BG_COLOR
	environment.environment.background_color = Color(0.42, 0.60, 0.76)
	environment.environment.ambient_light_source = Environment.AMBIENT_SOURCE_COLOR
	environment.environment.ambient_light_color = Color.WHITE
	environment.environment.ambient_light_energy = 0.7
	add_child(environment)
	if world.find_children("*", "Light3D", true, false).is_empty():
		var sun := DirectionalLight3D.new()
		sun.rotation_degrees = Vector3(-50, -30, 0)
		sun.light_energy = 1.0
		add_child(sun)
	if not desktop:
		xr = XRServer.find_interface("OpenXR")
		xr_active = xr != null and (xr.is_initialized() or xr.initialize())
		if not xr_active:
			fatal("OpenXR HMDが見つかりません。SteamVRを起動するか -Desktop で確認してください。")
			return
		get_viewport().use_xr = true
	walker = Walker.new()
	walker.eye_height = height
	walker.xr_enabled = xr_active
	add_child(walker)
	await get_tree().physics_frame
	await get_tree().physics_frame
	if not place_start():
		fatal("開始地点の足場が見つかりません。カメラを地面の上へ移すか WalkStart のEmptyを配置してください。")
		return
	voice = Voice.new()
	voice.eye = walker.camera
	voice.source_name = metadata.get("source", "")
	voice.status_changed.connect(set_status)
	add_child(voice)
	head_label.font = font
	head_label.font_size = 32
	head_label.pixel_size = 0.0008 * walker.size_factor
	head_label.position = Vector3(0, -0.25, -0.8) * walker.size_factor
	head_label.width = 900
	head_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	head_label.no_depth_test = true
	head_label.visible = xr_active
	# Capture cameras exclude the HUD layer; GPT sees only the world.
	head_label.layers = 1 << 19
	walker.camera.add_child(head_label)
	voice.capture_camera.cull_mask = (1 << 19) - 1
	RenderingServer.viewport_set_measure_render_time(get_viewport().get_viewport_rid(), true)
	ready_to_walk = true
	if desktop:
		walker.recenter()
	set_status("X: 押して話す / Y: マイク切替 / B: 中止 / Viewを1秒: 高さ・正面\n案内の声はAI合成音声です。")
	print("ARRIETTY_READY ", JSON.stringify({"meshes": scene_meshes, "triangles": scene_triangles,
		"height_m": height, "xr": xr_active, "collision": collision_info, "position": str(walker.position)}))

func place_start() -> bool:
	var start: Dictionary = metadata.get("start", {})
	var pos := vec(start.get("position", [0, 1.5, 0]))
	var forward := vec(start.get("forward", [0, 0, -1]))
	var candidates: Array[Vector3] = [pos]
	for marker in metadata.get("walk_starts", []):
		candidates.append(vec(marker))
	for radius in [1.0, 3.0, 10.0, 30.0, 100.0]:
		for i in 16:
			candidates.append(pos + Vector3(cos(i * TAU / 16.0) * radius, 0, sin(i * TAU / 16.0) * radius))
	for point in candidates:
		var hit: Dictionary = walker.ground(point + Vector3.UP * 0.3, point + Vector3.DOWN * 2000)
		if hit.is_empty():
			continue
		walker.global_position = hit.position
		if walker.head_path_blocked(hit.position + Vector3.UP * 0.01 * walker.size_factor,
				hit.position + Vector3.UP * walker.eye_height):
			continue
		walker.rotation.y = atan2(-forward.x, -forward.z)
		return true
	return false

func _physics_process(delta: float) -> void:
	if not ready_to_walk:
		return
	calibration_time += delta
	var pads := connected_pads()
	var pad := -1 if pads.is_empty() else pads[0]
	if pad != active_pad:
		if talk_was_down:
			voice.cancel()
		talk_was_down = false
		cancel_was_down = false
		microphone_was_down = false
		recenter_hold = 0.0
		recenter_done = false
		turn_ready = true
		active_pad = pad
	var movement := Vector2.ZERO
	var turn_axis := 0.0
	var recenter := Input.is_physical_key_pressed(KEY_R)
	var talk := Input.is_physical_key_pressed(KEY_SPACE)
	var cancel := Input.is_physical_key_pressed(KEY_B)
	var change_microphone := Input.is_physical_key_pressed(KEY_Y)
	if pad >= 0:
		movement = Vector2(axis(pad, JOY_AXIS_LEFT_X), axis(pad, JOY_AXIS_LEFT_Y)).limit_length()
		turn_axis = axis(pad, JOY_AXIS_RIGHT_X)
		recenter = recenter or Input.is_joy_button_pressed(pad, JOY_BUTTON_BACK)
		talk = talk or Input.is_joy_button_pressed(pad, JOY_BUTTON_X)
		cancel = cancel or Input.is_joy_button_pressed(pad, JOY_BUTTON_B)
		change_microphone = change_microphone or Input.is_joy_button_pressed(pad, JOY_BUTTON_Y)
	if desktop:
		movement += Vector2(float(Input.is_physical_key_pressed(KEY_D)) - float(Input.is_physical_key_pressed(KEY_A)),
			float(Input.is_physical_key_pressed(KEY_S)) - float(Input.is_physical_key_pressed(KEY_W)))
		turn_axis += float(Input.is_physical_key_pressed(KEY_E)) - float(Input.is_physical_key_pressed(KEY_Q))
		var pitch := float(Input.is_physical_key_pressed(KEY_DOWN)) - float(Input.is_physical_key_pressed(KEY_UP))
		walker.camera.rotation.x = clampf(walker.camera.rotation.x - pitch * delta, -1.3, 1.3)
	# Voice/cancel and exit must remain available while head tracking is unavailable.
	if talk and not talk_was_down:
		voice.begin()
	elif not talk and talk_was_down:
		if pad < 0 and not desktop:
			voice.cancel()
		else:
			voice.finish()
	if cancel and not cancel_was_down:
		voice.cancel()
	if change_microphone and not microphone_was_down:
		voice.cycle_microphone()
	talk_was_down = talk
	cancel_was_down = cancel
	microphone_was_down = change_microphone
	if Input.is_physical_key_pressed(KEY_ESCAPE):
		get_tree().quit()
		return
	if xr_active:
		if not head_tracking_ready():
			recenter_hold = 0.0
			recenter_done = false
			return
		if not walker.calibrated:
			if calibration_time > 1.0:
				walker.recenter()
			return
	if absf(turn_axis) < 0.3:
		turn_ready = true
	elif turn_ready:
		walker.turn(-signf(turn_axis) * deg_to_rad(30.0))
		turn_ready = false
	walker.room_scale_follow()
	walker.walk(walker.global_basis * Vector3(movement.x, 0, movement.y).limit_length() * walker.walking_speed * delta)
	if recenter:
		recenter_hold += delta
		if recenter_hold >= 1.0 and not recenter_done:
			walker.recenter()
			recenter_done = true
			set_status("高さ %.3f m と正面を調整しました。" % walker.eye_height)
	else:
		recenter_hold = 0.0
		recenter_done = false

func head_tracking_ready() -> bool:
	# Godot registers the head tracker as "head"; /user/head is an OpenXR path.
	var tracker := XRServer.get_tracker("head") as XRPositionalTracker
	if tracker == null or not tracker.has_pose("default"):
		return false
	var pose := tracker.get_pose("default")
	return pose.has_tracking_data and pose.tracking_confidence != XRPose.XR_TRACKING_CONFIDENCE_NONE

func connected_pads() -> Array[int]:
	var pads := Input.get_connected_joypads()
	var names := {}
	for pad in pads:
		names[pad] = Input.get_joy_name(pad)
	return prefer_xbox(pads, names)

static func prefer_xbox(pads: Array[int], names: Dictionary) -> Array[int]:
	# Device IDs can change after reconnecting; a virtual HID may remain at ID 0.
	var ordered: Array[int] = pads.duplicate()
	for pad in pads:
		var pad_name := str(names.get(pad, "")).to_lower()
		if pad_name.contains("xinput") or pad_name.contains("xbox"):
			ordered.erase(pad)
			ordered.push_front(pad)
			break
	return ordered

func _process(delta: float) -> void:
	if not ready_to_walk:
		return
	runtime += delta
	metrics_time += delta
	if desktop and benchmark_seconds > 0 and runtime > 3.0 and not captured_preview:
		captured_preview = true
		capture_preview()
	if metrics_time >= 1.0:
		metrics_time = 0.0
		var rid := get_viewport().get_viewport_rid()
		var gpu := RenderingServer.viewport_get_measured_render_time_gpu(rid)
		var cpu := RenderingServer.viewport_get_measured_render_time_cpu(rid) + RenderingServer.get_frame_setup_time_cpu()
		var hz := float(xr.get("display_refresh_rate")) if xr_active else 60.0
		if hz <= 0.0:
			hz = 60.0
		var fps := Engine.get_frames_per_second()
		var mode := "両眼" if xr_active else "Desktop・片眼"
		var pads := connected_pads()
		var controller_text := "Xbox未接続" if pads.is_empty() else Input.get_joy_name(pads[0])
		if xr_active and not head_tracking_ready():
			controller_text += " / HMD追跡待ち"
		info.text = "%s | %s | %.3f m | %d FPS | GPU %.2f ms / 予算 %.2f ms\n%s\n%s\n%s" % [
			metadata.get("source", ""), mode, walker.eye_height, fps, gpu, 1000.0 / hz, controller_text, voice.microphone_label(), status]
		head_label.text = "%d FPS · GPU %.1f ms\n%s\n%s\n%s" % [fps, gpu, controller_text, voice.microphone_label(), status.left(160)]
		write_diagnostics(pads, fps, gpu)
		if samples.size() < 36000:
			samples.append({"seconds": runtime, "fps": fps, "gpu_ms": gpu, "render_cpu_ms": cpu,
				"budget_ms": 1000.0 / hz, "stereo": xr_active})
	if benchmark_seconds > 0 and runtime >= benchmark_seconds:
		get_tree().quit()

func write_diagnostics(pads: Array[int], fps: float, gpu: float) -> void:
	var controllers: Array[Dictionary] = []
	for pad in pads:
		var buttons: Array[int] = []
		for button in range(JOY_BUTTON_MAX):
			if Input.is_joy_button_pressed(pad, button):
				buttons.append(button)
		controllers.append({"id": pad, "name": Input.get_joy_name(pad), "buttons": buttons,
			"left": [axis(pad, JOY_AXIS_LEFT_X), axis(pad, JOY_AXIS_LEFT_Y)],
			"right_x": axis(pad, JOY_AXIS_RIGHT_X)})
	var file := FileAccess.open("res://diagnostics.json", FileAccess.WRITE)
	if file:
		file.store_string(JSON.stringify({"seconds": runtime, "xr": xr_active,
			"head_tracking": head_tracking_ready() if xr_active else false,
			"calibrated": walker.calibrated, "controllers": controllers,
			"active_controller": active_pad,
			"collision": collision_info, "walk_blocked": walker.last_blocked, "walk_usec": walker.walk_usec,
			"voice": voice.diagnostics(),
			"fps": fps, "gpu_ms": gpu, "position": [walker.position.x, walker.position.y, walker.position.z]}, "\t"))

func _exit_tree() -> void:
	if not samples.is_empty():
		var file := FileAccess.open("res://metrics.json", FileAccess.WRITE)
		if file:
			file.store_string(JSON.stringify({"samples": samples, "meshes": scene_meshes,
				"triangles": scene_triangles, "stereo": xr_active}, "\t"))

func capture_preview() -> void:
	await RenderingServer.frame_post_draw
	var image := get_viewport().get_texture().get_image()
	if image != null and not image.is_empty():
		image.save_png("res://preview.png")

func set_status(text: String) -> void:
	status = text

func fatal(message: String) -> void:
	info.text = message
	push_error(message)
	get_tree().quit(1)

func axis(pad: int, stick_axis: int) -> float:
	var value := Input.get_joy_axis(pad, stick_axis)
	return signf(value) * maxf(0.0, (absf(value) - 0.15) / 0.85)

func vec(value: Array) -> Vector3:
	return Vector3(value[0], value[1], value[2])
