"""Offline engine, source conversion and voice contract checks (no API calls)."""
import os
from pathlib import Path
import subprocess
import sys
from launch import ROOT, executable, fingerprint, run_logged

env = os.environ.copy()
env.pop('OPENAI_API_KEY', None)
cache = ROOT / '.cache'
cache.mkdir(exist_ok=True)
blender = executable(None, 'ARRIETTY_BLENDER', [ROOT.parent / 'build_windows_Release_x64_vc17_Release/bin/blender.exe'])
godot = executable(None, 'ARRIETTY_GODOT', [ROOT.parent / 'godot/bin/godot.windows.editor.x86_64.exe'])
run_logged([godot, '--headless', '--xr-mode', 'off', '--fixed-fps', '90', '--path', ROOT / 'godot',
            '--script', 'res://tests/locomotion.gd'], cache / 'locomotion.log', env)
run_logged([godot, '--headless', '--xr-mode', 'off', '--path', ROOT / 'godot',
            '--script', 'res://tests/xr_input.gd'], cache / 'xr-input.log', env)
run_logged([godot, '--headless', '--xr-mode', 'off', '--path', ROOT / 'godot',
            '--script', 'res://tests/world_collision.gd'], cache / 'world-collision.log', env)
run_logged([godot, '--display-driver', 'headless', '--audio-driver', 'WASAPI', '--xr-mode', 'off',
            '--path', ROOT / 'godot', '--script', 'res://tests/microphone.gd'], cache / 'microphone-test.log', env)
subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', str(ROOT / 'tests'), '-v'], check=True, env=env)
fixture = cache / 'centimetre test.blend'
run_logged([blender, '--background', '--factory-startup', '--python-exit-code', '1', '--python',
            ROOT / 'tests/create_world.py', '--', fixture], cache / 'fixture.log', env)
subprocess.run([sys.executable, ROOT / 'tools/launch.py', fixture, '--convert-only', '--blender', blender,
                '--godot', godot], check=True, env=env)
project = cache / fingerprint(fixture, blender)
run_logged([godot, '--headless', '--xr-mode', 'off', '--path', project,
            '--script', 'res://tests/conversion.gd'], cache / 'conversion-test.log', env)
print('All offline checks passed.')
