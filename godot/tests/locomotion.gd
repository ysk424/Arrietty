extends SceneTree

const Walker = preload("res://walker.gd")
var world := Node3D.new()
var walker: Node3D
var fixtures: Array[Node] = []
var failures: Array[String] = []
var checks := 0

func _initialize() -> void:
	call_deferred("run")

func check(condition: bool, message: String) -> void:
	checks += 1
	if not condition:
		failures.append(message)
		push_error(message)

func box(size: Vector3, position: Vector3, angle := 0.0) -> void:
	var body := StaticBody3D.new()
	var shape := CollisionShape3D.new()
	var geometry := BoxShape3D.new()
	geometry.size = size
	shape.shape = geometry
	body.add_child(shape)
	world.add_child(body)
	body.position = position
	body.rotation.z = angle
	fixtures.append(body)

func clear() -> void:
	for node in fixtures:
		node.queue_free()
	fixtures.clear()
	if is_instance_valid(walker):
		walker.queue_free()
	await physics_frame
	await physics_frame

func person(height: float, position: Vector3) -> void:
	walker = Walker.new()
	walker.eye_height = height
	world.add_child(walker)
	walker.position = position
	await physics_frame
	await physics_frame

func traverse(distance: float, frames := 200) -> void:
	for i in frames:
		walker.walk(Vector3(distance / frames, 0, 0))
		await physics_frame

func run() -> void:
	root.add_child(world)
	for height in [0.15, 1.5, 15.0]:
		var scale: float = height / 1.5
		box(Vector3(12, 0.2, 4) * scale, Vector3(3, -0.1, 0) * scale)
		box(Vector3(2, 0.2, 3) * scale, Vector3(3, 0.1, 0) * scale)
		await person(height, Vector3.ZERO)
		await traverse(3.0 * scale)
		check(absf(walker.position.x - 3 * scale) < 0.05 * scale, "Climb stairs at height %s" % height)
		check(absf(walker.position.y - 0.2 * scale) < 0.02 * scale, "Follow stair height %s" % height)
		await traverse(2.0 * scale)
		check(absf(walker.position.y) < 0.02 * scale, "Descend stairs at height %s" % height)
		check(is_equal_approx(walker.walking_speed / scale, 1.4), "Proportional movement")
		await clear()
	# A slope, a stacked upper floor, and an unsupported edge.
	box(Vector3(20, 0.2, 4), Vector3.ZERO, deg_to_rad(12.0))
	await person(1.5, Vector3(-4, 0, 0))
	var hit: Dictionary = walker.ground(Vector3(-4, 4, 0), Vector3(-4, -4, 0))
	walker.position = hit.position
	await traverse(8.0)
	check(walker.position.x > 3.95 and walker.position.y > 0.85, "Continuous slope ascent")
	await traverse(-8.0)
	check(walker.position.x < -3.95 and walker.position.y < -0.7, "Continuous slope descent")
	await clear()
	box(Vector3(6, 0.2, 4), Vector3(0, -0.1, 0))
	box(Vector3(6, 0.2, 4), Vector3(0, 3.0, 0))
	await person(1.5, Vector3.ZERO)
	await traverse(6.0)
	check(walker.position.x < 2.95 and walker.position.x > 2.5, "Stop at unsupported edge")
	check(absf(walker.position.y) < 0.01, "Stay on lower floor beneath bridge")
	await clear()
	# A high wall cannot be treated as a stair.
	box(Vector3(20, 0.2, 4), Vector3(0, -0.1, 0))
	box(Vector3(0.2, 4, 4), Vector3(2, 2, 0))
	await person(1.5, Vector3.ZERO)
	await traverse(4.0)
	check(walker.position.x < 1.8, "Wall blocks head path")
	# Recenter preserves the view's horizontal heading and sets requested eye height.
	walker.camera.position = Vector3(0.2, 0.9, 0.1)
	walker.camera.rotation.y = 0.7
	var heading: Vector3 = -walker.camera.global_basis.z
	walker.recenter()
	check(absf(walker.camera.global_position.y - walker.position.y - 1.5) < 0.0001, "Seated recenter height")
	check(heading.distance_to(-walker.camera.global_basis.z) < 0.0001, "Recenter does not rotate the view")
	check(heading.distance_to(-walker.global_basis.z) < 0.0001, "Current gaze defines movement front")
	walker.camera.position.y -= 0.3
	check(absf(walker.camera.global_position.y - walker.position.y - 1.2) < 0.0001, "Preserve crouching")
	await clear()
	# Physical head movement follows rising ground while keeping crouching relative.
	box(Vector3(20, 0.2, 4), Vector3.ZERO, deg_to_rad(12.0))
	await person(1.5, Vector3(0, 0.11, 0))
	walker.recenter()
	walker.xr_enabled = true
	walker.camera.position.x += 0.5
	walker.camera.position.y -= 0.2
	walker.room_scale_follow()
	check(absf(walker.position.x - 0.5) < 0.01, "Room-scale physical movement advances feet")
	check(absf(walker.camera.global_position.y - walker.position.y - 1.3) < 0.001, "Room-scale slope keeps crouch offset")
	var before: Vector3 = walker.position
	walker.room_scale_follow()
	check(walker.position.distance_to(before) < 0.01, "Physical movement is not applied twice")
	await clear()
	box(Vector3(10, 0.2, 4), Vector3(0, -0.1, 0))
	box(Vector3(2, 0.2, 4), Vector3(2, 0.1, 0))
	box(Vector3(8, 0.2, 4), Vector3(1, 1.75, 0))
	await person(1.5, Vector3.ZERO)
	await traverse(3.0)
	check(walker.position.x < 1.0, "Low ceiling prevents stepping up through it")
	walker.camera.position.y -= 0.3
	await traverse(3.0)
	check(walker.position.x > 2.9, "Crouched head can pass beneath a low ceiling")
	await clear()
	# Slightly embedded contact must allow retreat, rather than lock all directions.
	box(Vector3(20, 0.2, 4), Vector3(0, -0.1, 0))
	box(Vector3(0.2, 4, 4), Vector3(2, 2, 0))
	await person(1.5, Vector3(1.725, 0, 0))
	await traverse(-1.0)
	check(walker.position.x < 0.75, "Back away from an initially overlapping wall")
	await traverse(3.0)
	check(walker.position.x < 1.75, "Recovery still blocks walking through a wall")
	await clear()
	# Scan fragment at torso height used to trap the whole-body sweep on a valid slope.
	box(Vector3(20, 0.2, 4), Vector3.ZERO, deg_to_rad(12.0))
	box(Vector3(0.1, 0.2, 1), Vector3(0.3, 1.0, 0))
	await person(1.5, Vector3(0, 0.102, 0))
	await traverse(1.5)
	check(walker.position.x > 1.49, "Torso-height scan fragment does not trap head movement")
	check(walker.position.y > 0.4, "Ground still rises beneath the moved head")
	await traverse(-1.5)
	check(absf(walker.position.x) < 0.01 and walker.position.y < 0.11, "Return downhill through the old trap")
	await clear()
	# Real scan floors are triangle meshes with noise and overlapping patches.
	for copy in 2:
		var body := StaticBody3D.new()
		var collision := CollisionShape3D.new()
		var shape := ConcavePolygonShape3D.new()
		var faces := PackedVector3Array()
		for x in range(-20, 20):
			for z in range(-5, 5):
				var a := noisy_floor_point(x, z)
				var b := noisy_floor_point(x + 1, z)
				var c := noisy_floor_point(x, z + 1)
				var d := noisy_floor_point(x + 1, z + 1)
				faces.append_array(PackedVector3Array([a, b, c, b, d, c]))
		shape.set_faces(faces)
		collision.shape = shape
		body.add_child(collision)
		world.add_child(body)
		fixtures.append(body)
	await person(1.5, Vector3.ZERO)
	await traverse(3.0)
	check(walker.position.x > 2.95, "Forward across a noisy overlapping triangle floor")
	await traverse(-6.0)
	check(walker.position.x < -2.95, "Backward across a noisy overlapping triangle floor")
	var floor_hit: Dictionary = walker.ground(walker.position + Vector3.UP, walker.position - Vector3.UP)
	check(not floor_hit.is_empty() and absf(walker.position.y - floor_hit.position.y) < 0.02, "Noisy floor still follows ground height")
	await clear()
	print("ARRIETTY_LOCOMOTION_TEST ", JSON.stringify({"checks": checks, "failures": failures}))
	quit(0 if failures.is_empty() else 1)

func noisy_floor_point(x: int, z: int) -> Vector3:
	return Vector3(x * 0.25, x * 0.01 + 0.018 * sin(x * 1.7 + z * 0.9), z * 0.25)
