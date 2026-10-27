#!/usr/bin/env python3
"""Seal round-three deliverables and the current source snapshot."""
import datetime, json, pathlib
from lab import ROOT, digest, snapshot, write

def main():
    root = ROOT; source_id = snapshot()
    audit = json.loads((root/'refinement/results/archive-audit.json').read_text(encoding='utf-8'))
    assert audit['pass'] and len(audit['recommendation_checks']) == 1
    paths = ['README.md', 'docs/16-第三轮补充实验协议.md', 'docs/17-第三轮结果与复现.md',
             'src/app/main.cpp', 'tools/refine.py', 'tools/profile_phases.py', 'tools/report_refine.py',
             'tools/check_refined.py', 'tools/seal_refinement.py', 'configs/refined/README.md',
             'refinement/results/refinement-summary.json', 'refinement/results/archive-audit.json',
             'refinement/results/preflight.json', 'refinement/results/runs.jsonl',
             'refinement/profiling/results/phase-summary.json', 'report/refinement/第三轮补充实验报告.md',
             f'snapshots/source/{source_id}/manifest.json']
    paths += [str(p.relative_to(root)) for p in (root/'configs/refined').glob('*.json')]
    for directory in audit['recommendation_checks']:
        paths += [directory+'/summary.json', directory+'/checksums.json']
    for path, h in audit['files'].items(): assert digest(root/path) == h
    result = {'created': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source_id': source_id,
              'research_processes': 168, 'timing_samples': 128, 'observation_processes': 20, 'config_checks': 4,
              'files': {p: digest(root/p) for p in sorted(set(paths))},
              'scope': 'round-three bounded experiments complete; current app instrumentation is separate from frozen performance binaries'}
    write(root/'refinement/results/delivery.json', result)
    print(json.dumps({'pass': True, 'source_id': source_id, 'files': len(result['files'])}))

if __name__ == '__main__': main()
