extends Node3D
## Foot position is the body origin. All distances below are in world metres.

var eye_height := 1.5
var size_factor := 1.0
var step_height := 0.25
var radius := 0.18
var walking_speed := 1.4
var origin: XROrigin3D
var camera: Camera3D
var xr_enabled := false
var calibrated := false
var last_blocked := ""
var walk_usec := 0

func _ready() -> void:
	configure(eye_height)
	origin = XROrigin3D.new()
	add_child(origin)
	if xr_enabled:
		camera = XRCamera3D.new()
	else:
		camera = Camera3D.new()
		camera.position.y = eye_height
	origin.add_child(camera)
	camera.current = true
	camera.near = maxf(0.001, 0.03 * size_factor)
	camera.far = maxf(2000.0, eye_height * 100.0)
	if xr_enabled:
		origin.world_scale = size_factor

func configure(height_metres: float) -> void:
	eye_height = height_metres
	size_factor = eye_height / 1.5
	step_height = 0.25 * size_factor
	radius = 0.18 * size_factor
	walking_speed = 1.4 * size_factor

func ground(from: Vector3, to: Vector3) -> Dictionary:
	var query := PhysicsRayQueryParameters3D.create(from, to, 1)
	query.hit_back_faces = false
	var hit := get_world_3d().direct_space_state.intersect_ray(query)
	if not hit.is_empty() and hit.normal.dot(Vector3.UP) >= cos(deg_to_rad(50.0)):
		return hit
	return {}

func support_at(point: Vector3, reference_y: float) -> Dictionary:
	# A short ray relative to the current floor cannot jump to a roof above us.
	var tolerance := 0.005 * size_factor
	return ground(Vector3(point.x, reference_y + step_height + tolerance, point.z),
		Vector3(point.x, reference_y - step_height - tolerance, point.z))

func walk(displacement: Vector3) -> void:
	var started := Time.get_ticks_usec()
	last_blocked = ""
	displacement.y = 0.0
	# Move horizontally, then match the floor at the destination in the same frame.
	# No full-body sweep: noisy scan triangles around the legs cannot pin the view.
	if displacement.length_squared() < 0.00000001 * size_factor * size_factor:
		walk_usec = Time.get_ticks_usec() - started
		return
	displacement = displacement.limit_length(radius * 0.5 * 64.0)
	var count := maxi(1, ceili(displacement.length() / (radius * 0.5)))
	count = mini(count, 64)
	var increment := displacement / count
	for index in count:
		var hit := support_at(global_position + increment, global_position.y)
		if hit.is_empty():
			last_blocked = "no_ground_or_step_too_high"
			break
		var target: Vector3 = hit.position
		var ahead := target + increment.normalized() * radius * 0.65
		if support_at(ahead, target.y).is_empty():
			last_blocked = "ground_edge"
			break
		var head := camera.global_position
		var horizontal_head := head + increment
		var destination_head := head + target - global_position
		# Check only the head's path against the chosen collision geometry.
		# Headroom is based on the actual tracked eye position, including crouching.
		if head_path_blocked(head, horizontal_head + increment.normalized() * radius):
			last_blocked = "head_wall"
			break
		if head_path_blocked(horizontal_head, destination_head):
			last_blocked = "head_ceiling"
			break
		global_position = target
	walk_usec = Time.get_ticks_usec() - started

func head_path_blocked(from: Vector3, to: Vector3) -> bool:
	if from.distance_squared_to(to) < 0.00000001 * size_factor * size_factor:
		return false
	var query := PhysicsRayQueryParameters3D.create(from, to, 1)
	# Exit an existing contact; only incoming surfaces should block a new move.
	query.hit_back_faces = false
	return not get_world_3d().direct_space_state.intersect_ray(query).is_empty()

func room_scale_follow() -> void:
	if not xr_enabled or not calibrated:
		return
	var head_offset := camera.global_position - global_position
	head_offset.y = 0.0
	# Consume physical horizontal motion once. Preserve physical vertical head motion.
	origin.global_position -= head_offset
	walk(head_offset)

func recenter() -> void:
	var old_origin := origin.global_transform
	var forward := -camera.global_basis.z
	forward.y = 0.0
	if forward.length_squared() > 0.001:
		rotation.y = atan2(-forward.x, -forward.z)
	origin.global_transform = old_origin
	var offset := camera.global_position - global_position
	origin.global_position += Vector3(-offset.x, eye_height - offset.y, -offset.z)
	calibrated = true

func turn(angle: float) -> void:
	rotate_y(angle)
