#!/usr/bin/env python3
"""Inspect current delivery evidence without building, timing, or changing original records."""
import argparse
import json
import pathlib
import re
import urllib.parse
import zipfile

import export_prompt_session
import lab


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--package-receipt', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    root = lab.ROOT
    package = read(root/args.package_receipt)
    archive, unpacked = root/package['archive'], root/package['unpacked']
    assert lab.digest(archive) == package['archive_sha256']
    manifest = read(unpacked/'PACKAGE-MANIFEST.json')
    assert lab.digest(unpacked/'PACKAGE-MANIFEST.json') == package['package_manifest_sha256']
    assert len(manifest['files']) == package['files_verified']
    assert not any(n.startswith('submission/unpacked-') for n in manifest['files'])
    with zipfile.ZipFile(archive) as z:
        assert len(z.namelist()) == len(set(z.namelist())) == package['files_verified']+1
        assert json.loads(z.read('PACKAGE-MANIFEST.json')) == manifest

    def verify(relative, expected=None):
        path = root/relative
        h = lab.digest(path)
        if expected is not None:
            assert h == expected, relative
        assert manifest['files'][relative]['sha256'] == h == lab.digest(unpacked/relative), relative
        return h

    native_dir = root/'submission/reproduction/20261025'
    native = read(native_dir/'receipt.json')
    assert native['pass'] and native['linux'] and not native['container_built']
    native_hashes = read(native_dir/'checksums.json')
    for rel, sha in native_hashes.items():
        verify('submission/reproduction/20261025/'+rel, sha)
    tested_inputs = []
    for rel, sha in read(native_dir/'source-files.json').items():
        if rel.startswith(('src/', 'include/')) or rel.startswith('tests/') and rel.endswith(('.cpp', '.hpp', '.py')) or rel in ('CMakeLists.txt', 'CMakePresets.json'):
            verify(rel, sha)
            tested_inputs.append(rel)
    ctests = []
    for name in ('default', 'optimized', 'uniform'):
        text = (native_dir/(name+'-ctest.stdout.log')).read_text()
        assert '"checks":2551' in text and '"checks": 497' in text
        assert '100% tests passed, 0 tests failed out of 2' in text
        assert read(native_dir/(name+'-ctest.command.json'))['returncode'] == 0
        built = (native_dir/(name+'-build.stdout.log')).read_text()+(native_dir/(name+'-build.stderr.log')).read_text()
        assert 'warning:' not in built.lower()
        ctests.append({'build': name, 'runtime_checks': 2551, 'cli_checks': 497,
                       'scope': 'archived verbose test output; unchanged code matched above; no new test run'})
    exact_runs = []
    for name, config_path in (
        ('recommended-light', 'configs/verified/light.json'),
        ('recommended-skewed', 'configs/verified/skewed.json'),
        ('recommended-memory', 'configs/verified/memory.json'),
        ('recommended-uniform', 'configs/verified/uniform.json'),
        ('memory-interleaved', 'configs/memory-interleaved/memory.json'),
        ('memory-interleaved-large', 'configs/memory-interleaved/memory-large.json')):
        result = read(native_dir/(name+'.json'))
        config = read(root/config_path)
        resolved = dict(config, steal_enabled=True)
        assert result['resolved_config'] == resolved and result['correctness']['pass']
        assert all(e['correctness']['mismatches'] == 0 and
                   e['correctness']['compared_elements'] == config['workload']['elements'] for e in result['epochs'])
        verify(config_path)
        exact_runs.append(name)

    report = read(root/'report/final/input-data.json')
    for rel, expected in report['source_sha256'].items():
        if lab.digest(root/rel) != expected:
            frozen = root/'snapshots/source'/report['narrative_source_snapshot']/rel
            assert lab.digest(frozen) == expected, rel
            verify(frozen.relative_to(root).as_posix(), expected)
        else:
            verify(rel, expected)
    for rel, entry in report['verified_raw_runs'].items():
        result_path = rel+'/result.json'
        verify(result_path, entry['result_sha256'])
        result, metadata = read(root/result_path), read(root/rel/'metadata.json')
        assert metadata['purpose'] == 'timing' and metadata['included'] and metadata['status'] == 'completed'
        assert metadata['exit_code'] == 0 and metadata['binary_sha256'] == entry['binary_sha256']
        assert not (root/rel/'stderr.log').read_bytes()
        assert result['correctness']['pass']
        assert result['timing']['epoch_seconds'] == entry['epoch']
        assert result['timing']['end_to_end_seconds'] == entry['app']
        n = result['resolved_config']['workload']['elements']
        assert all(e['correctness']['mismatches'] == 0 and
                   e['correctness']['compared_elements'] == n for e in result['epochs'])
    visual = read(root/'output/pdf/final-20261025-visual-review.json')
    assert visual['visual_review_pass'] and visual['pages_reviewed'] == list(range(1, 13))
    verify(visual['pdf'], visual['pdf_sha256'])

    recommendation_count = 0
    for b in read(root/'configs/verified/builds.json').values():
        verify(b['config'], b['config_sha256'])
        verify(b['snapshot']+'/worksteal', b['binary_sha256'])
        validation = read(root/b['snapshot']/'validation.json')
        assert validation['pass'] and validation['source_id'] == b['source_id']
        recommendation_count += 1
    memory = read(root/'configs/memory-interleaved/builds.json')
    verify(memory['build_snapshot']+'/worksteal', memory['release_binary_sha256'])
    for b in memory['configs']:
        verify(b['file'], b['sha256'])

    upstream_dir = root/'reference/upstream-20261025-api'
    upstream = read(upstream_dir/'verification.json')
    assert upstream['latest_revision_verified'] and upstream['all_documents_same_after_newline_normalization']
    for rel, sha in read(upstream_dir/'checksums.json').items():
        verify('reference/upstream-20261025-api/'+rel, sha)

    prompt_dir = root/'submission/prompts/session-20261025-v16-resource-close'
    prompt = read(prompt_dir/'manifest.json')
    for rel, sha in prompt['files'].items():
        verify('submission/prompts/session-20261025-v16-resource-close/'+rel, sha)
    original = pathlib.Path('C:/Users/admin/.codex/sessions/2026/10/15')/prompt['source_filename']
    with original.open('rb') as stream:
        prefix = stream.read(prompt['source_prefix_bytes'])
    import hashlib
    assert hashlib.sha256(prefix).hexdigest() == prompt['source_prefix_sha256']
    messages, _ = export_prompt_session.extract(prefix, prompt['session_id'])
    assert messages == read(prompt_dir/'prompt-response.json')['messages']

    prepared = read(root/'results/victim-selection-preparation-20261025.json')
    assert prepared['research_processes'] == prepared['formal_timing_samples'] == 0
    assert prepared['accepted'] is None and prepared['availability_attempts'] == 2
    for rel, sha in prepared['artifact_sha256'].items():
        verify(rel, sha)
    environment = read(root/'submission/environment/container-engine-recheck-20261025-final.json')
    assert not environment['container_actual_build_verified']
    assert not environment['configured_context']['named_pipe_connected']
    verify('submission/environment/container-engine-recheck-20261025-final.json')

    documents = ('README.md', 'submission/README.md', 'tools/README.md', 'report/README.md',
        'reference/README.md', 'docs/02-架构与文件职责.md', 'docs/07-阶段计划与CS149映射.md',
        'docs/42-最终交付验收台账.md', 'docs/45-第十六轮Victim选择协议.md',
        'docs/46-第十六轮Victim选择结果.md', 'docs/47-随机Victim序列相关性源码观察.md',
        'docs/48-最终复核与环境阻塞.md')
    links = 0
    for rel in documents:
        verify(rel)
        document = root/rel
        for link in re.findall(r'\]\(([^)]+)\)', document.read_text(encoding='utf-8')):
            if '://' in link or link.startswith('#'):
                continue
            target = (document.parent/urllib.parse.unquote(link.split('#')[0].strip('<>'))).resolve()
            assert target.exists(), (rel, link)
            target_relative = target.relative_to(root).as_posix()
            assert target_relative in manifest['files'] or target.is_dir(), (rel, link)
            links += 1
    result = {'created': lab.now(), 'audit_pass': True, 'goal_complete': False,
        'package': package, 'code_inputs_equal_native_tested_inputs': tested_inputs,
        'native_export_files_verified': len(native_hashes), 'native_builds': ctests,
        'exact_recommendation_functional_results_verified': exact_runs,
        'report_formal_runs_rechecked': len(report['verified_raw_runs']),
        'report_source_inputs_verified_current_or_frozen': len(report['source_sha256']),
        'historical_verified_build_config_pairs': recommendation_count,
        'memory_historical_build_and_two_configs_verified': True,
        'pdf_hash_matches_prior_twelve_page_visual_review': True,
        'upstream_commit': upstream['commit'], 'upstream_documents_unchanged': True,
        'session_prefix_messages_verified': len(messages),
        'active_documents_verified_in_package': len(documents), 'local_links_checked': links,
        'no_new_application_build_test_or_timing_claimed': True,
        'open_items': [
            {'requirement': 'project DevContainer actual build acceptance', 'status': 'blocked_no_local_engine_or_usable_configured_endpoint',
             'evidence': 'submission/environment/container-engine-recheck-20261025-final.json',
             'source_of_requirement': 'project acceptance ledger; official task recommends DevContainer'},
            {'requirement': 'V16 frozen victim comparison', 'status': 'not_sampled_resource_wait_budget_exhausted',
             'evidence': 'results/victim-selection-preparation-20261025.json'},
            {'requirement': 'original temporary binary image attachments', 'status': 'unavailable_at_original_paths; persisted continuous text is preserved',
             'evidence': 'submission/prompts/attachment-availability-20261025.json'},
            {'requirement': 'user personally understands and can explain the project', 'status': 'not_verifiable_by_agent_checks',
             'evidence': 'docs/07-阶段计划与CS149映射.md'}],
        'locality_limit': 'LLC scale coverage and controlled executor measurements exist; dynamic W03 diagnostics had zero successful steals, so dynamic cache-loss causality is unproven',
        'external_submission_sent': False}
    lab.write(root/args.out, result)
    print(json.dumps({'audit': args.out, 'audit_pass': True, 'goal_complete': False,
        'formal_runs_rechecked': result['report_formal_runs_rechecked'],
        'native_export_files_verified': len(native_hashes), 'local_links_checked': links}, ensure_ascii=False))


if __name__ == '__main__':
    main()
