extends SceneTree
## Explicit opt-in paid integration check, using synthetic speech, never a microphone.

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var app := load("res://main.tscn").instantiate() as Node3D
	root.add_child(app)
	while not app.ready_to_walk:
		await process_frame
	await process_frame
	var wav := AudioStreamWAV.load_from_file(OS.get_environment("ARRIETTY_TEST_WAV"))
	app.voice.speaker.volume_db = -80.0
	app.voice.submit(wav)
	var response = await app.voice.request.request_completed
	var payload = JSON.parse_string(response[3].get_string_from_utf8())
	var valid: bool = response[0] == HTTPRequest.RESULT_SUCCESS and response[1] == 200
	valid = valid and payload is Dictionary and payload.has("audio") and payload.has("answer")
	if valid:
		var audio := AudioStreamWAV.load_from_buffer(Marshalls.base64_to_raw(payload.audio))
		valid = audio != null and audio.get_length() > 0.2
	var output := FileAccess.open("res://voice-test.json", FileAccess.WRITE)
	output.store_string(JSON.stringify({"passed": valid, "code": response[1],
		"transcript": payload.get("transcript", "") if payload is Dictionary else "",
		"answer": payload.get("answer", "") if payload is Dictionary else ""}, "\t"))
	print("ARRIETTY_VOICE_LIVE_TEST passed=", valid)
	quit(0 if valid else 1)
