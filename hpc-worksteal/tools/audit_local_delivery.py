#!/usr/bin/env python3
"""Audit the actual unpacked local delivery; deferred container is never a pass."""
import argparse
import hashlib
import json
import pathlib
import re
import urllib.parse
import zipfile

import export_prompt_session_v2 as export_prompt_session
import lab


def read(path):return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--package-receipt',required=True)
    parser.add_argument('--out',required=True)
    args=parser.parse_args()
    root=lab.ROOT
    package=read(root/args.package_receipt)
    archive,unpacked=root/package['archive'],root/package['unpacked']
    assert lab.digest(archive)==package['archive_sha256']
    manifest=read(unpacked/'PACKAGE-MANIFEST.json')
    assert lab.digest(unpacked/'PACKAGE-MANIFEST.json')==package['package_manifest_sha256']
    assert len(manifest['files'])==package['files_verified']
    assert not any(n.startswith(('submission/unpacked-','submission/packages/')) for n in manifest['files'])
    with zipfile.ZipFile(archive) as z:
        assert len(z.namelist())==len(set(z.namelist()))==package['files_verified']+1
        assert set(z.namelist())==set(manifest['files'])|{'PACKAGE-MANIFEST.json'}
        assert json.loads(z.read('PACKAGE-MANIFEST.json'))==manifest

    def verify(rel,sha=None):
        entry=manifest['files'][rel]
        assert lab.digest(root/rel)==lab.digest(unpacked/rel)==entry['sha256'],rel
        assert (root/rel).stat().st_size==(unpacked/rel).stat().st_size==entry['bytes']
        if sha is not None:assert entry['sha256']==sha,rel

    for rel in manifest['files']:verify(rel)
    closure=read(root/'results/victim-selection-recovery-delivery-20261027.json')
    assert closure['status']=='completed' and not closure['accepted']
    assert (closure['processes'],closure['timing_samples'],closure['diagnostic_samples'])==(114,84,18)
    assert not closure['new_recommendation_created'] and not closure['new_cpp_build_or_sanitizer']
    for rel,sha in closure['artifact_sha256'].items():verify(rel,sha)
    for rel,sha in closure['unchanged_file_sha256'].items():verify(rel,sha)
    for name,sha in closure['prior_packages_sha256'].items():assert lab.digest(root/'submission/packages'/name)==sha

    native_dir=root/'submission/reproduction/20261025'
    native=read(native_dir/'receipt.json')
    assert native['pass'] and native['linux'] and not native['container_built']
    native_hashes=read(native_dir/'checksums.json')
    for rel,sha in native_hashes.items():verify('submission/reproduction/20261025/'+rel,sha)
    native_code=0
    for rel,sha in read(native_dir/'source-files.json').items():
        if rel.startswith(('src/','include/')) or rel.startswith('tests/') and rel.endswith(('.cpp','.hpp','.py')) or rel in ('CMakeLists.txt','CMakePresets.json'):
            verify(rel,sha);native_code+=1
    for name in ('default','optimized','uniform'):
        output=(native_dir/(name+'-ctest.stdout.log')).read_text()
        assert '"checks":2551' in output and '"checks": 497' in output
        assert '100% tests passed, 0 tests failed out of 2' in output
        assert read(native_dir/(name+'-ctest.command.json'))['returncode']==0
    exact=[]
    for name,rel in (('recommended-light','configs/verified/light.json'),('recommended-skewed','configs/verified/skewed.json'),
                     ('recommended-memory','configs/verified/memory.json'),('recommended-uniform','configs/verified/uniform.json'),
                     ('memory-interleaved','configs/memory-interleaved/memory.json'),
                     ('memory-interleaved-large','configs/memory-interleaved/memory-large.json')):
        r,c=read(native_dir/(name+'.json')),read(root/rel)
        assert r['resolved_config']==dict(c,steal_enabled=True) and r['correctness']['pass']
        assert all(e['correctness']['mismatches']==0 and e['correctness']['compared_elements']==c['workload']['elements'] for e in r['epochs'])
        exact.append(name)
    for build in read(root/'configs/verified/builds.json').values():
        verify(build['config'],build['config_sha256'])
        verify(build['snapshot']+'/worksteal',build['binary_sha256'])
        v=read(root/build['snapshot']/'validation.json')
        assert v['pass'] and v['source_id']==build['source_id']
    memory=read(root/'configs/memory-interleaved/builds.json')
    verify(memory['build_snapshot']+'/worksteal',memory['release_binary_sha256'])
    for config in memory['configs']:verify(config['file'],config['sha256'])

    old=read(root/'report/final/input-data.json')
    for rel,sha in old['source_sha256'].items():
        if lab.digest(root/rel)==sha:verify(rel,sha)
        else:verify('snapshots/source/'+old['narrative_source_snapshot']+'/'+rel,sha)
    inputs=read(root/'report/victim-selection/update-20261027/input-data.json')
    assert len(inputs['verified_raw_runs'])==663
    for rel,sha in inputs['source_sha256'].items():verify(rel,sha)
    for rel,v in inputs['verified_raw_runs'].items():
        verify(rel+'/result.json',v['result_sha256']);verify(rel+'/checksums.json',v['checksums_sha256'])
        r,m=read(root/rel/'result.json'),read(root/rel/'metadata.json')
        assert m['purpose']=='timing' and m['included'] and m['status']=='completed' and m['exit_code']==0
        assert m['binary_sha256']==v['binary_sha256'] and r['correctness']['pass']
        assert r['timing']['epoch_seconds']==v['epoch'] and r['timing']['end_to_end_seconds']==v['app']
    visual=read(root/'output/pdf/update-20261027-visual-review.json')
    assert visual['visual_review_pass'] and visual['pages_reviewed']==list(range(1,16))
    verify(visual['pdf'],visual['pdf_sha256'])
    for rel,sha in visual['rendered_pages'].items():verify(rel,sha)
    prompt_dir=root/'submission/prompts/session-20261027-v16-completed'
    prompt=read(prompt_dir/'manifest.json')
    for rel,sha in prompt['files'].items():verify('submission/prompts/session-20261027-v16-completed/'+rel,sha)
    source=pathlib.Path('C:/Users/admin/.codex/sessions/2026/10/15')/prompt['source_filename']
    with source.open('rb') as f:prefix=f.read(prompt['source_prefix_bytes'])
    assert hashlib.sha256(prefix).hexdigest()==prompt['source_prefix_sha256']
    messages,_=export_prompt_session.extract(prefix,prompt['session_id'])
    assert messages==read(prompt_dir/'prompt-response.json')['messages']
    assert any('暂时没有，先完成本机实验和交付' in b.get('text','') for m in messages if m['role']=='user' for b in m['content'])
    compatibility=read(root/'results/session-format-compatibility-20261027.json')
    assert compatibility['pass'] and compatibility['old_prefix_messages_identical']==365
    assert compatibility['fallback_count']==1 and compatibility['original_ui_blocks_preserved'] and compatibility['unsupported_event_rejected']
    verify('tools/export_prompt_session_v2.py',compatibility['extractor_sha256'])
    verify('tools/export_prompt_session.py',compatibility['original_extractor_sha256'])
    scope=read(root/'submission/environment/local-delivery-scope-20261027.json')
    assert scope['user_answer']=='暂时没有，先完成本机实验和交付' and not scope['container_actual_build_verified']
    upstream=read(root/'reference/upstream-20261025-api/verification.json')
    assert upstream['latest_revision_verified'] and upstream['all_documents_same_after_newline_normalization']
    for rel,sha in read(root/'reference/upstream-20261025-api/checksums.json').items():verify('reference/upstream-20261025-api/'+rel,sha)
    documents=('README.md','submission/README.md','tools/README.md','report/README.md','reference/README.md',
        'docs/02-架构与文件职责.md','docs/07-阶段计划与CS149映射.md','docs/42-最终交付验收台账.md',
        'docs/49-第十六轮资源恢复协议.md','docs/50-第十六轮Victim选择恢复结果.md','docs/51-本机交付索引.md',
        'report/victim-selection/第十六轮Victim选择报告-b339e9e0.md')
    links=0
    for rel in documents:
        for link in re.findall(r'\]\(([^)]+)\)',(root/rel).read_text(encoding='utf-8')):
            if '://' in link or link.startswith('#'):continue
            target=((root/rel).parent/urllib.parse.unquote(link.split('#')[0].strip('<>'))).resolve()
            assert target.exists(),(rel,link)
            assert target.is_dir() or target.relative_to(root).as_posix() in manifest['files'],(rel,link)
            links+=1
    result={'created':lab.now(),'audit_pass':True,'local_delivery_complete':True,'full_project_acceptance_complete':False,
        'scope':'User requested local experiments and delivery; container actual build deferred, not passed.',
        'package':package,'all_packaged_files_current_and_unpacked_sha256_verified':len(manifest['files']),
        'v16_processes':114,'v16_timing_samples':84,'v16_accepted':False,'v16_dual_audit_hash_checks_each':closure['hash_checks_each_audit'],
        'report_cited_formal_runs_verified':663,'report_pdf_pages_visually_reviewed':15,
        'unchanged_code_test_config_cmake_files':len(closure['unchanged_file_sha256']),
        'unchanged_native_tested_code_inputs':native_code,'native_export_files_verified':len(native_hashes),
        'native_release_builds':3,'archived_checks_each':{'runtime':2551,'cli':497},
        'six_exact_recommendation_functional_results':exact,'no_new_cpp_build_or_sanitizer_claimed':True,
        'continuous_session_messages':len(messages),'session_last_message_timestamp':prompt['last_message_timestamp'],
        'local_links_checked':links,'prior_packages_unchanged':True,'external_submission_sent':False,
        'upstream_check_scope':'last verified 2026-10-25; no new network claim',
        'deferred_items':[{'item':'DevContainer actual build','status':'deferred_by_user_no_available_engine'}],
        'limitations':['original temporary binary image attachments unavailable; persisted text preserved',
            'WSL1 physical placement and dynamic cache-loss causality unproven',
            'user personal understanding is not validated by automated checks']}
    lab.write(root/args.out,result)
    print(json.dumps({'audit':args.out,'audit_pass':True,'local_delivery_complete':True,
        'files_verified':len(manifest['files']),'report_cited_runs':663,'session_messages':len(messages),
        'links_checked':links,'container_actual_build_verified':False},ensure_ascii=False))


if __name__=='__main__':main()
