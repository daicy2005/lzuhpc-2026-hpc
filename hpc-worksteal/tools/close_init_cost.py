#!/usr/bin/env python3
"""Verify the V12 delivery without rerunning or modifying any experiment."""
import argparse
import json
import pathlib
import re
import shutil
import urllib.parse

import lab
from init_cost_study import load, read


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--target', required=True)
    args = parser.parse_args()
    root, target = lab.ROOT, pathlib.Path(args.target).resolve()
    collector = target/'init-cost'
    plan = load(collector)
    frozen = collector/'snapshots/source'/plan['collector_source_id']
    production = collector/'snapshots/source'/plan['builds']['app']['source_id']
    manifest, original = read(frozen/'manifest.json'), read(production/'manifest.json')
    code = [name for name in original['files'] if name.startswith(('src/','include/')) or
            name.startswith(('tests/','configs/')) and name.endswith(('.cpp','.hpp','.py','.json')) or
            name in ('CMakeLists.txt','CMakePresets.json')]
    for name in code:
        assert original['files'][name] == manifest['files'][name] == lab.digest(root/name)
    json_files = [name for name in original['files'] if name.startswith('configs/') and name.endswith('.json')]
    for name in json_files:
        assert lab.digest(root/name) == original['files'][name]
    for name in ('tools/init_cost_probe.cpp','tools/init_cost_study.py', plan['protocol']):
        assert lab.digest(root/name) == manifest['files'][name]
    exports = {}
    for directory in (collector, target/'init-cost-preparation-warning'):
        receipts = list((directory/'results').glob('export-*.json'))
        assert len(receipts) == 1
        r = read(receipts[0])
        for rel, sha in r['files'].items():
            assert lab.digest(directory/rel) == sha
        exports[directory.name] = len(r['files'])
    # Also check the prior delivered artifacts; none is rewritten by this study.
    previous = read(target/'results/fill-interleaved-delivery-20261022.json')
    for rel, sha in previous['artifact_sha256'].items():
        assert lab.digest(target/rel) == sha
    linux = collector/'results/audit-094db447cd11418aa45beb748f83b1eb.json'
    windows = collector/'results/audit-67bb9ac04d204d50845e8d9cc72ff0bd.json'
    a, b = read(linux), read(windows)
    assert {k:v for k,v in a.items() if k != 'created'} == {k:v for k,v in b.items() if k != 'created'}
    assert a['audit_pass'] and a['diagnostic_complete'] and a['accepted'] is None
    docs = [root/'README.md', root/'tools/README.md', root/'tests/README.md', root/'report/README.md',
            root/plan['protocol'], root/'docs/36-第十二轮成本诊断结果.md',
            root/'report/init-cost/第十二轮初始化成本诊断报告-8da32b9c.md']
    links = 0
    for document in docs:
        for link in re.findall(r'\]\(([^)]+)\)',document.read_text(encoding='utf-8')):
            if '://' in link or link.startswith('#'):
                continue
            resolved = document.parent/urllib.parse.unquote(link.split('#')[0].strip('<>'))
            assert resolved.exists(), (str(document),link)
            links += 1
    source = lab.snapshot()
    directory = root/'snapshots/source'/source
    dest = target/'snapshots/source'/source
    if directory.resolve() != dest.resolve():
        shutil.copytree(directory,dest,dirs_exist_ok=True)
    delivery = read(directory/'manifest.json')
    for name, sha in delivery['files'].items():
        assert lab.digest(dest/name) == sha
    batch = collector/'runs'/a['batch']
    availability = read(next((collector/'results').glob('availability-*.json')))
    artifacts = docs[4:]+[linux,windows,collector/'results/frozen-plan.json',
                collector/'results/disassembly-release.txt',collector/'results/disassembly-app.txt']
    receipt = {'date': '2026-10-22', 'study': 'V12 standalone initialization cost diagnosis',
        'status': 'completed_diagnostic_only', 'accepted': None, 'batch': a['batch'],
        'processes': a['processes'], 'profiling_samples': a['profiling_samples'], 'timing_samples': 0,
        'probe_selftest_cases_each': 36, 'probe_builds': ['release','asan_ubsan'],
        'batch_elapsed_seconds': read(batch/'completion.json')['elapsed_seconds'],
        'resource_samples': a['resource_samples'],
        'availability_observations': len(availability['observations']),
        'availability_elapsed_seconds': availability['elapsed_seconds'],
        'collector_source_id': plan['collector_source_id'], 'builds': plan['builds'],
        'delivery_source_id': source, 'delivery_source_files_verified': len(delivery['files']),
        'production_test_config_cmake_files_unchanged': len(code),
        'historical_config_json_unchanged': len(json_files), 'exported_files_verified': exports,
        'hash_checks_each_audit': a['hash_checks'], 'checked_local_links': links,
        'previous_delivery_artifact_checks': len(previous['artifact_sha256']),
        'frozen_protocol_and_probe_source_unchanged': True, 'new_recommendation_created': False,
        'preserved_recommendation': 'configs/memory-interleaved and original V8 provenance',
        'report': 'report/init-cost/第十二轮初始化成本诊断报告-8da32b9c.md',
        'analysis': 'docs/36-第十二轮成本诊断结果.md',
        'artifact_sha256': {f.relative_to(root if f.is_relative_to(root) else target).as_posix():lab.digest(f)
                            for f in artifacts}}
    path = target/'results/init-cost-delivery-20261022.json'
    lab.write(path,receipt)
    print(json.dumps({'receipt': str(path), 'sha256': lab.digest(path), 'source_id': source,
                      'source_files': len(delivery['files']), 'links': links},ensure_ascii=False))


if __name__ == '__main__':
    main()
