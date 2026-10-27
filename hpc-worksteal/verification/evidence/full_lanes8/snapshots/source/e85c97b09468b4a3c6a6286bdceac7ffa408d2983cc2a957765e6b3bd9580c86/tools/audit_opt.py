#!/usr/bin/env python3
"""Verify optimization archives and execute the exact recommended configurations."""
import argparse, datetime as dt, hashlib, json, pathlib, subprocess, sys, uuid

def read(p):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,j):
    p.parent.mkdir(parents=True,exist_ok=True)
    with p.open('x',encoding='utf-8') as f:json.dump(j,f,ensure_ascii=False,indent=2);f.write('\n')
def checks(root,lab_root):
    manifest=read(root/'configs/optimized/builds.json');summary=read(root/'optimization/results/optimization-summary.json')
    versions=summary['batches']['OPT3-heldout']['plan']['builds']
    dest=lab_root/'results'/('recommendation-check-'+dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]);dest.mkdir(parents=True)
    records=[];cli_records={}
    for kind,info in manifest.items():
        build=versions[info['build']];exe=pathlib.Path(build['exe']);assert sha(exe)==info['binary_sha256']
        config_path=root/info['config'];assert sha(config_path)==info['config_sha256'];d=dest/kind;d.mkdir()
        config=read(config_path);(d/'config.json').write_bytes(config_path.read_bytes())
        command=[str(exe),'--config',str(d/'config.json'),'--output',str(d/'result.json')];write(d/'command.json',{'argv':command,'cwd':str(lab_root),'build':info})
        p=subprocess.run(command,capture_output=True,cwd=lab_root,timeout=90)
        (d/'stdout.log').write_bytes(p.stdout);(d/'stderr.log').write_bytes(p.stderr)
        assert p.returncode==0;res=read(d/'result.json');assert res['correctness']['pass']
        r={'kind':kind,'pass':True,'binary_sha256':sha(exe),'config_sha256':sha(d/'config.json'),'epoch_seconds':res['timing']['epoch_seconds']};write(d/'metadata.json',r);records.append(r)
        print(json.dumps(r),flush=True)
        if info['build'] not in cli_records:
            command=[sys.executable,str(root/'tests/cli_checks.py'),str(exe),str(exe.parent/'worksteal_extension')]
            checked=subprocess.run(command,capture_output=True,text=True,timeout=120)
            cli_records[info['build']]={'argv':command,'returncode':checked.returncode,'stdout':checked.stdout,'stderr':checked.stderr,
                'test_sha256':sha(root/'tests/cli_checks.py'),'binary_sha256':sha(exe)}
            write(dest/('release-cli-'+info['build']+'.json'),cli_records[info['build']]);assert checked.returncode==0
    write(dest/'completion.json',{'pass':True,'processes':len(records),'records':records})
    write(dest/'checksums.json',{str(p.relative_to(dest)):sha(p) for p in dest.rglob('*') if p.is_file()})
    print(json.dumps({'recommendation_checks':str(dest),'pass':True}))

def audit(root):
    bases=[root/'optimization']+sorted(p for p in (root/'evidence').iterdir() if p.name.startswith('opt-'))
    count=0;manifests=0;validations=[]
    for base in bases:
        for manifest in (base/'snapshots/source').glob('*/manifest.json'):
            m=read(manifest);assert m['source_id']==manifest.parent.name
            identifier=hashlib.sha256(json.dumps(m['files'],sort_keys=True).encode()).hexdigest();assert identifier==m['source_id']
            for name,h in m['files'].items():assert sha(manifest.parent/name)==h;count+=1
            manifests+=1
        for manifest in (base/'snapshots/builds').glob('*/checksums.json'):
            m=read(manifest)
            for name,h in m.items():assert sha(manifest.parent/name)==h;count+=1
            v=read(manifest.parent/'validation.json');assert v['pass'];assert sha(manifest.parent/'worksteal')==v['binary_sha256']==manifest.parent.name
            checks=json.loads(v['records'][0]['stdout'])['checks']
            validations.append({'name':'baseline' if base.name=='optimization' else base.name[4:],'pass':v['pass'],'runtime_checks':checks,
                'binary_sha256':v['binary_sha256'],'source_id':v['source_id'],'path':str(manifest.parent.relative_to(root))})
            manifests+=1
        for manifest in (base/'results').glob('export-*.json'):
            m=read(manifest)
            for name,h in m['files'].items():assert sha(base/name)==h;count+=1
            manifests+=1
    summary=read(root/'optimization/results/optimization-summary.json');assert summary['complete']
    versions=summary['batches']['OPT3-heldout']['plan']['builds']
    for name,b in versions.items():
        assert any(v['binary_sha256']==b['binary_sha256'] and v['source_id']==b['source_id'] for v in validations)
    # Feature-complete canonical source, rather than the previous round's v3.
    canonical=next(v for v in validations if v['name']=='full_lanes8-asan')
    snapshot=root/'evidence/opt-full_lanes8-asan/snapshots/source'/canonical['source_id'];production={}
    for folder in ('src','include','tests'):
        for path in (root/folder).rglob('*'):
            if not path.is_file() or path.suffix=='.md' or '__pycache__' in path.parts:continue
            rel=path.relative_to(root);assert sha(path)==sha(snapshot/rel),'production drift: '+str(rel);production[str(rel)]=sha(path)
    assert sha(root/'CMakeLists.txt')==sha(snapshot/'CMakeLists.txt')
    checks_dirs=sorted((root/'optimization/results').glob('recommendation-check-*'));assert len(checks_dirs)==1
    check_dir=checks_dirs[0];done=read(check_dir/'completion.json');assert done['pass'] and done['processes']==4
    for name,h in read(check_dir/'checksums.json').items():assert sha(check_dir/name)==h;count+=1
    recommended=read(root/'configs/optimized/builds.json')
    presets={c['name']:c for c in read(root/'CMakePresets.json')['configurePresets']}
    for kind,info in recommended.items():
        assert sha(root/info['config'])==info['config_sha256']
        meta=read(check_dir/kind/'metadata.json');assert meta['pass'] and meta['binary_sha256']==info['binary_sha256']
        assert meta['config_sha256']==sha(check_dir/kind/'config.json')
        # Initial check records reserialized CRLF input as LF. Preserve sealed
        # bytes and verify JSON equivalence rather than rewriting those records.
        assert read(check_dir/kind/'config.json')==read(root/info['config'])
        d=summary['selection'][kind];wanted=d['screening_candidate']['build'] if d['accepted'] else 'baseline'
        assert info['build']==wanted
        preset=presets[{'light':'optimized-light','uniform':'optimized-uniform','skewed':'optimized-skewed','memory':'optimized-skewed'}[kind]]
        flags={s[2:].split('=',1)[0]:s.split('=',1)[1] for s in info['cmake_options']}
        for flag in ('CMAKE_BUILD_TYPE','WS_COMPLETION_BATCH','WS_STEAL_SCRATCH','WS_ENABLE_IPO'):
            assert preset['cacheVariables'][flag]==flags[flag]
        assert preset['cacheVariables']['WS_COMPUTE_LANES']==flags.get('WS_COMPUTE_LANES','1')
        independent=read(check_dir/('release-cli-'+info['build']+'.json'));assert independent['returncode']==0
        assert independent['test_sha256']==sha(root/'tests/cli_checks.py') and independent['binary_sha256']==info['binary_sha256']
        # Sanitizer evidence for every selected source/compile feature combination.
        if d['accepted']:
            for sanitizer in ('asan','tsan'):
                assert any(v['name']==wanted+'-'+sanitizer for v in validations),'missing selected sanitizer: '+wanted+'-'+sanitizer
    result={'pass':True,'manifests':manifests,'file_hash_checks':count,'validations':validations,'presets_match_measured_flags':True,
        'production_matches_feature_complete_source':True,'production_files':production,
        'recommendation_checks':str(check_dir.relative_to(root)), 'recommendation_processes':4,
        'limits':'source, archive and test evidence; not global optimum or physical-affinity proof'}
    output=root/'optimization/results/archive-audit.json';output.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'pass':True,'manifests':manifests,'file_hash_checks':count,'validations':len(validations),'recommendation_processes':4},indent=2))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--run-checks',action='store_true');ap.add_argument('--lab-root');a=ap.parse_args();root=pathlib.Path(a.root).resolve()
    if a.run_checks:checks(root,pathlib.Path(a.lab_root))
    else:audit(root)
if __name__=='__main__':main()
