"""Read-only private maintenance contracts; never send messages, grant rights or replay tools."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from check_package import sensitive
from check_workspace import check as check_workspace
from support_bundle import emit as support_event

ROOT = Path(__file__).resolve().parents[1]
ADDRESS = {"thread_id", "host_id", "project_id"}
SHA = re.compile(r"[a-f0-9]{64}")
ACTIONS = {"request", "callback", "replay"}
LIMIT = "Local record consistency only; verify native roles and original human/tool sources before action. No messaging, authority, live replay, isolation or installation proof."


class ContractError(ValueError): pass


def require(condition, code):
    if not condition: raise ContractError(code)


def fields(value, expected, code):
    require(isinstance(value, dict) and set(value) == set(expected), code)


def private_path(root, reference):
    require(isinstance(reference, str) and bool(reference), "private_reference")
    path = Path(reference)
    require(not path.is_absolute() and ".." not in path.parts, "private_reference")
    path = (root / path).resolve()
    require(path.is_relative_to(root.resolve()), "private_reference")
    return path


def read_json(path):
    require(path.stat().st_size <= 1024 * 1024, "record_too_large")
    return json.loads(path.read_text(encoding="utf-8"))


def sealed_json(root, reference, digest):
    require(isinstance(digest, str) and SHA.fullmatch(digest), "receipt_identity")
    path = private_path(root, reference)
    require(path.stat().st_size <= 1024 * 1024 and hashlib.sha256(path.read_bytes()).hexdigest() == digest, "receipt_changed")
    return read_json(path)


def address(binding): return {k: binding[k] for k in ADDRESS}


def check_registry(workspace, skills_root):
    workspace = Path(workspace).resolve(); skills_root = Path(skills_root).resolve()
    check_workspace(workspace, [ROOT, skills_root])
    settings = read_json(workspace / "settings.json")
    known = {item["name"] for item in read_json(skills_root / "capabilities.json")["capabilities"]}
    registry = read_json(workspace / "maintenance.json")
    fields(registry, {"schema_version", "coordinator", "maintainers", "clients", "grants"}, "registry_fields")
    require(type(registry["schema_version"]) is int and registry["schema_version"] == 1, "registry_schema")
    require(isinstance(registry["maintainers"], dict) and set(registry["maintainers"]) <= known, "maintainer_inventory")
    require(isinstance(registry["clients"], dict) and set(registry["clients"]) == set(settings["clients"]), "client_inventory")
    endpoints = {}
    if registry["coordinator"] is not None: endpoints["coordinator"] = registry["coordinator"]
    require(not (registry["clients"] or registry["maintainers"]) or "coordinator" in endpoints, "missing_coordinator")
    for client, record in registry["clients"].items():
        require(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", client), "client_id")
        fields(record, {"binding", "paused"}, "client_record")
        require(type(record["paused"]) is bool, "pause_state")
        endpoints["client:" + client] = record["binding"]
    endpoints.update({"skill:" + name: binding for name, binding in registry["maintainers"].items()})
    seen = set()
    for role, binding in endpoints.items():
        fields(binding, ADDRESS | {"receipt"}, "binding_fields")
        require(all(isinstance(binding[k], str) and binding[k] for k in {"thread_id", "host_id"}), "binding_identity")
        require(binding["project_id"] is None or isinstance(binding["project_id"], str), "binding_project")
        key = tuple(binding[k] for k in sorted(ADDRESS))
        require(key not in seen, "duplicate_binding"); seen.add(key)
        receipt = read_json(private_path(workspace, binding["receipt"]))
        fields(receipt, ADDRESS | {"role", "source_kind", "source_locator"}, "role_receipt")
        require(receipt["role"] == role and address(receipt) == address(binding)
                and receipt["source_kind"] == "native_thread_read"
                and isinstance(receipt["source_locator"], str) and receipt["source_locator"], "role_receipt")
    require(isinstance(registry["grants"], list), "grant_inventory")
    ids = set()
    for grant in registry["grants"]:
        fields(grant, {"id", "origin", "target", "origin_binding", "target_binding", "actions", "authority_ref", "revoked"}, "grant_fields")
        require(isinstance(grant["id"], str) and grant["id"] and grant["id"] not in ids, "grant_id"); ids.add(grant["id"])
        require(grant["origin"] in endpoints and grant["target"] in endpoints and grant["origin"] != grant["target"], "grant_endpoints")
        require(grant["origin_binding"] == address(endpoints[grant["origin"]])
                and grant["target_binding"] == address(endpoints[grant["target"]]), "grant_binding_drift")
        require(isinstance(grant["actions"], list) and set(grant["actions"]) <= ACTIONS
                and len(set(grant["actions"])) == len(grant["actions"]) and type(grant["revoked"]) is bool, "grant_actions")
        proof = read_json(private_path(workspace, grant["authority_ref"]))
        expected = {k: v for k, v in grant.items() if k != "authority_ref"}
        fields(proof, set(expected) | {"source_kind", "source_locator"}, "human_authority_receipt")
        require(proof["source_kind"] == "human_message" and isinstance(proof["source_locator"], str) and proof["source_locator"]
                and all(proof[k] == v for k, v in expected.items()), "human_authority_receipt")
    return {"workspace": workspace, "registry": registry, "endpoints": endpoints,
            "status": "PASS_LIMITED" if endpoints else "NEEDS_SETUP", "limitations": LIMIT}


def route(checked, origin, target, grant_id, action):
    grant = next((g for g in checked["registry"]["grants"] if g["id"] == grant_id), None)
    require(grant is not None and not grant["revoked"] and grant["origin"] == origin
            and grant["target"] == target and action in grant["actions"] and action in ACTIONS, "grant_scope")
    require(target == "coordinator" or target.startswith("skill:"), "maintenance_target_role")
    return {"origin": address(checked["endpoints"][origin]), "target": address(checked["endpoints"][target]),
            "sender": address(checked["endpoints"][target if action == "callback" else origin]),
            "recipient": address(checked["endpoints"][origin if action == "callback" else target]),
            "authority_ref": grant["authority_ref"], "status": "PASS_LIMITED", "limitations": LIMIT}


def check_incident(workspace, incident_path, skills_root, previous_path=None):
    checked = check_registry(workspace, skills_root); root = checked["workspace"]
    incident_path = Path(incident_path).resolve()
    require(incident_path.is_relative_to(root), "private_reference")
    incident = read_json(incident_path)
    fields(incident, {"schema_version", "incident_id", "origin", "target", "grant_id", "classification",
        "case_ref", "case_sha256", "source_sha256", "budget", "assets", "events"}, "incident_fields")
    require(type(incident["schema_version"]) is int and incident["schema_version"] == 1, "incident_schema")
    require(isinstance(incident["incident_id"], str) and re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", incident["incident_id"]), "incident_id")
    require(incident["classification"] in {"bug", "configuration", "access", "data_limit", "capability"}, "incident_classification")
    require(isinstance(incident["source_sha256"], str) and SHA.fullmatch(incident["source_sha256"]), "source_identity")
    route(checked, incident["origin"], incident["target"], incident["grant_id"], "request")
    case = sealed_json(root, incident["case_ref"], incident["case_sha256"])
    fields(case, {"expected", "actual", "reproducer", "allowed_scope"}, "case_fields")
    require(all(isinstance(v, str) and v.strip() for v in case.values()) and not sensitive(json.dumps(case)), "unsanitized_case")
    fields(incident["budget"], {"cap", "started"}, "budget_fields")
    cap, started = incident["budget"]["cap"], incident["budget"]["started"]
    require(type(cap) is int and type(started) is int and 0 <= started <= cap <= 200, "budget_scope")
    require(isinstance(incident["events"], list) and isinstance(incident["assets"], list), "incident_inventory")
    if previous_path is not None:
        previous_path = Path(previous_path).resolve(); require(previous_path.is_relative_to(root), "private_reference")
        previous = read_json(previous_path)
        require({k: v for k, v in previous.items() if k != "events"} == {k: v for k, v in incident.items() if k != "events"}
                and incident["events"][:len(previous["events"])] == previous["events"], "history_rewrite")
    state, blocked, fixed = "PREPARED", None, None
    event_ids, received, accepted = set(), False, False
    for event in incident["events"]:
        fields(event, {"id", "kind", "actor", "receipt", "receipt_sha256"}, "event_fields")
        require(isinstance(event["id"], str) and event["id"] and event["id"] not in event_ids, "duplicate_event")
        event_ids.add(event["id"]); kind = event["kind"]
        receipt = sealed_json(root, event["receipt"], event["receipt_sha256"])
        common = {"kind", "incident_id", "actor", "source_kind", "source_locator"}
        extras = {"candidate_ready": {"fix_sha256", "checks"}, "callback_received": {"fix_sha256"},
            "replay": {"result", "loaded_sha256", "origin_paused", "started_before", "started_after"},
            "blocked": {"reason"}, "assets_received": {"assets"}, "assets_accepted": {"assets"}}
        fields(receipt, common | extras.get(kind, set()), "event_receipt")
        require(receipt["kind"] == kind and receipt["incident_id"] == incident["incident_id"]
                and receipt["actor"] == event["actor"] and isinstance(receipt["source_locator"], str) and receipt["source_locator"]
                and receipt["source_kind"] in {"native_tool_result", "native_thread_read", "human_message", "local_attempt_ledger"}, "event_receipt")
        if kind == "request_started": require(receipt["source_kind"] == "local_attempt_ledger", "attempt_ledger_required")
        elif kind not in {"assets_accepted", "unblocked"}:
            require(receipt["source_kind"] in {"native_tool_result", "native_thread_read"}, "actual_tool_source_required")
        actor = incident["target"] if kind in {"acknowledged", "candidate_ready", "callback_received"} else incident["origin"]
        require(event["actor"] == actor, "event_actor")
        require(state != "RESOLVED" or kind in {"assets_received", "assets_accepted"}, "event_transition")
        require(blocked is None or kind == "unblocked", "event_transition")
        if kind == "request_started":
            require(state == "PREPARED", "event_transition"); state = "REQUEST_STARTED"
        elif kind == "request_sent":
            require(state in {"PREPARED", "REQUEST_STARTED"}, "event_transition"); state = "DELIVERED"
        elif kind == "acknowledged":
            require(state == "DELIVERED", "event_transition"); state = "ACKNOWLEDGED"
        elif kind == "candidate_ready":
            require(state == "ACKNOWLEDGED" and isinstance(receipt["fix_sha256"], str)
                    and SHA.fullmatch(receipt["fix_sha256"]), "event_transition")
            require(isinstance(receipt["checks"], list) and {"reproducer", "affected_regression"} <= set(receipt["checks"]), "candidate_checks")
            fixed = receipt["fix_sha256"]; state = "FIXED_CANDIDATE"
        elif kind == "callback_received":
            require(state == "FIXED_CANDIDATE" and receipt["fix_sha256"] == fixed, "event_transition")
            route(checked, incident["origin"], incident["target"], incident["grant_id"], "callback")
            state = "AWAITING_ORIGIN_VERIFICATION"
        elif kind == "replay":
            require(state == "AWAITING_ORIGIN_VERIFICATION", "event_transition")
            route(checked, incident["origin"], incident["target"], incident["grant_id"], "replay")
            require(receipt["origin_paused"] is False and receipt["loaded_sha256"] == fixed, "replay_identity_or_pause")
            if previous_path is not None and event not in previous["events"]:
                client = incident["origin"].removeprefix("client:")
                require(client not in checked["registry"]["clients"] or not checked["registry"]["clients"][client]["paused"], "owner_currently_paused")
            before, after = receipt["started_before"], receipt["started_after"]
            require(type(before) is int and type(after) is int and before == started and before <= after <= cap, "replay_budget")
            require(receipt["result"] in {"PASS", "FAIL"}, "replay_result")
            started = after
            if receipt["result"] == "PASS": state = "RESOLVED"
        elif kind == "blocked":
            require(receipt["reason"] in {"TARGET_BUSY", "TARGET_UNAVAILABLE", "PERMISSION_REQUIRED", "OWNER_PAUSED"}, "block_reason")
            blocked = receipt["reason"]
        elif kind == "unblocked":
            require(blocked is not None, "event_transition")
            if blocked in {"PERMISSION_REQUIRED", "OWNER_PAUSED"}:
                require(receipt["source_kind"] == "human_message", "human_resume_required")
            blocked = None
        elif kind in {"assets_received", "assets_accepted"}:
            require(state in {"AWAITING_ORIGIN_VERIFICATION", "RESOLVED"}
                    and receipt["assets"] == incident["assets"], "asset_receipt")
            if kind == "assets_received": received = True
            else:
                require(received and receipt["source_kind"] == "human_message", "asset_acceptance"); accepted = True
        else: raise ContractError("unknown_event")
    for asset in incident["assets"]:
        fields(asset, {"path", "sha256", "purpose"}, "asset_fields")
        require(asset["purpose"] in {"proof", "report"} and isinstance(asset["sha256"], str)
                and SHA.fullmatch(asset["sha256"]), "asset_identity")
        path = private_path(root, asset["path"])
        if asset["purpose"] == "report" and not (received and accepted):
            require(path.is_file(), "report_asset_missing")
            digest = hashlib.sha256()
            with path.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""): digest.update(chunk)
            require(digest.hexdigest() == asset["sha256"], "report_asset_changed")
    next_action = {"PREPARED": "VERIFY_SOURCES_THEN_REQUEST", "REQUEST_STARTED": "READBACK_OR_WAIT_NO_RESEND",
        "DELIVERED": "WAIT_FOR_ACK", "ACKNOWLEDGED": "WAIT_FOR_MAINTAINER",
        "FIXED_CANDIDATE": "VERIFY_SOURCES_THEN_CALLBACK", "AWAITING_ORIGIN_VERIFICATION": "VERIFY_INSTALLED_IDENTITY_AND_SCOPE_THEN_REPLAY",
        "RESOLVED": "NO_REPLAY"}[state]
    client = incident["origin"].removeprefix("client:")
    if state == "AWAITING_ORIGIN_VERIFICATION":
        if client in checked["registry"]["clients"] and checked["registry"]["clients"][client]["paused"]: next_action = "WAIT_FOR_OWNER_RESUME"
        elif started >= cap and cap: next_action = "REQUEST_BUDGET_DECISION"
    if blocked: next_action = "WAIT_FOR_TARGET" if blocked.startswith("TARGET_") else "WAIT_FOR_OWNER_DECISION"
    return {"status": "PASS_LIMITED", "state": state, "blocked": blocked, "budget_started": started,
            "next_action": next_action, "assets_received": received, "assets_accepted": accepted,
            "history_checked": previous_path is not None, "limitations": LIMIT}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path); parser.add_argument("--skills-root", type=Path, required=True)
    parser.add_argument("--incident", type=Path); parser.add_argument("--previous", type=Path)
    parser.add_argument("--origin"); parser.add_argument("--target"); parser.add_argument("--grant")
    parser.add_argument("--action", choices=sorted(ACTIONS))
    args = parser.parse_args()
    try:
        require(args.previous is None or args.incident is not None, "previous_requires_incident")
        if args.incident: require(not any([args.origin, args.target, args.grant, args.action]), "mixed_modes")
        elif any([args.origin, args.target, args.grant, args.action]):
            require(all([args.origin, args.target, args.grant, args.action]), "incomplete_route")
        if args.incident: result = check_incident(args.workspace, args.incident, args.skills_root, args.previous)
        elif args.action:
            result = route(check_registry(args.workspace, args.skills_root), args.origin, args.target, args.grant, args.action)
            result["next_action"] = "VERIFY_NATIVE_ROLE_AND_HUMAN_AUTHORITY"
        else:
            checked = check_registry(args.workspace, args.skills_root)
            result = {k: checked[k] for k in {"status", "limitations"}}
            result["roles"] = len(checked["endpoints"])
    except (ValueError, OSError, KeyError, TypeError) as error:
        result = {"status": "BLOCKED", "issue": str(error) if isinstance(error, ContractError) else "invalid_local_record"}
    support_event('maintenance','validation','check','failure' if result.get('status') == 'BLOCKED' else 'success',
                  'INVALID_INPUT' if result.get('status') == 'BLOCKED' else 'NONE')
    print(json.dumps(result)); raise SystemExit(result["status"] == "BLOCKED")
