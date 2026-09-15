"""Opt-in paid Whisper + vision GPT + TTS test. Uses synthetic speech, no mic."""
import argparse
import os
from pathlib import Path
import secrets
import threading
from launch import ROOT, executable, run_logged
from voice_service import OpenAI, make_server

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('converted_project', type=Path)
args = parser.parse_args()
project = args.converted_project.resolve()
api = OpenAI()
wav = ROOT / '.cache' / 'synthetic-question.wav'
wav.write_bytes(api.speak('この景色を簡単に説明してください。'))
token = secrets.token_urlsafe(32)
server = make_server(token)
threading.Thread(target=server.serve_forever, daemon=True).start()
env = os.environ.copy()
env.pop('OPENAI_API_KEY', None)
env['ARRIETTY_VOICE_URL'] = f'http://127.0.0.1:{server.server_port}'
env['ARRIETTY_VOICE_TOKEN'] = token
env['ARRIETTY_TEST_WAV'] = str(wav)
godot = executable(None, 'ARRIETTY_GODOT', [ROOT.parent / 'godot/bin/godot.windows.editor.x86_64.exe'])
try:
    run_logged([godot, '--xr-mode', 'off', '--path', project, '--script', 'res://tests/voice_live.gd',
                '--', '--desktop'], ROOT / '.cache' / 'voice-live.log', env)
finally:
    server.shutdown()
    server.server_close()
print('Live voice check passed. Report:', project / 'voice-test.json')
