#!/usr/bin/env python3
"""Fresh Linux source copy, real builds/checks and exact recommendation runs."""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import time

import lab


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--destination', required=True)
    parser.add_argument('--export-target', required=True)
    args = parser.parse_args()
    assert os.name == 'posix', 'build and functional verification require Linux'
    root = pathlib.Path(args.destination).resolve()
    root.mkdir(parents=True, exist_ok=False)
    files = {p.relative_to(lab.ROOT).as_posix(): lab.digest(p) for p in lab.source_files()}
    for rel, sha in files.items():
        target = root/rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(lab.ROOT/rel, target)
        assert lab.digest(target) == sha
    evidence = root/'reproduction-evidence'
    evidence.mkdir()
    records = []
    lab.write(evidence/'source-files.json', files)
    def command(label, argv, timeout=240):
        start = time.monotonic()
        p = subprocess.run(argv, cwd=root, capture_output=True, timeout=timeout)
        (evidence/(label+'.stdout.log')).write_bytes(p.stdout)
        (evidence/(label+'.stderr.log')).write_bytes(p.stderr)
        record = {'label': label, 'argv': argv, 'returncode': p.returncode,
                  'elapsed_seconds': time.monotonic()-start}
        records.append(record)
        lab.write(evidence/(label+'.command.json'), record)
        print(json.dumps(record), flush=True)
        assert p.returncode == 0, label
        return p
    command('environment', ['uname', '-a'])
    command('compiler', ['c++', '--version'])
    command('cmake-version', ['cmake', '--version'])
    command('dependencies', ['dpkg-query', '-W', 'g++', 'cmake', 'nlohmann-json3-dev', 'python3'])
    # Distinct clean builds prove both the naive and tuned compile-time paths.
    for name, options in (('default', []), ('optimized', [
        '-DWS_COMPLETION_BATCH=32', '-DWS_STEAL_SCRATCH=ON',
        '-DWS_ENABLE_IPO=ON', '-DWS_COMPUTE_LANES=8'])):
        bd = root/('build-'+name)
        command(name+'-configure', ['cmake', '-S', str(root), '-B', str(bd),
                '-DCMAKE_BUILD_TYPE=Release', *options])
        p = command(name+'-build', ['cmake', '--build', str(bd), '-j2'])
        assert b'warning:' not in p.stdout.lower()+p.stderr.lower(), 'inspect build warning'
        command(name+'-ctest', ['ctest', '--test-dir', str(bd), '--verbose', '--output-on-failure'])
        for binary in ('worksteal', 'worksteal_extension', 'runtime_checks'):
            shutil.copy2(bd/binary, evidence/(name+'-'+binary))
    # Use exact existing JSON, not an easier substitute. These are new functional
    # checks, not reproductions of old elapsed times or measured binary hashes.
    for kind in ('light', 'skewed', 'memory'):
        cfg = 'configs/verified/'+kind+'.json'
        command('recommended-'+kind, [str(root/'build-optimized/worksteal'), '--config', str(root/cfg),
                '--output', str(evidence/('recommended-'+kind+'.json'))], timeout=90)
    for name, cfg in (('memory-interleaved', 'configs/memory-interleaved/memory.json'),
                      ('memory-interleaved-large', 'configs/memory-interleaved/memory-large.json')):
        command(name, [str(root/'build-optimized/worksteal'), '--config', str(root/cfg),
                '--output', str(evidence/(name+'.json'))], timeout=90)
    # Uniform's measured build uses a different completion/scratch combination.
    bd = root/'build-uniform'
    command('uniform-configure', ['cmake', '-S', str(root), '-B', str(bd), '-DCMAKE_BUILD_TYPE=Release',
        '-DWS_COMPLETION_BATCH=1', '-DWS_STEAL_SCRATCH=OFF', '-DWS_ENABLE_IPO=ON', '-DWS_COMPUTE_LANES=8'])
    p = command('uniform-build', ['cmake', '--build', str(bd), '-j2'])
    assert b'warning:' not in p.stdout.lower()+p.stderr.lower()
    command('uniform-ctest', ['ctest', '--test-dir', str(bd), '--verbose', '--output-on-failure'])
    command('recommended-uniform', [str(bd/'worksteal'), '--config', str(root/'configs/verified/uniform.json'),
            '--output', str(evidence/'recommended-uniform.json')], timeout=90)
    shutil.copy2(bd/'worksteal', evidence/'uniform-worksteal')
    results = {}
    for name in ('recommended-light', 'recommended-skewed', 'recommended-memory',
                 'recommended-uniform', 'memory-interleaved', 'memory-interleaved-large'):
        result = json.loads((evidence/(name+'.json')).read_text())
        assert result['correctness']['pass'] and all(e['correctness']['mismatches'] == 0 and
            e['correctness']['compared_elements'] == result['resolved_config']['workload']['elements'] for e in result['epochs'])
        results[name] = {'correctness': result['correctness'], 'epochs': len(result['epochs']),
                         'config': result['resolved_config'], 'output_hashes': [e['correctness']['output_hash_fnv1a64'] for e in result['epochs']]}
    for rel, sha in files.items():
        assert lab.digest(root/rel) == sha, 'build must preserve sources'
    lab.write(evidence/'receipt.json', {'created': lab.now(), 'pass': True, 'fresh_directory': str(root),
        'linux': True, 'container_built': False, 'source_file_count': len(files), 'commands': records,
        'new_build_sha256': {n: lab.digest(evidence/n) for n in ('default-worksteal', 'optimized-worksteal', 'uniform-worksteal')},
        'recommendation_runs': results, 'scope': 'fresh native Linux functional reproduction; not historical timing reproduction, not a container check; no new sanitizer checks'})
    lab.seal(evidence)
    target = pathlib.Path(args.export_target).resolve()
    shutil.copytree(evidence, target)
    hashes = json.loads((target/'checksums.json').read_text())
    assert set(hashes) == {f.relative_to(target).as_posix() for f in target.rglob('*') if f.is_file() and f.name != 'checksums.json'}
    for rel, sha in hashes.items():
        assert lab.digest(target/rel) == sha
    print(json.dumps({'reproduction_pass': True, 'exported': str(target), 'files_verified': len(hashes)}, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
