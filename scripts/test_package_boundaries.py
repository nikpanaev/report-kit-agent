"""Synthetic adversarial package/workspace checks, no service calls or installed settings."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

from check_package import check as package_check, files, sensitive
from check_workspace import check


class Boundaries(unittest.TestCase):
    def test_distribution_icons_are_packaged_square_svg(self):
        from test_prepare_release import Releases
        fixture = Releases('runTest'); fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        root = fixture.skills; path = root / 'plugin.json'
        original = json.loads(path.read_text(encoding='utf-8'))
        for name in ['', './assets/missing.svg', '../other.svg', './assets/../VERSION']:
            manifest = json.loads(json.dumps(original)); manifest['extensions']['com.openai']['interface']['logo'] = name
            path.write_text(json.dumps(manifest), encoding='utf-8')
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, 'plugin_icon_'): package_check(root)
        path.write_text(json.dumps(original), encoding='utf-8')
        icon = root / 'assets/icon.svg'; icon.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 49"/>', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'plugin_icon_dimensions'): package_check(root)
        icon.write_text('<svg broken', encoding='utf-8')
        with self.assertRaisesRegex(ValueError, 'plugin_icon_xml'): package_check(root)
        for value in [None, [], 'invalid']:
            manifest = dict(original, extensions=value); path.write_text(json.dumps(manifest), encoding='utf-8')
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, 'plugin_extensions'): package_check(root)

    def test_known_secret_shapes_and_email(self):
        samples = ["/" + "Users/operator/private/file", "-----BEGIN " + "PRIVATE KEY-----",
                   "sk-" + "a" * 30, "person@" + "company.invalid",
                   "https://docs.google.com/presentation/d/" + "A" * 20 + "/edit"]
        for sample in samples:
            self.assertTrue(sensitive(sample))
        self.assertFalse(sensitive("owner@example.test; synthetic-key; credential-service"))

    def test_private_binary_symlink_and_unknown_file(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "safe.md").write_text("Synthetic public example", encoding="utf-8")
            (root / ".DS_Store").write_bytes(b"\x80\xff")
            (root / "nested").mkdir()
            (root / "nested/.DS_Store").write_bytes(b"\x80\xff")
            self.assertEqual(set(files(root)), {"safe.md"})
            for name in [".auth/credentials.json", "local/settings.json", "preview.png", "settings.json"]:
                path = root / name
                path.parent.mkdir(exist_ok=True)
                path.write_text("synthetic", encoding="utf-8")
                with self.assertRaises(ValueError):
                    files(root)
                path.unlink()
                if path.parent != root:
                    path.parent.rmdir()
            external = root.parent / (root.name + "-outside")
            external.write_text("Synthetic outside", encoding="utf-8")
            try:
                (root / "link.md").symlink_to(external)
                with self.assertRaises(ValueError):
                    files(root)
            finally:
                (root / "link.md").unlink()
                external.unlink()

    def test_removed_secret_still_rejected_in_reachable_history(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            (root / "VERSION").write_text("0.1.0-dev.0\n", encoding="utf-8")
            (root / "plugin.json").write_text(json.dumps({"name": "fixture", "version": "0.1.0-dev.0", "extensions": {"com.openai": {"interface": {"logo": "./assets/icon.svg", "composerIcon": "./assets/icon.svg"}}}}), encoding="utf-8")
            (root / "assets").mkdir(); (root / "assets/icon.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48"/>', encoding="utf-8")
            skill = root / "skills/fixture"
            skill.mkdir(parents=True)
            (skill / "SKILL.md").write_text('---\nname: fixture\ndescription: "Synthetic test only"\n---\n', encoding="utf-8")
            market = root / ".agents/plugins"
            market.mkdir(parents=True)
            (market / "marketplace.json").write_text(json.dumps({"plugins": [{"name": "fixture", "source": {"source": "local", "path": "./"}}]}), encoding="utf-8")
            def git(*args):
                return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, check=True)
            git("init", "-b", "main")
            git("config", "user.name", "Synthetic maintainer")
            git("config", "user.email", "maintainer@example.invalid")
            canary = root / "canary.txt"
            canary.write_text("sk-" + "x" * 30, encoding="utf-8")
            git("add", "--", "VERSION", "plugin.json", "skills/fixture/SKILL.md", ".agents/plugins/marketplace.json", "canary.txt")
            git("commit", "-m", "Synthetic rejected payload")
            canary.unlink()
            git("add", "--", "canary.txt")
            git("commit", "-m", "Synthetic removal is insufficient")
            inventory = files(root)
            (root / "PUBLIC-FILES.json").write_text(json.dumps({"schema_version": 1, "files": [*inventory, "PUBLIC-FILES.json"]}), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "sensitive_git_history"):
                package_check(root, history=True)

    def test_workspace_separation_and_secret_field(self):
        with tempfile.TemporaryDirectory() as folder:
            parent = Path(folder)
            package = parent / "package"
            workspace = parent / "workspace"
            package.mkdir()
            workspace.mkdir()
            settings = {"schema_version": 2, "timezone": "Europe/Moscow",
                        "packages": {"report-kit-agent": None, "report-kit-skills": None},
                        "capabilities": {}, "clients": []}
            (workspace / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
            self.assertEqual(check(workspace, [package])["status"], "PASS_LIMITED")
            for path in [package, package / "nested", parent]:
                with self.assertRaises(ValueError):
                    check(path, [package])
            legacy = dict(settings, schema_version=1)
            (workspace / "settings.json").write_text(json.dumps(legacy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "settings_schema_or_timezone"):
                check(workspace, [package])
            legacy = dict(settings, packages={"report-agent": None, "report-skills": None})
            (workspace / "settings.json").write_text(json.dumps(legacy), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "package_capability_inventory"):
                check(workspace, [package])
            settings["api_key"] = "synthetic-canary"
            (workspace / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
            with self.assertRaises(ValueError):
                check(workspace, [package])


if __name__ == "__main__":
    unittest.main()
