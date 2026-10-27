#!/usr/bin/env python3
"""Read-only verification of the files and formal records in this repository."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    manifest = load(ROOT / 'MATERIALS-MANIFEST.json')
    assert not manifest['dialogue_included']
    for rel, info in manifest['files'].items():
        path = ROOT / rel
        assert path.is_file() and path.stat().st_size == info['bytes'], rel
        assert sha(path) == info['sha256'], rel
    evidence = load(ROOT / 'report/evidence-index.json')
    ws_runs = evidence['worksteal_rechecked_formal_runs']
    for rel, expected in ws_runs.items():
        run = ROOT / 'hpc-worksteal' / rel
        for name, digest in load(run / 'checksums.json').items():
            assert sha(run / name) == digest, (rel, name)
        result = load(run / 'result.json')
        metadata = load(run / 'metadata.json')
        assert metadata['status'] == 'completed' and metadata['purpose'] == 'timing'
        assert metadata['included'] and result['correctness']['pass']
        assert result == json.loads((run / 'stdout.log').read_bytes())
        assert result['timing']['epoch_seconds'] == expected['epoch']
        assert result['timing']['end_to_end_seconds'] == expected['app']
        assert sha(run / 'result.json') == expected['result_sha256']
    rt_runs = evidence['raytracing_formal_runs']
    for rid, expected in rt_runs.items():
        run = ROOT / 'hpc-raytracing/runs' / rid
        assert sha(run / 'metadata.json') == expected['metadata_sha256']
        for line in (run / 'checksums.sha256').read_text(encoding='utf-8').splitlines():
            digest, name = line.split(maxsplit=1)
            assert sha(run / name.lstrip('*')) == digest, (rid, name)
        metadata = load(run / 'metadata.json')
        assert metadata['quality']['official']['different_channels'] == 0
    assert len(ws_runs) == 663 and len(rt_runs) == 24
    print(json.dumps({'pass': True, 'copied_files': len(manifest['files']),
                      'worksteal_formal_runs': len(ws_runs),
                      'raytracing_formal_runs': len(rt_runs),
                      'dialogue_included': False, 'experiments_executed': 0}))


if __name__ == '__main__':
    main()
