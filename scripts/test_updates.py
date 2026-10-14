"""Protected synthetic update/compatibility/rollback cases, no network or installs."""
import copy
import hashlib
import json
import subprocess
import sys
from pathlib import Path
import tempfile
import unittest

from check_package import identity
from maintenance import ContractError
from updates import due, select_release, preflight, rollout, rollback_preflight, activation_decision, document_identity


class Updates(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="updates-fixture-"); self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name); self.workspace = self.base / "workspace"; self.workspace.mkdir()
        self.current_agent = self.package("current-agent", "report-kit-agent", "0.1.0-dev.1")
        self.current_skills = self.package("current-skills", "report-kit-skills", "0.1.0-dev.1")
        self.candidate_agent = self.package("candidate-agent", "report-kit-agent", "0.1.0-dev.2")
        self.candidate_skills = self.package("candidate-skills", "report-kit-skills", "0.1.0-dev.2")
        self.old = self.pair(self.current_agent, self.current_skills)
        self.new = self.pair(self.candidate_agent, self.candidate_skills)
        self.release = {"release_id": "fixture-dev2", "channel": "working", "published": True,
            "revoked": False, "packages": self.new}
        self.source = {"schema_version": 1, "agent_repository": "https://github.com/example/report-kit-agent",
            "skills_repository": "https://github.com/example/report-kit-skills", "channel": "working", "interval_hours": 24}
        self.write("settings.json", {"schema_version": 2, "timezone": "UTC", "packages": self.old,
            "capabilities": {}, "clients": ["first", "second"]})
        profile = {}
        for client in ["first", "second"]:
            p = self.workspace / "clients" / client / "AGENT.md"; p.parent.mkdir(parents=True)
            p.write_text("Accepted client rules; keep historical snapshot and own font override")
            sha = hashlib.sha256(p.read_bytes()).hexdigest()
            receipt = {"kind": "compatibility", "source_kind": "native_tool_result", "source_locator": "synthetic run",
                "client_id": client, "candidate": self.new, "profile_sha256": sha,
                "result": "PASS", "checks": ["client_overrides", "protected_history", "affected_components"]}
            path = self.write(f"receipts/{client}.json", receipt)
            profile[client] = {"binding": {"thread_id": "synthetic-" + client, "host_id": "local", "project_id": "synthetic-project"},
                "profile_path": f"clients/{client}/AGENT.md", "profile_sha256": sha, "profile_revision": 1,
                "protected_files": {f"clients/{client}/AGENT.md": sha}, "required_skills": ["vk-comment-screenshot"],
                "interfaces": {"workspace": 2, "maintenance": 1, "template_registry": 3, "profile": 1,
                    "source:vk-comment-screenshot": 1, "source:vk-post-screenshot": 1, "shared:ui_queue": 1},
                "permission_scopes": ["vk.read"], "active_run": False,
                "regression_receipt": path.relative_to(self.workspace).as_posix(), "regression_sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        self.compatibility = {"schema_version": 1, "checked_at": "2026-10-14T10:00:00Z",
            "host_capabilities": ["native-plugin-update", "native-thread-read"], "clients": profile}
        self.compat = self.write("compatibility.json", self.compatibility)

    def write(self, relative, data):
        path = self.workspace / relative; path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data)); return path

    def package(self, folder, name, version):
        root = self.base / folder; root.mkdir()
        (root / "VERSION").write_text(version + "\n")
        (root / "plugin.json").write_text(json.dumps({"name": name, "version": version}))
        contracts = {"schema_version": 1, "package": name, "package_version": version,
            "interfaces": {"workspace": 2, "maintenance": 1, "template_registry": 3, "profile": 1},
            "host_capabilities": ["native-plugin-update"], "permissions": []}
        if name == "report-kit-skills":
            contracts["interfaces"] = {"source:vk-post-screenshot": 1, "source:vk-comment-screenshot": 1, "shared:ui_queue": 1}
            contracts["permissions"] = {"vk-post-screenshot": ["vk.read"], "vk-comment-screenshot": ["vk.read"]}
            catalog = {"schema_version": 1, "package_version": version, "capabilities": [
                {"name": "vk-post-screenshot", "requires": []}, {"name": "vk-comment-screenshot", "requires": ["vk-post-screenshot"]}],
                "shared": ["skills/_shared/ui_queue.py"]}
            (root / "capabilities.json").write_text(json.dumps(catalog))
        (root / "contracts.json").write_text(json.dumps(contracts))
        names = sorted(p.name for p in root.iterdir()); names.append("PUBLIC-FILES.json")
        (root / "PUBLIC-FILES.json").write_text(json.dumps({"schema_version": 1, "files": names}))
        return root

    @staticmethod
    def pair(agent, skills):
        return {name: {"version": (root / "VERSION").read_text().strip(), "package_sha256": identity(root)}
                for name, root in [("report-kit-agent", agent), ("report-kit-skills", skills)]}

    def preflight(self):
        self.write("compatibility.json", self.compatibility)
        return preflight(self.workspace, self.current_agent, self.current_skills,
                         self.candidate_agent, self.candidate_skills, self.release, self.compat,
                         "2026-10-14T10:05:00Z")

    def test_missing_skill_permission_declaration_blocks(self):
        path = self.candidate_skills / "contracts.json"
        data = json.loads(path.read_text()); del data["permissions"]["vk-comment-screenshot"]
        path.write_text(json.dumps(data))
        candidate = self.pair(self.candidate_agent, self.candidate_skills)
        self.release["packages"] = candidate
        with self.assertRaisesRegex(ContractError, "permission_contract_inventory"):
            self.preflight()

    def test_daily_check_quiet_and_offline_keeps_current(self):
        self.assertEqual(due(self.source, "2026-10-14T09:00:00Z", "2026-10-14T10:00:00Z")["action"], "USE_CACHE")
        self.assertFalse(due(self.source, "2026-10-14T09:00:00Z", "2026-10-14T10:00:00Z")["notify"])
        self.assertEqual(due(self.source, "2026-10-13T09:00:00Z", "2026-10-14T10:00:00Z")["action"], "READ_WITH_NATIVE_TOOL")
        self.assertEqual(due(self.source, None, "2026-10-14T10:00:00Z", offline=True)["action"], "KEEP_CURRENT_OFFLINE")

    def test_unknown_source_future_time_or_credentials_rejected(self):
        source = copy.deepcopy(self.source); source["agent_repository"] = None
        self.assertEqual(due(source, None, "2026-10-14T10:00:00Z")["action"], "CONFIGURE_SOURCE")
        for url in [self.source["agent_repository"].replace("https://", "https://user:password@"), "https://elsewhere.invalid/example/repo", "https://github.com/example/repo?token=value"]:
            source["agent_repository"] = url
            with self.assertRaises(ValueError): due(source, None, "2026-10-14T10:00:00Z")
        with self.assertRaises(ValueError): due(self.source, "2026-10-15T10:00:00Z", "2026-10-14T10:00:00Z")

    def test_working_channel_not_preview_draft_revoked_or_downgrade(self):
        preview = copy.deepcopy(self.release); preview.update(release_id="preview", channel="preview")
        preview["packages"]["report-kit-agent"]["version"] = "0.2.0"
        draft = copy.deepcopy(self.release); draft.update(release_id="draft", published=False)
        revoked = copy.deepcopy(self.release); revoked.update(release_id="revoked", revoked=True)
        self.assertEqual(select_release({"schema_version": 1, "releases": [preview, draft, revoked, self.release]}, self.source, self.old)["release_id"], "fixture-dev2")
        self.assertIsNone(select_release({"schema_version": 1, "releases": [self.release]}, self.source, self.new))

    def test_semver_numeric_not_lexical_and_ambiguous_identity_rejected(self):
        newer = copy.deepcopy(self.release); newer["release_id"] = "dev10"; newer["packages"]["report-kit-agent"]["version"] = "0.1.0-dev.10"
        self.assertEqual(select_release({"schema_version": 1, "releases": [self.release, newer]}, self.source, self.old)["release_id"], "dev10")
        duplicate = copy.deepcopy(self.release); duplicate["packages"]["report-kit-agent"]["package_sha256"] = "f" * 64
        with self.assertRaises(ValueError): select_release({"schema_version": 1, "releases": [self.release, duplicate]}, self.source, self.old)

    def test_complete_clients_and_candidate_specific_regression(self):
        result = self.preflight(); self.assertEqual(result["status"], "READY_FOR_REVIEW")
        self.assertEqual(result["clients_checked"], 2)
        self.assertFalse(result["install_authorized"])

    def test_one_incompatible_client_blocks_global_update(self):
        self.compatibility["clients"]["second"]["interfaces"]["source:vk-post-screenshot"] = 2
        with self.assertRaisesRegex(ValueError, "interface_incompatible"): self.preflight()

    def test_transitive_skill_missing_and_cycle_blocked(self):
        del self.compatibility["clients"]["first"]["interfaces"]["source:vk-post-screenshot"]
        with self.assertRaisesRegex(ValueError, "interface_incompatible"): self.preflight()
        self.setUp_catalog_cycle()
        with self.assertRaises(ValueError): self.preflight()

    def setUp_catalog_cycle(self):
        p = self.candidate_skills / "capabilities.json"; d = json.loads(p.read_text())
        d["capabilities"][0]["requires"] = ["vk-comment-screenshot"]; p.write_text(json.dumps(d))
        self.release["packages"] = self.pair(self.candidate_agent, self.candidate_skills)

    def test_missing_stale_or_unregistered_client_blocked(self):
        del self.compatibility["clients"]["second"]
        with self.assertRaisesRegex(ValueError, "client_inventory"): self.preflight()
        self.compatibility["clients"]["second"] = copy.deepcopy(self.compatibility["clients"]["first"])
        self.compatibility["checked_at"] = "2026-10-12T10:00:00Z"
        with self.assertRaisesRegex(ValueError, "stale_compatibility"): self.preflight()

    def test_profile_edit_and_protected_history_change_blocked(self):
        (self.workspace / "clients/first/AGENT.md").write_text("Owner edited rules")
        with self.assertRaisesRegex(ValueError, "profile_changed"): self.preflight()

    def test_active_run_new_permission_missing_host_or_candidate_tamper(self):
        for edit, code in [(lambda d: d["clients"]["first"].update(active_run=True), "active_run"),
                           (lambda d: d["clients"]["first"].update(permission_scopes=[]), "permission_change"),
                           (lambda d: d.update(host_capabilities=[]), "missing_host_capability")]:
            saved = copy.deepcopy(self.compatibility); edit(self.compatibility)
            with self.assertRaisesRegex(ValueError, code): self.preflight()
            self.compatibility = saved
        (self.candidate_agent / "VERSION").write_text("0.1.0-dev.99\n")
        with self.assertRaises(ValueError): self.preflight()

    def test_failed_or_old_candidate_regression_is_not_compatibility(self):
        p = self.workspace / "receipts/first.json"; d = json.loads(p.read_text()); d["candidate"] = self.old
        p.write_text(json.dumps(d)); self.compatibility["clients"]["first"]["regression_sha256"] = hashlib.sha256(p.read_bytes()).hexdigest()
        with self.assertRaisesRegex(ValueError, "regression_receipt"): self.preflight()

    def test_rollout_requires_actual_ack_for_every_client(self):
        plan = self.preflight(); receipts = {}
        for client in ["first", "second"]:
            receipts[client] = {"kind": "context_refresh", "source_kind": "native_tool_result", "source_locator": "synthetic original completed turn",
                "client_id": client, "binding": self.compatibility["clients"][client]["binding"],
                "packages": self.new, "profile_sha256": self.compatibility["clients"][client]["profile_sha256"],
                "result": "PASS", "blockers": [], "loaded_identity_verified": True}
        result = rollout(plan, self.compatibility, {"first": receipts["first"]}, self.new)
        self.assertEqual(result["status"], "PARTIAL"); self.assertEqual(result["pending_clients"], ["second"])
        self.assertEqual(rollout(plan, self.compatibility, receipts, self.new)["status"], "APPLIED_LIMITED")
        receipts["second"]["source_kind"] = "agent_message"
        with self.assertRaises(ValueError): rollout(plan, self.compatibility, receipts, self.new)

    def test_rollout_loaded_identity_is_not_source_presence(self):
        with self.assertRaisesRegex(ValueError, "loaded_identity"):
            rollout(self.preflight(), self.compatibility, {}, self.old)

    def rollback_snapshot(self):
        return {"schema_version": 1, "old": self.old, "new": self.new, "clients": ["first", "second"],
            "protected_files": {k: v for record in self.compatibility["clients"].values() for k, v in record["protected_files"].items()}}

    def test_rollback_is_readonly_and_preserves_owner_edits(self):
        snapshot = self.rollback_snapshot()
        self.assertEqual(rollback_preflight(self.workspace, snapshot, self.old, self.new)["writes"], [])
        path = self.workspace / "clients/second/AGENT.md"; path.write_text("Later owner edit")
        with self.assertRaisesRegex(ValueError, "subsequent_owner_edit"):
            rollback_preflight(self.workspace, snapshot, self.old, self.new)
        self.assertEqual(path.read_text(), "Later owner edit")

    def test_rollback_wrong_pair_and_incomplete_protection_rejected(self):
        with self.assertRaisesRegex(ValueError, "rollback_identity"):
            rollback_preflight(self.workspace, self.rollback_snapshot(), self.new, self.new)
        snapshot = self.rollback_snapshot(); del snapshot["protected_files"]["clients/second/AGENT.md"]
        with self.assertRaisesRegex(ValueError, "rollback_protected_inventory"):
            rollback_preflight(self.workspace, snapshot, self.old, self.new)

    def test_ghost_client_duplicate_version_and_source_revocation(self):
        ghost = self.workspace / "clients/ghost/AGENT.md"; ghost.parent.mkdir(); ghost.write_text("Unregistered")
        with self.assertRaisesRegex(ValueError, "client_inventory"): self.preflight()
        revoked = copy.deepcopy(self.release); revoked["revoked"] = True
        with self.assertRaisesRegex(ValueError, "current_release_revoked"):
            select_release({"schema_version": 1, "releases": [revoked]}, self.source, self.new)

    def test_all_inspections_leave_workspace_bytes_unchanged(self):
        self.write("compatibility.json", self.compatibility)
        before = {p.relative_to(self.workspace).as_posix(): p.read_bytes() for p in self.workspace.rglob("*") if p.is_file()}
        self.preflight(); rollback_preflight(self.workspace, self.rollback_snapshot(), self.old, self.new)
        after = {p.relative_to(self.workspace).as_posix(): p.read_bytes() for p in self.workspace.rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_client_cannot_disappear_between_preflight_and_rollout(self):
        plan = self.preflight(); changed = copy.deepcopy(self.compatibility)
        del changed["clients"]["second"]
        with self.assertRaisesRegex(ValueError, "preflight_snapshot_changed"):
            rollout(plan, changed, {}, self.new)

    def test_full_refresh_does_not_accept_wrong_chat_binding(self):
        plan = self.preflight(); client = "first"
        receipt = {"kind": "context_refresh", "source_kind": "native_tool_result", "source_locator": "synthetic turn",
            "client_id": client, "binding": {"thread_id": "wrong", "host_id": "local", "project_id": "synthetic-project"},
            "packages": self.new, "profile_sha256": self.compatibility["clients"][client]["profile_sha256"],
            "result": "PASS", "blockers": [], "loaded_identity_verified": True}
        with self.assertRaisesRegex(ValueError, "refresh_receipt"):
            rollout(plan, self.compatibility, {client: receipt}, self.new)

    def update_policy(self):
        return {"schema_version": 1, "mode": "compatible", "source_sha256": document_identity(self.source),
                "authority": {"source_kind": "human_message", "source_locator": "synthetic owner choice", "decision": "compatible_updates"}, "revoked": False}

    def test_compatible_preference_keeps_native_permission_boundary(self):
        plan = self.preflight()
        for host, route in [("required", "WAIT_FOR_HOST_APPROVAL"), ("unknown", "CHECK_HOST_APPROVAL"), ("unavailable", "MANUAL_HOST_STEP"), ("not_required", "NATIVE_COMPATIBLE_ROUTE")]:
            result = activation_decision(self.update_policy(), self.source, plan, self.compatibility, host)
            self.assertEqual(result["route"], route)
            self.assertFalse(result["install_authorized"])

    def test_update_choice_default_and_revocation_ask_again(self):
        policy = {"schema_version": 1, "mode": "ask_each", "source_sha256": None, "authority": None, "revoked": False}
        self.assertEqual(activation_decision(policy, self.source, self.preflight(), self.compatibility, "not_required")["route"], "ASK_FOR_UPDATE")
        policy = self.update_policy(); policy["revoked"] = True
        self.assertEqual(activation_decision(policy, self.source, self.preflight(), self.compatibility, "not_required")["route"], "ASK_FOR_UPDATE")

    def test_automatic_choice_requires_same_source_and_working_channel(self):
        plan = self.preflight()
        for change in [("agent_repository", "https://github.com/example/another"), ("channel", "preview"), ("skills_repository", None)]:
            source = dict(self.source); source[change[0]] = change[1]
            with self.assertRaisesRegex(ValueError, "update_policy_source"):
                activation_decision(self.update_policy(), source, plan, self.compatibility, "not_required")

    def test_agent_message_or_missing_choice_cannot_select_auto(self):
        for value in [None, {"source_kind": "agent_message", "source_locator": "synthetic", "decision": "compatible_updates"}, {"source_kind": "human_message", "source_locator": "", "decision": "compatible_updates"}]:
            policy = self.update_policy(); policy["authority"] = value
            with self.assertRaises(ValueError): activation_decision(policy, self.source, self.preflight(), self.compatibility, "not_required")

    def test_automatic_route_requires_unchanged_full_preflight(self):
        plan = self.preflight(); compatibility = copy.deepcopy(self.compatibility)
        del compatibility["clients"]["second"]
        with self.assertRaisesRegex(ValueError, "preflight_snapshot_changed"):
            activation_decision(self.update_policy(), self.source, plan, compatibility, "not_required")
        plan["status"] = "PARTIAL"
        with self.assertRaisesRegex(ValueError, "preflight_required"):
            activation_decision(self.update_policy(), self.source, plan, self.compatibility, "not_required")

    def test_policy_cli_defaults_to_unknown_host_permission_without_writes(self):
        policy = self.write("update-policy.json", self.update_policy())
        source = self.write("source.json", self.source)
        plan = self.write("plan.json", self.preflight())
        before = {p.relative_to(self.workspace).as_posix(): p.read_bytes() for p in self.workspace.rglob("*") if p.is_file()}
        result = subprocess.run([sys.executable, "-B", str(Path(__file__).with_name("updates.py")), "policy", str(policy), str(source), str(plan), str(self.compat)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual(record["route"], "CHECK_HOST_APPROVAL")
        self.assertFalse(record["install_authorized"])
        self.assertEqual(before, {p.relative_to(self.workspace).as_posix(): p.read_bytes() for p in self.workspace.rglob("*") if p.is_file()})


if __name__ == "__main__": unittest.main()
