"""Blender fixture: centimetre units, transforms, hidden collider and camera."""
import bpy
import sys
from pathlib import Path

bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.context.scene.unit_settings.system = 'METRIC'
bpy.context.scene.unit_settings.scale_length = 0.01
bpy.ops.mesh.primitive_cube_add(size=2, location=(100, 200, -10))
floor = bpy.context.object
floor.name = 'Floor'
floor.scale = (500, 500, 10)
bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
bpy.ops.mesh.primitive_cube_add(size=2, location=(100, 200, 10))
step = bpy.context.object
step.name = 'Step-colonly'
step.scale = (50, 50, 10)
step.hide_render = True
step.hide_set(True)
bpy.ops.object.camera_add(location=(100, 200, 170))
bpy.context.scene.camera = bpy.context.object
bpy.ops.wm.save_as_mainfile(filepath=str(Path(sys.argv[sys.argv.index('--') + 1]).resolve()))
