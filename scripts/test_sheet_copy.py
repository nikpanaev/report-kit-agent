"""Native-copy guard: reuse the existing synthetic workbook without changing its oracle."""
from copy import deepcopy
import hashlib
import json
import unittest

import test_sheet_templates as original
import test_update_interfaces as compatibility
from check_report_templates import digest
from check_sheet_copy import check


class SheetCopy(unittest.TestCase):
    def setUp(self):
        self.fixture = original.SheetTemplates()
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.source = deepcopy(self.fixture.raw)
        self.output = deepcopy(self.source)
        self.output["spreadsheetId"] = "separate-copy"
        self.output["properties"]["title"] = "Новая копия"
        texts, _, _ = self.fixture.sheet_inventory(self.source)
        baseline = {p: v for p, v in texts.items() if p != "/properties/title" and "/@chartId/" not in p}
        self.plan = {"schema_version": 1, "source_id": "sheet-template", "account_email": "owner@example.test",
                     "folder_id": "reports", "approval_source": "synthetic owner decision",
                     "source_cells_sha256": digest(baseline),
                     "source_charts_sha256": digest({"0/7": "Итоги {{MONTH}}"})}
        self.drive = {"id": "sheet-template", "mime_type": "application/vnd.google-apps.spreadsheet",
                      "parent_ids": ["reports"], "permissions": [{"role": "owner", "emailAddress": "owner@example.test"}]}
        self.write("profile.json", {"email": "owner@example.test"})
        self.write("source-drive.json", self.drive)
        self.write("output-drive.json", {**self.drive, "id": "separate-copy"})
        self.write("copy.json", {"success": True, "id": "separate-copy"})
        self.write("review.json", {"scope": "Synthetic direct checks only"})
        review_hash = hashlib.sha256((self.root / "review.json").read_bytes()).hexdigest()
        self.run = {"schema_version": 1, "plan_sha256": digest(self.plan), "source_path": "source.json",
                    "output_path": "output.json", "source_drive_path": "source-drive.json",
                    "output_drive_path": "output-drive.json", "profile_path": "profile.json", "copy_action_path": "copy.json",
                    "reviews": {name: {"result": "PASS", "path": "review.json", "sha256": review_hash,
                                         "observation": "synthetic check"}
                                for name in ("coverage", "charts", "visual", "calculations", "history")}}

    def write(self, name, value):
        self.fixture.write(name, value)

    def execute(self):
        self.write("source.json", self.source)
        self.write("output.json", self.output)
        self.write("plan.json", self.plan)
        self.write("receipt.json", self.run)
        return check(self.root / "plan.json", self.root / "receipt.json")

    def blocked(self, message):
        result = self.execute()
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertIn(message, " ".join(result["issues"]))

    def test_native_copy_without_drive_version(self):
        self.assertEqual(self.execute()["status"], "PASS_LIMITED")

    def test_formula_and_format_changes_are_detected(self):
        for key, value in (("userEnteredValue", {"formulaValue": "=1"}),
                           ("userEnteredFormat", {"textFormat": {"bold": True}})):
            with self.subTest(key=key):
                self.output = deepcopy(self.source)
                self.output["spreadsheetId"] = "separate-copy"
                self.output["sheets"][0]["data"][0]["rowData"][0]["values"][2][key] = value
                self.blocked("unexpected cell")

    def test_formula_error_is_not_a_valid_baseline(self):
        self.output["sheets"][0]["data"][0]["rowData"][0]["values"][2]["effectiveValue"] = {
            "errorValue": {"type": "REF", "message": "bad reference"}}
        self.blocked("formula error")

    def test_source_change_requires_new_approval(self):
        self.source["sheets"][0]["data"][0]["rowData"][0]["values"][0]["note"] = "changed"
        self.blocked("approved source cells changed")

    def test_hidden_sheet_and_grid_changes_are_detected(self):
        self.output["sheets"].pop()
        self.blocked("worksheet structure")

    def test_wrong_owner_folder_and_account_are_detected(self):
        self.write("output-drive.json", {**self.drive, "id": "separate-copy", "parent_ids": ["wrong"]})
        self.blocked("owner/folder")
        self.write("output-drive.json", {**self.drive, "id": "separate-copy", "permissions": []})
        self.blocked("owner/folder")
        self.write("profile.json", {"email": "other@example.test"})
        self.blocked("selected account")

    def test_source_is_never_the_output(self):
        self.output["spreadsheetId"] = self.source["spreadsheetId"]
        self.blocked("copy identity")

    def test_chart_loss_is_detected(self):
        self.output["sheets"][0].pop("charts")
        self.blocked("chart inventory")

    def test_source_chart_change_and_duplicate_are_blocked(self):
        self.source["sheets"][0]["charts"][0]["spec"]["title"] = "changed"
        self.blocked("approved source chart inventory changed")
        self.source = deepcopy(self.fixture.raw)
        self.output["sheets"][0]["charts"].append(deepcopy(self.output["sheets"][0]["charts"][0]))
        self.blocked("duplicate chart inventory")
        self.output["sheets"][0]["charts"].pop()
        self.output["sheets"][0]["charts"][0]["spec"] = []
        self.blocked("invalid chart specification")

    def test_missing_review_and_tampered_review_are_blocked(self):
        self.run["reviews"].pop("charts")
        self.blocked("incomplete direct")
        self.run["reviews"]["charts"] = deepcopy(self.run["reviews"]["visual"])
        self.write("review.json", {"scope": "changed"})
        self.blocked("changed review evidence")

    def test_review_path_cannot_escape(self):
        self.run["reviews"]["charts"]["path"] = "../outside.json"
        self.blocked("escapes")

    def test_changed_plan_is_blocked(self):
        self.plan["approval_source"] = "changed"
        self.blocked("changed check plan")

    def test_new_route_participates_in_existing_update_preflight(self):
        fixture = compatibility.OptionalInterfaces()
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        client = fixture.fixture.compatibility["clients"]["second"]
        client["interfaces"]["template_copy_sheets"] = 1
        with self.assertRaisesRegex(ValueError, "interface_incompatible"):
            fixture.fixture.preflight()
        fixture.candidate_interface("template_copy_sheets", 1)
        self.assertEqual(fixture.fixture.preflight()["clients_checked"], 2)
        fixture.candidate_interface("template_copy_sheets", 2)
        with self.assertRaisesRegex(ValueError, "interface_incompatible"):
            fixture.fixture.preflight()


if __name__ == "__main__":
    unittest.main()
