#!/usr/bin/env python3
"""Seal the final reviewable optimization deliverables without rewriting raw runs."""
import argparse, datetime, hashlib, json, pathlib

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--source-id',required=True);a=ap.parse_args();root=pathlib.Path(a.root).resolve()
    manifest=root/'snapshots/source'/a.source_id/'manifest.json';source=json.loads(manifest.read_text(encoding='utf-8'))
    assert source['source_id']==a.source_id
    for name,h in source['files'].items():assert sha(root/name)==h==sha(manifest.parent/name)
    summary=json.loads((root/'optimization/results/optimization-summary.json').read_text(encoding='utf-8'));assert summary['complete']
    audit=json.loads((root/'optimization/results/archive-audit.json').read_text(encoding='utf-8'));assert audit['pass']
    render=json.loads((root/'output/pdf/optimization-render-check.json').read_text(encoding='utf-8'))
    assert sha(root/'output/pdf/Mini-WorkSteal-第二轮优化.pdf')==render['pdf_sha256']
    assert sha(root/'optimization/results/optimization-summary.json')==render['summary_sha256']
    paths=['README.md','CMakePresets.json','docs/14-第二轮优化协议.md','docs/15-第二轮结果与复现.md',
        'configs/optimized/builds.json','configs/optimized/README.md','optimization/results/optimization-summary.json',
        'optimization/results/archive-audit.json','optimization/results/runs.jsonl','report/optimization/第二轮优化报告.md',
        'output/pdf/Mini-WorkSteal-第二轮优化.pdf','output/pdf/optimization-render-check.json']
    paths += [str(p.relative_to(root)) for p in (root/'report/optimization/figures').iterdir() if p.is_file()]
    paths += [str(p.relative_to(root)) for p in (root/'configs/optimized').glob('*.json')]
    result={'created':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source_id':a.source_id,
        'source_manifest':str(manifest.relative_to(root)),'files':{p:sha(root/p) for p in sorted(set(paths))},
        'research_processes':summary['processes'],'timing_samples':summary['timing_samples'],'config_checks':4,
        'all_heldout_accepted':all(d['accepted'] for d in summary['selection'].values()),
        'pdf_pages':render['pages'],'scope':'finite optimization completed; not final contest submission or global optimum proof'}
    output=root/'optimization/results/delivery.json'
    with output.open('x',encoding='utf-8') as f:json.dump(result,f,ensure_ascii=False,indent=2);f.write('\n')
    print(json.dumps({'delivery':str(output),'files':len(result['files']),'source_id':a.source_id,'pass':True},ensure_ascii=False))
if __name__=='__main__':main()
