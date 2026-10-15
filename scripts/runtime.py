"""Verified inert runtime assets; native tools acquire files and authorize execution."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import uuid

from maintenance import require, fields, read_json
from updates import archive_files, identity_file
from support_bundle import emit as support_event

ROOT = Path(__file__).resolve().parents[1]
LAYERS = {'core', 'capture', 'images', 'livedune-node'}
PLATFORMS = {'macos-arm64', 'windows-x64'}
IMPORTS = {'capture': ['playwright', 'pyee', 'greenlet', 'typing_extensions'], 'images': ['PIL', 'numpy']}


def inventory_json(path):
    # Runtime inventories are larger than workflow records; do not widen the shared private-record limit.
    require(path.stat().st_size <= 8 * 1024 * 1024, 'runtime_inventory_size')
    with path.open('rb') as stream: raw = stream.read(8 * 1024 * 1024 + 1)
    require(len(raw) <= 8 * 1024 * 1024, 'runtime_inventory_size')
    return json.loads(raw)


def host_platform():
    return {('Darwin', 'arm64'): 'macos-arm64', ('Windows', 'AMD64'): 'windows-x64',
            ('Windows', 'x86_64'): 'windows-x64'}.get((platform.system(), platform.machine()), 'unsupported')


def host_requirements():
    """First test profiles: macOS14+ arm64, Windows11+ x64; server/other CPU builds are unverified."""
    target = host_platform()
    require(target in PLATFORMS, 'runtime_unsupported_host')
    if target == 'macos-arm64':
        major = platform.mac_ver()[0].split('.')[0]
        require(major.isdigit() and int(major) >= 14, 'runtime_macos_too_old')
    else:
        require(sys.platform == 'win32' and sys.getwindowsversion().build >= 22000, 'runtime_windows_too_old')
    return target


def needed_layers(capabilities):
    require(isinstance(capabilities, list) and all(isinstance(x, str) for x in capabilities), 'runtime_capabilities')
    layers = {'core'}
    for name in capabilities:
        if name == 'livedune': layers.add('livedune-node')
        elif name.startswith(('vk-', 'instagram-', 'threads-', 'tiktok-')): layers.add('capture')
        elif name.startswith(('telegram-', 'max-')): layers.add('images')
        elif name != 'google': raise ValueError('runtime_unknown_capability')
    return sorted(layers)


def boundary(path, protected=()):
    path = Path(path).expanduser()
    require(not path.is_symlink(), 'runtime_symlink')
    path = path.resolve()
    for root in [ROOT, *protected]:
        root = Path(root).resolve()
        require(not path.is_relative_to(root) and not root.is_relative_to(path), 'runtime_boundary')
    return path


def stage(delivery, downloads, output, target, layers, protected=()):
    """New inert directory only. No download, install, subprocess or pointer replacement."""
    operation = str(uuid.uuid4()); support_event('setup', 'stage', 'started', operation=operation)
    fields(delivery, {'schema_version', 'runtime_id', 'platform', 'assets'}, 'runtime_delivery')
    require(delivery['schema_version'] == 1 and delivery['platform'] == target and target in PLATFORMS, 'runtime_platform')
    require(re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,79}', delivery['runtime_id']) is not None, 'runtime_identity')
    require(set(layers) <= LAYERS and 'core' in layers and set(downloads) == set(layers), 'runtime_layers')
    output = boundary(output, protected); require(not output.exists(), 'runtime_exists')
    payload, executables = {}, set()
    for layer in layers:
        asset = delivery['assets'][layer]
        fields(asset, {'filename', 'size', 'sha256'} | ({'bootstrap_receipt_sha256'} if 'bootstrap_receipt_sha256' in asset else set()), 'runtime_asset')
        path = Path(downloads[layer])
        require(path.name == asset['filename'] and not path.is_symlink() and path.is_file(), 'runtime_asset_path')
        require(type(asset['size']) is int and 0 < asset['size'] <= 512 * 1024 * 1024
                and path.stat().st_size == asset['size'] and identity_file(path) == asset['sha256'], 'runtime_checksum')
        raw = path.read_bytes(); entries = archive_files(raw, max_bytes=512 * 1024 * 1024, binary=True)
        if 'runtime-receipt.json' in entries:
            bootstrap_raw = entries.pop('runtime-receipt.json')
            require(layer == 'core' and hashlib.sha256(bootstrap_raw).hexdigest() == asset.get('bootstrap_receipt_sha256'), 'runtime_bootstrap_receipt')
            require(json.loads(bootstrap_raw)['files'] == {n: hashlib.sha256(v).hexdigest() for n, v in entries.items()}, 'runtime_bootstrap_files')
        key = 'manifests/' + layer + '.json'; require(key in entries, 'runtime_manifest_missing')
        manifest = json.loads(entries[key].decode('utf-8'))
        fields(manifest, {'runtime_id', 'platform', 'layer', 'files', 'executables', 'versions'}, 'runtime_manifest')
        require((manifest['runtime_id'], manifest['platform'], manifest['layer']) ==
                (delivery['runtime_id'], target, layer), 'runtime_manifest_identity')
        require({n: hashlib.sha256(v).hexdigest() for n, v in entries.items() if n != key} == manifest['files'], 'runtime_files')
        require(set(manifest['executables']) <= set(manifest['files']), 'runtime_executables')
        for name, data in entries.items():
            require(name not in payload or payload[name] == data, 'runtime_layer_collision')
            payload[name] = data
        executables.update(manifest['executables'])
    require(sum(map(len, payload.values())) <= 768 * 1024 * 1024, 'runtime_total_size')
    output.mkdir(mode=0o700, parents=True)
    for name, data in payload.items():
        path = output / name; path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        with path.open('xb') as stream: stream.write(data)
        path.chmod(0o600)  # Execution requires a separate native permission, even for a checked asset.
    receipt = {'schema_version': 1, 'runtime_id': delivery['runtime_id'], 'platform': target,
               'layers': sorted(layers), 'files': {n: hashlib.sha256(v).hexdigest() for n, v in payload.items()},
               'executables': sorted(executables), 'status': 'STAGED_NOT_INSTALLED'}
    record = output / 'runtime-receipt.json'
    record.write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')
    support_event('setup', 'stage', 'finished', 'success', operation=operation)
    return {**receipt, 'receipt_sha256': identity_file(record)}


def verify(root, required=(), expected_receipt_sha256=None):
    root = boundary(root)
    if expected_receipt_sha256 is not None:
        require(identity_file(root / 'runtime-receipt.json') == expected_receipt_sha256, 'runtime_receipt_changed')
    receipt = inventory_json(root / 'runtime-receipt.json')
    require(receipt['schema_version'] == 1 and set(required) <= set(receipt['layers']), 'runtime_missing_layer')
    observed = {}
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'runtime_symlink')
        if path.is_file() and path != root / 'runtime-receipt.json': observed[path.relative_to(root).as_posix()] = identity_file(path)
    require(observed == receipt['files'], 'runtime_changed')
    return receipt


def probe(root, expected_receipt_sha256, *, execution_authorized=False):
    require(execution_authorized is True, 'runtime_execution_permission')
    operation = str(uuid.uuid4()); support_event('setup', 'validation', 'started', operation=operation)
    require(isinstance(expected_receipt_sha256, str) and re.fullmatch('[0-9a-f]{64}', expected_receipt_sha256), 'runtime_trusted_receipt')
    root = Path(root).resolve(); receipt = verify(root, expected_receipt_sha256=expected_receipt_sha256)
    require(receipt['platform'] == host_requirements(), 'runtime_wrong_host')
    python = root / ('python/python.exe' if receipt['platform'] == 'windows-x64' else 'python/bin/python3')
    for name in receipt['executables']: (root / name).chmod(0o700)
    modules = sorted({'tzdata', *{m for layer in receipt['layers'] for m in IMPORTS.get(layer, [])}})
    # Only a reviewed, immutable runtime is run; no candidate script or raw error is imported as instructions.
    code = 'import sys,json,importlib,importlib.metadata as m;sys.path.insert(0,sys.argv[1]);mods=json.loads(sys.argv[2]);[importlib.import_module(n) for n in mods];print(json.dumps({"python":sys.version.split()[0],"modules":mods,"versions":{("Pillow" if n=="PIL" else n):m.version("Pillow" if n=="PIL" else n) for n in mods}}))'
    result = subprocess.run([str(python), '-I', '-B', '-c', code, str(root / 'site'), json.dumps(modules)],
                            capture_output=True, text=True, timeout=45, env={k: v for k, v in os.environ.items() if not k.startswith('PYTHON')})
    require(result.returncode == 0, 'runtime_probe_failed')
    value = json.loads(result.stdout); require(value['modules'] == modules, 'runtime_probe_result')
    expected = read_json(root / 'manifests/core.json')['versions']
    require(value['python'] == expected['python'] and all(expected[n] == v for n, v in value['versions'].items()), 'runtime_version_mismatch')
    if 'livedune-node' in receipt['layers']:
        node = root / ('node/node.exe' if receipt['platform'] == 'windows-x64' else 'node/bin/node')
        run = subprocess.run([str(node), '--version'], capture_output=True, text=True, timeout=15)
        require(run.returncode == 0 and run.stdout.strip() == 'v' + expected['node'], 'runtime_node_mismatch')
        value['node'] = expected['node']
    support_event('setup', 'validation', 'finished', 'success', operation=operation,
                  program_versions={'python': value['python'], **{n.lower(): v for n, v in value['versions'].items()},
                                    **({'node': value['node']} if 'node' in value else {})})
    return {'status': 'LOCAL_RUNTIME_PROBE_PASS', **value, 'native_windows': receipt['platform'] == 'windows-x64'}


def execution_plan(root, receipt_hash, source_root, source_identity, script, arguments, *, browser=None):
    """Return argv for a verified package script; the native executor still checks authority."""
    from check_package import identity
    root = Path(root).resolve(); receipt = verify(root, expected_receipt_sha256=receipt_hash)
    require(receipt['platform'] == host_requirements(), 'runtime_wrong_host')
    source_root = Path(source_root).resolve(); script = Path(script).resolve()
    require(identity(source_root) == source_identity and script.is_relative_to(source_root)
            and script.is_file() and script.suffix == '.py', 'runtime_script_identity')
    require(isinstance(arguments, list) and all(isinstance(v, str) for v in arguments), 'runtime_arguments')
    require(browser in {None, 'chrome', 'chromium'}, 'browser_channel')
    python = root / ('python/python.exe' if receipt['platform'] == 'windows-x64' else 'python/bin/python3')
    code = 'import runpy,sys;sys.path.insert(0,sys.argv.pop(1));script=sys.argv.pop(1);sys.path.insert(0,__import__("os").path.dirname(script));sys.argv[0]=script;runpy.run_path(script,run_name="__main__")'
    environment = {'PYTHONPATH': str(root / 'site'), 'PYTHONNOUSERSITE': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    if browser: environment['REPORT_KIT_BROWSER_CHANNEL'] = browser
    return {'command': [str(python), '-I', '-B', '-c', code, str(root / 'site'), str(script), *arguments],
            'environment': environment, 'remove_environment': ['PYTHONHOME'],
            'execution_authorized': False, 'limits': 'Native approval, source scope, queue and account authorization remain required.'}


def browser_plan(channel, observed, *, install_consent=False):
    require(channel in {'chrome', 'chromium'}, 'browser_channel')
    require(observed in {'working', 'missing', 'incompatible', 'policy_denied'}, 'browser_observation')
    if observed == 'working': return {'action': 'USE_VERIFIED_BROWSER', 'notify': False}
    if observed == 'policy_denied': return {'action': 'CONTACT_IT', 'message': 'Организация запрещает управление браузером. Нужна помощь вашей ИТ-службы.'}
    if channel == 'chrome': return {'action': 'OFFER_CHROME_OR_REQUIRED_CHROMIUM', 'message': 'Подходящий браузер пока недоступен. Можно установить Chrome или подготовить отдельный браузер для этой задачи.'}
    return {'action': 'NATIVE_INSTALL_PLAYWRIGHT_BROWSER' if install_consent else 'ASK_BROWSER_CONSENT',
            'message': 'Для этого скилла нужен отдельный браузер Playwright Chromium. Разрешите подготовить его? Ваш обычный Chrome и его настройки не изменятся.',
            'command_for_agent_only': ['-m', 'playwright', 'install', 'chromium'] if install_consent else None}


def client_preflight(workspace, candidate_agent, clients):
    """Optional new runtime contract; the original client/profile guard remains authoritative."""
    recipe = Path(candidate_agent) / 'assets/runtime-recipe.json'
    if not recipe.exists(): return
    selection = Path(workspace) / 'runtime-selection.json'
    proposed = Path(workspace) / 'runtime-candidate.json'
    chosen = read_json(proposed if proposed.exists() else selection)
    fields(chosen, {'runtime_id', 'root', 'receipt_sha256'}, 'runtime_selection')
    require(chosen['runtime_id'] == read_json(recipe)['runtime_id'], 'runtime_candidate_incompatible')
    required = set(needed_layers([skill for client in clients.values() for skill in client['required_skills']]))
    receipt = verify(chosen['root'], required, chosen['receipt_sha256'])
    require(receipt['runtime_id'] == chosen['runtime_id'] and receipt['platform'] == host_requirements(), 'runtime_selection_identity')
    return {'candidate': chosen, 'previous': read_json(selection) if selection.exists() else None,
            'selection_changed': False, 'limits': 'Native activation must preserve previous selection until package and runtime checks pass; rollback excludes client data.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Проверка подготовленной среды; установки и скачивания нет.')
    parser.add_argument('root', type=Path)
    parser.add_argument('--expected-receipt-sha256', required=True)
    args = parser.parse_args()
    try: result = {'status': 'VERIFIED_NOT_EXECUTED', 'runtime': verify(args.root, expected_receipt_sha256=args.expected_receipt_sha256)}
    except (ValueError, OSError, KeyError, TypeError): result = {'status': 'BLOCKED', 'code': 'RUNTIME_NOT_READY'}
    support_event('setup', 'preflight', 'check', 'failure' if result['status'] == 'BLOCKED' else 'success',
                  'UNKNOWN' if result['status'] == 'BLOCKED' else 'NONE')
    print(json.dumps(result)); raise SystemExit(result['status'] == 'BLOCKED')
