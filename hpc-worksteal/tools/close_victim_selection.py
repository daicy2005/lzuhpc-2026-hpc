#!/usr/bin/env python3
"""V16 delivery: verify both audits, immutable history, source boundaries and links."""
import argparse
import json
import re
import urllib.parse

import lab
import victim_selection_study as study


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', required=True)
    args = parser.parse_args()
    root, collector = lab.ROOT, lab.ROOT/'victim-selection'
    plan = study.load(collector)
    frozen = collector/'snapshots/source'/plan['collector_source_id']
    current = study.read(frozen/'manifest.json')
    stable = [n for n in current['files'] if n.startswith(('src/', 'include/')) or
              n.startswith(('tests/', 'configs/')) and n.endswith(('.cpp', '.hpp', '.py', '.json')) or
              n in ('CMakeLists.txt', 'CMakePresets.json')]
    for name in stable:
        assert lab.digest(root/name) == current['files'][name]
    for name in (plan['protocol'], 'tools/victim_selection_study.py', 'tools/shuffle_oracle.cpp'):
        assert lab.digest(root/name) == lab.digest(frozen/name)
    exports = list((collector/'results').glob('export-*.json'))
    assert len(exports) == 1
    exported = study.read(exports[0])
    for rel, sha in exported['files'].items():
        assert lab.digest(collector/rel) == sha
    audits = list((collector/'results').glob('audit-*.json'))
    assert len(audits) == 2
    a, b = map(study.read, audits)
    assert {k: v for k, v in a.items() if k != 'created'} == {k: v for k, v in b.items() if k != 'created'}
    assert a['audit_pass'] and a['complete'] and a['processes'] == 114 and a['timing_samples'] == 84
    preserved = 0
    for name in ('stealing-boundary-delivery-20261025.json', 'batch-migration-delivery-20261025.json',
                 'idle-backoff-delivery-20261025.json'):
        for rel, sha in study.read(root/'results'/name)['artifact_sha256'].items():
            assert lab.digest(root/rel) == sha
            preserved += 1
    # Keep the previous delivered ZIP intact; it intentionally predates V16.
    previous = root/'submission/packages/Mini-WorkSteal-候选提交包-20261025.zip'
    assert lab.digest(previous) == '144e31409a82af619a2acf0fcfba2b8ffcf298518cbd71d217a595eb8ca5866c'
    recommendation = root/'configs/victim-selection'
    if not a['accepted']:
        assert not recommendation.exists()
    else:
        assert study.read(recommendation/'builds.json')['binary_sha256'] == study.SHA
        for item in plan['study']['conditions']:
            if item['stage'] == 'confirm' and item['config']['policies']['victim']['name'] == 'seeded_random':
                assert study.read(recommendation/(item['id']+'.json')) == item['config']
    replay = study.read(root/'results/victim-collector-replay-20261025.json')
    assert replay['pass'] and len(replay['rejected_corruptions']) == 6
    for rel, sha in replay['source_sha256'].items():
        assert lab.digest(root/rel) == sha
    for rel, sha in replay['original_sha256'].items():
        assert lab.digest(root/replay['original_directory']/rel) == sha
    documents = [root/n for n in ('README.md', 'tools/README.md', 'report/README.md', 'submission/README.md',
        'docs/02-架构与文件职责.md', 'docs/07-阶段计划与CS149映射.md',
        'docs/47-随机Victim序列相关性源码观察.md', 'docs/42-最终交付验收台账.md',
        plan['protocol'], 'docs/46-第十六轮Victim选择结果.md', args.report)]
    links = 0
    for document in documents:
        for link in re.findall(r'\]\(([^)]+)\)', document.read_text(encoding='utf-8')):
            if '://' in link or link.startswith('#'):
                continue
            assert (document.parent/urllib.parse.unquote(link.split('#')[0].strip('<>'))).exists(), (str(document), link)
            links += 1
    available = [study.read(p) for p in (collector/'results').glob('availability-*.json')]
    batch = collector/'runs'/a['batch']
    artifacts = [root/plan['protocol'], root/'docs/46-第十六轮Victim选择结果.md',
                 root/'docs/47-随机Victim序列相关性源码观察.md',
                 root/'results/victim-collector-replay-20261025.json', root/args.report,
                 *audits, collector/'results/frozen-plan.json']
    source = lab.snapshot()
    receipt = {'date': '2026-10-25', 'study': 'V16 round_robin versus seeded_random seed17',
        'status': 'completed', 'accepted': a['accepted'], 'batch': a['batch'],
        'processes': a['processes'], 'timing_samples': a['timing_samples'],
        'diagnostic_samples': a['diagnostic_samples'], 'confirmation': a['confirmation'],
        'batch_elapsed_seconds': study.read(batch/'completion.json')['elapsed_seconds'],
        'resource_samples': a['resource_samples'], 'availability_attempts': len(available),
        'availability_observations': sum(len(v['observations']) for v in available),
        'availability_elapsed_seconds': sum(v['elapsed_seconds'] for v in available),
        'collector_source_id': plan['collector_source_id'], 'build': plan['build'],
        'delivery_source_id': source, 'unchanged_current_production_test_config_cmake_files': len(stable),
        'measured_source_is_historical_and_separate_from_collector': True,
        'exported_files_verified': len(exported['files']), 'hash_checks_each_audit': a['hash_checks'],
        'shuffle_model_reference_cases': 50, 'prior_artifact_checks': preserved, 'checked_local_links': links,
        'previous_candidate_zip_unchanged': True, 'previous_candidate_zip_contains_v16': False,
        'report': args.report, 'analysis': 'docs/46-第十六轮Victim选择结果.md',
        'new_recommendation_created': a['accepted'],
        'artifact_sha256': {p.relative_to(root).as_posix(): lab.digest(p) for p in artifacts}}
    path = root/'results/victim-selection-delivery-20261025.json'
    lab.write(path, receipt)
    print(json.dumps({'receipt': str(path), 'sha256': lab.digest(path), 'source_id': source}, ensure_ascii=False))


if __name__ == '__main__':
    main()
