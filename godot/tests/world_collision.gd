extends SceneTree

const WorldCollision = preload("res://world_collision.gd")

func _initialize() -> void:
	var world := Node3D.new()
	var scan := MeshInstance3D.new()
	scan.mesh = BoxMesh.new()
	world.add_child(scan)
	var authored := StaticBody3D.new()
	world.add_child(authored)
	var prepared := WorldCollision.prepare(world)
	assert(prepared.mode == "authored" and prepared.bodies == 1)
	assert(scan.get_child_count() == 0, "Do not add raw scan collisions alongside authored ground")
	authored.free()
	prepared = WorldCollision.prepare(world)
	assert(prepared.mode == "generated" and prepared.bodies == 1)
	assert(scan.find_children("*", "StaticBody3D", true, false).size() == 1)
	world.free()
	print("ARRIETTY_WORLD_COLLISION_TEST passed")
	quit()
