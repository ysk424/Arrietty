extends SceneTree
## Run against the locally converted san_marino_ground.blend cache, no HMD/audio.

const Walker = preload("res://walker.gd")
const WorldCollision = preload("res://world_collision.gd")
var failures: Array[String] = []

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var world := load("res://world.glb").instantiate() as Node3D
	root.add_child(world)
	var collision_info := WorldCollision.prepare(world)
	var walker := Walker.new()
	root.add_child(walker)
	await physics_frame
	await physics_frame
	var start := Vector3(48.733875, 3.213962, 34.061604)
	var direction := Vector3(-0.319219, 0, -0.947681).normalized()
	walker.position = start
	var records: Array[Dictionary] = []
	for sign_direction in [1, -1]:
		var before := walker.position
		var total_usec := 0
		var max_usec := 0
		for frame in 180:
			walker.walk(direction * sign_direction * 1.4 / 90.0)
			total_usec += walker.walk_usec
			max_usec = maxi(max_usec, walker.walk_usec)
		var distance := Vector2(walker.position.x - before.x, walker.position.z - before.z).length()
		if distance < 2.75:
			failures.append("Movement stopped: %s, %.3f m, %s" % [sign_direction, distance, walker.last_blocked])
		var ground_hit := walker.support_at(walker.position, walker.position.y)
		if ground_hit.is_empty() or absf(walker.position.y - ground_hit.position.y) > 0.005:
			failures.append("Head did not follow ground")
		if absf(walker.camera.global_position.y - walker.position.y - 1.5) > 0.001:
			failures.append("Eye height changed relative to ground")
		records.append({"direction": sign_direction, "distance_m": distance,
			"height_change_m": walker.position.y - before.y, "mean_walk_usec": total_usec / 180.0,
			"max_walk_usec": max_usec, "position": str(walker.position)})
	if walker.position.distance_to(start) > 0.02:
		failures.append("Downhill return did not reach original position")
	print("ARRIETTY_STREET_TEST ", JSON.stringify({"collision": collision_info, "records": records, "failures": failures}))
	quit(0 if failures.is_empty() else 1)
