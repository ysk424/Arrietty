extends SceneTree

func _initialize() -> void:
	call_deferred("run")

func run() -> void:
	var scene := load("res://world.glb").instantiate() as Node3D
	root.add_child(scene)
	var meshes := scene.find_children("*", "MeshInstance3D", true, false)
	for mesh in meshes:
		mesh.create_trimesh_collision()
	await physics_frame
	await physics_frame
	var query := PhysicsRayQueryParameters3D.create(Vector3(1, 3, -2), Vector3(1, -1, -2))
	var hit: Dictionary = scene.get_world_3d().direct_space_state.intersect_ray(query)
	var metadata = JSON.parse_string(FileAccess.get_file_as_string("res://scene.json"))
	var valid: bool = meshes.size() == 1 and not hit.is_empty()
	valid = valid and absf(hit.position.y - 0.2) < 0.001
	valid = valid and absf(metadata.start.position[1] - 1.7) < 0.001
	print("ARRIETTY_CONVERSION_TEST ", JSON.stringify({"passed": valid, "meshes": meshes.size(),
		"ground": str(hit.get("position")), "camera": metadata.start.position}))
	quit(0 if valid else 1)
