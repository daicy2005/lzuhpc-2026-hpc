#!/usr/bin/env python3
"""Seal the completed V16 recovery while preserving every previous delivery."""
import json

import lab
import recover_victim_selection as recovery


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    root, area = lab.ROOT, lab.ROOT/'victim-selection-recovery'
    plan = recovery.validate_prior(area)
    frozen = area/'snapshots/source'/plan['collector_source_id']
    files = read(frozen/'manifest.json')['files']
    stable = [n for n in files if n.startswith(('src/','include/')) or
              n.startswith(('tests/','configs/')) and n.endswith(('.cpp','.hpp','.py','.json')) or
              n in ('CMakeLists.txt','CMakePresets.json')]
    for name in stable:
        assert lab.digest(root/name) == files[name],name
    for name in (plan['protocol'],'docs/45-第十六轮Victim选择协议.md',
                 'tools/victim_selection_study.py','tools/recover_victim_selection.py','tools/shuffle_oracle.cpp'):
        assert lab.digest(root/name) == lab.digest(frozen/name),name
    exports=list((area/'results').glob('export-*.json'))
    assert len(exports)==1
    exported=read(exports[0])
    for rel,sha in exported['files'].items():assert lab.digest(area/rel)==sha,rel
    audits=sorted((area/'results').glob('audit-*.json'))
    assert len(audits)==2
    a,b=map(read,audits)
    assert {k:v for k,v in a.items() if k!='created'}=={k:v for k,v in b.items() if k!='created'}
    assert a['audit_pass'] and a['complete'] and not a['accepted']
    assert (a['processes'],a['timing_samples'],a['diagnostic_samples'])==(114,84,18)
    assert not (root/'configs/victim-selection').exists()
    waits=list((area/'results').glob('availability-*.json'))
    assert len(waits)==1 and read(waits[0])['status']=='ready'
    prior_checks=0
    for name in ('stealing-boundary-delivery-20261025.json','batch-migration-delivery-20261025.json',
                 'idle-backoff-delivery-20261025.json','victim-selection-preparation-20261025.json'):
        for rel,sha in read(root/'results'/name)['artifact_sha256'].items():
            assert lab.digest(root/rel)==sha,rel
            prior_checks+=1
    link=read(area/'results/recovery-link.json')
    for rel,sha in link['files'].items():assert lab.digest(root/'victim-selection/results'/rel)==sha,rel
    assert not list((root/'victim-selection/runs').glob('*'))
    old_packages={
        'Mini-WorkSteal-候选提交包-20261025.zip':'144e31409a82af619a2acf0fcfba2b8ffcf298518cbd71d217a595eb8ca5866c',
        'Mini-WorkSteal-候选提交包-20261025-v16状态.zip':'bfe98f6c8eaa3715d183a58438b27255f700c7974eeaf6bb2cec81155c6cccae'}
    for name,sha in old_packages.items():assert lab.digest(root/'submission/packages'/name)==sha
    visual=read(root/'output/pdf/update-20261027-visual-review.json')
    assert visual['visual_review_pass'] and visual['pages_reviewed']==list(range(1,16))
    assert lab.digest(root/visual['pdf'])==visual['pdf_sha256']
    for rel,sha in visual['rendered_pages'].items():assert lab.digest(root/rel)==sha
    inputs=read(root/'report/victim-selection/update-20261027/input-data.json')
    assert len(inputs['verified_raw_runs'])==663
    for rel,sha in inputs['source_sha256'].items():assert lab.digest(root/rel)==sha,rel
    artifact_paths=[*audits,exports[0],waits[0],area/'results/frozen-plan.json',area/'results/recovery-link.json',
        root/'docs/49-第十六轮资源恢复协议.md',root/'docs/50-第十六轮Victim选择恢复结果.md',
        root/'docs/51-本机交付索引.md',root/'report/victim-selection/第十六轮Victim选择报告-b339e9e0.md',
        root/'report/victim-selection/update-20261027/input-data.json',
        root/visual['pdf'],root/'output/pdf/update-20261027-visual-review.json',
        root/'output/pdf/update-20261027-render-check.json',root/'submission/environment/local-delivery-scope-20261027.json']
    receipt={'created':lab.now(),'date':'2026-10-27','status':'completed','accepted':False,
        'batch':a['batch'],'processes':114,'timing_samples':84,'diagnostic_samples':18,'warmup_samples':12,
        'confirmation':a['confirmation'],'resource_samples':a['resource_samples'],
        'resource_window_count':1,'resource_wait_seconds':read(waits[0])['elapsed_seconds'],
        'elapsed_seconds':read(area/'runs'/a['batch']/'completion.json')['elapsed_seconds'],
        'exported_files_verified':len(exported['files']),'hash_checks_each_audit':a['hash_checks'],
        'unchanged_production_test_config_cmake_files':len(stable),'unchanged_file_sha256':{n:files[n] for n in stable},
        'prior_artifact_checks':prior_checks,'prior_packages_sha256':old_packages,
        'old_v16_preparation_remains_unsampled':True,'collector_source_id':plan['collector_source_id'],'build':plan['build'],
        'cited_report_formal_runs':663,'new_recommendation_created':False,'new_cpp_build_or_sanitizer':False,
        'container_actual_build_verified':False,'container_status':'deferred_by_user; local delivery requested',
        'delivery_source_id':lab.snapshot(),
        'artifact_sha256':{p.relative_to(root).as_posix():lab.digest(p) for p in artifact_paths}}
    path=root/'results/victim-selection-recovery-delivery-20261027.json'
    lab.write(path,receipt)
    print(json.dumps({'receipt':str(path),'sha256':lab.digest(path),'exported_files':len(exported['files']),
                      'stable_code_test_config_cmake_files':len(stable),'prior_artifact_checks':prior_checks},ensure_ascii=False))


if __name__=='__main__':main()
