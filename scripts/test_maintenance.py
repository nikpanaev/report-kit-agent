"""Synthetic maintenance contract oracle; no chats, accounts, API or installation."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
import subprocess
import sys

from maintenance import check_registry, check_incident, route


AGENT = Path(__file__).resolve().parents[1]
SKILLS = AGENT.parent / "report-kit-skills"


class MaintenanceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="maintenance-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.write("settings.json", {"schema_version": 2, "timezone": "UTC",
            "packages": {"report-kit-agent": None, "report-kit-skills": None},
            "capabilities": {}, "clients": ["sample"]})
        self.registry = {"schema_version": 1, "coordinator": self.binding("coordinator", 1),
            "maintainers": {"vk-comment-screenshot": self.binding("skill:vk-comment-screenshot", 2),
                            "vk-message-screenshot": self.binding("skill:vk-message-screenshot", 3)},
            "clients": {"sample": {"binding": self.binding("client:sample", 4), "paused": False}},
            "grants": []}
        grant = {"id": "g1", "origin": "client:sample", "target": "skill:vk-comment-screenshot",
            "origin_binding": self.address(self.registry["clients"]["sample"]["binding"]),
            "target_binding": self.address(self.registry["maintainers"]["vk-comment-screenshot"]),
            "actions": ["request", "callback", "replay"], "authority_ref": "receipts/grant.json", "revoked": False}
        self.registry["grants"].append(grant)
        self.write("receipts/grant.json", {**{k: v for k, v in grant.items() if k != "authority_ref"},
            "source_kind": "human_message", "source_locator": "synthetic fixture; not a real authorization"})
        self.write("maintenance.json", self.registry)
        self.case = {"expected": "Only comments captured", "actual": "Post included",
            "reproducer": "Synthetic fixture", "allowed_scope": "No real service or account actions"}
        case_path = self.write("cases/sample.json", self.case)
        self.incident = {"schema_version": 1, "incident_id": "case-1", "origin": "client:sample",
            "target": "skill:vk-comment-screenshot", "grant_id": "g1", "classification": "bug",
            "case_ref": "cases/sample.json", "case_sha256": hashlib.sha256(case_path.read_bytes()).hexdigest(), "source_sha256": "a" * 64,
            "budget": {"cap": 2, "started": 0}, "assets": [], "events": []}

    def write(self, relative, value):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return path

    def binding(self, role, n):
        value = {"thread_id": f"00000000-0000-4000-8000-{n:012d}", "host_id": "local",
                 "project_id": "synthetic-project", "receipt": f"receipts/role-{n}.json"}
        self.write(value["receipt"], {"role": role, **self.address(value),
            "source_kind": "native_thread_read", "source_locator": "synthetic role observation"})
        return value

    @staticmethod
    def address(binding):
        return {k: binding[k] for k in ["thread_id", "host_id", "project_id"]}

    def event(self, kind, actor=None, **extra):
        n = len(self.incident["events"])
        actor = actor or (self.incident["target"] if kind in {"acknowledged", "candidate_ready", "callback_received"} else self.incident["origin"])
        receipt = {"kind": kind, "incident_id": "case-1", "actor": actor,
            "source_kind": "native_tool_result", "source_locator": f"synthetic result {n}", **extra}
        path = f"receipts/event-{n}.json"
        receipt_path = self.write(path, receipt)
        self.incident["events"].append({"id": f"e{n}", "kind": kind, "actor": actor, "receipt": path,
            "receipt_sha256": hashlib.sha256(receipt_path.read_bytes()).hexdigest()})

    def prepare_callback(self):
        self.event("request_sent")
        self.event("acknowledged")
        self.event("candidate_ready", fix_sha256="b" * 64, checks=["reproducer", "affected_regression"])
        self.event("callback_received", fix_sha256="b" * 64)

    def check(self, previous=None):
        path = self.write("incident.json", self.incident)
        return check_incident(self.root, path, SKILLS, previous)

    def test_exact_comment_route_not_messages(self):
        checked = check_registry(self.root, SKILLS)
        result = route(checked, "client:sample", "skill:vk-comment-screenshot", "g1", "request")
        self.assertEqual(result["target"]["thread_id"], self.registry["maintainers"]["vk-comment-screenshot"]["thread_id"])
        callback = route(checked, "client:sample", "skill:vk-comment-screenshot", "g1", "callback")
        self.assertEqual(callback["recipient"]["thread_id"], self.registry["clients"]["sample"]["binding"]["thread_id"])
        with self.assertRaisesRegex(ValueError, "grant_scope"):
            route(checked, "client:sample", "skill:vk-message-screenshot", "g1", "request")

    def test_unconfirmed_wrong_role_and_duplicate_binding_rejected(self):
        role = self.registry["maintainers"]["vk-comment-screenshot"]["receipt"]
        d = json.loads((self.root / role).read_text()); d["role"] = "skill:vk-message-screenshot"
        self.write(role, d)
        with self.assertRaisesRegex(ValueError, "role_receipt"):
            check_registry(self.root, SKILLS)
        self.registry["maintainers"]["vk-comment-screenshot"] = self.registry["maintainers"]["vk-message-screenshot"]
        self.write("maintenance.json", self.registry)
        with self.assertRaises(ValueError): check_registry(self.root, SKILLS)

    def test_missing_revoked_and_changed_endpoint_authority(self):
        for mutate in [lambda g: g.update(revoked=True), lambda g: g.update(actions=["callback"]),
                       lambda g: g["target_binding"].update(thread_id="different-thread")]:
            with self.subTest(mutate=mutate):
                registry = copy.deepcopy(self.registry); mutate(registry["grants"][0])
                self.write("maintenance.json", registry)
                with self.assertRaises(ValueError):
                    checked = check_registry(self.root, SKILLS)
                    route(checked, "client:sample", "skill:vk-comment-screenshot", "g1", "request")

    def test_authority_message_not_model_message(self):
        grant = json.loads((self.root / "receipts/grant.json").read_text()); grant["source_kind"] = "agent_message"
        self.write("receipts/grant.json", grant)
        with self.assertRaisesRegex(ValueError, "human_authority_receipt"):
            check_registry(self.root, SKILLS)

    def test_registry_full_client_inventory_and_unknown_skill(self):
        for edit in [lambda r: r["clients"].clear(), lambda r: r["maintainers"].update({"unknown": r["coordinator"]})]:
            registry = copy.deepcopy(self.registry); edit(registry); self.write("maintenance.json", registry)
            with self.assertRaises(ValueError): check_registry(self.root, SKILLS)

    def test_callback_alone_never_resolves(self):
        self.prepare_callback()
        self.assertEqual(self.check()["state"], "AWAITING_ORIGIN_VERIFICATION")

    def test_origin_replay_matches_fix_and_consumes_original_budget(self):
        self.prepare_callback()
        self.event("replay", result="PASS", loaded_sha256="b" * 64, origin_paused=False,
                   started_before=0, started_after=1)
        self.assertEqual(self.check()["state"], "RESOLVED")
        self.assertEqual(self.check()["budget_started"], 1)

    def test_failed_replay_remains_open_then_retry(self):
        self.prepare_callback()
        self.event("replay", result="FAIL", loaded_sha256="b" * 64, origin_paused=False,
                   started_before=0, started_after=1)
        self.assertEqual(self.check()["state"], "AWAITING_ORIGIN_VERIFICATION")
        self.event("replay", result="PASS", loaded_sha256="b" * 64, origin_paused=False,
                   started_before=1, started_after=2)
        self.assertEqual(self.check()["state"], "RESOLVED")

    def test_paused_origin_and_exhausted_budget_stop_next_replay(self):
        self.prepare_callback()
        self.registry["clients"]["sample"]["paused"] = True
        self.write("maintenance.json", self.registry)
        self.assertEqual(self.check()["next_action"], "WAIT_FOR_OWNER_RESUME")
        self.registry["clients"]["sample"]["paused"] = False
        self.write("maintenance.json", self.registry)
        self.incident["budget"]["started"] = 2
        self.assertEqual(self.check()["next_action"], "REQUEST_BUDGET_DECISION")

    def test_false_fix_wrong_actor_pause_or_budget_bypass_rejected(self):
        self.prepare_callback(); base = copy.deepcopy(self.incident)
        variants = [dict(loaded_sha256="c" * 64), dict(actor=self.incident["target"]),
                    dict(origin_paused=True), dict(started_before=1), dict(started_after=3)]
        for variant in variants:
            with self.subTest(variant=variant):
                self.incident = copy.deepcopy(base)
                data = dict(result="PASS", loaded_sha256="b" * 64, origin_paused=False, started_before=0, started_after=1)
                data.update(variant); self.event("replay", **data)
                with self.assertRaises(ValueError): self.check()

    def test_duplicate_send_and_duplicate_event_id_rejected(self):
        self.event("request_sent"); self.event("request_sent")
        with self.assertRaisesRegex(ValueError, "event_transition"): self.check()
        self.incident["events"][-1]["id"] = "e0"
        with self.assertRaises(ValueError): self.check()

    def test_blocked_target_waits_without_resending(self):
        self.event("request_sent"); self.event("blocked", reason="TARGET_BUSY")
        self.assertEqual(self.check()["next_action"], "WAIT_FOR_TARGET")
        self.event("unblocked"); self.event("acknowledged")
        self.assertEqual(self.check()["state"], "ACKNOWLEDGED")

    def test_prior_history_and_case_cannot_be_rewritten(self):
        self.event("request_sent"); previous = self.write("previous.json", self.incident)
        self.event("acknowledged")
        self.assertEqual(self.check(previous)["state"], "ACKNOWLEDGED")
        self.incident["events"][0]["id"] = "rewritten"
        with self.assertRaisesRegex(ValueError, "history_rewrite"): self.check(previous)

    def test_report_image_retained_until_receiver_ack_and_acceptance(self):
        raw = b"synthetic asset bytes; not an actual screenshot"
        image = self.root / "report.png"; image.write_bytes(raw)
        asset = {"path": "report.png", "sha256": hashlib.sha256(raw).hexdigest(), "purpose": "report"}
        self.incident["assets"] = [asset]; self.prepare_callback(); self.check()
        image.unlink()
        with self.assertRaisesRegex(ValueError, "report_asset_missing"): self.check()
        self.event("assets_received", assets=[asset])
        with self.assertRaisesRegex(ValueError, "report_asset_missing"): self.check()
        self.event("assets_accepted", assets=[asset], source_kind="human_message")
        self.assertEqual(self.check()["state"], "AWAITING_ORIGIN_VERIFICATION")

    def test_proof_only_hash_is_not_report_asset(self):
        self.incident["assets"] = [{"path": "deleted-proof.png", "sha256": "d" * 64, "purpose": "proof"}]
        self.prepare_callback(); self.check()
        self.incident["assets"][0]["purpose"] = "report"
        with self.assertRaisesRegex(ValueError, "report_asset_missing"): self.check()

    def test_external_reference_unknown_fields_and_secret_case_rejected(self):
        self.registry["credentials"] = "not allowed"; self.write("maintenance.json", self.registry)
        with self.assertRaises(ValueError): check_registry(self.root, SKILLS)
        del self.registry["credentials"]; self.write("maintenance.json", self.registry)
        self.incident["case_ref"] = "../outside.json"
        with self.assertRaises(ValueError): self.check()
        self.incident["case_ref"] = "cases/sample.json"
        self.case["actual"] = "sk-" + "A" * 30; self.write("cases/sample.json", self.case)
        self.incident["case_sha256"] = hashlib.sha256((self.root / "cases/sample.json").read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "unsanitized_case"): self.check()

    def test_symlink_escape_rejected(self):
        with tempfile.TemporaryDirectory() as outside:
            target = Path(outside) / "case.json"; target.write_text(json.dumps(self.case))
            (self.root / "escaped.json").symlink_to(target)
            self.incident["case_ref"] = "escaped.json"
            with self.assertRaisesRegex(ValueError, "private_reference"): self.check()

    def test_receipt_and_original_case_tampering_detected(self):
        self.prepare_callback()
        self.event("replay", result="FAIL", loaded_sha256="b" * 64, origin_paused=False,
                   started_before=0, started_after=1)
        path = self.root / self.incident["events"][-1]["receipt"]
        value = json.loads(path.read_text()); value["result"] = "PASS"; path.write_text(json.dumps(value))
        with self.assertRaisesRegex(ValueError, "receipt_changed"): self.check()
        self.incident["events"].pop()
        self.case["expected"] = "Changed requirement"; self.write("cases/sample.json", self.case)
        with self.assertRaisesRegex(ValueError, "receipt_changed"): self.check()

    def test_uncertain_delivery_never_suggests_resend(self):
        self.event("request_started", source_kind="local_attempt_ledger")
        self.assertEqual(self.check()["next_action"], "READBACK_OR_WAIT_NO_RESEND")
        self.event("request_started", source_kind="local_attempt_ledger")
        with self.assertRaisesRegex(ValueError, "event_transition"): self.check()

    def test_current_pause_blocks_new_replay_even_with_false_receipt(self):
        self.prepare_callback(); previous = self.write("previous.json", self.incident)
        self.registry["clients"]["sample"]["paused"] = True; self.write("maintenance.json", self.registry)
        self.event("replay", result="PASS", loaded_sha256="b" * 64, origin_paused=False,
                   started_before=0, started_after=1)
        with self.assertRaisesRegex(ValueError, "owner_currently_paused"): self.check(previous)

    def test_human_claim_is_not_a_replay_tool_result(self):
        self.prepare_callback()
        self.event("replay", result="PASS", loaded_sha256="b" * 64, origin_paused=False,
                   started_before=0, started_after=0, source_kind="human_message")
        with self.assertRaisesRegex(ValueError, "actual_tool_source_required"): self.check()

    def test_cli_private_error_and_incomplete_mode(self):
        command = [sys.executable, "-B", str(AGENT / "scripts/maintenance.py"), str(self.root), "--skills-root", str(SKILLS)]
        before = {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()}
        result = subprocess.run([*command, "--origin", "client:sample"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1); self.assertEqual(json.loads(result.stdout)["issue"], "incomplete_route")
        self.write("maintenance.json", {"unexpected_secret": "sk-" + "A" * 30})
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1); self.assertNotIn("A" * 30, result.stdout + result.stderr)
        self.write("maintenance.json", self.registry)
        self.assertEqual(before, {str(p): p.read_bytes() for p in self.root.rglob("*") if p.is_file()})


if __name__ == "__main__": unittest.main()
