"""Synthetic setup/runtime boundaries. Native Windows is deliberately not simulated as PASS."""
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from check_package import identity
import onboarding
import prepare_runtime
import runtime
import support_bundle
import updates


def notice_payload():
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w') as archive:
        for name, raw in {'notice.txt': b'synthetic notice', 'inventory.json': json.dumps({'notice_sources': [
                {'file': 'notice.txt', 'sha256': hashlib.sha256(b'synthetic notice').hexdigest()}]}).encode()}.items():
            archive.writestr(zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0)), raw)
    return out.getvalue()


class PortableRuntime(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='report-kit-runtime-test-')
        self.root = Path(self.temp.name).resolve(); self.addCleanup(self.temp.cleanup)
        environment = patch.dict(os.environ, {'REPORT_SKILLS_STATE_DIR': str(self.root / 'state')})
        environment.start(); self.addCleanup(environment.stop)
        def receipt():
            print(json.dumps({'test': self.id(), 'result': 'Synthetic assertions; see unittest outcome',
                'temporary_files': {str(f): updates.identity_file(f) for f in self.root.rglob('*') if f.is_file()}}))
        self.addCleanup(receipt)
        self.workspace = self.root / 'workspace'; self.workspace.mkdir()
        self.data = {'python/bin/python3': b'not executable; synthetic', 'NOTICE': b'Synthetic notice'}
        self.recipe = {'runtime_id': 'fixture-v1', 'python_version': '3.12.15', 'node_version': '24.21.0', 'packages': {}}
        self.manifest = {'runtime_id': 'fixture-v1', 'platform': 'macos-arm64', 'layer': 'core',
            'files': {n: hashlib.sha256(v).hexdigest() for n, v in self.data.items()},
            'executables': ['python/bin/python3'], 'versions': {'python': '3.12.15', 'node': '24.21.0'}}
        self.data['manifests/core.json'] = json.dumps(self.manifest).encode()
        self.archive = self.root / 'core.tar'; self.archive.write_bytes(prepare_runtime.tar_bytes(self.data))
        self.delivery = {'schema_version': 1, 'runtime_id': 'fixture-v1', 'platform': 'macos-arm64',
            'assets': {'core': {'filename': 'core.tar', 'size': self.archive.stat().st_size, 'sha256': updates.identity_file(self.archive)}}}

    def stage(self, name='stage'):
        return runtime.stage(self.delivery, {'core': self.archive}, self.root / name, 'macos-arm64', ['core'])

    def test_supplemental_notices_are_pinned_inert_inputs(self):
        path = self.root / 'notices.zip'; path.write_bytes(notice_payload())
        item = {'filename': path.name, 'size': path.stat().st_size, 'sha256': updates.identity_file(path)}
        self.assertEqual(prepare_runtime.notice_bytes(self.root, item), path.read_bytes())
        path.write_bytes(b'changed')
        with self.assertRaisesRegex(ValueError, 'runtime_notice_identity'):
            prepare_runtime.notice_bytes(self.root, item)
        item['filename'] = '../notices.zip'
        with self.assertRaisesRegex(ValueError, 'runtime_notice_identity'):
            prepare_runtime.notice_bytes(self.root, item)

    def test_notice_index_rejects_missing_changed_and_duplicate_text(self):
        original = notice_payload()
        with zipfile.ZipFile(io.BytesIO(original)) as archive:
            entries = {name: archive.read(name) for name in archive.namelist()}
        for mode in ['missing', 'changed', 'duplicate']:
            out = io.BytesIO()
            with zipfile.ZipFile(out, 'w') as archive:
                archive.writestr('inventory.json', entries['inventory.json'])
                if mode != 'missing': archive.writestr('notice.txt', b'changed' if mode == 'changed' else entries['notice.txt'])
                if mode == 'duplicate':
                    with self.assertWarns(UserWarning): archive.writestr('notice.txt', entries['notice.txt'])
            with self.subTest(mode=mode), self.assertRaisesRegex(ValueError, 'runtime_notice_inventory'):
                prepare_runtime.validate_notice_archive(out.getvalue())

    def test_recipe_rejects_old_notice_even_with_same_runtime_versions(self):
        recipe = dict(self.recipe, notice_package={'sha256': hashlib.sha256(b'new terms').hexdigest()})
        with self.assertRaisesRegex(ValueError, 'runtime_notice_missing_or_changed'):
            runtime.manifest_recipe_match(self.manifest, recipe)

    def test_stage_is_inert_and_original_source_guard_stays_text_only(self):
        r = self.stage(); self.assertEqual(r['status'], 'STAGED_NOT_INSTALLED')
        self.assertEqual((self.root / 'stage/python/bin/python3').stat().st_mode & 0o111, 0)
        runtime.verify(self.root / 'stage', ['core'], r['receipt_sha256'])
        binary = prepare_runtime.tar_bytes({'binary': b'\xff\x00'})
        with self.assertRaises(ValueError): updates.archive_files(binary)
        self.assertEqual(updates.archive_files(binary, binary=True)['binary'], b'\xff\x00')

    def test_corrupt_and_incomplete_downloads_do_not_create_stage(self):
        original = self.archive.read_bytes()
        for value in [original[:-40], b'X' + original[1:]]:
            self.archive.write_bytes(value)
            with self.assertRaises(ValueError): self.stage()
            self.assertFalse((self.root / 'stage').exists())

    def test_wrong_platform_existing_output_and_package_boundary(self):
        with self.assertRaises(ValueError): runtime.stage(self.delivery, {'core': self.archive}, self.root / 'duplicates', 'macos-arm64', ['core', 'core'])
        with self.assertRaises(ValueError): runtime.stage(self.delivery, {'core': self.archive}, self.root / 'bad', 'windows-x64', ['core'])
        self.stage()
        with self.assertRaises(ValueError): self.stage()
        with self.assertRaises(ValueError): runtime.stage(self.delivery, {'core': self.archive}, runtime.ROOT / 'bad', 'macos-arm64', ['core'])

    def test_modified_runtime_or_receipt_cannot_be_executed(self):
        r = self.stage(); output = self.root / 'stage'
        (output / 'NOTICE').write_bytes(b'changed')
        with self.assertRaises(ValueError): runtime.verify(output, expected_receipt_sha256=r['receipt_sha256'])
        (output / 'NOTICE').write_bytes(b'Synthetic notice')
        (output / 'runtime-receipt.json').write_text('{}')
        with self.assertRaises(ValueError): runtime.probe(output, r['receipt_sha256'], execution_authorized=True)

    def test_execution_needs_permission_and_matching_host(self):
        r = self.stage()
        with self.assertRaises(ValueError): runtime.probe(self.root / 'stage', r['receipt_sha256'])
        with patch.object(runtime, 'host_platform', return_value='windows-x64'):
            with self.assertRaises(ValueError): runtime.probe(self.root / 'stage', r['receipt_sha256'], execution_authorized=True)

    def windows_fixture(self):
        candidate = self.root / 'candidate'; (candidate / 'references').mkdir(parents=True)
        (candidate / 'assets').mkdir()
        terms = candidate / 'references/windows-terms.md'; terms.write_text('Synthetic terms only', encoding='utf-8')
        consent = {'accepted': True, 'terms_sha256': updates.identity_file(terms), 'response_locator': 'synthetic-human-reply'}
        recipe = dict(self.recipe, packages={'tzdata': '2026.5'}, windows_terms={
            'path': 'references/windows-terms.md', 'sha256': consent['terms_sha256'],
            'python_license_sha256': hashlib.sha256(b'synthetic Python license').hexdigest()})
        data = {'python/python.exe': b'not executable; synthetic', 'python/LICENSE.txt': b'synthetic Python license'}
        manifest = dict(self.manifest, platform='windows-x64', files={n: hashlib.sha256(v).hexdigest() for n, v in data.items()},
                        executables=['python/python.exe'], versions={'python': '3.12.15', 'node': '24.21.0', 'tzdata': '2026.5'})
        data['manifests/core.json'] = json.dumps(manifest).encode()
        self.archive.write_bytes(prepare_runtime.tar_bytes(data))
        delivery = dict(self.delivery, platform='windows-x64', assets={'core': {'filename': self.archive.name,
            'size': self.archive.stat().st_size, 'sha256': updates.identity_file(self.archive)}})
        staged = runtime.stage(delivery, {'core': self.archive}, self.root / 'win', 'windows-x64', ['core'])
        (candidate / 'assets/runtime-recipe.json').write_text(json.dumps(recipe), encoding='utf-8')
        script = candidate / 'check.py'; script.write_text('raise AssertionError("must not run")', encoding='utf-8')
        (candidate / 'PUBLIC-FILES.json').write_text(json.dumps({'schema_version': 1, 'files': [
            'PUBLIC-FILES.json', 'assets/runtime-recipe.json', 'check.py', 'references/windows-terms.md']}), encoding='utf-8')
        return candidate, recipe, consent, staged, script

    def test_windows_terms_require_explicit_current_receipt(self):
        candidate, recipe, consent, _, _ = self.windows_fixture()
        for value in [None, dict(consent, accepted=False), dict(consent, terms_sha256='0'*64),
                      dict(consent, response_locator=' '), dict(consent, extra='forbidden')]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'runtime_windows_terms_consent'):
                runtime.windows_terms_check('windows-x64', recipe, value, source_root=candidate)
        runtime.windows_terms_check('windows-x64', recipe, consent, source_root=candidate)
        runtime.windows_terms_check('macos-arm64', {}, None)
        (candidate / 'references/windows-terms.md').write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'runtime_windows_terms_changed'):
            runtime.windows_terms_check('windows-x64', recipe, consent, source_root=candidate)

    def test_windows_terms_gate_probe_and_command_before_execution(self):
        candidate, recipe, consent, staged, script = self.windows_fixture()
        with patch.object(runtime, 'ROOT', candidate), patch.object(runtime, 'host_requirements', return_value='windows-x64'), \
                patch.object(runtime.subprocess, 'run') as run:
            for value in [None, dict(consent, terms_sha256='0'*64)]:
                with self.assertRaisesRegex(ValueError, 'runtime_windows_terms_consent'):
                    runtime.probe(self.root / 'win', staged['receipt_sha256'], execution_authorized=True, terms_acceptance=value)
                with self.assertRaisesRegex(ValueError, 'runtime_windows_terms_consent'):
                    runtime.execution_plan(self.root / 'win', staged['receipt_sha256'], candidate, identity(candidate), script, [], terms_acceptance=value)
                run.assert_not_called()
            run.return_value = subprocess.CompletedProcess([], 0, json.dumps({'python': '3.12.15', 'modules': ['tzdata'], 'versions': {'tzdata': '2026.5'}}))
            self.assertEqual(runtime.probe(self.root / 'win', staged['receipt_sha256'], execution_authorized=True,
                                          terms_acceptance=consent)['status'], 'LOCAL_RUNTIME_PROBE_PASS')
            plan = runtime.execution_plan(self.root / 'win', staged['receipt_sha256'], candidate,
                identity(candidate), script, [], terms_acceptance=consent)
            self.assertFalse(plan['execution_authorized'])
            self.assertEqual(run.call_count, 1)

    def test_windows_client_update_preserves_selection_and_checks_new_terms(self):
        candidate, recipe, consent, staged, _ = self.windows_fixture()
        chosen = {'runtime_id': 'fixture-v1', 'root': str(self.root / 'win'), 'receipt_sha256': staged['receipt_sha256']}
        selection = self.workspace / 'runtime-selection.json'; selection.write_text(json.dumps(chosen), encoding='utf-8')
        before = selection.read_bytes(); record = self.workspace / 'windows-terms-consent.json'
        with patch.object(runtime, 'host_requirements', return_value='windows-x64'):
            with self.assertRaisesRegex(ValueError, 'runtime_windows_terms_consent'): runtime.client_preflight(self.workspace, candidate, {})
            record.write_text(json.dumps(dict(consent, terms_sha256='0'*64)), encoding='utf-8')
            with self.assertRaisesRegex(ValueError, 'runtime_windows_terms_consent'): runtime.client_preflight(self.workspace, candidate, {})
            record.write_text(json.dumps(consent), encoding='utf-8')
            runtime.client_preflight(self.workspace, candidate, {})
        self.assertEqual(selection.read_bytes(), before)

    def test_windows_python_license_and_bootstrap_contract(self):
        candidate, recipe, _, _, _ = self.windows_fixture()
        manifest = json.loads((self.root / 'win/manifests/core.json').read_text(encoding='utf-8'))
        runtime.manifest_recipe_match(manifest, recipe)
        manifest['files']['python/LICENSE.txt'] = '0'*64
        with self.assertRaisesRegex(ValueError, 'runtime_windows_license_changed'): runtime.manifest_recipe_match(manifest, recipe)
        script = (runtime.ROOT / 'scripts/bootstrap_runtime.ps1').read_text(encoding='utf-8')
        self.assertLess(script.index('RUNTIME_WINDOWS_TERMS_CONSENT_REQUIRED'), script.index('Copy-Item'))
        self.assertIn('$TermsResponseLocator', script)

    def test_release_rejects_changed_windows_terms_before_copy(self):
        from prepare_release import append_runtime_assets
        candidate, recipe, _, _, _ = self.windows_fixture()
        recipe['platforms'] = {'windows-x64': {}}
        (candidate / 'assets/runtime-recipe.json').write_text(json.dumps(recipe), encoding='utf-8')
        assets = self.root / 'assets'; assets.mkdir()
        (assets / 'runtime-build.json').write_text(json.dumps({'runtime_id': 'fixture-v1', 'installation_performed': False}), encoding='utf-8')
        (candidate / 'references/windows-terms.md').write_text('changed', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'runtime_windows_terms_changed'):
            append_runtime_assets(candidate, assets, self.root / 'no-output', {})
        self.assertFalse((self.root / 'no-output').exists())

    def test_archive_traversal_links_and_collision_are_still_blocked(self):
        for name in ['../escape', '/escape', 'dir/CON.txt']:
            with self.subTest(name=name), self.assertRaises(ValueError): updates.archive_files(prepare_runtime.tar_bytes({name: b'bad'}), binary=True)
        with self.assertRaises(ValueError): updates.archive_files(prepare_runtime.tar_bytes({'x': b'a', 'X': b'b'}), binary=True)

    def test_layers_are_lazy_and_cover_all_registered_clients(self):
        self.assertEqual(runtime.needed_layers(['google']), ['core'])
        self.assertEqual(runtime.needed_layers(['vk-post-screenshot', 'telegram-post-screenshot', 'livedune']), ['capture', 'core', 'images', 'livedune-node'])
        r = self.stage(); candidate = self.root / 'candidate'; (candidate / 'assets').mkdir(parents=True)
        (candidate / 'assets/runtime-recipe.json').write_text(json.dumps(self.recipe))
        (self.workspace / 'runtime-selection.json').write_text(json.dumps({'runtime_id': 'fixture-v1', 'root': str(self.root / 'stage'), 'receipt_sha256': r['receipt_sha256']}))
        with patch.object(runtime, 'host_requirements', return_value='macos-arm64'):
            runtime.client_preflight(self.workspace, candidate, {})
            with self.assertRaises(ValueError): runtime.client_preflight(self.workspace, candidate, {'second': {'required_skills': ['vk-post-screenshot']}})
        self.assertEqual((self.root / 'stage/NOTICE').read_bytes(), b'Synthetic notice')

    def test_browser_install_offer_requires_consent_and_respects_policy(self):
        self.assertEqual(runtime.browser_plan('chromium', 'missing')['action'], 'ASK_BROWSER_CONSENT')
        self.assertEqual(runtime.browser_plan('chromium', 'missing', install_consent=True)['command_for_agent_only'], ['-m', 'playwright', 'install', 'chromium'])
        self.assertEqual(runtime.browser_plan('chrome', 'working')['action'], 'USE_VERIFIED_BROWSER')
        self.assertEqual(runtime.browser_plan('chrome', 'policy_denied', install_consent=True)['action'], 'CONTACT_IT')

    def test_recipe_drift_is_blocked_before_probe_or_execution(self):
        staged = self.stage(); output = self.root / 'stage'
        candidate = self.root / 'candidate'; (candidate / 'assets').mkdir(parents=True)
        path = candidate / 'assets/runtime-recipe.json'
        (self.workspace / 'runtime-selection.json').write_text(json.dumps({
            'runtime_id': 'fixture-v1', 'root': str(output), 'receipt_sha256': staged['receipt_sha256']}), encoding='utf-8')
        for key, value in [('python_version', '3.99.99'), ('node_version', '99.0.0'), ('packages', {'tzdata': '9999.1'})]:
            recipe = dict(self.recipe, **{key: value}); path.write_text(json.dumps(recipe), encoding='utf-8')
            with self.subTest(key=key), patch.object(runtime, 'ROOT', candidate), patch.object(runtime, 'host_requirements', return_value='macos-arm64'):
                with self.assertRaisesRegex(ValueError, 'runtime_recipe_versions'): runtime.client_preflight(self.workspace, candidate, {})
                with patch.object(runtime.subprocess, 'run') as run:
                    with self.assertRaisesRegex(ValueError, 'runtime_recipe_versions'): runtime.probe(output, staged['receipt_sha256'], execution_authorized=True)
                    with self.assertRaisesRegex(ValueError, 'runtime_recipe_versions'): runtime.execution_plan(output, staged['receipt_sha256'], candidate, '0'*64, path, [])
                    run.assert_not_called()
                self.assertEqual((output / 'python/bin/python3').stat().st_mode & 0o111, 0)
        runtime.recipe_match(output, staged, self.recipe)

    def test_recipe_checks_every_staged_layer(self):
        staged = self.stage(); output = self.root / 'stage'
        other = output / 'manifests/capture.json'; other.write_text(json.dumps({'runtime_id': 'fixture-v1', 'versions': {'python': 'old'}}), encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'runtime_recipe_versions'):
            runtime.recipe_match(output, dict(staged, layers=['core', 'capture']), self.recipe)

    def test_old_os_is_not_accepted_by_cpu_name_alone(self):
        with patch.object(runtime, 'host_platform', return_value='macos-arm64'), patch.object(runtime.platform, 'mac_ver', return_value=('13.7', (), '')):
            with self.assertRaises(ValueError): runtime.host_requirements()
        with patch.object(runtime, 'host_platform', return_value='macos-arm64'), patch.object(runtime.platform, 'mac_ver', return_value=('14.0', (), '')):
            self.assertEqual(runtime.host_requirements(), 'macos-arm64')

    def test_setup_starts_without_special_request_and_resumes(self):
        self.assertEqual(onboarding.next_step(self.workspace)['step'], 'discovery')
        state = onboarding.record(self.workspace, 'discovery', 'PASS', 'synthetic-native-observation', expected_revision=0)
        state = onboarding.record(self.workspace, 'workspace', 'PASS', 'synthetic-native-observation', expected_revision=state['revision'], answers={'update_mode': 'ask_each'})
        self.assertEqual(onboarding.next_step(self.workspace)['step'], 'runtime')
        self.assertEqual(onboarding.read_state(self.workspace)['answers']['update_mode'], 'ask_each')
        with self.assertRaises(ValueError): onboarding.record(self.workspace, 'ready', 'PASS', 'synthetic', expected_revision=2)

    def test_setup_does_not_connect_services_before_needed(self):
        for index, step in enumerate(onboarding.STEPS): onboarding.record(self.workspace, step, 'PASS', 'synthetic', expected_revision=index)
        self.assertEqual(onboarding.next_step(self.workspace)['action'], 'READY_FOR_REQUESTED_TASK')
        self.assertEqual(onboarding.next_step(self.workspace, needed_services=['google'])['service'], 'google')
        onboarding.record(self.workspace, 'google', 'PASS', 'synthetic', expected_revision=6, service=True)
        self.assertEqual(onboarding.next_step(self.workspace, needed_services=['google'])['action'], 'READY_FOR_REQUESTED_TASK')
        self.assertEqual(onboarding.next_step(self.workspace, invalidated=['runtime'])['step'], 'runtime')

    def test_setup_preserves_previous_state_on_failed_write_and_refuses_secret_fields(self):
        onboarding.record(self.workspace, 'discovery', 'PASS', 'synthetic', expected_revision=0)
        before = (self.workspace / 'setup-progress.json').read_bytes()
        with self.assertRaises(ValueError): onboarding.record(self.workspace, 'workspace', 'PASS', 'synthetic', expected_revision=1, answers={'password': 'synthetic'})
        with patch.object(onboarding.os, 'replace', side_effect=OSError('synthetic')):
            with self.assertRaises(OSError): onboarding.record(self.workspace, 'workspace', 'PASS', 'synthetic', expected_revision=1)
        self.assertEqual((self.workspace / 'setup-progress.json').read_bytes(), before)
        self.assertFalse((self.workspace / '.setup-progress.lock').exists())

    def test_stale_revision_and_corrupt_setup_do_not_reset_answers(self):
        onboarding.record(self.workspace, 'discovery', 'PASS', 'synthetic', expected_revision=0)
        with self.assertRaises(ValueError): onboarding.record(self.workspace, 'workspace', 'PASS', 'synthetic', expected_revision=0)
        (self.workspace / 'setup-progress.json').write_bytes(b'{partial')
        with self.assertRaises(ValueError): onboarding.next_step(self.workspace)
        self.assertEqual((self.workspace / 'setup-progress.json').read_bytes(), b'{partial')

    def test_fallback_uses_prepared_python_without_system_python(self):
        folder = support_bundle.prepare_fallback(self.root / 'support', self.root / 'state', Path(sys.executable))
        self.assertEqual((folder / 'runtime-python.txt').read_text().strip(), str(Path(sys.executable).resolve()))
        self.assertIn('устанавливать Python вручную не нужно', (folder / 'КАК ПЕРЕДАТЬ.txt').read_text())

    def test_compressed_runtime_and_dead_setup_lock_recovery(self):
        raw = prepare_runtime.tar_bytes(self.data, compress=True)
        self.archive.write_bytes(raw); self.delivery['assets']['core'].update(size=len(raw), sha256=updates.identity_file(self.archive))
        self.stage()
        lock = self.workspace / '.setup-progress.lock'; lock.write_text(json.dumps({'pid': 123456789, 'operation': 'synthetic'}))
        digest = updates.identity_file(lock)
        with self.assertRaises(ValueError): onboarding.recover_lock(self.workspace, digest, {'pid': 123456789, 'alive': True})
        self.assertTrue(lock.exists())
        result = onboarding.recover_lock(self.workspace, digest, {'pid': 123456789, 'alive': False, 'source_kind': 'native_tool_result', 'locator': 'synthetic-native-process-observation'})
        self.assertEqual(result['step'], 'discovery'); self.assertFalse(lock.exists())

    def test_runtime_proposal_does_not_replace_current_selection(self):
        r = self.stage(); candidate = self.root / 'candidate'; (candidate / 'assets').mkdir(parents=True)
        (candidate / 'assets/runtime-recipe.json').write_text(json.dumps(self.recipe))
        current = self.workspace / 'runtime-selection.json'; current.write_text(json.dumps({'runtime_id': 'old', 'root': 'unchanged', 'receipt_sha256': '0' * 64}))
        before = current.read_bytes()
        (self.workspace / 'runtime-candidate.json').write_text(json.dumps({'runtime_id': 'fixture-v1', 'root': str(self.root / 'stage'), 'receipt_sha256': r['receipt_sha256']}))
        with patch.object(runtime, 'host_requirements', return_value='macos-arm64'):
            plan = runtime.client_preflight(self.workspace, candidate, {})
        self.assertFalse(plan['selection_changed']); self.assertEqual(current.read_bytes(), before)
        self.assertEqual(plan['previous']['runtime_id'], 'old')

    def test_runtime_delivery_uses_original_package_release_proof(self):
        from test_single_entry import SingleEntry
        fixture = SingleEntry('runTest'); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        asset = fixture.delivery['assets']['report-kit-agent']
        proof = {'repository': asset['repository'], 'tag': asset['tag'], 'commit': asset['commit'],
                 'asset_url': asset['repository'] + '/releases/download/' + asset['tag'] + '/core.tar',
                 'published': True, 'draft': False, 'source_kind': 'native_tool_result', 'source_locator': 'synthetic release observation'}
        result = updates.stage_runtime_candidate(fixture.source, fixture.delivery, fixture.observed, self.delivery,
                {'core': proof}, {'core': self.archive}, self.root / 'delivery-stage', 'macos-arm64', ['core'], [])
        self.assertEqual(result['status'], 'STAGED_NOT_INSTALLED')
        proof['commit'] = '0' * 40
        with self.assertRaises(ValueError):
            updates.stage_runtime_candidate(fixture.source, fixture.delivery, fixture.observed, self.delivery,
                {'core': proof}, {'core': self.archive}, self.root / 'wrong-origin', 'macos-arm64', ['core'], [])
        self.assertFalse((self.root / 'wrong-origin').exists())

    def test_release_includes_runtime_assets_and_keeps_publication_false(self):
        from prepare_release import append_runtime_assets
        self.recipe['platforms'] = {'macos-arm64': {}}
        agent = self.root / 'agent'; (agent / 'assets').mkdir(parents=True)
        (agent / 'assets/runtime-recipe.json').write_text(json.dumps(self.recipe))
        assets = self.root / 'assets'; assets.mkdir(); (assets / 'core.tar').write_bytes(self.archive.read_bytes())
        (assets / 'runtime-build.json').write_text(json.dumps({'runtime_id': 'fixture-v1', 'installation_performed': False,
            'platforms': {'macos-arm64': self.delivery}, 'license_review': 'PENDING'}))
        output = self.root / 'release'; output.mkdir()
        record = {'release': {'packages': {'synthetic': 'pair'}}, 'artifacts': {}}
        append_runtime_assets(agent, assets, output, record)
        self.assertFalse(json.loads((output / 'draft-runtime-delivery.json').read_text())['published'])
        self.assertEqual((output / 'core.tar').read_bytes(), self.archive.read_bytes())
        self.assertIn('core.tar', (output / 'SHA256SUMS').read_text())
        (agent / 'assets/runtime-recipe.json').write_text(json.dumps(dict(self.recipe, python_version='3.99.99')), encoding='utf-8')
        wrong = self.root / 'wrong-release'; wrong.mkdir()
        with self.assertRaisesRegex(ValueError, 'runtime_recipe_versions'):
            append_runtime_assets(agent, assets, wrong, {'release': record['release'], 'artifacts': {}})
        self.assertFalse((wrong / 'core.tar').exists())
        notice = {'filename': 'notices.zip', 'size': 4, 'sha256': hashlib.sha256(b'text').hexdigest(), 'url': None}
        (agent / 'assets/runtime-recipe.json').write_text(json.dumps(dict(self.recipe, notice_package=notice)))
        missing = self.root / 'missing-notice'; missing.mkdir()
        with self.assertRaisesRegex(ValueError, 'runtime_notice_missing_or_changed'):
            append_runtime_assets(agent, assets, missing, {'release': record['release'], 'artifacts': {}})
        self.assertFalse((missing / 'core.tar').exists())
        for value in [{}, {'macos-arm64': dict(self.delivery, assets={})}]:
            data = {'runtime_id': 'fixture-v1', 'installation_performed': False, 'platforms': value, 'license_review': 'PENDING'}
            (assets / 'runtime-build.json').write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'runtime_platform_inventory|runtime_core_missing'):
                append_runtime_assets(agent, assets, missing, {'release': record['release'], 'artifacts': {}})

    def test_prepare_and_release_retain_notice_bytes_and_bootstrap_hash(self):
        from prepare_release import append_runtime_assets
        downloads = self.root / 'downloads'; downloads.mkdir()
        def item(name, payload):
            path = downloads / name; path.write_bytes(payload)
            return {'filename': name, 'size': len(payload), 'sha256': updates.identity_file(path), 'url': None}
        python = item('python.tar.gz', prepare_runtime.tar_bytes({'python/bin/python3': b'synthetic'}, compress=True))
        node = item('node.tar.gz', prepare_runtime.tar_bytes({'vendor/bin/node': b'synthetic'}, compress=True))
        notice = item('notice.zip', notice_payload())
        recipe = dict(self.recipe, notice_package=notice, platforms={'macos-arm64': {'python': python, 'wheels': {}, 'node': node}})
        agent = self.root / 'agent'; (agent / 'assets').mkdir(parents=True)
        path = agent / 'assets/runtime-recipe.json'; path.write_text(json.dumps(recipe))
        assets = self.root / 'prepared'; result = prepare_runtime.prepare(path, downloads, assets)
        asset = result['platforms']['macos-arm64']['assets']['core']
        with tarfile.open(assets / asset['filename']) as archive:
            key = 'python/REPORT-KIT-NOTICES.zip'; self.assertEqual(archive.extractfile(key).read(), notice_payload())
            manifest = json.load(archive.extractfile('manifests/core.json'))
            bootstrap = archive.extractfile('runtime-receipt.json').read()
            self.assertEqual(manifest['files'][key], notice['sha256'])
            self.assertEqual(json.loads(bootstrap)['files'][key], notice['sha256'])
            self.assertEqual(hashlib.sha256(bootstrap).hexdigest(), asset['bootstrap_receipt_sha256'])
        output = self.root / 'release'; output.mkdir()
        append_runtime_assets(agent, assets, output, {'release': {'packages': {}}, 'artifacts': {}})
        self.assertEqual((output / asset['filename']).read_bytes(), (assets / asset['filename']).read_bytes())

    def test_killed_setup_writer_retains_previous_answers_and_can_resume(self):
        onboarding.record(self.workspace, 'discovery', 'PASS', 'synthetic', expected_revision=0, answers={'update_mode': 'ask_each'})
        before = (self.workspace / 'setup-progress.json').read_bytes()
        code = 'import sys,os;sys.path.insert(0,sys.argv[1]);import onboarding;onboarding.os.replace=lambda *a:os._exit(9);onboarding.record(sys.argv[2],"workspace","PASS","synthetic",expected_revision=1)'
        run = subprocess.run([sys.executable, '-B', '-c', code, str(runtime.ROOT / 'scripts'), str(self.workspace)])
        self.assertEqual(run.returncode, 9); self.assertEqual((self.workspace / 'setup-progress.json').read_bytes(), before)
        lock = self.workspace / '.setup-progress.lock'; owner = json.loads(lock.read_text())
        result = onboarding.recover_lock(self.workspace, updates.identity_file(lock), {'pid': owner['pid'], 'alive': False,
            'source_kind': 'native_tool_result', 'locator': 'synthetic child process exited9; subprocess result'})
        self.assertEqual(result['step'], 'workspace')
        self.assertEqual(onboarding.read_state(self.workspace)['answers']['update_mode'], 'ask_each')

    def test_failed_or_missing_runtime_readback_requires_pair_and_runtime_rollback(self):
        import test_updates
        fixture = test_updates.Updates('runTest'); fixture.setUp(); self.addCleanup(fixture.doCleanups)
        plan = {'status': 'READY_FOR_REVIEW', 'current': fixture.old, 'candidate': fixture.new,
                'runtime': {'previous': {'runtime_id': 'previous'}, 'candidate': {'runtime_id': 'candidate'}}}
        saved = {'packages': fixture.old, 'verified': True, 'source_locator': 'synthetic saved pair',
                 'runtime_selection': plan['runtime']['previous']}
        result = updates.activation_result(plan, saved, fixture.new, True)
        self.assertEqual(result['status'], 'ROLLBACK_REQUIRED')
        self.assertEqual(result['selected_runtime'], plan['runtime']['previous'])
        self.assertEqual(result['client_data_writes'], [])
        result = updates.activation_result(plan, saved, fixture.new, True, loaded_runtime=plan['runtime']['candidate'])
        self.assertEqual(result['status'], 'VERIFY_CLIENT_REFRESH')
        self.assertEqual(saved['runtime_selection'], {'runtime_id': 'previous'})

    @unittest.skipUnless(sys.platform == 'darwin', 'Native macOS shell only; not Windows proof')
    def test_native_core_bootstrap_needs_no_python_and_never_executes_it(self):
        # Only the exact core prefixes are accepted; an executable-looking file remains inert.
        data = {k: v for k, v in self.data.items() if k != 'NOTICE'}; file = self.root / 'bootstrap.tar'; file.write_bytes(prepare_runtime.tar_bytes(data))
        command = ['/bin/sh', str(runtime.ROOT / 'scripts/bootstrap_runtime.sh'), '--approved', str(file), updates.identity_file(file), str(self.root / 'bootstrap')]
        run = subprocess.run(command, capture_output=True, text=True, env={'PATH': '/usr/bin:/bin'})
        self.assertEqual(run.returncode, 0, run.stderr); self.assertIn('NOT_ACTIVATED', run.stdout)
        self.assertEqual((self.root / 'bootstrap/python/bin/python3').stat().st_mode & 0o111, 0)
        command[-1] = str(self.root / 'bad-hash'); command[-2] = '0' * 64
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        self.assertFalse((self.root / 'bad-hash').exists())


if __name__ == '__main__': unittest.main()
