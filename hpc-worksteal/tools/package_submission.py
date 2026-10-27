#!/usr/bin/env python3
"""Create and really unpack a self-contained project/evidence archive."""
import argparse
import hashlib
import json
import os
import pathlib
import re
import shutil
import zipfile

import lab


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--output', required=True)
    p.add_argument('--verify-dir', required=True)
    args = p.parse_args()
    root = lab.ROOT.resolve()
    output, unpack = pathlib.Path(args.output).resolve(), pathlib.Path(args.verify_dir).resolve()
    assert output.is_relative_to(root/'submission') and unpack.is_relative_to(root/'submission')
    assert not output.exists() and not unpack.exists()
    assert (root/'output/pdf/Mini-WorkSteal-最终技术报告-20261025.pdf').exists()
    assert (root/'results/idle-backoff-delivery-20261025.json').exists()
    assert json.loads((root/'submission/reproduction/20261025/receipt.json').read_text())['pass']
    ignored = {'.cache', '__pycache__', '.git', 'build', 'tmp'}
    # A later candidate must not recursively include an earlier unpacked copy.
    # Preserve those verification copies on disk, but exclude all of them.
    excluded_paths = (root/'submission/packages', unpack,
                      *(p for p in (root/'submission').glob('unpacked-*') if p.is_dir()))
    files = {}
    patterns = (rb'\bsk-[A-Za-z0-9_-]{20,}', rb'\bgh[pousr]_[A-Za-z0-9]{20,}',
                rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
    text_ext = {'.py','.cpp','.hpp','.md','.txt','.json','.jsonl','.log','.yml','.yaml','.toml','.sh','.ps1'}
    for top, dirs, names in os.walk(root):
        current = pathlib.Path(top)
        dirs[:] = [d for d in dirs if d not in ignored and not d.startswith('build-') and
                   not any((current/d).is_relative_to(e) for e in excluded_paths)]
        for name in sorted(names):
            src = current/name
            assert src.resolve().is_relative_to(root) and not src.is_symlink()
            if src == output or src.suffix in ('.pyc','.pyo'):
                continue
            if src.suffix in text_ext:
                data = src.read_bytes()
                assert not any(re.search(p, data) for p in patterns), 'possible credential in '+src.relative_to(root).as_posix()
            files[src.relative_to(root).as_posix()] = {'sha256':lab.digest(src),'bytes':src.stat().st_size}
    assert not any(n.startswith(('.cache/','build/','tmp/')) for n in files)
    assert not any(n.startswith('submission/unpacked-') for n in files)
    assert all(n in files for n in ('CMakeLists.txt','README.md','.devcontainer/devcontainer.json',
        'submission/README.md','report/final/input-data.json','output/pdf/Mini-WorkSteal-最终技术报告-20261025.pdf'))
    manifest = {'created':lab.now(),'scope':'project sources, configs, reports, all archived studies including failures and historical snapshots; excludes only regenerable caches/build directories and package output',
        'files':files, 'file_count':len(files),'uncompressed_bytes':sum(v['bytes'] for v in files.values()),
        'container_built':False, 'native_reproduction_pass':True, 'external_submission_sent':False}
    output.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(output,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=5,allowZip64=True) as z:
        for index,(rel,entry) in enumerate(sorted(files.items()),1):
            assert lab.digest(root/rel)==entry['sha256'], 'source changed while packaging'
            z.write(root/rel,rel)
            if index%2000==0:
                print(json.dumps({'packaged_files':index,'total':len(files)}),flush=True)
        z.writestr('PACKAGE-MANIFEST.json',json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    unpack.mkdir(parents=True,exist_ok=False)
    with zipfile.ZipFile(output) as z:
        assert len(z.namelist())==len(set(z.namelist()))==len(files)+1
        assert set(z.namelist())==set(files)|{'PACKAGE-MANIFEST.json'}
        assert json.loads(z.read('PACKAGE-MANIFEST.json'))==manifest
        for entry in z.infolist():
            rel=pathlib.PurePosixPath(entry.filename)
            assert not rel.is_absolute() and '..' not in rel.parts
            target=unpack/pathlib.Path(*rel.parts)
            assert target.resolve().is_relative_to(unpack)
            target.parent.mkdir(parents=True,exist_ok=True)
            with z.open(entry) as src,target.open('xb') as dest:
                shutil.copyfileobj(src,dest)
    for rel,entry in files.items():
        assert lab.digest(unpack/rel)==entry['sha256'] and (unpack/rel).stat().st_size==entry['bytes']
    # Exact native-tested production and test inputs must match the unpacked copy.
    tested=json.loads((unpack/'submission/reproduction/20261025/source-files.json').read_text())
    tested_count=0
    for rel,sha in tested.items():
        if rel.startswith(('src/','include/')) or rel.startswith('tests/') and rel.endswith(('.cpp','.hpp','.py')) or rel in ('CMakeLists.txt','CMakePresets.json'):
            assert lab.digest(unpack/rel)==sha
            tested_count+=1
    receipt={'created':lab.now(),'archive':output.relative_to(root).as_posix(),'archive_sha256':lab.digest(output),
        'archive_bytes':output.stat().st_size,'unpacked':unpack.relative_to(root).as_posix(),
        'files_verified':len(files),'native_tested_code_files_verified':tested_count,
        'package_manifest_sha256':lab.digest(unpack/'PACKAGE-MANIFEST.json'),
        'container_built':False,'native_reproduction_pass':True,'external_submission_sent':False,
        'scope':'all files actually unpacked and rehashed; final completion still follows docs/42'}
    lab.write(output.with_suffix('.receipt.json'),receipt)
    print(json.dumps(receipt,ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
