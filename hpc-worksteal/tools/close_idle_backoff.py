#!/usr/bin/env python3
"""Close V15 with cross-platform audits, failed-batch preservation and provenance."""
import argparse
import ast
import json
import re
import urllib.parse

import idle_backoff_study as study
import lab


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    root, collector = lab.ROOT, lab.ROOT/'idle-backoff'
    plan = study.load(collector)
    frozen = collector/'snapshots/source'/plan['collector_source_id']
    original = study.read(collector/'snapshots/source'/plan['build']['source_id']/'manifest.json')
    stable = [n for n in original['files'] if n.startswith(('src/', 'include/')) or
              n.startswith(('tests/', 'configs/')) and n.endswith(('.cpp', '.hpp', '.py', '.json')) or
              n in ('CMakeLists.txt', 'CMakePresets.json')]
    for name in stable:
        assert lab.digest(root/name) == original['files'][name] == lab.digest(frozen/name)
    for name in (plan['protocol'], 'docs/41-第十五轮空闲退避协议.md',
                 'tools/batch_migration_study.py', 'tools/stealing_boundary_study.py'):
        assert lab.digest(root/name) == lab.digest(frozen/name)
    # Sampling used its frozen collector. The later read-only report fixed links
    # for the separate failed directory; no sampling/check/decision code changed.
    def functions(path):
        return {n.name: ast.dump(n, include_attributes=False) for n in ast.parse(path.read_text(encoding='utf-8')).body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    before, after = (functions(p) for p in (frozen/'tools/idle_backoff_study.py', root/'tools/idle_backoff_study.py'))
    assert before.keys() == after.keys()
    changed = [name for name in before if before[name] != after[name]]
    assert changed == ['report']
    preserved = 0
    for name in ('stealing-boundary-delivery-20261025.json', 'batch-migration-delivery-20261025.json'):
        for rel, sha in study.read(root/'results'/name)['artifact_sha256'].items():
            assert lab.digest(root/rel) == sha
            preserved += 1
    exports = list((collector/'results').glob('export-*.json'))
    assert len(exports) == 1
    export = study.read(exports[0])
    for rel, sha in export['files'].items():
        assert lab.digest(collector/rel) == sha
    audits = list((collector/'results').glob('audit-*.json'))
    assert len(audits) == 2
    left, right = map(study.read, audits)
    assert {k:v for k,v in left.items() if k!='created'} == {k:v for k,v in right.items() if k!='created'}
    assert left['audit_pass'] and left['complete']
    failed = root/'idle-backoff-collector-failure'
    failure_exports = list((failed/'results').glob('export-*.json'))
    assert len(failure_exports) == 1
    failure_receipt = study.read(failure_exports[0])
    for rel, sha in failure_receipt['files'].items():
        assert lab.digest(failed/rel) == sha
    failure_audits = list((failed/'results').glob('audit-*.json'))
    assert len(failure_audits) == 2
    fa, fb = map(study.read, failure_audits)
    assert {k:v for k,v in fa.items() if k!='created'} == {k:v for k,v in fb.items() if k!='created'}
    assert fa['audit_pass'] and not fa['complete'] and fa['processes'] == 5 and fa['timing_samples'] == 0
    recommended = root/'configs/idle-backoff'
    if not left['accepted']:
        assert not recommended.exists()
    else:
        provenance = study.read(recommended/'builds.json')
        assert provenance['accepted'] and provenance['binary_sha256'] == study.SHA
        for it in plan['study']['conditions']:
            if it['stage'] == 'confirm' and it['policy'] == 'bounded_backoff':
                assert study.read(recommended/(it['id']+'.json')) == it['config']
    documents = [root/n for n in ('README.md', 'tools/README.md', 'tests/README.md', 'report/README.md',
        plan['protocol'], 'docs/41-第十五轮空闲退避协议.md', 'docs/44-第十五轮空闲退避结果.md', args.report)]
    links = 0
    for document in documents:
        for link in re.findall(r'\]\(([^)]+)\)', document.read_text(encoding='utf-8')):
            if '://' in link or link.startswith('#'):
                continue
            assert (document.parent/urllib.parse.unquote(link.split('#')[0].strip('<>'))).exists(), (str(document), link)
            links += 1
    source_id = lab.snapshot()
    manifest = study.read(root/'snapshots/source'/source_id/'manifest.json')
    for rel, sha in manifest['files'].items():
        assert lab.digest(root/'snapshots/source'/source_id/rel) == sha
    batch = collector/'runs'/left['batch']
    available = [study.read(p) for p in (collector/'results').glob('availability-*.json')]
    artifacts = [root/plan['protocol'], root/'docs/41-第十五轮空闲退避协议.md',
        root/'docs/44-第十五轮空闲退避结果.md', root/args.report, *audits, *failure_audits,
        collector/'results/frozen-plan.json', failed/'results/frozen-plan.json']
    receipt = {'date':'2026-10-25', 'study':'V15 immediate versus bounded_backoff',
        'status':'completed', 'accepted':left['accepted'], 'batch':left['batch'],
        'processes':left['processes'], 'timing_samples':left['timing_samples'],
        'diagnostic_samples':left['diagnostic_samples'], 'confirmation':left['confirmation'],
        'batch_elapsed_seconds':study.read(batch/'completion.json')['elapsed_seconds'],
        'resource_samples':left['resource_samples'], 'availability_attempts':len(available),
        'availability_observations':sum(len(v['observations']) for v in available),
        'availability_elapsed_seconds':sum(v['elapsed_seconds'] for v in available),
        'collector_source_id':plan['collector_source_id'], 'build':plan['build'],
        'delivery_source_id':source_id, 'delivery_snapshot_files_verified':len(manifest['files']),
        'unchanged_production_test_config_cmake_files':len(stable),
        'historical_config_json_unchanged':sum(n.startswith('configs/') and n.endswith('.json') for n in original['files']),
        'post_sampling_functions_changed':changed, 'post_sampling_change_scope':'report links only; frozen sampler unchanged',
        'exported_files_verified':len(export['files']), 'hash_checks_each_audit':left['hash_checks'],
        'failed_batch':{'batch':fa['batch'], 'processes':5, 'timing_samples':0,
            'exported_files_verified':len(failure_receipt['files']), 'audit_hash_checks':fa['hash_checks']},
        'prior_artifact_checks':preserved, 'checked_local_links':links,
        'report':args.report, 'analysis':'docs/44-第十五轮空闲退避结果.md',
        'new_recommendation_created':left['accepted'],
        'artifact_sha256':{p.relative_to(root).as_posix():lab.digest(p) for p in artifacts}}
    path = root/'results/idle-backoff-delivery-20261025.json'
    lab.write(path, receipt)
    print(json.dumps({'receipt':str(path),'sha256':lab.digest(path),'source_id':source_id},ensure_ascii=False))


if __name__ == '__main__':
    main()
