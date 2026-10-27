#!/usr/bin/env python3
"""Check V14 delivery, preserve former artifacts, snapshot source and receipt."""
import argparse
import json
import pathlib
import re
import urllib.parse

import batch_migration_study as study
import lab


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--report',required=True)
    args=parser.parse_args();root=lab.ROOT;collector=root/'batch-migration';p=study.load(collector)
    source=collector/'snapshots/source'/p['collector_source_id']
    original=study.read(collector/'snapshots/source'/p['build']['source_id']/'manifest.json')
    frozen=study.read(source/'manifest.json')
    files=[name for name in original['files'] if name.startswith(('src/','include/')) or
        name.startswith(('tests/','configs/')) and name.endswith(('.cpp','.hpp','.py','.json')) or
        name in ('CMakeLists.txt','CMakePresets.json')]
    for name in files:assert lab.digest(root/name)==original['files'][name]==frozen['files'][name]
    for name in ('tools/batch_migration_study.py','tools/stealing_boundary_study.py',p['protocol']):
        assert lab.digest(root/name)==frozen['files'][name]
    preserved=0
    for name in ('fill-interleaved-delivery-20261022.json','init-cost-delivery-20261022.json','stealing-boundary-delivery-20261025.json'):
        old=study.read(root/'results'/name)
        for rel,sha in old['artifact_sha256'].items():assert lab.digest(root/rel)==sha;preserved+=1
    exports=list((collector/'results').glob('export-*.json'));assert len(exports)==1
    export=study.read(exports[0])
    for rel,sha in export['files'].items():assert lab.digest(collector/rel)==sha
    audits=list((collector/'results').glob('audit-*.json'));assert len(audits)==2
    a,b=map(study.read,audits)
    assert {k:v for k,v in a.items() if k!='created'}=={k:v for k,v in b.items() if k!='created'}
    assert a['audit_pass'] and a['complete']
    recommended=root/'configs/batch-migration'
    if not a['accepted']:assert not recommended.exists(),'do not recommend a failed candidate'
    else:
        choice=a['selection']['selected_cap'];branch=p['study']['confirmation_branches'][str(choice)]
        provenance=study.read(recommended/'builds.json')
        assert provenance['accepted'] and provenance['binary_sha256']==study.SHA
        for item in branch['conditions']:
            if item['cap']==choice:
                assert study.read(recommended/(item['id']+'.json'))==item['config']
    docs=[root/'README.md',root/'tools/README.md',root/'tests/README.md',root/'report/README.md',
        root/p['protocol'],root/'docs/40-第十四轮批量窃取结果.md',root/args.report]
    if a['accepted']:docs.append(recommended/'README.md')
    links=0
    for document in docs:
        for link in re.findall(r'\]\(([^)]+)\)',document.read_text(encoding='utf-8')):
            if '://' in link or link.startswith('#'):continue
            assert (document.parent/urllib.parse.unquote(link.split('#')[0].strip('<>'))).exists(),(str(document),link)
            links+=1
    identifier=lab.snapshot();snap=root/'snapshots/source'/identifier;manifest=study.read(snap/'manifest.json')
    for name,sha in manifest['files'].items():assert lab.digest(snap/name)==sha
    batch=collector/'runs'/a['batch'];available=study.read(next((collector/'results').glob('availability-*.json')))
    artifacts=[root/p['protocol'],root/'docs/40-第十四轮批量窃取结果.md',root/args.report,*audits,collector/'results/frozen-plan.json']
    result={'date':'2026-10-25','study':'V14 bounded batch migration','status':'completed',
        'accepted':a['accepted'],'batch':a['batch'],'processes':a['processes'],'timing_samples':a['timing_samples'],
        'diagnostic_samples':a['diagnostic_samples'],'selection':a['selection'],'confirmation':a['confirmation'],
        'batch_elapsed_seconds':study.read(batch/'completion.json')['elapsed_seconds'],
        'resource_samples':a['resource_samples'],'availability_observations':len(available['observations']),
        'availability_elapsed_seconds':available['elapsed_seconds'],'collector_source_id':p['collector_source_id'],
        'build':p['build'],'delivery_source_id':identifier,'delivery_snapshot_files_verified':len(manifest['files']),
        'unchanged_production_test_config_cmake_files':len(files),
        'historical_config_json_unchanged':sum(n.startswith('configs/') and n.endswith('.json') for n in original['files']),
        'frozen_protocol_and_collector_unchanged':True,'exported_files_verified':len(export['files']),
        'hash_checks_each_audit':a['hash_checks'],'prior_artifact_checks':preserved,'checked_local_links':links,
        'new_recommendation_created':a['accepted'],'scope':'fixed 16 workers/grain8/K256; do not replace 32-worker recommendations',
        'report':args.report,'analysis':'docs/40-第十四轮批量窃取结果.md',
        'artifact_sha256':{f.relative_to(root).as_posix():lab.digest(f) for f in artifacts}}
    path=root/'results/batch-migration-delivery-20261025.json';lab.write(path,result)
    print(json.dumps({'receipt':str(path),'sha256':lab.digest(path),'source_id':identifier,'source_files':len(manifest['files']),'links':links},ensure_ascii=False))


if __name__=='__main__':main()
