"""Small resumable setup record; native observations/permissions remain external controls."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import uuid

from maintenance import require, read_json, fields
from runtime import boundary
from support_bundle import emit as support_event

STEPS = ['discovery', 'workspace', 'runtime', 'packages', 'support', 'ready']
ANSWERS = {'timezone', 'workspace', 'update_mode'}


def read_state(workspace):
    workspace = boundary(workspace); file = workspace / 'setup-progress.json'
    require(not file.is_symlink(), 'setup_symlink')
    if not file.exists(): return {'schema_version': 1, 'revision': 0, 'answers': {}, 'steps': {}, 'services': {}}
    state = read_json(file)
    fields(state, {'schema_version', 'revision', 'answers', 'steps', 'services'}, 'setup_record')
    require(state['schema_version'] == 1 and type(state['revision']) is int and state['revision'] >= 0, 'setup_version')
    require(all(isinstance(state[k], dict) for k in ['answers', 'steps', 'services']), 'setup_record_shape')
    require(set(state['answers']) <= ANSWERS and set(state['steps']) <= set(STEPS), 'setup_fields')
    for item in [*state['steps'].values(), *state['services'].values()]:
        fields(item, {'result', 'locator', 'checked_at'}, 'setup_observation')
        require(item['result'] in {'PASS', 'FAIL', 'UNKNOWN'} and isinstance(item['locator'], str)
                and isinstance(item['checked_at'], str), 'setup_observation')
    return state


def next_step(workspace, *, needed_services=(), invalidated=()):
    state = read_state(workspace)
    require(set(invalidated) <= set(STEPS), 'setup_invalidated')
    for step in STEPS:
        if step in invalidated or state['steps'].get(step, {}).get('result') != 'PASS':
            return {'action': 'CONTINUE_SETUP', 'step': step, 'revision': state['revision'],
                    'greeting': 'Сейчас подготовлю работу с отчётами. Проверю доступные инструменты и спрошу только то, что нужно.'}
    for service in needed_services:
        require(service in {'google', 'livedune', 'vk', 'instagram', 'threads', 'tiktok', 'telegram', 'max', 'gmail'}, 'setup_service')
        if state['services'].get(service, {}).get('result') != 'PASS':
            return {'action': 'CONNECT_WHEN_NEEDED', 'service': service, 'revision': state['revision']}
    return {'action': 'READY_FOR_REQUESTED_TASK', 'revision': state['revision'],
            'limitations': 'Saved observations only; revalidate changed tools, permissions, selected runtime and account at use.'}


def record(workspace, step, result, locator, *, expected_revision, answers=None, service=False):
    workspace = boundary(workspace); require(workspace.is_dir(), 'setup_workspace_missing')
    state = read_state(workspace); require(state['revision'] == expected_revision, 'setup_stale_revision')
    permitted = {'google', 'livedune', 'vk', 'instagram', 'threads', 'tiktok', 'telegram', 'max', 'gmail'} if service else set(STEPS)
    require(step in permitted and result in {'PASS', 'FAIL', 'UNKNOWN'}, 'setup_step')
    require(isinstance(locator, str) and 0 < len(locator) <= 1000, 'setup_observation_locator')
    answers = answers or {}; require(set(answers) <= ANSWERS, 'setup_secret_or_unknown_answer')
    require(all(isinstance(v, str) and len(v) <= 4096 for v in answers.values()), 'setup_answer')
    if 'update_mode' in answers: require(answers['update_mode'] in {'ask_each', 'compatible'}, 'setup_update_mode')
    if not service and result == 'PASS':
        require(all(state['steps'].get(s, {}).get('result') == 'PASS' for s in STEPS[:STEPS.index(step)]), 'setup_predecessor')
    # Only the coordinator writes setup. Exclusive lock refuses concurrent writers; stale lock recovery needs native owner evidence.
    lock = workspace / '.setup-progress.lock'; fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    temp = workspace / ('.setup-progress-' + str(uuid.uuid4()) + '.tmp')
    try:
        os.write(fd, json.dumps({'pid': os.getpid(), 'operation': str(uuid.uuid4())}).encode()); os.fsync(fd)
        require(read_state(workspace)['revision'] == expected_revision, 'setup_stale_revision')
        state['answers'].update(answers)
        state['services' if service else 'steps'][step] = {'result': result, 'locator': locator,
            'checked_at': datetime.now(timezone.utc).isoformat()}
        if not service:
            for later in STEPS[STEPS.index(step) + 1:]: state['steps'].pop(later, None)
        state['revision'] += 1
        with temp.open('x', encoding='utf-8') as stream:
            json.dump(state, stream, ensure_ascii=False, indent=2); stream.flush(); os.fsync(stream.fileno())
        temp.chmod(0o600); os.replace(temp, workspace / 'setup-progress.json')
        support_event('setup', 'setup', 'check', {'PASS': 'success', 'FAIL': 'failure', 'UNKNOWN': 'unknown'}[result],
                      'UNKNOWN' if result == 'FAIL' else 'NONE')
        return state
    finally:
        os.close(fd); lock.unlink(); temp.unlink(missing_ok=True)


def recover_lock(workspace, lock_sha256, owner_observation):
    """Native executor must establish the recorded process is dead; never clear an unknown/live owner."""
    from updates import identity_file
    workspace = boundary(workspace); lock = workspace / '.setup-progress.lock'
    require(not lock.is_symlink() and identity_file(lock) == lock_sha256, 'setup_lock_changed')
    owner = read_json(lock)
    require(type(owner.get('pid')) is int and owner['pid'] > 0 and owner_observation.get('pid') == owner['pid']
            and owner_observation.get('alive') is False and owner_observation.get('source_kind') == 'native_tool_result'
            and isinstance(owner_observation.get('locator'), str) and owner_observation['locator'].strip(), 'setup_owner_not_proven_dead')
    require(identity_file(lock) == lock_sha256, 'setup_lock_changed'); lock.unlink()
    support_event('setup', 'recovery', 'recovery', 'success')
    return next_step(workspace)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Продолжить первоначальную настройку. Команды выполняет агент.')
    parser.add_argument('workspace', type=Path); args = parser.parse_args()
    try: result = next_step(args.workspace)
    except (ValueError, OSError, KeyError, TypeError): result = {'action': 'RECOVER_SETUP', 'code': 'SETUP_RECORD_NOT_READY'}
    print(json.dumps(result, ensure_ascii=False))
