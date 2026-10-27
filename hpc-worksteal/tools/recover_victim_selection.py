#!/usr/bin/env python3
"""Resume the unsampled V16 plan in a new directory with one resource window."""
import argparse
import json
import pathlib
import shutil

import lab
import victim_selection_study as study

PROTOCOL = 'docs/49-第十六轮资源恢复协议.md'
study.PROTOCOL = PROTOCOL


def validate_prior(root):
    link = study.read(root/'results/recovery-link.json')
    prior = root/'results/prior-preparation'
    for name, sha in link['files'].items():
        assert lab.digest(prior/name) == sha
    old = study.read(prior/'frozen-plan.json')
    assert lab.digest(prior/'frozen-plan.json') == study.read(prior/'preparation.json')['plan_sha256']
    new = study.load(root)
    assert new['study'] == old['study'] and new['build'] == old['build']
    assert len(link['availability_files']) == 2 and link['prior_research_processes'] == 0
    for name in link['availability_files']:
        assert study.read(prior/name)['status'] == 'deferred_busy'
    assert link['max_resource_windows'] == 1
    frozen = root/'snapshots/source'/new['collector_source_id']
    assert lab.digest(frozen/'tools/victim_selection_study.py') == link['original_collector_sha256']
    return new


def prepare(root, previous):
    old = study.load(previous)
    assert not list((previous/'runs').glob('*'))
    waits = sorted((previous/'results').glob('availability-*.json'))
    assert len(waits) == 2 and all(study.read(p)['status'] == 'deferred_busy' for p in waits)
    frozen = previous/'snapshots/source'/old['collector_source_id']
    original_sha = lab.digest(frozen/'tools/victim_selection_study.py')
    assert lab.digest(lab.ROOT/'tools/victim_selection_study.py') == original_sha
    study.prepare(root)
    prior = root/'results/prior-preparation'
    prior.mkdir(parents=True)
    files = {}
    for source in [previous/'results/frozen-plan.json', previous/'results/preparation.json', *waits]:
        destination = prior/source.name
        shutil.copy2(source, destination)
        assert lab.digest(source) == lab.digest(destination)
        files[source.name] = lab.digest(source)
    lab.write(root/'results/recovery-link.json', {'created': lab.now(), 'previous_root': str(previous),
        'files': files, 'availability_files': [p.name for p in waits], 'prior_research_processes': 0,
        'max_resource_windows': 1, 'original_collector_sha256': original_sha})
    validate_prior(root)
    print(json.dumps({'recovery_link_verified': True, 'previous_plan_unchanged': True}), flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=('prepare', 'run', 'audit', 'export', 'report'))
    parser.add_argument('--root', required=True)
    parser.add_argument('--previous-root')
    parser.add_argument('--target')
    args = parser.parse_args()
    root = pathlib.Path(args.root).resolve()
    if args.action == 'prepare':
        assert args.previous_root
        prepare(root, pathlib.Path(args.previous_root).resolve())
        return 0
    validate_prior(root)
    if args.action != 'report':
        lab.ROOT = root
    if args.action == 'run':
        assert not list((root/'results').glob('availability-*.json')), 'one recovery resource window only'
        return study.run(root, 600)
    if args.action == 'audit':
        study.audit(root)
    if args.action == 'export':
        lab.export(argparse.Namespace(target=args.target))
    if args.action == 'report':
        study.report(root)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
