#!/usr/bin/env python3
"""Run the delivered config bytes against their exact frozen Linux binaries."""
import argparse, datetime, json, pathlib, shutil, subprocess, uuid
from lab import digest, write, seal

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); a = ap.parse_args(); root = pathlib.Path(a.root).resolve()
    info = json.loads((root/'configs/refined/builds.json').read_text(encoding='utf-8'))
    prior = json.loads((root/'optimization/results/optimization-summary.json').read_text(encoding='utf-8'))
    target = root/'refinement/results'/('recommendation-check-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]); target.mkdir()
    records = []
    for kind, b in info.items():
        exe = pathlib.Path('/root/lzuhpc-experiments')/('ws-20261016-opt-'+b['build'])/'build-none/worksteal'
        assert digest(exe) == b['binary_sha256'] and digest(root/b['config']) == b['config_sha256']
        directory = target/kind; directory.mkdir(); shutil.copy2(root/b['config'], directory/'config.json')
        argv = [str(exe), '--config', str(directory/'config.json'), '--output', str(directory/'result.json')]
        p = subprocess.run(argv, capture_output=True, text=True, timeout=90)
        write(directory/'command.json', {'argv': argv, 'returncode': p.returncode, 'stdout': p.stdout, 'stderr': p.stderr})
        assert p.returncode == 0
        result = json.loads((directory/'result.json').read_text()); assert result['correctness']['pass']
        expected = json.loads((directory/'config.json').read_text()); expected['steal_enabled'] = True
        assert result['resolved_config'] == expected
        old = next(g for g in prior['groups'] if g['stage'] == 'OPT1-build-screen' and g['kind'] == kind and g['build'] == 'baseline')
        e = result['epochs'][0]; assert e['correctness']['output_hash_fnv1a64'] == old['output_hash']
        for f in ('input_hash_fnv1a64', 'cost_hash_fnv1a64', 'data_hash_fnv1a64', 'total_cost_units'):
            assert e['identity'][f] == old['identity'][f]
        records.append({'kind': kind, 'config_sha256': digest(directory/'config.json'), 'binary_sha256': digest(exe), 'correct': True, 'output_hash': old['output_hash']})
        seal(directory)
    write(target/'summary.json', {'pass': True, 'processes': 4, 'purpose': 'delivery config verification; excluded from selection', 'records': records})
    seal(target); print(json.dumps({'pass': True, 'directory': str(target), 'processes': 4}, ensure_ascii=False))

if __name__ == '__main__': main()
