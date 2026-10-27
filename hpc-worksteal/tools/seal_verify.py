#!/usr/bin/env python3
"""Seal round-four deliverables without modifying historical measurements."""
import datetime, json
from lab import ROOT, digest, snapshot, write

def main():
    root=ROOT; audit=json.loads((root/'verification/results/archive-audit.json').read_text(encoding='utf-8'))
    assert audit['pass'] and len(audit['recommendation_checks'])==1
    assert audit['processes']==180 and audit['timing_samples']==140
    for rel,h in audit['files'].items(): assert digest(root/rel)==h
    source_id=snapshot()
    paths=['README.md','docs/03-策略与接口契约.md','docs/18-第四轮并行核验协议.md','docs/19-第四轮结果与核验契约.md',
           'include/worksteal/workload.hpp','src/workloads/workload.cpp','src/app/main.cpp','tests/runtime_checks.cpp','tests/cli_checks.py',
           'tools/verify_study.py','tools/report_verify.py','tools/check_verified.py','tools/seal_verify.py',
           'verification/results/verification-summary.json','verification/results/archive-audit.json','verification/results/runs.jsonl',
           'report/verification/第四轮并行核验报告.md','configs/verified/README.md',f'snapshots/source/{source_id}/manifest.json']
    paths += [str(p.relative_to(root)) for p in (root/'configs/verified').glob('*.json')]
    for d in audit['recommendation_checks']: paths += [d+'/summary.json',d+'/checksums.json']
    result={'created':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_id':source_id,
            'files':{p:digest(root/p) for p in sorted(set(paths))},'research_processes':180,'timing_samples':140,'config_checks':4,
            'scope':'parallel full scalar reference verification; shared WSL1 host with another experiment; not work-stealing epoch speedup',
            'host_overlap':audit['host_overlap']}
    write(root/'verification/results/delivery.json',result)
    print(json.dumps({'pass':True,'files':len(result['files']),'source_id':source_id}))

if __name__=='__main__': main()
