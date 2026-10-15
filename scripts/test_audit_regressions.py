"""Downloaded-package and locale regressions; synthetic local files only."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import unittest
from unittest.mock import patch

from check_package import check
from maintenance import read_json
import test_prepare_release as release_fixture
import test_updates as update_fixture


class AuditRegressions(unittest.TestCase):
    def setUp(self):
        self.fixture = release_fixture.Releases('test_exact_archives_and_draft_only')
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)

    def test_downloaded_pair_needs_no_git_history(self):
        f = self.fixture
        f.build()
        roots = {}
        for name in ('report-kit-agent', 'report-kit-skills'):
            root = f.base / ('download-' + name); root.mkdir(); roots[name] = root
            with tarfile.open(f.output / (name + '-0.1.0-dev.0.tar')) as archive:
                archive.extractall(root, filter='data')
        with patch('check_package.subprocess.run', side_effect=AssertionError('Archive check must not need Git executable')):
            result = check(roots['report-kit-agent'], roots['report-kit-skills'])
        self.assertEqual(result['status'], 'PASS_LIMITED')
        self.assertEqual(result['history_status'], 'NOT_CHECKED_ARCHIVE')
        with self.assertRaisesRegex(ValueError, 'history_requires_package_repository'):
            check(roots['report-kit-agent'], history=True)

    def test_required_validation_survives_optimized_python(self):
        root = self.fixture.agent
        manifest = json.loads((root / 'plugin.json').read_text(encoding='utf-8'))
        manifest['version'] = '9.9.9'
        (root / 'plugin.json').write_text(json.dumps(manifest), encoding='utf-8')
        for mode in ([], ['-O']):
            process = subprocess.run([sys.executable, *mode, str(Path(__file__).with_name('check_package.py')), str(root)],
                                     capture_output=True, text=True, timeout=15)
            self.assertEqual(process.returncode, 1)
            self.assertEqual(json.loads(process.stdout)['issue'], 'version_drift')

    def test_utf8_records_ignore_host_locale(self):
        path = self.fixture.base / 'russian.json'
        value = {'title': 'Отчёт: июль — принят'}
        path.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')
        original = io.open
        def locale_open(file, mode='r', buffering=-1, encoding=None, *args, **kwargs):
            if 'b' not in mode and encoding in (None, 'locale'): encoding = 'cp1252'
            return original(file, mode, buffering, encoding, *args, **kwargs)
        with patch.object(io, 'open', locale_open):
            self.assertEqual(read_json(path), value)
            self.assertEqual(check(self.fixture.agent, self.fixture.skills)['status'], 'PASS_LIMITED')

    def test_old_queue_contract_blocks_automatic_update(self):
        fixture = update_fixture.Updates('test_one_incompatible_client_blocks_global_update')
        fixture.setUp(); self.addCleanup(fixture.doCleanups)
        path = fixture.candidate_skills / 'contracts.json'
        data = json.loads(path.read_text(encoding='utf-8'))
        data['interfaces']['shared:ui_queue'] = 2
        path.write_text(json.dumps(data), encoding='utf-8')
        fixture.release['packages'] = fixture.pair(fixture.candidate_agent, fixture.candidate_skills)
        with self.assertRaisesRegex(ValueError, 'interface_incompatible'):
            fixture.preflight()


if __name__ == '__main__':
    unittest.main()
