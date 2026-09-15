"""Executed by background Blender. Export a static snapshot in metres."""
import json
from pathlib import Path
import sys
import bpy
from mathutils import Vector

out = Path(sys.argv[sys.argv.index('--') + 1])
scene = bpy.context.scene
units = scene.unit_settings.scale_length


def godot_vector(v):
    return [v.x * units, v.z * units, -v.y * units]


camera = scene.camera
start = {'position': [0, 1.5, 0], 'forward': [0, 0, -1], 'camera': None}
if camera:
    start = {'position': godot_vector(camera.matrix_world.translation),
             'forward': godot_vector(camera.matrix_world.to_quaternion() @ Vector((0, 0, -1))),
             'camera': camera.name}
markers = [godot_vector(o.matrix_world.translation) for o in scene.objects
           if o.name.lower().startswith('walkstart')]

# glTF's exporter uses Blender coordinates, not scene.unit_settings.scale_length.
# Put exported roots under a metre-scale parent (without modifying the original file).
objects = [o for o in scene.objects if (not o.hide_render or '-colonly' in o.name.lower())
           and o.type in {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META', 'EMPTY', 'LIGHT'}]
for collection in bpy.data.collections:
    collection.hide_viewport = False
    collection.hide_render = False


def enable_layers(layer):
    layer.exclude = False
    layer.hide_viewport = False
    for child in layer.children:
        enable_layers(child)


enable_layers(bpy.context.view_layer.layer_collection)
for obj in objects:
    obj.hide_set(False)
    obj.hide_viewport = False
    obj.hide_render = False
bpy.ops.object.select_all(action='DESELECT')
for obj in objects:
    obj.select_set(True)
# Scale all root transforms, including children of omitted cameras/parents.
root = bpy.data.objects.new('Arrietty metres', None)
scene.collection.objects.link(root)
for obj in objects:
    if obj.parent not in objects:
        world = obj.matrix_world.copy()
        obj.parent = root
        obj.matrix_world = world
root.scale = (units, units, units)
root.select_set(True)
bpy.context.view_layer.update()
result = bpy.ops.export_scene.gltf(
    filepath=str(out / 'world.glb'), export_format='GLB', use_selection=True,
    export_apply=True, export_extras=True, export_cameras=False, export_lights=True,
    export_animations=False, export_yup=True, export_gn_mesh=True,
    export_import_convert_lighting_mode='COMPAT')
if 'FINISHED' not in result:
    raise RuntimeError(f'glTF export failed: {result}')
metadata = {'source': Path(bpy.data.filepath).name, 'unit_scale': units,
            'start': start, 'walk_starts': markers, 'blender': bpy.app.version_string,
            'warnings': ['Static glTF snapshot: arbitrary Blender shaders, volumes and simulations may need baking.']}
(out / 'scene.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
print('ARRIETTY_EXPORT_COMPLETE', len(objects), 'objects', json.dumps(start))
