#!/usr/bin/env python3
"""Replay real historical p32 evidence and require corrupt records to be rejected."""
import copy
import json

import lab
import victim_selection_study as study


def main():
    relative = 'verification/runs/20261016T043755Z-V4B-heldout-8b2129/0091-timing-skewed-ref32-s4001-candidate-r5-905b8c'
    directory = lab.ROOT/relative
    config, result = (study.read(directory/name) for name in ('config.json', 'result.json'))
    cache, outputs = {}, {}
    assert study.check(config, result, False, cache, outputs) is None
    corruptions = []
    for name in ('queue_identity', 'reference_coverage', 'reference_workers', 'affinity', 'output', 'resolved_policy'):
        bad = copy.deepcopy(result)
        if name == 'queue_identity':
            bad['epochs'][0]['identity']['queue_hash_fnv1a64'] = '0000000000000000'
        elif name == 'reference_coverage':
            bad['epochs'][0]['correctness']['compared_elements'] -= 1
        elif name == 'reference_workers':
            bad['epochs'][0]['correctness']['reference_workers_used'] = 16
        elif name == 'affinity':
            bad['affinity']['actual_workers'][0] = [1]
        elif name == 'output':
            bad['epochs'][0]['correctness']['output_hash_fnv1a64'] = '0000000000000000'
        elif name == 'resolved_policy':
            bad['resolved_config']['policies']['victim'] = {'name': 'seeded_random', 'seed': 17}
        try:
            study.check(config, bad, False, cache, outputs)
        except AssertionError:
            corruptions.append(name)
        else:
            raise AssertionError('collector accepted corruption: '+name)
    receipt = {'created': lab.now(), 'pass': True, 'scope': 'read-only replay of one real historical p32 timing; six deliberately corrupt copies rejected; no new application process or performance sample',
        'original_directory': relative, 'rejected_corruptions': corruptions,
        'source_sha256': {name: lab.digest(lab.ROOT/name) for name in (
            'tools/victim_selection_study.py', 'tools/validate_victim_collector.py')},
        'original_sha256': {name: lab.digest(directory/name) for name in ('config.json', 'result.json')}}
    target = lab.ROOT/'results/victim-collector-replay-20261025.json'
    lab.write(target, receipt)
    print(json.dumps({'receipt': str(target), 'pass': True, 'corruptions_rejected': len(corruptions)}))


if __name__ == '__main__':
    main()
