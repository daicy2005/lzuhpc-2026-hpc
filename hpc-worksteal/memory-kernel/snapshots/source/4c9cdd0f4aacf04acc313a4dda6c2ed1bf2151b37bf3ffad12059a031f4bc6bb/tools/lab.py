#!/usr/bin/env python3
"""Frozen plans, immutable process records, source snapshots and verified export."""
import argparse, copy, datetime as dt, hashlib, json, os, pathlib, random, shutil
import statistics, subprocess, sys, time, uuid

ROOT = pathlib.Path(__file__).resolve().parents[1]
def now(): return dt.datetime.now(dt.timezone.utc).isoformat()
def digest(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def write(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,'x',encoding='utf-8') as f:json.dump(data,f,ensure_ascii=False,indent=2);f.write('\n')
def source_files():
    for folder in ('include','src','tests','tools','configs','docs','reference','.devcontainer'):
        for f in sorted((ROOT/folder).rglob('*')):
            if f.is_file() and '__pycache__' not in f.parts:yield f
    for name in ('CMakeLists.txt','CMakePresets.json','README.md','AGENTS.md','.gitignore','report/requirements.txt'):
        yield ROOT/name
def snapshot():
    files={str(f.relative_to(ROOT)):digest(f) for f in source_files()}
    identifier=hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest()
    directory=ROOT/'snapshots'/'source'/identifier
    if not directory.exists():
        directory.mkdir(parents=True)
        for name in files:
            dst=directory/name;dst.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,dst)
        write(directory/'manifest.json',{'source_id':identifier,'files':files,'created':now()})
    return identifier
def seal(directory):
    files={str(f.relative_to(directory)):digest(f) for f in sorted(directory.rglob('*')) if f.is_file() and f.name!='checksums.json'}
    write(directory/'checksums.json',files)
def environment(exe):
    def command(args):
        p=subprocess.run(args,capture_output=True,text=True,timeout=15);return {'command':args,'exit_code':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    probe=command([str(exe.parent/'host_probe')]);probe['parsed']=json.loads(probe['stdout']) if probe['exit_code']==0 else None
    return {'time':now(),'uname':command(['uname','-a']),'compiler':command(['c++','--version']),
            'cmake':command(['cmake','--version']),'lscpu':command(['lscpu']),
            'processes':command(['ps','-eo','pid,comm,args']),
            'meminfo':pathlib.Path('/proc/meminfo').read_text(),
            'allowed':sorted(os.sched_getaffinity(0)),'cpuid':probe,
            'affinity_limit':'WSL1 singleton masks are verified, but CPUID APIC IDs were not stable per logical mask; physical placement is unproven',
            'cache_limit':'CPUID leaf4 reports 36 MiB LLC; Windows CIM corroborated total, per-worker sharing/mapping unproven'}
class Batch:
    def __init__(self,name,plan,exe,budget=900):
        self.exe=exe.resolve();self.identifier=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')+'-'+name+'-'+uuid.uuid4().hex[:6]
        self.path=ROOT/'runs'/self.identifier;self.path.mkdir(parents=True)
        self.source=snapshot();self.start=time.monotonic();self.budget=budget;self.records=[];self.binary=digest(exe)
        write(self.path/'plan.json',{'batch_id':self.identifier,'created':now(),'source_id':self.source,'binary_sha256':self.binary,'budget_seconds':budget,**plan})
        write(self.path/'environment.json',environment(exe))
        build_logs=exe.parent/'validation.json'
        if build_logs.exists():shutil.copy2(build_logs,self.path/'validation.json')
    def run(self,config,condition,purpose,rep=0,timeout=30,expected=0):
        remaining=self.budget-(time.monotonic()-self.start)
        if remaining<=0:raise RuntimeError('batch_budget_exhausted')
        rid=f'{len(self.records):04d}-{purpose}-{condition}-r{rep}-{uuid.uuid4().hex[:6]}'
        rd=self.path/rid;rd.mkdir();write(rd/'config.json',config)
        cmd=[str(self.exe),'--config',str(rd/'config.json'),'--output',str(rd/'result.json')]
        (rd/'command.txt').write_text(json.dumps({'cwd':str(ROOT),'argv':cmd,'explicit_environment':{}},indent=2)+'\n')
        before=now();t0=time.monotonic();reason=None;returncode=None;out=b'';err=b''
        try:
            p=subprocess.run(cmd,cwd=ROOT,capture_output=True,timeout=min(timeout,remaining));returncode=p.returncode;out=p.stdout;err=p.stderr
            if returncode!=expected:reason=f'exit_{returncode}_expected_{expected}'
        except subprocess.TimeoutExpired as e:out=e.stdout or b'';err=e.stderr or b'';reason='timeout'
        (rd/'stdout.log').write_bytes(out);(rd/'stderr.log').write_bytes(err)
        result=None
        if (rd/'result.json').exists():
            try:result=json.loads((rd/'result.json').read_text())
            except Exception as e:reason=f'invalid_json:{e}'
        if expected==0 and (not result or result.get('correctness',{}).get('pass') is not True):reason=reason or 'incorrect_or_missing'
        record={'run_id':rid,'batch_id':self.identifier,'condition':condition,'purpose':purpose,'repeat':rep,'started':before,'ended':now(),
                'elapsed_process_seconds':time.monotonic()-t0,'exit_code':returncode,'expected_exit':expected,'status':'completed' if reason is None else 'failed',
                'failure_reason':reason,'source_id':self.source,'binary_sha256':self.binary,'collector_sha256':digest(pathlib.Path(__file__)),
                'environment_ref':'../environment.json','correctness':result.get('correctness') if result else None,
                'timing':result.get('timing') if result else None,'included':reason is None and purpose=='timing'}
        write(rd/'metadata.json',record);seal(rd);self.records.append(record)
        if reason is not None:raise RuntimeError(f'{rid}: {reason}')
        print(json.dumps({'run':rid,'epoch':record['timing']['epoch_seconds'] if record['timing'] else None,'status':record['status']}),flush=True)
        return result
    def finish(self,status='completed',reason=None):
        write(self.path/'records.json',self.records);write(self.path/'completion.json',{'status':status,'reason':reason,'elapsed_seconds':time.monotonic()-self.start,'ended':now(),'processes':len(self.records)})
        seal(self.path);return self.path

def config(executor='worksteal',p=4,grain=64,k=256,n=262144,seed=42,workload='compute_uniform',**kw):
    off=executor in ('off','serial');actual='worksteal' if executor in ('off','on') else executor
    j={'schema_version':1,'executor':actual,'workers':p,'workload':{'name':workload,'elements':n,'iterations':k,'seed':seed},
       'policies':{'partition':{'name':'fixed_grain','grain':grain},'victim':{'name':'round_robin'},'steal_timing':{'name':'disabled' if off else 'immediate'},
                   'migration':{'name':'single'},'affinity':{'name':'explicit','cpus':list(range(p))},'placement':{'name':'round_robin'}},
       'measurement':{'mode':'timing','epochs':1},'layout':'policy','layout_seed':seed}
    for key,value in kw.items():j[key]=value
    return j

def validate_build(args):
    exe=pathlib.Path(args.exe).resolve();bd=exe.parent;source=snapshot();records=[]
    for command in ([str(bd/'runtime_checks')],[sys.executable,str(ROOT/'tests/cli_checks.py'),str(exe),str(bd/'worksteal_extension')]):
        p=subprocess.run(command,capture_output=True,text=True,timeout=120)
        records.append({'command':command,'returncode':p.returncode,'stdout':p.stdout,'stderr':p.stderr})
        if p.returncode!=0:break
    path=bd/'validation.json'
    if path.exists():raise RuntimeError('validation already recorded; use new build directory')
    write(path,{'source_id':source,'binary_sha256':digest(exe),'records':records,'pass':all(x['returncode']==0 for x in records),'created':now()})
    artifact=ROOT/'snapshots'/'builds'/digest(exe)
    if not artifact.exists():
        artifact.mkdir(parents=True)
        for name in ('worksteal','worksteal_extension','runtime_checks','host_probe','validation.json','build.json','build-0.log','build-1.log','CMakeCache.txt'):
            if (bd/name).exists():shutil.copy2(bd/name,artifact/name)
        seal(artifact)
    if not all(x['returncode']==0 for x in records):raise RuntimeError('validation failed')
    print(json.dumps({'validation':str(path),'status':'pass'}))

def first(args):
    exe=pathlib.Path(args.exe).resolve();validation=json.loads((exe.parent/'validation.json').read_text())
    if not validation['pass'] or validation['binary_sha256']!=digest(exe):raise RuntimeError('unvalidated binary')
    p0=min(4,len(os.sched_getaffinity(0)));seed=20261015
    conditions=[('S0',config('serial',1,262144))]
    for m in ('static','central','off','on'):
        for p in sorted(set((1,p0))):
            for g in (1,64,4096):conditions.append((f'{m}-p{p}-g{g}',config(m,p,g)))
    rng=random.Random(seed);base=list(range(len(conditions)));rng.shuffle(base)
    blocks=[('warmup',0,base)]+[('timing',r+1,base[(r*len(base)//3):]+base[:(r*len(base)//3)]) for r in range(3)]
    plan={'experiment':'W00_W01','logical_cpu_pilot':True,'calibration_candidates':[64,256,1024],'calibration_target':[.2,1.0],
          'conditions':[{'id':cid,'config':c} for cid,c in conditions], 'order':[(purpose,rep,conditions[i][0]) for purpose,rep,b in blocks for i in b],
          'note':'condition iterations replaced only with first qualifying serial calibration; no candidate-specific changes; three blocks distribute positions without exact complete balance'}
    batch=Batch('W00-W01',plan,exe)
    try:
        # Twenty integration processes: all five modes on zero, singleton, tail, and grain>N cases.
        for m in ('serial','static','central','off','on'):
            for n,g in ((0,1),(1,1),(3,64),(31,7)):
                c=config(m,1 if m=='serial' else p0,g,2,n);c['measurement']={'mode':'diagnostic','epochs':3,'pause_seed':73}
                batch.run(c,f'W00-{m}-n{n}-g{g}','development',timeout=10)
        selected=None
        for k in (64,256,1024):
            result=batch.run(config('serial',1,262144,k),'calibration-K'+str(k),'development')
            t=result['timing']['epoch_seconds']
            if .2<=t<=1:selected=k;break
            if t>1:break
        if selected is None:raise RuntimeError('calibration_range_inapplicable')
        write(batch.path/'calibration_selection.json',{'selected_k':selected,'rule':'first correct S0 epoch in [0.2,1.0]','frozen':now()})
        for purpose,rep,b in blocks:
            for i in b:
                cid,c=conditions[i];c=copy.deepcopy(c);c['workload']['iterations']=selected;batch.run(c,cid,purpose,rep)
        for m in ('off','on'):
            for g in (1,4096):
                c=config(m,p0,g,selected);c['measurement']['mode']='diagnostic';batch.run(c,f'diag-{m}-p{p0}-g{g}','diagnostic')
        path=batch.finish()
    except Exception as e:batch.finish('failed',str(e));raise
    print(json.dumps({'batch':str(path),'status':'completed'}))

def export(args):
    target=pathlib.Path(args.target).resolve();target.mkdir(parents=True,exist_ok=True)
    folders=('runs','snapshots','results')
    entries={}
    for folder in folders:
        for f in sorted((ROOT/folder).rglob('*')):
            if not f.is_file():continue
            relative=f.relative_to(ROOT);dest=target/relative;h=digest(f)
            if dest.exists() and digest(dest)!=h:raise RuntimeError('refuse different existing export '+str(dest))
            if not dest.exists():dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(f,dest)
            if digest(dest)!=h:raise RuntimeError('export hash mismatch')
            entries[str(relative)]=h
    stamp=dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    write(target/'results'/('export-'+stamp+'.json'),{'source_root':str(ROOT),'target':str(target),'time':now(),'files':entries})
    print(json.dumps({'exported_files':len(entries),'target':str(target)}))

def main():
    ap=argparse.ArgumentParser();sub=ap.add_subparsers(dest='action',required=True)
    v=sub.add_parser('validate');v.add_argument('--exe',required=True)
    f=sub.add_parser('first');f.add_argument('--exe',required=True)
    e=sub.add_parser('export');e.add_argument('--target',required=True)
    sub.add_parser('snapshot')
    a=ap.parse_args();{'validate':validate_build,'first':first,'export':export,'snapshot':lambda _:print(json.dumps({'source_id':snapshot()}))}[a.action](a)
if __name__=='__main__':main()
