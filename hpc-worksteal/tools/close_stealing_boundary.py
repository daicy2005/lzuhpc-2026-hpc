#!/usr/bin/env python3
"""Read-only V13 delivery checks, Linux source snapshot and new receipt."""
import argparse
import ast
import json
import pathlib
import re
import urllib.parse

import lab
from stealing_boundary_study import load, read


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',required=True)
    args=parser.parse_args();root=lab.ROOT
    collector=root/'stealing-boundary';p=load(collector)
    collector_source=collector/'snapshots/source'/p['collector_source_id']
    measured_source=collector/'snapshots/source'/p['build']['source_id']
    frozen,original=read(collector_source/'manifest.json'),read(measured_source/'manifest.json')
    code=[name for name in original['files'] if name.startswith(('src/','include/')) or
          name.startswith(('tests/','configs/')) and name.endswith(('.cpp','.hpp','.py','.json')) or
          name in ('CMakeLists.txt','CMakePresets.json')]
    for name in code:assert lab.digest(root/name)==original['files'][name]==frozen['files'][name]
    assert lab.digest(root/p['protocol'])==frozen['files'][p['protocol']]
    # Retain the frozen collector. Only its post-run audit was corrected:
    # compute workloads have null pretouch identity, not an all-zero FNV.
    tool='tools/stealing_boundary_study.py'
    def definitions(path):
        tree=ast.parse(path.read_text(encoding='utf-8'))
        return {node.name:ast.dump(node,include_attributes=False) for node in tree.body if isinstance(node,ast.FunctionDef)}
    before,after=definitions(collector_source/tool),definitions(root/tool)
    assert before.keys()==after.keys()
    assert [name for name in before if before[name]!=after[name]]==['audit']
    previous=read(root/'results/init-cost-delivery-20261022.json')
    for name,sha in previous['artifact_sha256'].items():assert lab.digest(root/name)==sha
    prior=read(root/'results/fill-interleaved-delivery-20261022.json')
    for name,sha in prior['artifact_sha256'].items():assert lab.digest(root/name)==sha
    receipts=list((collector/'results').glob('export-*.json'));assert len(receipts)==1
    exported=read(receipts[0])
    for name,sha in exported['files'].items():assert lab.digest(collector/name)==sha
    audits=list((collector/'results').glob('audit-*.json'));assert len(audits)==2
    a,b=map(read,audits)
    assert {k:v for k,v in a.items() if k!='created'}=={k:v for k,v in b.items() if k!='created'}
    assert a['audit_pass'] and a['complete'] and a['accepted'] is None
    documents=[root/'README.md',root/'tools/README.md',root/'tests/README.md',root/'report/README.md',
        root/p['protocol'],root/'docs/38-第十三轮窃取边界结果.md',root/args.report]
    checked_links=0
    for document in documents:
        for link in re.findall(r'\]\(([^)]+)\)',document.read_text(encoding='utf-8')):
            if '://' in link or link.startswith('#'):continue
            assert (document.parent/urllib.parse.unquote(link.split('#')[0].strip('<>'))).exists(),(str(document),link)
            checked_links+=1
    source=lab.snapshot();snap=root/'snapshots/source'/source;delivery=read(snap/'manifest.json')
    for name,sha in delivery['files'].items():assert lab.digest(snap/name)==sha
    batch=collector/'runs'/a['batch'];availability=read(next((collector/'results').glob('availability-*.json')))
    artifacts=[root/p['protocol'],documents[-2],documents[-1],*audits,collector/'results/frozen-plan.json']
    receipt={'date':'2026-10-25','sampling_date':'2026-10-22','study':'V13 optimized-runtime off/on grain and placement boundaries',
        'status':'completed_mechanism_only','accepted':None,'batch':a['batch'],
        'processes':a['processes'],'timing_samples':a['timing_samples'],'diagnostic_samples':a['diagnostic_samples'],
        'batch_elapsed_seconds':read(batch/'completion.json')['elapsed_seconds'],
        'resource_samples':a['resource_samples'],'availability_observations':len(availability['observations']),
        'availability_elapsed_seconds':availability['elapsed_seconds'],
        'collector_source_id':p['collector_source_id'],'measured_build':p['build'],
        'delivery_source_id':source,'delivery_source_files_verified':len(delivery['files']),
        'production_test_config_cmake_files_unchanged':len(code),
        'historical_config_json_unchanged':sum(name.startswith('configs/') and name.endswith('.json') for name in original['files']),
        'exported_files_verified':len(exported['files']),'hash_checks_each_audit':a['hash_checks'],
        'checked_document_links':checked_links,'previous_delivery_artifacts_preserved':len(previous['artifact_sha256'])+len(prior['artifact_sha256']),
        'frozen_protocol_and_collector_unchanged':True,'current_audit_corrected_compute_pretouch_null':True,
        'corrected_tool_sha256':lab.digest(root/tool),'new_recommendation_created':False,
        'repeated_observations':a['repeated_observations'],'report':args.report,
        'analysis':'docs/38-第十三轮窃取边界结果.md',
        'artifact_sha256':{path.relative_to(root).as_posix():lab.digest(path) for path in artifacts}}
    path=root/'results/stealing-boundary-delivery-20261025.json';lab.write(path,receipt)
    print(json.dumps({'receipt':str(path),'sha256':lab.digest(path),'delivery_source_id':source,
        'source_files':len(delivery['files']),'checked_links':checked_links},ensure_ascii=False))


if __name__=='__main__':main()
