"""Read-only package inventory, local dependency identity and publication hygiene checks."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

IGNORED = {".git", ".token-optimizer", "__pycache__", ".pytest_cache", ".DS_Store"}
PRIVATE = {".auth", ".env", ".venv", "node_modules", "local", "work", "private"}
RULES = {
    "personal_home": re.compile(r"(?:/Users|/home)/[A-Za-z0-9._-]+/"),
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "provider_token": re.compile(r"\b(?:sk|ghp|github_pat|xox[baprs])[-_][A-Za-z0-9_-]{20,}\b"),
    "live_google_file": re.compile(r"https://(?:docs\.google\.com/(?:presentation|spreadsheets|document)/d|drive\.google\.com/(?:drive/(?:u/\d+/)?folders|file/d))/[A-Za-z0-9_-]{12,}"),
}
EMAIL = re.compile(r"[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})")


def _require(condition, message):
    if not condition: raise ValueError(message)


def sensitive(text):
    findings = [name for name, pattern in RULES.items() if pattern.search(text)]
    if any(m.group(1) not in {"example.test", "example.invalid", "example.com"} for m in EMAIL.finditer(text)):
        findings.append("non_synthetic_email")
    return findings


def files(root):
    root = root.resolve()
    result = {}
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if any(part in IGNORED for part in relative.parts):
            continue
        if path.is_symlink():
            raise ValueError(f"symlink:{relative}")
        if any(part in PRIVATE or part.startswith(".env.") for part in relative.parts):
            raise ValueError(f"private_path:{relative}")
        if path.is_file():
            if path.name in {"settings.json", "credentials.json", "cookies.json", "state.json", "session.json", "vk-session.json"}:
                raise ValueError(f"runtime_data_file:{relative}")
            if path.suffix in {".png", ".jpg", ".pdf", ".pptx", ".xlsx", ".sqlite3", ".pem", ".key"}:
                raise ValueError(f"private_or_binary_artifact:{relative}")
            raw = path.read_bytes()
            text = raw.decode("utf-8")
            findings = sensitive(text)
            if findings:
                raise ValueError(f"sensitive_content:{relative}:{','.join(findings)}")
            result[relative.as_posix()] = hashlib.sha256(raw).hexdigest()
    return result


def identity(root):
    inventory = files(root)
    allowed = json.loads((root / "PUBLIC-FILES.json").read_text(encoding="utf-8"))
    _require(allowed["schema_version"] == 1 and set(allowed["files"]) == set(inventory), "unexpected_or_missing_public_file")
    return hashlib.sha256(json.dumps(inventory, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def check(root, skills_root=None, *, history=False):
    root = root.resolve()
    inventory = files(root)
    manifest = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
    _require(manifest["version"] == (root / "VERSION").read_text(encoding="utf-8").strip(), "version_drift")
    _require(re.fullmatch(r"[a-z0-9-]+", manifest["name"]), "plugin_name")
    count = 0
    for path in sorted((root / "skills").glob("*/SKILL.md")):
        content = path.read_text(encoding="utf-8")
        front = re.match(r'---\nname: ([a-z0-9-]+)\ndescription: "(.+)"\n---', content)
        _require(front and front.group(1) == path.parent.name, f"skill_frontmatter:{path.parent.name}")
        for target in re.findall(r"\]\(([^)]+)\)", content):
            if target.startswith(("https://", "http://", "#")):
                continue
            resolved = (path.parent / target.split("#")[0]).resolve()
            _require(resolved.is_relative_to(root) and resolved.exists(), f"broken_skill_reference:{path.parent.name}")
        count += 1
    _require(count, "no_skills")
    marketplace = json.loads((root / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
    entry, = marketplace["plugins"]
    _require(entry["name"] == manifest["name"] and entry["source"] == {"source": "local", "path": "./"}, "local_marketplace")
    if manifest["name"] == "report-kit-skills":
        catalog = json.loads((root / "capabilities.json").read_text(encoding="utf-8"))
        names = {item["name"] for item in catalog["capabilities"]}
        _require(names == {p.parent.name for p in (root / "skills").glob("*/SKILL.md")}, "capability_inventory")
        _require(all(set(item["requires"]) <= names for item in catalog["capabilities"]), "missing_transitive_skill")
        _require(catalog["package_version"] == manifest["version"], "catalog_version")
    elif skills_root is not None:
        required = json.loads((root / "dependencies.json").read_text(encoding="utf-8"))["report-kit-skills"]
        _require((skills_root / "VERSION").read_text(encoding="utf-8").strip() == required["version"], "dependency_version")
        _require(identity(skills_root) == required["package_sha256"], "dependency_content_drift")
        for source, target in [('support_events.py','support_bundle.py'),('support-policy.json','support-policy.json')]:
            candidate = root / 'scripts' / target
            if candidate.exists():
                _require(candidate.read_bytes() == (skills_root / 'skills/_shared' / source).read_bytes(), 'support_collector_drift')
    history_result = check_history(root) if history else {"history_status": "NOT_CHECKED_ARCHIVE"}
    return {"status": "PASS_LIMITED", "files": len(inventory), "skills": count, **history_result, "package_sha256": identity(root),
            "limitations": "Pattern/inventory/source identity checks only; no complete secret detector, license review, enforced isolation, installation or live service proof."}


def check_history(root):
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=root, capture_output=True, text=True, encoding="utf-8", check=True).stdout.strip()
        if Path(top).resolve() != root.resolve(): raise ValueError("history_requires_package_repository")
    except (OSError, subprocess.CalledProcessError):
        raise ValueError("history_requires_package_repository") from None
    # Scan reachable commit contents and author/committer metadata, not just the working tree.
    history = subprocess.run(["git", "log", "--all", "--format=%H"], cwd=root, capture_output=True, text=True, check=True).stdout.splitlines()
    blobs = set()
    for commit in history:
        metadata = subprocess.run(["git", "show", "-s", "--format=%an <%ae> %cn <%ce>", commit], cwd=root, capture_output=True, text=True, check=True).stdout
        _require(not sensitive(metadata), "private_git_identity")
        tree = subprocess.run(["git", "ls-tree", "-r", "-z", commit], cwd=root, capture_output=True, check=True).stdout
        for record in tree.split(b"\0"):
            if not record:
                continue
            info, name = record.split(b"\t", 1)
            mode, kind, blob = info.decode().split()
            _require(mode != "120000" and kind == "blob", "history_symlink_or_submodule")
            _require(not any(part in PRIVATE | IGNORED for part in Path(name.decode()).parts), "private_history_path")
            if blob not in blobs:
                raw = subprocess.run(["git", "cat-file", "blob", blob], cwd=root, capture_output=True, check=True).stdout
                _require(not sensitive(raw.decode("utf-8")), "sensitive_git_history")
                blobs.add(blob)
    return {"history_status": "CHECKED_LIMITED", "history_commits": len(history), "history_unique_blobs": len(blobs)}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--skills-root", type=Path)
    parser.add_argument("--history", action="store_true", help="Maintainer source-history check; requires this package Git repository")
    args = parser.parse_args()
    try:
        result = check(args.root, args.skills_root, history=args.history)
    except (AssertionError, ValueError, OSError, UnicodeError, KeyError, subprocess.CalledProcessError) as error:
        result = {"status": "FAIL", "issue": str(error)}
    print(json.dumps(result, ensure_ascii=False))
    raise SystemExit(result["status"] == "FAIL")
