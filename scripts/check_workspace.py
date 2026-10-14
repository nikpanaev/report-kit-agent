"""Validate a chosen external workspace skeleton; never create folders or read credentials."""
import argparse
import json
from pathlib import Path


def check(workspace, package_roots):
    workspace = workspace.resolve()
    for package in package_roots:
        package = package.resolve()
        if workspace.is_relative_to(package) or package.is_relative_to(workspace):
            raise ValueError("workspace_and_packages_must_be_separate")
    settings = json.loads((workspace / "settings.json").read_text())
    if set(settings) != {"schema_version", "timezone", "packages", "capabilities", "clients"}:
        raise ValueError("unexpected_settings_field")
    if settings["schema_version"] != 1 or not settings["timezone"]:
        raise ValueError("settings_schema_or_timezone")
    if not isinstance(settings["clients"], list) or len(settings["clients"]) != len(set(settings["clients"])):
        raise ValueError("client_inventory")
    if not isinstance(settings["capabilities"], dict) or set(settings["packages"]) != {"report-agent", "report-skills"}:
        raise ValueError("package_capability_inventory")
    return {"status": "PASS_LIMITED", "clients": len(settings["clients"]),
            "limitations": "Only workspace separation/schema; no ACL, access, identity, client/template or secret-store readiness proof."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", type=Path)
    parser.add_argument("--package-root", type=Path, action="append", required=True)
    args = parser.parse_args()
    try:
        result = check(args.workspace, args.package_root)
    except (ValueError, OSError, KeyError, TypeError) as error:
        result = {"status": "FAIL", "issue": str(error)}
    print(json.dumps(result))
    raise SystemExit(result["status"] == "FAIL")
