"""Native Sheets guard regression: synthetic local evidence, no account or writes."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from check_report_templates import check, digest, frozen_history, inventory, native_digest


class SheetTemplates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.cleanup_fixture)
        self.root = Path(self.temp.name)
        now = datetime.now(timezone.utc)
        self.role = "sheets_monthly"
        self.raw = {"spreadsheetId": "sheet-template", "properties": {"title": "Отчёт {{MONTH}}"},
                    "sheets": [{"properties": {"sheetId": 0, "title": "Summary", "sheetType": "GRID",
                                               "gridProperties": {"rowCount": 10, "columnCount": 8}},
                                "data": [{"rowData": [{"values": [
                                    {"userEnteredValue": {"stringValue": "Клиент"}},
                                    {"userEnteredValue": {"stringValue": "{{VALUE}}"},
                                     "effectiveValue": {"stringValue": "{{VALUE}}"},
                                     "formattedValue": "{{VALUE}}"},
                                    {"userEnteredValue": {"formulaValue": "=SUM(B2:B3)"},
                                     "effectiveValue": {"numberValue": 0}, "formattedValue": "0"}]}]}],
                                "charts": [{"chartId": 7, "spec": {"title": "Итоги {{MONTH}}",
                                    "basicChart": {"chartType": "COLUMN", "series": [{"series": {
                                        "sourceRange": {"sources": [{"sheetId": 0, "startRowIndex": 1,
                                                                    "endRowIndex": 3, "startColumnIndex": 1,
                                                                    "endColumnIndex": 2}]}}}]}}}]},
                               {"properties": {"sheetId": 5, "title": "Source", "hidden": True,
                                               "sheetType": "GRID", "gridProperties": {
                                                   "rowCount": 5, "columnCount": 3}},
                                "data": [{"rowData": [{"values": [{"note": "Определение показателя"}]}]}]}]}
        texts, _, links = self.sheet_inventory(self.raw)
        slots = {p: v for p, v in texts.items() if "{{" in v}
        self.template = {"role": self.role, "id": "sheet-template", "revision": "12",
                         "approved_sha256": native_digest(self.raw), "approval_path": "approval.json",
                         "semantic_kind": "neutral_template", "text_slots": slots,
                         "static_text": {p: v for p, v in texts.items() if p not in slots},
                         "allowed_images": {}, "linked_data": {p: {"object_sha256": v,
                             "source_sha256": digest(self.raw["sheets"])} for p, v in links.items()}}
        self.registry = {"schema_version": 3, "client_id": "fixture", "account_email": "owner@example.test",
                         "reports_folder_id": "reports", "required_roles": [self.role],
                         "reference_and_report_ids": ["reference", "past-report"], "templates": [self.template]}
        self.current = {"id": "sheet-template", "mimeType": "application/vnd.google-apps.spreadsheet",
                        "trashed": False, "parents": ["reports"], "owners": [{"emailAddress": "owner@example.test"}],
                        "checked_at": (now - timedelta(seconds=1)).isoformat(), "run_id": "run", "link_id": "link",
                        "native_path": "native.json", "image_paths": {},
                        "linked_data_paths": {p: "chart-source.json" for p in links},
                        "sheets_read": {"request": {"includeGridData": True},
                            "drive_before_path": "before.json", "drive_after_path": "after.json",
                            "before_at": (now - timedelta(seconds=2)).isoformat(),
                            "after_at": (now - timedelta(seconds=1)).isoformat(),
                            "sheet_ids": [0, 5], "unreadable": [], "unsupported_objects": [],
                            "supplemental_review_source": "fixture-native-object-review"}}
        self.run = {"schema_version": 3, "client_id": "fixture", "account_email": "owner@example.test",
                    "link_id": "link", "run_id": "run", "started_at": (now - timedelta(seconds=3)).isoformat(),
                    "selected_role": self.role, "copy_source_id": "sheet-template", "files": [self.current],
                    "new_month": "2026-09", "collection_months": ["2026-09"]}
        self.drive = {k: deepcopy(self.current[k]) for k in ("id", "mimeType", "trashed", "parents", "owners")}
        self.drive["version"] = "12"
        self.write("before.json", self.drive)
        self.write("after.json", self.drive)
        self.write("chart-source.json", self.raw["sheets"])
        self.approve()

    @staticmethod
    def sheet_inventory(raw):
        # Independent expected locators: this fixture does not call the new parser to construct its oracle.
        texts = {"/properties/title": raw["properties"]["title"]}
        links = {}
        for sheet in raw["sheets"]:
            p = f'/@sheetId/{sheet["properties"]["sheetId"]}'
            texts[p + "/properties/title"] = sheet["properties"]["title"]
            for grid in sheet["data"]:
                for r, row in enumerate(grid.get("rowData", []), grid.get("startRow", 0)):
                    for c, cell in enumerate(row.get("values", []), grid.get("startColumn", 0)):
                        if cell:
                            texts[f"{p}/cells/{r}/{c}"] = json.dumps(cell, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            for chart in sheet.get("charts", []):
                cp = f'{p}/@chartId/{chart["chartId"]}'
                for key in ("title", "subtitle", "altText"):
                    if key in chart["spec"]:
                        texts[cp + "/spec/" + key] = chart["spec"][key]
                links[cp + "/spec"] = digest(chart["spec"])
        return texts, {}, links

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value, ensure_ascii=False))

    def cleanup_fixture(self):
        print(json.dumps({"test": self.id(), "result": "Fixture inspected by assertions in run log; cleanup follows",
                          "temporary_files": [{"path": str(p), "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                                              for p in sorted(self.root.rglob("*")) if p.is_file()]}))
        self.temp.cleanup()

    def approve(self):
        self.template["approved_sha256"] = native_digest(self.raw)
        self.write("approval.json", {"result": "APPROVED", "owner_decision_source": "fixture-owner",
                                   **{k: self.template[k] for k in ("id", "revision", "approved_sha256")}})

    def execute(self):
        self.write("native.json", self.raw)
        self.write("registry.json", self.registry)
        self.write("preflight.json", self.run)
        return check(self.root / "registry.json", self.root / "preflight.json", self.registry["required_roles"])

    def blocked(self, message):
        result = self.execute()
        self.assertEqual(result["status"], "BLOCKED", result)
        self.assertTrue(any(message in i for i in result["issues"]), result)

    def test_full_monthly_and_native_envelope(self):
        self.assertEqual(self.execute()["status"], "PASS_LIMITED")
        self.raw = {"isError": False, "structuredContent": self.raw, "content": [{"text": "untrusted duplicate"}]}
        self.assertEqual(self.execute()["status"], "PASS_LIMITED")

    def test_full_typed_inventory_and_absolute_coordinates(self):
        raw = deepcopy(self.raw)
        raw["sheets"][0]["data"][0].update(startRow=3, startColumn=2)
        self.assertEqual(inventory(raw, allow_links=True), self.sheet_inventory(raw))
        first = inventory(raw, allow_links=True)[0]
        raw["sheets"][0]["data"][0]["rowData"][0]["values"][2]["effectiveValue"] = {"boolValue": False}
        self.assertNotEqual(first, inventory(raw, allow_links=True)[0])

    def test_partial_coverage_and_unsupported_objects(self):
        original = deepcopy(self.current["sheets_read"])
        changes = [("request", {"includeGridData": False}), ("request", {"includeGridData": 1}),
                   ("request", {"includeGridData": True, "fields": "sheets"}),
                   ("request", {"includeGridData": True, "ranges": ["Summary!A1"]}),
                   ("request", {"includeGridData": True, "excludeTablesInBandedRanges": True}),
                   ("sheet_ids", [0]), ("sheet_ids", [0, 5, 5]), ("unreadable", ["Source"]),
                   ("unsupported_objects", ["over-grid-image"]), ("supplemental_review_source", "")]
        for key, value in changes:
            with self.subTest(key=key, value=value):
                self.current["sheets_read"] = {**deepcopy(original), key: value}
                self.blocked("Sheets")

    def test_fresh_drive_version_and_metadata_bracket(self):
        for key, value in [("version", "13"), ("version", 12), ("version", ""), ("id", "wrong"),
                           ("mimeType", "wrong"), ("trashed", True), ("parents", ["elsewhere"]),
                           ("owners", [{"emailAddress": "other@example.test"}])]:
            with self.subTest(key=key):
                self.write("after.json", {**deepcopy(self.drive), key: value})
                self.blocked("Sheets Drive")
        self.write("after.json", self.drive)
        self.current["sheets_read"]["before_at"] = self.run["started_at"].replace("+00:00", "")
        self.blocked("Sheets")

    def test_native_id_formula_format_and_hidden_tab_drift(self):
        original = deepcopy(self.raw)
        def changes(raw):
            yield lambda: raw.update(spreadsheetId="other")
            yield lambda: raw["sheets"][0]["data"][0]["rowData"][0]["values"][2].update(userEnteredValue={"formulaValue": "=SUM(B2:B4)"})
            yield lambda: raw["sheets"][0]["data"][0]["rowData"][0]["values"][0].update(userEnteredFormat={"textFormat": {"bold": True}})
            yield lambda: raw["sheets"].pop()
        for index in range(4):
            self.raw = deepcopy(original)
            list(changes(self.raw))[index]()
            self.blocked("coverage" if index == 3 else "native")

    def test_unmapped_cell_and_non_neutral_slot_even_after_reapproval(self):
        self.raw["sheets"][0]["data"][0]["rowData"][0]["values"].append({"userEnteredValue": {"numberValue": 987}})
        self.approve()
        self.blocked("unmapped")
        self.raw["sheets"][0]["data"][0]["rowData"][0]["values"].pop()
        cell = self.raw["sheets"][0]["data"][0]["rowData"][0]["values"][1]
        cell["effectiveValue"] = {"numberValue": 987}
        self.template["text_slots"]["/@sheetId/0/cells/0/1"] = json.dumps(cell, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        self.approve()
        self.blocked("neutral slot")

    def test_chart_source_and_structure_are_not_exempt(self):
        self.write("chart-source.json", {"changed": True})
        self.blocked("chart/source")
        self.write("chart-source.json", self.raw["sheets"])
        self.current["linked_data_paths"] = {}
        self.blocked("chart/source inventory")

    def test_duplicate_native_ids_cells_and_grid_type(self):
        variants = []
        raw = deepcopy(self.raw); raw["sheets"].append(deepcopy(raw["sheets"][0])); variants.append(raw)
        raw = deepcopy(self.raw); raw["sheets"][0]["data"] *= 2; variants.append(raw)
        raw = deepcopy(self.raw); raw["sheets"][0]["charts"] *= 2; variants.append(raw)
        raw = deepcopy(self.raw); raw["sheets"][1]["properties"]["sheetType"] = "DATA_SOURCE"; variants.append(raw)
        for raw in variants:
            with self.subTest(raw=raw):
                self.raw = raw; self.approve()
                self.blocked("Sheets")

    def test_malformed_cells_grids_and_failed_read_fail_closed(self):
        original = deepcopy(self.raw)
        for value in ([], None, True, "bad"):
            with self.subTest(value=value):
                self.raw = deepcopy(original)
                self.raw["sheets"][0]["data"][0]["rowData"][0]["values"][0] = value
                self.approve(); self.blocked("Sheets")
        self.raw = {"isError": True, "structuredContent": original}
        self.blocked("failed")

    def test_mixed_docs_and_sheets_required_set_is_not_shrunk(self):
        raw = {"documentId": "docs-template", "revisionId": "r1", "body": {"content": [
            {"textRun": {"content": "{{MONTH}}"}}]}}
        text = {"/body/content/0/textRun/content": "{{MONTH}}"}
        self.write("docs.json", raw)
        self.write("docs-approval.json", {"result": "APPROVED", "owner_decision_source": "fixture-owner",
            "id": "docs-template", "revision": "r1", "approved_sha256": native_digest(raw)})
        self.registry["required_roles"].append("docs")
        self.registry["templates"].append({"role": "docs", "id": "docs-template", "revision": "r1",
            "approved_sha256": native_digest(raw), "approval_path": "docs-approval.json",
            "semantic_kind": "neutral_template", "text_slots": text, "static_text": {}, "allowed_images": {}})
        current = {k: deepcopy(self.current[k]) for k in ("trashed", "parents", "owners", "checked_at", "run_id", "link_id")}
        current.update(id="docs-template", mimeType="application/vnd.google-apps.document", native_path="docs.json", image_paths={})
        self.run["files"].append(current)
        self.assertEqual(self.execute()["status"], "PASS_LIMITED")
        self.registry["templates"].pop()
        self.blocked("incomplete")

    def make_cumulative(self):
        self.role = "sheets_cumulative"
        self.template.update(role=self.role, semantic_kind="cumulative_base")
        self.registry["required_roles"] = [self.role]
        self.run["selected_role"] = self.role
        pointer = "/@sheetId/0/cells/0/0"
        value = self.template["static_text"].pop(pointer)
        snapshot = {"client_id": "fixture", "month": "2026-06", "accepted_report_id": "accepted-june",
                    "acceptance_source": "fixture-owner", "source_hashes": {"posts": "a" * 64},
                    "texts": {pointer: value}, "images": {}}
        self.write("frozen.json", snapshot)
        self.template["frozen_months"] = [{"month": "2026-06", "snapshot_path": "frozen.json", "sha256": digest(snapshot)}]
        self.template["mutable_text"] = {"/properties/title": self.template["text_slots"].pop("/properties/title")}

    def test_frozen_cells_append_survives_tab_order_and_rejects_changed_history(self):
        self.make_cumulative()
        self.assertEqual(self.execute()["status"], "PASS_LIMITED")
        output = deepcopy(self.raw); output["sheets"].reverse()
        self.assertEqual(frozen_history(self.template, self.root, output, "fixture", "2026-09", ["2026-09"], {})[2], ["2026-06"])
        output["sheets"][1]["data"][0]["rowData"][0]["values"][0]["userEnteredValue"] = {"numberValue": 1}
        with self.assertRaisesRegex(ValueError, "accepted historical"):
            frozen_history(self.template, self.root, output, "fixture", "2026-09", ["2026-09"], {})
        self.run["collection_months"] = ["2026-06", "2026-09"]
        self.blocked("recollection")

    def test_cli_and_filled_output_history(self):
        self.make_cumulative()
        self.execute()
        self.write("output.json", self.raw)
        self.write("images.json", {})
        command = [sys.executable, str(Path(__file__).with_name("check_report_templates.py")),
                   str(self.root / "registry.json"), str(self.root / "preflight.json"), "--roles", self.role,
                   "--output-native", str(self.root / "output.json"), "--output-image-manifest", str(self.root / "images.json")]
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertEqual(json.loads(result.stdout)["output_history"], "PASS_LIMITED")


if __name__ == "__main__":
    unittest.main()
