extends RefCounted
## Authored collision geometry is authoritative when provided by the scene.

static func prepare(world: Node3D) -> Dictionary:
	var authored := world.find_children("*", "StaticBody3D", true, false)
	if not authored.is_empty():
		return {"mode": "authored", "bodies": authored.size()}
	var count := 0
	for mesh in world.find_children("*", "MeshInstance3D", true, false):
		if mesh.mesh == null or mesh.name.to_lower().contains("visual only") or mesh.get_meta("arrietty_collision", true) == false:
			continue
		mesh.create_trimesh_collision()
		count += 1
	return {"mode": "generated", "bodies": count}
