"""Build a local draft from exact clean commits using native Git; never publish/install."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile

from check_package import check as package_check, files
from updates import actual_pair, release_check, source_check


def git(root, *args):
    return subprocess.run(["git", *args], cwd=root, capture_output=True, check=True).stdout


def committed(root, expected):
    if not isinstance(expected,str) or not re.fullmatch(r"[0-9a-f]{40}",expected):raise ValueError("commit_identity")
    if git(root,"rev-parse","HEAD").decode().strip()!=expected:raise ValueError("commit_changed")
    if git(root,"status","--porcelain=v1","--untracked-files=all"):raise ValueError("dirty_package")
    inventory=files(root)
    tracked={p.decode() for p in git(root,"ls-files","-z").split(b"\0") if p}
    allowed=json.loads((root/"PUBLIC-FILES.json").read_text(encoding="utf-8"))["files"]
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


def prepare(agent, skills, output, commits, channel, source=None, runtime_assets=None):
    agent=Path(agent).resolve();skills=Path(skills).resolve();output=Path(output).resolve()
    roots={"report-kit-agent":agent,"report-kit-skills":skills}
    if set(commits)!=set(roots) or channel not in {"working","preview"}:raise ValueError("release_inputs")
    if any(output.is_relative_to(root) or root.is_relative_to(output) for root in roots.values()):raise ValueError("output_boundary")
    if output.exists():raise ValueError("output_exists")
    inventories={name:committed(root,commits[name]) for name,root in roots.items()}
    checks={"report-kit-skills":package_check(skills,history=True),"report-kit-agent":package_check(agent,skills,history=True)}
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
    if source is not None:
        source_check(source)
        if source['channel'] != channel: raise ValueError('delivery_channel')
    assets={}
    for name in roots:
        filename=f"{name}-{pair[name]['version']}.tar"
        repository=source['agent_repository' if name=='report-kit-agent' else 'skills_repository'] if source else None
        tag='v'+pair[name]['version']
        assets[name]={'repository':repository,'tag':tag,'commit':commits[name],
            'url':repository+'/releases/download/'+tag+'/'+filename if repository else None,
            'size':len(payloads[filename]),'archive_sha256':hashlib.sha256(payloads[filename]).hexdigest()}
    payloads['draft-delivery.json']=(json.dumps({'schema_version':1,'release':release,'assets':assets},indent=2)+'\n').encode()
    notes="# Local draft — publication not approved\n\n"
    for name,root in roots.items():
        changelog=root/"CHANGELOG.md"
        if not changelog.is_file():raise ValueError("missing_release_notes")
        notes+=f"## {name} {pair[name]['version']}\n\n"+changelog.read_text(encoding="utf-8")+"\n"
    payloads["RELEASE-NOTES.md"]=notes.encode()
    artifacts={name:hashlib.sha256(raw).hexdigest() for name,raw in payloads.items()}
    payloads["SHA256SUMS"]="".join(f"{sha}  {name}\n" for name,sha in sorted(artifacts.items())).encode()
    artifacts["SHA256SUMS"]=hashlib.sha256(payloads["SHA256SUMS"]).hexdigest()
    record={"schema_version":1,"status":"LOCAL_DRAFT_NOT_APPROVED","commits":commits,"release":release,
        "package_checks":checks,"artifacts":artifacts,"publication_authorized":False,
        "blockers":["Third-party license texts/notices and compatibility review pending",
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
    with path.open("x",encoding="utf-8") as stream:stream.write(json.dumps(record,indent=2)+"\n")
    path.chmod(0o600)
    if runtime_assets is not None:
        append_runtime_assets(agent, Path(runtime_assets), output, record)
    return record


def append_runtime_assets(agent, assets_root, output, record):
    """Same local release; large reviewed artifacts remain outside source Git history."""
    from maintenance import read_json, require
    from updates import identity_file
    from runtime import manifest_recipe_match
    runtime = read_json(assets_root / 'runtime-build.json')
    recipe = read_json(agent / 'assets/runtime-recipe.json')
    require(runtime['runtime_id'] == recipe['runtime_id'] and runtime['installation_performed'] is False, 'runtime_build_identity')
    require(bool(runtime['platforms']) and set(runtime['platforms']) == set(recipe['platforms']), 'runtime_platform_inventory')
    require(all('core' in p['assets'] for p in runtime['platforms'].values()), 'runtime_core_missing')
    for platform in runtime['platforms'].values():
        for layer, asset in platform['assets'].items():
            name = asset['filename']; require(Path(name).name == name, 'runtime_asset_name')
            src = assets_root / name; dest = output / name
            require(not src.is_symlink() and src.stat().st_size == asset['size'] and identity_file(src) == asset['sha256'], 'runtime_asset_changed')
            with tarfile.open(src, 'r:*') as archive:
                members = [m for m in archive.getmembers() if m.name == 'manifests/' + layer + '.json']
                require(len(members) == 1 and members[0].isfile() and members[0].size <= 8 * 1024 * 1024, 'runtime_manifest_missing')
                manifest = json.loads(archive.extractfile(members[0]).read())
                require(manifest['layer'] == layer and manifest['platform'] == platform['platform'], 'runtime_manifest_identity')
                manifest_recipe_match(manifest, recipe)
                if layer == 'core' and 'notice_package' in recipe:
                    from prepare_runtime import validate_notice_archive
                    key = 'python/REPORT-KIT-NOTICES.zip'; notice = recipe['notice_package']
                    items = [m for m in archive.getmembers() if m.name == key]
                    require(len(items) == 1 and items[0].isfile() and items[0].size == notice['size']
                            and hashlib.sha256(archive.extractfile(items[0]).read()).hexdigest() == notice['sha256']
                            and manifest['files'].get(key) == notice['sha256'], 'runtime_notice_missing_or_changed')
                    validate_notice_archive(archive.extractfile(items[0]).read())
            with src.open('rb') as source, dest.open('xb') as target: shutil.copyfileobj(source, target)
            dest.chmod(0o600)
            require(identity_file(dest) == asset['sha256'], 'runtime_copy_changed')
            record['artifacts'][name] = asset['sha256']
    delivery = {'schema_version': 1, 'published': False, 'packages': record['release']['packages'],
                'runtime_id': runtime['runtime_id'], 'platforms': runtime['platforms'], 'license_review': runtime['license_review']}
    path = output / 'draft-runtime-delivery.json'
    with path.open('x', encoding='utf-8') as stream: json.dump(delivery, stream, indent=2); stream.write('\n')
    path.chmod(0o600); record['artifacts'][path.name] = identity_file(path)
    hashes = output / 'SHA256SUMS'
    hashes.write_text(''.join(f'{sha}  {name}\n' for name, sha in sorted(record['artifacts'].items()) if name != 'SHA256SUMS'), encoding='utf-8')
    record['artifacts']['SHA256SUMS'] = identity_file(hashes)
    record['runtime'] = {'runtime_id': runtime['runtime_id'], 'platforms': sorted(runtime['platforms']), 'license_review': runtime['license_review'], 'native_windows': 'NOT_RUN'}
    (output / 'build-record.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')


if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ["agent-root","skills-root","output"]:parser.add_argument("--"+key,type=Path,required=True)
    for key in ["agent-commit","skills-commit"]:parser.add_argument("--"+key,required=True)
    parser.add_argument("--channel",choices=["working","preview"],default="working")
    parser.add_argument('--source',type=Path,help='Approved repository source record; no network or publication')
    parser.add_argument('--runtime-assets',type=Path,help='Prepared inert runtime assets; no installation')
    args=parser.parse_args()
    try:
        result=prepare(args.agent_root,args.skills_root,args.output,
            {"report-kit-agent":args.agent_commit,"report-kit-skills":args.skills_commit},args.channel,
            json.loads(args.source.read_text(encoding='utf-8')) if args.source else None, args.runtime_assets)
        result={"status":result["status"],"artifacts":result["artifacts"],"publication_authorized":False,"blockers":result["blockers"]}
    except (ValueError,AssertionError,OSError,KeyError,subprocess.CalledProcessError):
        result={"status":"BLOCKED","issue":"invalid_or_changed_package_or_output","publication_authorized":False}
    print(json.dumps(result));raise SystemExit(result["status"]=="BLOCKED")
