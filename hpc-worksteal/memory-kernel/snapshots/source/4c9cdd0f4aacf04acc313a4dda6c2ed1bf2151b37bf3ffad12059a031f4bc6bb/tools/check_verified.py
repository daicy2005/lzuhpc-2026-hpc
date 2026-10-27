#!/usr/bin/env python3
"""Execute round-four delivered config bytes with their measured binaries."""
import argparse, datetime, json, pathlib, shutil, subprocess, uuid
from lab import digest, write, seal

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); a=ap.parse_args(); root=pathlib.Path(a.root).resolve()
    info=json.loads((root/'configs/verified/builds.json').read_text(encoding='utf-8'))
    prior=json.loads((root/'optimization/results/optimization-summary.json').read_text(encoding='utf-8'))
    target=root/'verification/results'/('recommendation-check-'+datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]); target.mkdir()
    records=[]
    for kind,b in info.items():
        exe=pathlib.Path('/root/lzuhpc-experiments')/('ws-20261016-verify-'+b['build'])/'build-none/worksteal'
        assert digest(exe)==b['binary_sha256'] and digest(root/b['config'])==b['config_sha256']
        d=target/kind; d.mkdir(); shutil.copy2(root/b['config'],d/'config.json')
        argv=[str(exe),'--config',str(d/'config.json'),'--output',str(d/'result.json')]
        p=subprocess.run(argv,capture_output=True,text=True,timeout=90)
        write(d/'command.json',{'argv':argv,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr}); assert p.returncode==0
        result=json.loads((d/'result.json').read_text()); assert result['correctness']['pass']
        cfg=json.loads((d/'config.json').read_text()); cfg['steal_enabled']=True
        assert result['resolved_config']==cfg and len(result['epochs'])==1
        old=next(g for g in prior['groups'] if g['stage']=='OPT1-build-screen' and g['kind']==kind and g['build']=='baseline')
        e=result['epochs'][0]; cr=e['correctness']; assert cr['output_hash_fnv1a64']==old['output_hash']
        for f in ('input_hash_fnv1a64','cost_hash_fnv1a64','data_hash_fnv1a64','total_cost_units'): assert e['identity'][f]==old['identity'][f]
        n=cfg['workload']['elements']; tile=1 if kind=='memory' else 256
        assert cr['pass'] and cr['compared_elements']==n and cr['mismatches']==0
        assert cr['reference_workers_used']==min(b['reference_workers'],(n+tile-1)//tile)
        records.append({'kind':kind,'config_sha256':digest(d/'config.json'),'binary_sha256':digest(exe),'reference_workers':b['reference_workers'], 'correct':True,'output_hash':old['output_hash']})
        seal(d)
    write(target/'summary.json',{'pass':True,'processes':4,'purpose':'delivery verification; excluded from selection','records':records}); seal(target)
    print(json.dumps({'pass':True,'processes':4,'directory':str(target)},ensure_ascii=False))

if __name__=='__main__': main()
