"""Optional client formats must participate in whole-client update compatibility."""
import hashlib
import json
import unittest

import test_updates


class OptionalInterfaces(unittest.TestCase):
    def setUp(self):
        self.fixture = test_updates.Updates()
        self.fixture.setUp()
        self.addCleanup(self.cleanup_fixture)

    def cleanup_fixture(self):
        print(json.dumps({"test": self.id(), "result": "Fixture inspected by assertions in run log; cleanup follows",
                          "temporary_files": [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                                              for p in sorted(self.fixture.base.rglob("*")) if p.is_file()]}))
        self.fixture.doCleanups()

    def candidate_interface(self, name, version):
        f = self.fixture
        path = f.candidate_agent / "contracts.json"
        data = json.loads(path.read_text()); data["interfaces"][name] = version
        path.write_text(json.dumps(data))
        f.new = f.pair(f.candidate_agent, f.candidate_skills)
        f.release["packages"] = f.new
        for record in f.compatibility["clients"].values():
            path = f.workspace / record["regression_receipt"]
            receipt = json.loads(path.read_text()); receipt["candidate"] = f.new
            path.write_text(json.dumps(receipt))
            record["regression_sha256"] = hashlib.sha256(path.read_bytes()).hexdigest()

    def test_missing_optional_interface_blocks_even_one_client(self):
        self.fixture.compatibility["clients"]["second"]["interfaces"]["template_registry_sheets"] = 1
        with self.assertRaisesRegex(ValueError, "interface_incompatible"):
            self.fixture.preflight()

    def test_supported_optional_interface_passes_and_wrong_version_blocks(self):
        self.candidate_interface("template_registry_sheets", 1)
        f = self.fixture
        f.compatibility["clients"]["second"]["interfaces"]["template_registry_sheets"] = 1
        self.assertEqual(f.preflight()["clients_checked"], 2)
        for value in (2, True, "1"):
            with self.subTest(value=value):
                f.compatibility["clients"]["second"]["interfaces"]["template_registry_sheets"] = value
                with self.assertRaisesRegex(ValueError, "interface_incompatible"):
                    f.preflight()


if __name__ == "__main__":
    unittest.main()
