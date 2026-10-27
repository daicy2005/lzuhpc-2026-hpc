#!/usr/bin/env python3
"""Run a frozen, small W00/W01 matrix and retain every raw process result."""
import argparse, datetime as dt, hashlib, json, os, pathlib, platform, subprocess, sys, time

def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--exe',required=True); ap.add_argument('--out',required=True)
    ap.add_argument('--n',type=int,default=262144); ap.add_argument('--k',type=int,default=64); ap.add_argument('--workers',default='1,4')
    ap.add_argument('--repeat',type=int,default=3); ap.add_argument('--timeout',type=float,default=30); ap.add_argument('--smoke',action='store_true')
    a=ap.parse_args(); exe=pathlib.Path(a.exe).resolve(); out=pathlib.Path(a.out).resolve(); out.mkdir(parents=True,exist_ok=True)
    ws=[int(x) for x in a.workers.split(',')]; grains=[1,64,4096] if not a.smoke else [1,64]
    modes=['static','central','steal-off','steal-on']
    batch=dt.datetime.now(dt.timezone.utc).strftime('batch-%Y%m%dT%H%M%SZ')
    batchdir=out/batch; batchdir.mkdir()
    conditions=[{'id':'S0','executor':'serial','workers':1,'grain':1}]
    for m in modes:
        for p in ws:
            for g in grains: conditions.append({'id':f'{m}-p{p}-g{g}','executor':m,'workers':p,'grain':g})
    plan={'schema_version':1,'batch_id':batch,'purpose':'W01_timing','status':'running','seed':42,'n':a.n,'k':a.k,'workers':ws,'grains':grains,'conditions':conditions,'repeat':a.repeat,'source_sha256':sha(exe)}
    (batchdir/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    records=[]
    # Fixed interleaving: each block follows a deterministic rotation, saved above through execution_order.
    order=[]
    for r in range(a.repeat):
        block=conditions[r%len(conditions):]+conditions[:r%len(conditions)]
        order.extend((r,c['id']) for c in block)
    (batchdir/'execution_order.json').write_text(json.dumps(order,indent=2)+'\n')
    for index,(rep,cid) in enumerate(order):
        c=next(x for x in conditions if x['id']==cid)
        config={'schema_version':1,'executor':('worksteal' if c['executor'].startswith('steal') else c['executor']),
                'workers':c['workers'],'workload':{'name':'compute_uniform','elements':a.n,'iterations':a.k,'seed':42},
                'policies':{'partition':{'name':'fixed_grain','grain':c['grain']},'victim':{'name':'round_robin'},
                  'steal_timing':{'name':'disabled' if c['executor'] in ('steal-off','serial') else 'immediate'},'migration':{'name':'single'},
                  'affinity':{'name':'explicit','cpus':list(range(c['workers']))},'placement':{'name':'round_robin'}},
                'layout':'policy','layout_seed':42,'measurement':{'mode':'timing','epochs':1}}
        if c['executor']=='serial': config['executor']='serial'; config['steal_enabled']=False
        rid=f'{index:04d}-{cid}-r{rep+1}'; rd=batchdir/rid; rd.mkdir()
        (rd/'config.json').write_text(json.dumps(config,indent=2)+'\n')
        cmd=[str(exe),'--config',str(rd/'config.json'),'--output',str(rd/'result.json')]
        (rd/'command.txt').write_text(' '.join(cmd)+'\n')
        t0=time.monotonic(); status='completed'; reason=None; rc=None
        try:
            p=subprocess.run(cmd,capture_output=True,text=True,timeout=a.timeout)
            rc=p.returncode;(rd/'stdout.log').write_text(p.stdout);(rd/'stderr.log').write_text(p.stderr)
            if rc!=0: status='failed';reason=f'exit_{rc}'
        except subprocess.TimeoutExpired as e:
            status='timeout';reason='process_timeout';(rd/'stdout.log').write_text(e.stdout or '');(rd/'stderr.log').write_text(e.stderr or '')
        rec={'run_id':rid,'condition':cid,'repeat':rep+1,'status':status,'reason':reason,'exit_code':rc,
             'wall_seconds':time.monotonic()-t0,'executable_sha256':plan['source_sha256']}
        result=rd/'result.json'
        if result.exists():
            try:
                rj=json.loads(result.read_text());rec['correct']=rj.get('correctness',{}).get('pass');rec['epoch_seconds']=rj.get('timing',{}).get('epoch_seconds');rec['end_to_end_seconds']=rj.get('timing',{}).get('end_to_end_seconds')
            except Exception as e: rec['parse_error']=str(e);status='failed';rec['status']=status
        (rd/'metadata.json').write_text(json.dumps(rec,indent=2)+'\n');records.append(rec)
        if status!='completed' or rec.get('correct') is not True:
            plan['status']='failed';plan['failure_at']=rid;break
        if index%8==0: print(json.dumps(rec),flush=True)
    if plan['status']=='running':plan['status']='completed'
    (batchdir/'records.json').write_text(json.dumps(records,indent=2)+'\n');(batchdir/'plan.json').write_text(json.dumps(plan,indent=2)+'\n')
    print(json.dumps({'batch':batch,'status':plan['status'],'runs':len(records),'directory':str(batchdir)}))
    return 0 if plan['status']=='completed' else 1

if __name__=='__main__': sys.exit(main())
