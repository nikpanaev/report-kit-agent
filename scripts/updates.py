"""Readonly release/compatibility/rollout contracts. Native tools fetch and install; this does neither."""
import argparse
import hashlib
from datetime import datetime, timezone
import json
from pathlib import Path
import re

from check_package import identity
from check_workspace import check as check_workspace
from maintenance import ContractError, require, fields, private_path, read_json, sealed_json, SHA

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = {"report-kit-agent", "report-kit-skills"}
CORE = {"workspace", "maintenance", "template_registry", "profile"}
LIMIT = "Contract/identity/local-file checks only. Verify original human/native sources, release provenance, current runs, actual host/installed identities and permissions before action; no install or authority proof."


def timestamp(value):
    require(isinstance(value, str), "timestamp")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    require(result.tzinfo is not None, "timestamp_timezone")
    return result


def version(value):
    require(isinstance(value, str) and len(value) <= 200, "version")
    m = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?", value)
    require(m is not None, "version")
    parts = m.group(4).split(".") if m.group(4) else []
    require(all(not p.isdigit() or p == "0" or not p.startswith("0") for p in parts), "version_numeric_identifier")
    return tuple(map(int, m.group(1, 2, 3))), not bool(parts), tuple((0, int(p)) if p.isdigit() else (1, p) for p in parts)


def source_check(source):
    fields(source, {"schema_version", "agent_repository", "skills_repository", "channel", "interval_hours"}, "source_fields")
    require(type(source["schema_version"]) is int and source["schema_version"] == 1
            and source["channel"] in {"working", "preview"} and source["interval_hours"] == 24, "source_policy")
    for key in ["agent_repository", "skills_repository"]:
        value = source[key]
        require(value is None or (isinstance(value, str) and re.fullmatch(r"https://github\.com/[A-Za-z0-9][A-Za-z0-9-]{0,38}/[A-Za-z0-9][A-Za-z0-9._-]{0,99}", value)), "source_repository")


def due(source, checked_at, now, offline=False):
    source_check(source); current = timestamp(now)
    action = "READ_WITH_NATIVE_TOOL"
    if None in [source["agent_repository"], source["skills_repository"]]: action = "CONFIGURE_SOURCE"
    elif offline: action = "KEEP_CURRENT_OFFLINE"
    elif checked_at is not None:
        elapsed = (current - timestamp(checked_at)).total_seconds()
        require(elapsed >= 0, "future_source_observation")
        if elapsed < 86400: action = "USE_CACHE"
    return {"action": action, "notify": False, "limitations": LIMIT}


def pair_check(pair):
    fields(pair, PACKAGES, "package_pair")
    for record in pair.values():
        fields(record, {"version", "package_sha256"}, "package_record")
        version(record["version"])
        require(isinstance(record["package_sha256"], str) and SHA.fullmatch(record["package_sha256"]), "package_identity")


def release_check(release):
    fields(release, {"release_id", "channel", "published", "revoked", "packages"}, "release_record")
    require(isinstance(release["release_id"], str) and release["release_id"] and release["channel"] in {"working", "preview"}
            and type(release["published"]) is bool and type(release["revoked"]) is bool, "release_record")
    pair_check(release["packages"])


def document_identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def select_release(index, source, current):
    source_check(source); pair_check(current)
    fields(index, {"schema_version", "releases"}, "release_index")
    require(type(index["schema_version"]) is int and index["schema_version"] == 1 and isinstance(index["releases"], list), "release_index")
    versions, ids, selected = {}, set(), None
    for release in index["releases"]:
        release_check(release); key = (release["channel"], version(release["packages"]["report-kit-agent"]["version"]))
        require(release["release_id"] not in ids, "ambiguous_release_identity"); ids.add(release["release_id"])
        require(key not in versions or versions[key] == release["packages"], "ambiguous_release_identity")
        versions[key] = release["packages"]
        if release["packages"] == current and release["revoked"]: raise ContractError("current_release_revoked")
        if release["channel"] != source["channel"] or not release["published"] or release["revoked"]: continue
        if version(release["packages"]["report-kit-agent"]["version"]) == version(current["report-kit-agent"]["version"]):
            require(release["packages"] == current, "same_version_content_drift")
        if version(release["packages"]["report-kit-agent"]["version"]) <= version(current["report-kit-agent"]["version"]): continue
        if selected is None or version(release["packages"]["report-kit-agent"]["version"]) > version(selected["packages"]["report-kit-agent"]["version"]): selected = release
    return selected


def actual_pair(agent, skills):
    pair = {name: {"version": (root / "VERSION").read_text().strip(), "package_sha256": identity(root)}
            for name, root in [("report-kit-agent", agent), ("report-kit-skills", skills)]}
    pair_check(pair)
    for name, root in [("report-kit-agent", agent), ("report-kit-skills", skills)]:
        manifest = read_json(root / "plugin.json")
        require(manifest["name"] == name and manifest["version"] == pair[name]["version"], "package_manifest")
    dependency = agent / "dependencies.json"
    if dependency.exists():
        needed = read_json(dependency)["report-kit-skills"]
        require(needed["version"] == pair["report-kit-skills"]["version"]
                and needed["package_sha256"] == pair["report-kit-skills"]["package_sha256"], "dependency_identity")
    return pair


def contracts(root, name, package_version):
    data = read_json(root / "contracts.json")
    fields(data, {"schema_version", "package", "package_version", "interfaces", "host_capabilities", "permissions"}, "contracts_fields")
    require(type(data["schema_version"]) is int and data["schema_version"] == 1
            and data["package"] == name and data["package_version"] == package_version, "contracts_identity")
    require(isinstance(data["interfaces"], dict) and all(isinstance(k, str) and type(v) is int and v > 0 for k, v in data["interfaces"].items()), "contracts_interfaces")
    require(isinstance(data["host_capabilities"], list) and all(isinstance(v, str) for v in data["host_capabilities"]), "host_contract")
    if name == "report-kit-agent": require(isinstance(data["permissions"], list) and all(isinstance(v, str) for v in data["permissions"]), "permission_contract")
    else: require(isinstance(data["permissions"], dict) and all(isinstance(v, list) and all(isinstance(x, str) for x in v) for v in data["permissions"].values()), "permission_contract")
    return data


def skill_closure(catalog, names):
    graph = {item["name"]: item["requires"] for item in catalog["capabilities"]}
    require(len(graph) == len(catalog["capabilities"]), "capability_inventory")
    seen = set()
    def visit(name, active):
        require(name in graph and name not in active, "skill_dependency")
        if name in seen: return
        require(isinstance(graph[name], list) and all(isinstance(v, str) for v in graph[name]), "skill_dependency")
        for child in graph[name]: visit(child, active | {name})
        seen.add(name)
    for name in names: visit(name, set())
    return seen


def preflight(workspace, current_agent, current_skills, candidate_agent, candidate_skills, release, compatibility_path, now):
    roots = [Path(p).resolve() for p in [current_agent, current_skills, candidate_agent, candidate_skills]]
    workspace = Path(workspace).resolve(); check_workspace(workspace, roots + [ROOT])
    current_agent, current_skills, candidate_agent, candidate_skills = roots
    settings = read_json(workspace / "settings.json")
    current = actual_pair(current_agent, current_skills); candidate = actual_pair(candidate_agent, candidate_skills)
    require(version(candidate["report-kit-agent"]["version"]) > version(current["report-kit-agent"]["version"]),
            "candidate_version_not_newer")
    release_check(release)
    require(settings["packages"] == current, "current_package_drift")
    require(release["packages"] == candidate and release["published"] is True and release["revoked"] is False, "candidate_identity")
    compatibility_path = Path(compatibility_path).resolve(); require(compatibility_path.is_relative_to(workspace), "private_reference")
    data = read_json(compatibility_path)
    fields(data, {"schema_version", "checked_at", "host_capabilities", "clients"}, "compatibility_fields")
    require(type(data["schema_version"]) is int and data["schema_version"] == 1, "compatibility_schema")
    age = (timestamp(now) - timestamp(data["checked_at"])).total_seconds()
    require(0 <= age < 86400, "stale_compatibility")
    require(isinstance(data["clients"], dict) and set(data["clients"]) == set(settings["clients"]), "client_inventory")
    on_disk = {p.parent.name for p in (workspace / "clients").glob("*/AGENT.md")}
    require(on_disk == set(settings["clients"]), "client_inventory")
    agent = contracts(candidate_agent, "report-kit-agent", candidate["report-kit-agent"]["version"])
    skills = contracts(candidate_skills, "report-kit-skills", candidate["report-kit-skills"]["version"])
    require(CORE <= set(agent["interfaces"]), "core_contract")
    require(isinstance(data["host_capabilities"], list) and all(isinstance(v, str) for v in data["host_capabilities"])
            and set(agent["host_capabilities"] + skills["host_capabilities"]) <= set(data["host_capabilities"]), "missing_host_capability")
    catalog = read_json(candidate_skills / "capabilities.json")
    require(catalog["package_version"] == candidate["report-kit-skills"]["version"], "catalog_identity")
    require(set(skills["permissions"]) == {item["name"] for item in catalog["capabilities"]}, "permission_contract_inventory")
    interfaces = {**agent["interfaces"], **skills["interfaces"]}
    for client, record in data["clients"].items():
        fields(record, {"binding", "profile_path", "profile_sha256", "profile_revision", "protected_files", "required_skills",
            "interfaces", "permission_scopes", "active_run", "regression_receipt", "regression_sha256"}, "client_contract_fields")
        fields(record["binding"], {"thread_id", "host_id", "project_id"}, "client_binding")
        require(all(isinstance(record["binding"][k], str) and record["binding"][k] for k in {"thread_id", "host_id"}), "client_binding")
        require(record["profile_path"] == f"clients/{client}/AGENT.md", "profile_scope")
        path = private_path(workspace, record["profile_path"])
        require(isinstance(record["profile_sha256"], str) and SHA.fullmatch(record["profile_sha256"])
                and identity_file(path) == record["profile_sha256"], "profile_changed")
        require(type(record["profile_revision"]) is int and record["profile_revision"] > 0, "profile_revision")
        require(isinstance(record["protected_files"], dict) and record["protected_files"].get(record["profile_path"]) == record["profile_sha256"], "protected_inventory")
        for reference, sha in record["protected_files"].items():
            require(isinstance(sha, str) and SHA.fullmatch(sha) and identity_file(private_path(workspace, reference)) == sha, "protected_file_changed")
        require(record["active_run"] is False, "active_run")
        require(isinstance(record["required_skills"], list) and all(isinstance(v, str) for v in record["required_skills"]), "required_skills")
        required = skill_closure(catalog, record["required_skills"])
        needed = CORE | {"source:" + name for name in required} | {k for k in skills["interfaces"] if k.startswith("shared:")}
        require(isinstance(record["interfaces"], dict) and all(type(record["interfaces"].get(k)) is int
                and record["interfaces"].get(k) == interfaces.get(k)
                for k in needed | set(record["interfaces"])), "interface_incompatible")
        require(isinstance(record["permission_scopes"], list) and all(isinstance(v, str) for v in record["permission_scopes"]), "permission_inventory")
        permission = set(agent["permissions"])
        for name in required: permission.update(skills["permissions"].get(name, []))
        require(permission <= set(record["permission_scopes"]), "permission_change")
        receipt = sealed_json(workspace, record["regression_receipt"], record["regression_sha256"])
        fields(receipt, {"kind", "source_kind", "source_locator", "client_id", "candidate", "profile_sha256", "result", "checks"}, "regression_receipt")
        require(receipt["kind"] == "compatibility" and receipt["source_kind"] == "native_tool_result" and isinstance(receipt["source_locator"], str)
                and receipt["source_locator"] and receipt["client_id"] == client and receipt["candidate"] == candidate
                and receipt["profile_sha256"] == record["profile_sha256"] and receipt["result"] == "PASS"
                and isinstance(receipt["checks"], list) and {"client_overrides", "protected_history", "affected_components"} <= set(receipt["checks"]), "regression_receipt")
    return {"status": "READY_FOR_REVIEW", "clients_checked": len(data["clients"]), "clients": sorted(data["clients"]),
            "compatibility_sha256": document_identity(data), "current": current,
            "candidate": candidate, "install_authorized": False, "limitations": LIMIT}


def identity_file(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""): digest.update(chunk)
    return digest.hexdigest()


def same_snapshot(plan, compatibility):
    require(plan["status"] == "READY_FOR_REVIEW", "preflight_required")
    require(plan["clients"] == sorted(compatibility["clients"]) and plan["clients_checked"] == len(compatibility["clients"])
            and plan["compatibility_sha256"] == document_identity(compatibility), "preflight_snapshot_changed")


def activation_decision(policy, source, plan, compatibility, host_approval):
    source_check(source)
    same_snapshot(plan, compatibility)
    require(host_approval in {"required", "not_required", "unknown", "unavailable"}, "host_approval")
    fields(policy, {"schema_version", "mode", "source_sha256", "authority", "revoked"}, "update_policy_fields")
    require(type(policy["schema_version"]) is int and policy["schema_version"] == 1
            and policy["mode"] in {"ask_each", "compatible"} and type(policy["revoked"]) is bool, "update_policy")
    route = "ASK_FOR_UPDATE"
    if policy["mode"] == "compatible" and not policy["revoked"]:
        require(None not in [source["agent_repository"], source["skills_repository"]]
                and source["channel"] == "working" and policy["source_sha256"] == document_identity(source), "update_policy_source")
        authority = policy["authority"]
        fields(authority, {"source_kind", "source_locator", "decision"}, "update_policy_authority")
        require(authority["source_kind"] == "human_message" and authority["decision"] == "compatible_updates"
                and isinstance(authority["source_locator"], str) and authority["source_locator"].strip(), "update_policy_authority")
        route = {"required": "WAIT_FOR_HOST_APPROVAL", "unknown": "CHECK_HOST_APPROVAL",
                 "unavailable": "MANUAL_HOST_STEP", "not_required": "NATIVE_COMPATIBLE_ROUTE"}[host_approval]
    return {"route": route, "candidate": plan["candidate"], "clients": plan["clients"],
            "install_authorized": False, "limitations": LIMIT + " Policy is a revocable preference; original human choice and host permissions must be independently checked. No installation performed."}


def rollout(plan, compatibility, receipts, loaded):
    require(plan["status"] == "READY_FOR_REVIEW" and loaded == plan["candidate"], "loaded_identity")
    same_snapshot(plan, compatibility)
    expected = set(compatibility["clients"]); require(isinstance(receipts, dict) and set(receipts) <= expected, "refresh_inventory")
    pending = sorted(expected - set(receipts))
    for client, receipt in receipts.items():
        fields(receipt, {"kind", "source_kind", "source_locator", "client_id", "binding", "packages", "profile_sha256", "result", "blockers", "loaded_identity_verified"}, "refresh_receipt")
        require(receipt["kind"] == "context_refresh" and receipt["source_kind"] == "native_tool_result"
                and isinstance(receipt["source_locator"], str) and receipt["source_locator"] and receipt["client_id"] == client
                and receipt["binding"] == compatibility["clients"][client]["binding"]
                and receipt["packages"] == loaded and receipt["profile_sha256"] == compatibility["clients"][client]["profile_sha256"], "refresh_receipt")
        require(isinstance(receipt["blockers"], list) and type(receipt["loaded_identity_verified"]) is bool, "refresh_receipt")
        if receipt["result"] != "PASS" or receipt["blockers"] or not receipt["loaded_identity_verified"]: pending.append(client)
    return {"status": "PARTIAL" if pending else "APPLIED_LIMITED", "pending_clients": sorted(pending), "limitations": LIMIT}


def rollback_preflight(workspace, snapshot, selected_old_pair, actual_new_pair):
    workspace = Path(workspace).resolve(); pair_check(selected_old_pair); pair_check(actual_new_pair)
    fields(snapshot, {"schema_version", "old", "new", "protected_files", "clients"}, "rollback_snapshot")
    require(type(snapshot["schema_version"]) is int and snapshot["schema_version"] == 1
            and snapshot["old"] == selected_old_pair and snapshot["new"] == actual_new_pair, "rollback_identity")
    settings = read_json(workspace / "settings.json")
    require(isinstance(snapshot["clients"], list) and set(snapshot["clients"]) == set(settings["clients"]), "rollback_client_inventory")
    require(isinstance(snapshot["protected_files"], dict), "rollback_protected_inventory")
    for client in snapshot["clients"]:
        require(f"clients/{client}/AGENT.md" in snapshot["protected_files"], "rollback_protected_inventory")
    for path, sha in snapshot["protected_files"].items():
        require(isinstance(sha, str) and SHA.fullmatch(sha)
                and identity_file(private_path(workspace, path)) == sha, "subsequent_owner_edit")
    return {"status": "READY_FOR_ROLLBACK_REVIEW", "selected": selected_old_pair,
            "writes": [], "limitations": LIMIT + " Package selection rollback is not data migration/restore."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="mode", required=True)
    read = sub.add_parser("due"); read.add_argument("source", type=Path); read.add_argument("--checked-at"); read.add_argument("--offline", action="store_true")
    select = sub.add_parser("select"); select.add_argument("source", type=Path); select.add_argument("index", type=Path); select.add_argument("current", type=Path)
    check = sub.add_parser("preflight"); check.add_argument("workspace", type=Path)
    for key in ["current-agent", "current-skills", "candidate-agent", "candidate-skills", "release", "compatibility"]: check.add_argument("--" + key, type=Path, required=True)
    refresh = sub.add_parser("rollout"); refresh.add_argument("plan", type=Path); refresh.add_argument("compatibility", type=Path); refresh.add_argument("receipts", type=Path); refresh.add_argument("loaded", type=Path)
    undo = sub.add_parser("rollback"); undo.add_argument("workspace", type=Path); undo.add_argument("snapshot", type=Path); undo.add_argument("old", type=Path); undo.add_argument("actual_new", type=Path)
    policy = sub.add_parser("policy")
    for key in ["policy", "source", "plan", "compatibility"]: policy.add_argument(key, type=Path)
    policy.add_argument("--host-approval", choices=["required", "not_required", "unknown", "unavailable"], default="unknown")
    args = parser.parse_args(); now = datetime.now(timezone.utc).isoformat()
    try:
        if args.mode == "due": result = due(read_json(args.source), args.checked_at, now, args.offline)
        elif args.mode == "select": result = {"selected": select_release(read_json(args.index), read_json(args.source), read_json(args.current)), "limitations": LIMIT}
        elif args.mode == "rollout": result = rollout(read_json(args.plan), read_json(args.compatibility), read_json(args.receipts), read_json(args.loaded))
        elif args.mode == "rollback": result = rollback_preflight(args.workspace, read_json(args.snapshot), read_json(args.old), read_json(args.actual_new))
        elif args.mode == "policy": result = activation_decision(read_json(args.policy), read_json(args.source), read_json(args.plan), read_json(args.compatibility), args.host_approval)
        else: result = preflight(args.workspace, args.current_agent, args.current_skills, args.candidate_agent, args.candidate_skills,
                                read_json(args.release), args.compatibility, now)
    except (ValueError, OSError, KeyError, TypeError, AssertionError) as error:
        result = {"status": "BLOCKED", "issue": str(error) if isinstance(error, ContractError) else "invalid_local_record"}
    print(json.dumps(result)); raise SystemExit(result.get("status") == "BLOCKED")
