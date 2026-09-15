extends SceneTree
## Exercise the actual application's input path with a registered Godot head tracker.

const Main = preload("res://main.gd")
var failures: Array[String] = []
var checks := 0

class TestApp extends Main:
	func connected_pads() -> Array[int]:
		return [0]

class TestWalker extends Node3D:
	var calibrated := false
	var moves := 0
	var turns := 0
	var walking_speed := 1.4
	var last_motion := Vector3.ZERO
	func recenter() -> void:
		calibrated = true
	func turn(_angle: float) -> void:
		turns += 1
	func room_scale_follow() -> void:
		pass
	func walk(motion: Vector3) -> void:
		last_motion = motion
		if motion.length() > 0.01:
			moves += 1

class TestVoice extends Node:
	var begins := 0
	var finishes := 0
	var cancels := 0
	var changes := 0
	func begin() -> void:
		begins += 1
	func finish() -> void:
		finishes += 1
	func cancel() -> void:
		cancels += 1
	func cycle_microphone() -> void:
		changes += 1

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)
		push_error(message)

func button(index: int, pressed: bool) -> void:
	var event := InputEventJoypadButton.new()
	event.device = 0
	event.button_index = index
	event.pressed = pressed
	Input.parse_input_event(event)
	Input.flush_buffered_events()

func axis(index: int, value: float) -> void:
	var event := InputEventJoypadMotion.new()
	event.device = 0
	event.axis = index
	event.axis_value = value
	Input.parse_input_event(event)
	Input.flush_buffered_events()

func run() -> void:
	check(Main.prefer_xbox([0, 1], {0: "0xbeef/0x046d", 1: "XInput Controller"}) == [1, 0],
		"Reconnected Xbox is preferred over a virtual device at ID 0")
	check(Main.prefer_xbox([3, 7], {3: "Virtual HID", 7: "Xbox Wireless Controller"}) == [7, 3],
		"Xbox selection does not depend on device ID")
	check(Main.prefer_xbox([], {}) == [], "Disconnected controller list is supported")
	# Do not add Main to the tree: no scene load, HMD, microphone or network is used.
	var app := TestApp.new()
	var walker := TestWalker.new()
	root.add_child(walker)
	var voice := TestVoice.new()
	app.walker = walker
	app.voice = voice
	app.xr_active = true
	app.ready_to_walk = true
	button(JOY_BUTTON_X, true)
	app._physics_process(0.1)
	check(voice.begins == 1, "X remains available without head tracking")
	button(JOY_BUTTON_X, false)
	app._physics_process(0.1)
	check(voice.finishes == 1, "X release is processed without head tracking")
	button(JOY_BUTTON_B, true)
	app._physics_process(0.1)
	check(voice.cancels == 1, "B remains available without head tracking")
	button(JOY_BUTTON_B, false)
	button(JOY_BUTTON_Y, true)
	app._physics_process(0.1)
	app._physics_process(0.1)
	check(voice.changes == 1, "Y cycles microphone once per press without head tracking")
	button(JOY_BUTTON_Y, false)
	axis(JOY_AXIS_LEFT_Y, -1.0)
	app._physics_process(0.1)
	check(walker.moves == 0 and not walker.calibrated, "Movement waits for a valid head pose")
	var head := XRPositionalTracker.new()
	head.type = XRServer.TRACKER_HEAD
	head.name = "head"
	head.set_pose("default", Transform3D.IDENTITY, Vector3.ZERO, Vector3.ZERO, XRPose.XR_TRACKING_CONFIDENCE_HIGH)
	XRServer.add_tracker(head)
	check(app.head_tracking_ready(), "Recognize Godot's head tracker")
	app._physics_process(1.1)
	check(walker.calibrated, "Head pose allows initial calibration")
	app._physics_process(0.1)
	check(walker.moves == 1, "Xbox stick reaches locomotion with an HMD")
	check(walker.last_motion.z < 0.0, "Left stick up moves forward")
	axis(JOY_AXIS_LEFT_Y, 1.0)
	app._physics_process(0.1)
	check(walker.last_motion.z > 0.0, "Left stick down moves backward")
	axis(JOY_AXIS_RIGHT_X, 1.0)
	app._physics_process(0.1)
	check(walker.turns == 1, "Xbox right stick turns with an HMD")
	head.set_pose("default", Transform3D.IDENTITY, Vector3.ZERO, Vector3.ZERO, XRPose.XR_TRACKING_CONFIDENCE_NONE)
	check(not app.head_tracking_ready(), "A stale pose with no tracking confidence is rejected")
	var moves_before: int = walker.moves
	app._physics_process(0.1)
	check(walker.moves == moves_before, "Lost tracking pauses movement")
	XRServer.remove_tracker(head)
	axis(JOY_AXIS_LEFT_Y, 0.0)
	axis(JOY_AXIS_RIGHT_X, 0.0)
	app.info.free()
	app.head_label.free()
	app.free()
	voice.free()
	walker.free()
	print("ARRIETTY_XR_INPUT_TEST ", JSON.stringify({"checks": checks, "failures": failures}))
	quit(0 if failures.is_empty() else 1)
