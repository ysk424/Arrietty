extends SceneTree
## Exercise the real recording bus using a synthetic tone. No microphone or API use.

const Voice = preload("res://voice.gd")
var failures: Array[String] = []
var checks := 0

class TestVoice extends Voice:
	var captured: AudioStreamWAV
	func submit(audio: AudioStreamWAV) -> void:
		captured = audio

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)
		push_error(message)

func run() -> void:
	var devices := PackedStringArray(["Default", "Microphone (VIVE Pro)", "Microphone (USB)"])
	check(Voice.match_microphone(devices, "VIVE Pro") == devices[1], "Select headset by partial name")
	check(Voice.match_microphone(devices, "usb") == devices[2], "Case insensitive microphone selection")
	check(Voice.match_microphone(devices, "Microphone").is_empty(), "Ambiguous device name is rejected")
	check(Voice.match_microphone(devices, "missing").is_empty(), "Missing requested microphone is not silently substituted")
	var voice := TestVoice.new()
	voice.voice_url = "http://127.0.0.1:1"
	var buses_before := AudioServer.bus_count
	root.add_child(voice)
	check(not voice.microphone.playing, "Microphone is idle before PTT")
	var tone := AudioStreamWAV.new()
	tone.format = AudioStreamWAV.FORMAT_16_BITS
	tone.mix_rate = 48000
	var samples := PackedByteArray()
	samples.resize(48000 * 2)
	for i in 48000:
		samples.encode_s16(i * 2, roundi(sin(i * TAU * 440 / 48000) * 16000))
	tone.data = samples
	voice.microphone.stream = tone
	voice.begin()
	await create_timer(0.65).timeout
	voice.finish()
	check(voice.captured != null, "PTT captures audio through the real audio bus")
	if voice.captured != null:
		var peak := 0
		var recorded: PackedByteArray = voice.captured.data
		for i in range(0, recorded.size(), 2):
			peak = maxi(peak, absi(recorded.decode_s16(i)))
		check(peak > 14000, "Recording retains signal through the muted monitor")
		check(voice.peak_db > -12, "Live meter sees the input signal")
		check(voice.last_recording.seconds > 0.3, "Record duration and byte diagnostics")
		var encoded := Voice.wav_bytes(voice.captured)
		check(encoded.decode_u32(40) == recorded.size(), "Submission WAV preserves recorded PCM")
	check(AudioServer.is_bus_mute(AudioServer.get_bus_index(voice.monitor_bus)), "Microphone monitoring stays silent")
	check(not voice.microphone.playing and not voice.recording, "PTT release stops audio input")
	voice.free()
	check(AudioServer.bus_count == buses_before, "Recording buses are cleaned up")
	print("ARRIETTY_MICROPHONE_TEST ", JSON.stringify({"checks": checks, "failures": failures}))
	quit(0 if failures.is_empty() else 1)
