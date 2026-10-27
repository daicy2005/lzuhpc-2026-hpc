#!/usr/bin/env python3
"""Materialize evidence-selected configs, exercise them, and audit archived builds."""
import argparse, hashlib, json, pathlib, sys

def load(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def recommend(root):
    summary=load(root/'results/study-summary.json');assert summary['complete']
    screen=summary['batches']['W04'];conditions={c['id']:c['config'] for c in screen['plan']['conditions']}
    output={}
    for kind,decision in summary['selection'].items():
        name=kind+'--'+decision['selected'];config=conditions[name]
        dest=root/'configs/recommended'/f'{kind}.json';save(dest,config)
        output[kind]={'config':str(dest.relative_to(root)), 'config_sha256':sha(dest),
                      'screen_group':name,'decision':decision}
    save(root/'results/selection.json',{'scope':'predeclared steal-on candidates; retain default unless both held-out inputs pass',
        'summary_sha256':sha(root/'results/study-summary.json'),'recommended':output})
    print(json.dumps({'recommended':list(output)},ensure_ascii=False))

def check(root,lab_root,exe):
    sys.path.insert(0,str(lab_root/'tools'))
    from lab import Batch,digest
    v=load(exe.parent/'validation.json');assert v['pass'] and v['binary_sha256']==digest(exe)
    cases=[{'id':k,'config':load(root/'configs/recommended'/f'{k}.json')} for k in ('uniform','skewed','memory')]
    batch=Batch('recommendation-check',{'experiment':'recommendation-check','conditions':[], 'order':[],
        'checks':cases,'purpose':'exercise exact recommended configs; not selection samples'},exe,budget=120)
    try:
        for c in cases:batch.run(c['config'],c['id'],'development',timeout=60)
        path=batch.finish()
    except Exception as e:batch.finish('failed',str(e));raise
    print(json.dumps({'batch':str(path),'status':'completed'}))

def audit(root):
    manifests=0;files=0;validations=[]
    for base in [root]+sorted((root/'evidence').iterdir()):
        if not base.is_dir():continue
        for manifest in (base/'snapshots/source').glob('*/manifest.json'):
            m=load(manifest);assert manifest.parent.name==m['source_id']
            for name,expected in m['files'].items():assert sha(manifest.parent/name)==expected
            manifests+=1;files+=len(m['files'])
        for manifest in (base/'snapshots/builds').glob('*/checksums.json'):
            m=load(manifest)
            for name,expected in m.items():assert sha(manifest.parent/name)==expected
            v=load(manifest.parent/'validation.json')
            assert sha(manifest.parent/'worksteal')==v['binary_sha256']==manifest.parent.name
            validations.append({'path':str(manifest.parent.relative_to(root)), 'pass':v['pass'],
                                'source_id':v['source_id'],'binary_sha256':v['binary_sha256'],
                                'returncodes':[r['returncode'] for r in v['records']]})
            manifests+=1;files+=len(m)
        for manifest in (base/'results').glob('export-*.json'):
            m=load(manifest)
            for name,expected in m['files'].items():assert sha(base/name)==expected
            manifests+=1;files+=len(m['files'])
    summary=load(root/'results/study-summary.json');v3=summary['batches']['W05-confirm']['plan']['binary_sha256']
    build=root/'snapshots/builds'/v3;validation=load(build/'validation.json')
    snapshot=root/'snapshots/source'/validation['source_id'];production={}
    for folder in ('src','include','tests'):
        for path in sorted((root/folder).rglob('*')):
            if not path.is_file() or '__pycache__' in path.parts or path.name.endswith('.md'):continue
            rel=path.relative_to(root);assert sha(path)==sha(snapshot/rel),'production drift: '+str(rel)
            production[str(rel)]=sha(path)
    assert sha(root/'CMakeLists.txt')==sha(snapshot/'CMakeLists.txt')
    cmake=(root/'CMakeLists.txt').read_text(encoding='utf-8')
    assert 'ws_core' in cmake and 'tests/register_reverse.cpp' in cmake
    assert 'test_reverse' in (root/'tests/cli_checks.py').read_text(encoding='utf-8')
    selected=load(root/'results/selection.json')
    for c in selected['recommended'].values():assert sha(root/c['config'])==c['config_sha256']
    result={'pass':True,'verified_manifests':manifests,'file_hash_checks':files,
        'validations':validations,'production_matches_validated_v3':True,'production_files':production,
        'extension_evidence':{'core_target':'ws_core','registration':'tests/register_reverse.cpp',
            'check':'tests/cli_checks.py test_reverse execution','validation':str((build/'validation.json').relative_to(root))},
        'scope':'archive, build validation and production-source identity; not physical-affinity or statistical proof'}
    save(root/'results/closeout-audit.json',result)
    print(json.dumps({k:result[k] for k in ('pass','verified_manifests','file_hash_checks','production_matches_validated_v3')},indent=2))

def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('recommend','check','audit'));p.add_argument('--root',required=True)
    p.add_argument('--lab-root');p.add_argument('--exe');a=p.parse_args();root=pathlib.Path(a.root).resolve()
    if a.action=='recommend':recommend(root)
    elif a.action=='audit':audit(root)
    else:check(root,pathlib.Path(a.lab_root),pathlib.Path(a.exe))
if __name__=='__main__':main()
