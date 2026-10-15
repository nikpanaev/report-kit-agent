"""Assemble pinned downloaded distributions as inert release assets; no pip/install/network."""
import argparse
import hashlib
import gzip
import io
import json
from pathlib import Path
import posixpath
import tarfile
import zipfile

from maintenance import require, read_json
from runtime import boundary
from updates import archive_files, identity_file


def vendor_files(path, item):
    require(path.name == item['filename'] and not path.is_symlink() and path.stat().st_size == item['size']
            and identity_file(path) == item['sha256'], 'vendor_identity')
    data, links, executable = {}, {}, set()
    if path.suffix == '.whl' or path.suffix == '.zip':
        with zipfile.ZipFile(path) as z:
            require(len(z.infolist()) < 20000 and sum(i.file_size for i in z.infolist()) < 512 * 1024 * 1024, 'vendor_size')
            for i in z.infolist():
                if i.is_dir(): continue
                require(i.filename not in data and (i.external_attr >> 16) & 0o170000 != 0o120000, 'vendor_link')
                data[i.filename] = z.read(i)
                if (i.external_attr >> 16) & 0o111: executable.add(i.filename)
    else:
        with tarfile.open(path, 'r:gz') as z:
            members = z.getmembers(); require(len(members) < 20000 and sum(i.size for i in members) < 512 * 1024 * 1024, 'vendor_size')
            for i in members:
                if i.isdir(): continue
                require(i.name not in data and i.name not in links, 'vendor_duplicate')
                if i.issym() or i.islnk():
                    target = posixpath.normpath(posixpath.join(posixpath.dirname(i.name), i.linkname)) if i.issym() else i.linkname
                    links[i.name] = target
                else:
                    require(i.isfile(), 'vendor_type'); data[i.name] = z.extractfile(i).read()
                if i.mode & 0o111: executable.add(i.name)
    # Resolve only archive-internal links, then feed plain files through the existing traversal/collision guard.
    for _ in range(len(links) + 1):
        for name, target in list(links.items()):
            if target in data:
                data[name] = data[target]
                if target in executable: executable.add(name)
                del links[name]
        if not links: break
    require(not links, 'vendor_external_or_cyclic_link')
    raw = tar_bytes(data, executable); archive_files(raw, max_bytes=512 * 1024 * 1024, binary=True)
    return data, executable


def tar_bytes(payload, executables=(), *, compress=False):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode='w', format=tarfile.PAX_FORMAT) as z:
        for name, raw in sorted(payload.items()):
            member = tarfile.TarInfo(name); member.size = len(raw); member.mode = 0o700 if name in executables else 0o600
            z.addfile(member, io.BytesIO(raw))
    if compress:
        compressed = io.BytesIO()
        with gzip.GzipFile(fileobj=compressed, mode='wb', mtime=0) as stream: stream.write(out.getvalue())
        return compressed.getvalue()
    return out.getvalue()


def validate_notice_archive(raw):
    try:
        with zipfile.ZipFile(io.BytesIO(raw)) as archive:
            members = archive.infolist(); names = [m.filename for m in members]
            require(len(names) == len(set(names)) and len(names) <= 1000
                    and sum(m.file_size for m in members) <= 32 * 1024 * 1024, 'runtime_notice_inventory')
            entries = json.loads(archive.read('inventory.json'))['notice_sources']
            require(isinstance(entries, list) and entries, 'runtime_notice_inventory')
            for entry in entries:
                require(hashlib.sha256(archive.read(entry['file'])).hexdigest() == entry['sha256'], 'runtime_notice_inventory')
    except (zipfile.BadZipFile, KeyError, TypeError, UnicodeError) as error:
        raise ValueError('runtime_notice_inventory') from error


def notice_bytes(downloads, item):
    path = Path(downloads) / item['filename']
    require(Path(item['filename']).name == item['filename'] and not path.is_symlink()
            and path.is_file() and 0 < item['size'] <= 4 * 1024 * 1024
            and path.stat().st_size == item['size'] and identity_file(path) == item['sha256'], 'runtime_notice_identity')
    raw = path.read_bytes()
    validate_notice_archive(raw)
    return raw


def prepare(recipe_path, downloads, output):
    recipe = read_json(recipe_path); output = boundary(output)
    require(not output.exists(), 'runtime_output_exists'); output.mkdir(parents=True, mode=0o700)
    result = {'schema_version': 1, 'runtime_id': recipe['runtime_id'], 'platforms': {}, 'license_review': 'PENDING',
              'installation_performed': False, 'browsers_included': False, 'upstream': {}, 'limits': 'Inert assembly; not native Windows or independent license/security approval.'}
    for target, config in recipe['platforms'].items():
        layers = {'core': ({}, set()), 'capture': ({}, set()), 'images': ({}, set()), 'livedune-node': ({}, set())}
        if 'notice_package' in recipe:
            item = recipe['notice_package']
            layers['core'][0]['python/REPORT-KIT-NOTICES.zip'] = notice_bytes(downloads, item)
            result['upstream'][item['filename']] = {'sha256': item['sha256'], 'url': item['url']}
        for label, item in [('python', config['python']), *config['wheels'].items(), ('node', config['node'])]:
            raw, executable = vendor_files(Path(downloads) / item['filename'], item)
            result['upstream'][item['filename']] = {'sha256': item['sha256'], 'url': item['url']}
            layer = 'core' if label in {'python', 'tzdata'} else 'livedune-node' if label == 'node' else 'images' if label == 'Pillow' else 'capture'
            if label == 'python': mapped = raw; execute = executable
            elif label == 'node':
                mapped = {'node/' + n.split('/', 1)[1]: v for n, v in raw.items()}
                execute = {'node/' + n.split('/', 1)[1] for n in executable}
            else:
                # Wheel packages stay in a private site directory; no wheel scripts or pip lifecycle is executed.
                mapped = {'site/' + n: v for n, v in raw.items()}; execute = {'site/' + n for n in executable}
            payload, flags = layers[layer]
            require(not set(payload) & set(mapped), 'vendor_wheel_collision'); payload.update(mapped); flags.update(execute)
        result['platforms'][target] = {'schema_version': 1, 'runtime_id': recipe['runtime_id'], 'platform': target, 'assets': {}}
        for layer, (payload, executable) in layers.items():
            manifest = {'runtime_id': recipe['runtime_id'], 'platform': target, 'layer': layer,
                        'files': {n: hashlib.sha256(v).hexdigest() for n, v in payload.items()},
                        'executables': sorted(executable), 'versions': {'python': recipe['python_version'], 'node': recipe['node_version'], **recipe['packages']}}
            payload['manifests/' + layer + '.json'] = json.dumps(manifest, sort_keys=True).encode()
            bootstrap = None
            if layer == 'core':
                bootstrap = {'schema_version': 1, 'runtime_id': recipe['runtime_id'], 'platform': target,
                             'layers': ['core'], 'files': {n: hashlib.sha256(v).hexdigest() for n, v in payload.items()},
                             'executables': sorted(executable), 'status': 'STAGED_NOT_INSTALLED'}
                payload['runtime-receipt.json'] = (json.dumps(bootstrap, indent=2) + '\n').encode()
            data = tar_bytes(payload, executable, compress=True); name = 'report-kit-runtime-' + recipe['runtime_id'] + '-' + target + '-' + layer + '.tar.gz'
            with (output / name).open('xb') as stream: stream.write(data)
            (output / name).chmod(0o600)
            result['platforms'][target]['assets'][layer] = {'filename': name, 'size': len(data), 'sha256': hashlib.sha256(data).hexdigest()}
            if bootstrap is not None:
                result['platforms'][target]['assets'][layer]['bootstrap_receipt_sha256'] = hashlib.sha256(payload['runtime-receipt.json']).hexdigest()
    (output / 'runtime-build.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for key in ['recipe', 'downloads', 'output']: parser.add_argument('--' + key, type=Path, required=True)
    args = parser.parse_args()
    try: result = prepare(args.recipe, args.downloads, args.output); print(json.dumps({'status': 'PREPARED_NOT_INSTALLED', 'platforms': list(result['platforms'])}))
    except (ValueError, OSError, KeyError): print(json.dumps({'status': 'BLOCKED', 'code': 'RUNTIME_BUILD_FAILED'})); raise SystemExit(1)
