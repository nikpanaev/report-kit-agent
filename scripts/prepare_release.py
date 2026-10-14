"""Build a local draft from exact clean commits using native Git; never publish/install."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import subprocess
import tarfile

from check_package import check as package_check, files
from updates import actual_pair, release_check


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=True).stdout


def committed(root, expected):
    if not isinstance(expected,str) or not re.fullmatch(r"[0-9a-f]{40}",expected):raise ValueError("commit_identity")
    if git(root,"rev-parse","HEAD").decode().strip()!=expected:raise ValueError("commit_changed")
    if git(root,"status","--porcelain=v1","--untracked-files=all"):raise ValueError("dirty_package")
    inventory=files(root)
    tracked={p.decode() for p in git(root,"ls-files","-z").split(b"\0") if p}
    allowed=json.loads((root/"PUBLIC-FILES.json").read_text())["files"]
    if tracked!=set(inventory) or tracked!=set(allowed):raise ValueError("committed_inventory")
    return inventory


def verify_archive(raw, inventory):
    observed={}
    with tarfile.open(fileobj=io.BytesIO(raw),mode="r:") as archive:
        for member in archive.getmembers():
            path=Path(member.name)
            if path.is_absolute() or ".." in path.parts:raise ValueError("archive_path")
            if member.isdir():continue
            if not member.isfile() or member.name in observed:raise ValueError("archive_type")
            stream=archive.extractfile(member)
            observed[member.name]=hashlib.sha256(stream.read()).hexdigest()
    if observed!=inventory:raise ValueError("archive_content")
    return observed


def prepare(agent, skills, output, commits, channel):
    agent=Path(agent).resolve();skills=Path(skills).resolve();output=Path(output).resolve()
    roots={"report-kit-agent":agent,"report-kit-skills":skills}
    if set(commits)!=set(roots) or channel not in {"working","preview"}:raise ValueError("release_inputs")
    if any(output.is_relative_to(root) or root.is_relative_to(output) for root in roots.values()):raise ValueError("output_boundary")
    if output.exists():raise ValueError("output_exists")
    inventories={name:committed(root,commits[name]) for name,root in roots.items()}
    checks={"report-kit-skills":package_check(skills),"report-kit-agent":package_check(agent,skills)}
    pair=actual_pair(agent,skills)
    payloads={}
    for name,root in roots.items():
        raw=git(root,"archive","--format=tar",commits[name],"--",*sorted(inventories[name]))
        verify_archive(raw,inventories[name])
        payloads[f"{name}-{pair[name]['version']}.tar"]=raw
    # Recheck both after assembly; never export uncommitted bytes or a moved head.
    for name,root in roots.items():
        if committed(root,commits[name])!=inventories[name]:raise ValueError("source_changed")
    release={"release_id":"prepared-"+pair["report-kit-agent"]["version"],"channel":channel,"published":False,"revoked":False,"packages":pair}
    release_check(release)
    payloads["draft-release.json"]=(json.dumps(release,indent=2)+"\n").encode()
    notes="# Local draft — publication not approved\n\n"
    for name,root in roots.items():
        changelog=root/"CHANGELOG.md"
        if not changelog.is_file():raise ValueError("missing_release_notes")
        notes+=f"## {name} {pair[name]['version']}\n\n"+changelog.read_text()+"\n"
    payloads["RELEASE-NOTES.md"]=notes.encode()
    artifacts={name:hashlib.sha256(raw).hexdigest() for name,raw in payloads.items()}
    payloads["SHA256SUMS"]="".join(f"{sha}  {name}\n" for name,sha in sorted(artifacts.items())).encode()
    artifacts["SHA256SUMS"]=hashlib.sha256(payloads["SHA256SUMS"]).hexdigest()
    record={"schema_version":1,"status":"LOCAL_DRAFT_NOT_APPROVED","commits":commits,"release":release,
        "package_checks":checks,"artifacts":artifacts,"publication_authorized":False,
        "blockers":["Original rate-limit failure requires diagnosis or owner risk decision",
            "Third-party license texts/notices and compatibility review pending",
            "Independent QA/security and packaged/employee host acceptance pending",
            "Real repository URLs and separate publication authority required"],
        "limitations":"Byte/inventory/history pattern checks and local archive only; no signature trust, live install/update or release approval. Git source archives do not contain client workspaces."}
    output.mkdir(parents=True,mode=0o700)
    # Partial own output remains for diagnosis; never overwrite or sweep it.
    for name,raw in payloads.items():
        path=output/name
        with path.open("xb") as stream:stream.write(raw)
        path.chmod(0o600)
    path=output/"build-record.json"
    with path.open("x") as stream:stream.write(json.dumps(record,indent=2)+"\n")
    path.chmod(0o600)
    return record


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ["agent-root","skills-root","output"]:parser.add_argument("--"+key,type=Path,required=True)
    for key in ["agent-commit","skills-commit"]:parser.add_argument("--"+key,required=True)
    parser.add_argument("--channel",choices=["working","preview"],default="working")
    args=parser.parse_args()
    try:
        result=prepare(args.agent_root,args.skills_root,args.output,
            {"report-kit-agent":args.agent_commit,"report-kit-skills":args.skills_commit},args.channel)
        result={"status":result["status"],"artifacts":result["artifacts"],"publication_authorized":False,"blockers":result["blockers"]}
    except (ValueError,AssertionError,OSError,KeyError,subprocess.CalledProcessError):
        result={"status":"BLOCKED","issue":"invalid_or_changed_package_or_output","publication_authorized":False}
    print(json.dumps(result));raise SystemExit(result["status"]=="BLOCKED")
