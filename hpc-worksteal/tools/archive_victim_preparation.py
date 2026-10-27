#!/usr/bin/env python3
"""Verify an exported V16 preparation when both resource waits defer before sampling."""
import hashlib
import json
import re
import urllib.parse

import lab
import victim_selection_study as study


def main():
    root, area = lab.ROOT, lab.ROOT/'victim-selection'
    plan = study.load(area)
    assert not list((area/'runs').glob('*')), 'use the completed/failed-batch audit if a batch exists'
    receipts = list((area/'results').glob('export-*.json'))
    assert len(receipts) == 1
    exported = study.read(receipts[0])
    for rel, sha in exported['files'].items():
        assert lab.digest(area/rel) == sha
    checks = 0
    for manifest in (area/'snapshots/source').glob('*/manifest.json'):
        source = study.read(manifest)
        assert hashlib.sha256(json.dumps(source['files'], sort_keys=True).encode()).hexdigest() == source['source_id'] == manifest.parent.name
        for rel, sha in source['files'].items():
            assert lab.digest(manifest.parent/rel) == sha
            checks += 1
    frozen = area/'snapshots/source'/plan['collector_source_id']
    for name in (study.PROTOCOL, 'tools/victim_selection_study.py', 'tools/shuffle_oracle.cpp'):
        assert lab.digest(root/name) == lab.digest(frozen/name)
    for rel, sha in study.read(frozen/'manifest.json')['files'].items():
        if rel.startswith(('src/', 'include/')) or rel.startswith(('tests/', 'configs/')) and rel.endswith(('.cpp', '.hpp', '.py', '.json')) or rel in ('CMakeLists.txt', 'CMakePresets.json'):
            assert lab.digest(root/rel) == sha
    for manifest in (area/'snapshots/builds').glob('*/checksums.json'):
        for rel, sha in study.read(manifest).items():
            assert lab.digest(manifest.parent/rel) == sha
            checks += 1
    validation = study.read(area/'snapshots/builds'/study.SHA/'validation.json')
    assert validation['pass'] and validation['source_id'] == study.SOURCE
    assert lab.digest(area/'snapshots/builds'/study.SHA/'worksteal') == validation['binary_sha256'] == study.SHA
    waits = [study.read(p) for p in (area/'results').glob('availability-*.json')]
    assert len(waits) == 2 and all(w['status'] == 'deferred_busy' for w in waits)
    assert all(w['observations'] and w['wait_budget_seconds'] == 600 for w in waits)
    replay = study.read(root/'results/victim-collector-replay-20261025.json')
    assert replay['pass'] and len(replay['rejected_corruptions']) == 6
    for rel, sha in replay['source_sha256'].items():
        assert lab.digest(root/rel) == sha
    for rel, sha in replay['original_sha256'].items():
        assert lab.digest(root/replay['original_directory']/rel) == sha
    archive = root/'submission/packages/Mini-WorkSteal-候选提交包-20261025.zip'
    assert lab.digest(archive) == '144e31409a82af619a2acf0fcfba2b8ffcf298518cbd71d217a595eb8ca5866c'
    documents = [root/n for n in ('README.md', 'tools/README.md', 'report/README.md', 'submission/README.md',
        'docs/02-架构与文件职责.md', 'docs/07-阶段计划与CS149映射.md', 'docs/42-最终交付验收台账.md',
        study.PROTOCOL, 'docs/46-第十六轮Victim选择结果.md', 'docs/47-随机Victim序列相关性源码观察.md')]
    links = 0
    for document in documents:
        for link in re.findall(r'\]\(([^)]+)\)', document.read_text(encoding='utf-8')):
            if '://' in link or link.startswith('#'):
                continue
            assert (document.parent/urllib.parse.unquote(link.split('#')[0].strip('<>'))).exists(), (str(document), link)
            links += 1
    artifacts = [area/'results/frozen-plan.json', receipts[0],
        *sorted((area/'results').glob('availability-*.json')), root/study.PROTOCOL,
        root/'docs/46-第十六轮Victim选择结果.md', root/'docs/47-随机Victim序列相关性源码观察.md',
        root/'results/victim-collector-replay-20261025.json']
    source_id = lab.snapshot()
    receipt = {'created': lab.now(), 'status': 'prepared_resource_waits_exhausted_no_sampling',
        'research_processes': 0, 'formal_timing_samples': 0, 'accepted': None,
        'scientific_conclusion': None, 'frozen_planned_processes': 114, 'frozen_planned_timing_samples': 84,
        'availability_attempts': 2, 'availability_observations': sum(len(w['observations']) for w in waits),
        'availability_elapsed_seconds': sum(w['elapsed_seconds'] for w in waits),
        'exported_files_verified': len(exported['files']), 'source_build_hash_checks': checks,
        'shuffle_oracle_cases': 50, 'historical_replay_rejections': 6, 'checked_local_links': links,
        'collector_source_id': plan['collector_source_id'], 'build': plan['build'],
        'delivery_source_id': source_id, 'production_code_unchanged': True,
        'prior_candidate_archive_unchanged': True, 'prior_candidate_archive_contains_v16': False,
        'goal_complete': False, 'container_actual_build_verified': False,
        'next_step': 'No third wait or sampling under this exhausted protocol. Preserve preparation and resource receipts; future resource resumption requires an explicit new resource protocol before any sampling. Do not retune inputs, candidates or thresholds from these waits.',
        'artifact_sha256': {p.relative_to(root).as_posix(): lab.digest(p) for p in artifacts}}
    target = root/'results/victim-selection-preparation-20261025.json'
    lab.write(target, receipt)
    print(json.dumps({'receipt': str(target), 'sha256': lab.digest(target),
        'exported_files_verified': len(exported['files']), 'research_processes': 0}, ensure_ascii=False))


if __name__ == '__main__':
    main()
