"""Convert a read-only Blender source and run Arrietty. Python stdlib only."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parents[1]


def executable(explicit, env_name, candidates):
    requested = explicit or os.environ.get(env_name)
    if requested:
        path = Path(requested).expanduser().resolve()
        if not path.is_file():
            raise ValueError(f'{env_name}: executable not found: {path}')
        return path
    for candidate in candidates:
        if candidate and Path(candidate).is_file():
            return Path(candidate).resolve()
    raise ValueError(f'Set {env_name} to the executable path.')


def fingerprint(source, blender):
    digest = hashlib.sha256()
    for value in (str(source), str(blender), str(blender.stat().st_mtime_ns)):
        digest.update(value.encode())
    # Hash the source contents: timestamps alone miss restored files.
    for path in (source, ROOT / 'tools' / 'export_blend.py'):
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
                digest.update(block)
    return digest.hexdigest()[:24]


def run_logged(command, log, env=None):
    print(f'Running {Path(command[0]).name}; log: {log}', flush=True)
    with log.open('w', encoding='utf-8') as output:
        result = subprocess.run([str(x) for x in command], stdout=output,
                                stderr=subprocess.STDOUT, env=env)
    raw = log.read_bytes()
    try:
        log_text = raw.decode('utf-8')
    except UnicodeDecodeError:
        log_text = raw.decode('cp932', errors='replace')
        log.write_text(log_text, encoding='utf-8')
    if result.returncode:
        tail = log_text[-5000:]
        raise RuntimeError(f'Exit {result.returncode}\n{tail}')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('blend', type=Path)
    parser.add_argument('--height', type=float, default=1.5)
    parser.add_argument('--blender')
    parser.add_argument('--godot')
    parser.add_argument('--microphone', help='Exact or unique partial Windows input device name')
    parser.add_argument('--desktop', action='store_true')
    parser.add_argument('--convert-only', action='store_true')
    parser.add_argument('--rebuild', action='store_true')
    parser.add_argument('--benchmark-seconds', type=int, default=0)
    args = parser.parse_args()
    if not math.isfinite(args.height) or not 0.01 <= args.height <= 1000:
        parser.error('Eye height must be between 0.01 and 1000 metres.')
    source = args.blend.expanduser().resolve(strict=True)
    if source.suffix.lower() != '.blend':
        parser.error('Specify a .blend file.')
    parent = ROOT.parent
    blender = executable(args.blender, 'ARRIETTY_BLENDER', [
        parent / 'build_windows_Release_x64_vc17_Release/bin/blender.exe', shutil.which('blender')])
    godot = executable(args.godot, 'ARRIETTY_GODOT', [
        parent / 'godot/bin/godot.windows.editor.x86_64.exe', shutil.which('godot')])
    cache = ROOT / '.cache' / fingerprint(source, blender)
    cache.mkdir(parents=True, exist_ok=True)
    # The project lives with its imported GLB. Never put API credentials here.
    for path in (ROOT / 'godot').rglob('*'):
        if path.is_file() and '.godot' not in path.parts and path.suffix != '.uid':
            dest = cache / path.relative_to(ROOT / 'godot')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
    if args.rebuild or not (cache / 'scene.json').exists() or not (cache / 'world.glb').exists():
        export_env = os.environ.copy()
        export_env.pop('OPENAI_API_KEY', None)
        run_logged([blender, '--background', '--factory-startup', '--disable-autoexec',
                    source, '--python-exit-code', '1', '--python', ROOT / 'tools/export_blend.py',
                    '--', cache], cache / 'convert.log', export_env)
    clean_env = os.environ.copy()
    # The engine and Blender never need the API key; only the Python voice worker does.
    clean_env.pop('OPENAI_API_KEY', None)
    import_settings = cache / 'world.glb.import'
    if import_settings.exists():
        settings = import_settings.read_text(encoding='utf-8')
        settings = re.sub(r'meshes/generate_lods=\w+', 'meshes/generate_lods=false', settings)
        settings = re.sub(r'meshes/force_disable_compression=\w+', 'meshes/force_disable_compression=true', settings)
        import_settings.write_text(settings, encoding='utf-8')
    run_logged([godot, '--headless', '--xr-mode', 'off', '--path', cache, '--import'], cache / 'import.log', clean_env)
    if 'SCRIPT ERROR:' in (cache / 'import.log').read_text(encoding='utf-8', errors='replace'):
        raise RuntimeError(f'Godot script import failed; see {cache / "import.log"}')
    print(f'Converted project: {cache}', flush=True)
    if args.convert_only:
        return 0
    from voice_service import make_server
    token = secrets.token_urlsafe(32)
    server = make_server(token)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    clean_env['ARRIETTY_VOICE_URL'] = f'http://127.0.0.1:{server.server_port}'
    clean_env['ARRIETTY_VOICE_TOKEN'] = token
    if args.microphone:
        clean_env['ARRIETTY_MICROPHONE'] = args.microphone
    command = [str(godot), '--path', str(cache)]
    if args.desktop:
        command.extend(['--xr-mode', 'off'])
    command.extend(['--', '--height', str(args.height)])
    if args.desktop:
        command.append('--desktop')
    if args.benchmark_seconds:
        command.extend(['--benchmark-seconds', str(args.benchmark_seconds)])
    try:
        run_logged(command, cache / 'runtime.log', clean_env)
        return 0
    finally:
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (ValueError, OSError, RuntimeError) as error:
        print(f'Arrietty: {error}', file=sys.stderr)
        sys.exit(1)
