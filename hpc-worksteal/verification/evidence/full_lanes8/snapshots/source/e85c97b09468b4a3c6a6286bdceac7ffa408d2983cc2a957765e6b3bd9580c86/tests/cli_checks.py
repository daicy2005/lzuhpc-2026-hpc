#!/usr/bin/env python3
import copy,json,pathlib,subprocess,sys,tempfile
MASK=(1<<64)-1
def mix(x):
 x=((x^(x>>30))*0xbf58476d1ce4e5b9)&MASK;x=((x^(x>>27))*0x94d049bb133111eb)&MASK;return x^(x>>31)
def main():
 exe=sys.argv[1];extension=sys.argv[2];base=json.loads((pathlib.Path(__file__).parents[1]/'configs/runtime/diagnostic.json').read_text())
 base['workload']['elements']=17;base['workload']['iterations']=3;base['policies']['partition']['grain']=5;base['measurement']['epochs']=3
 base['policies']['affinity']={'name':'unbound'}
 with tempfile.TemporaryDirectory(prefix='ws-cli-') as d:
  path=pathlib.Path(d)/'config.json';checks=0
  def run(config,code=0,exe=exe,flags=()):
   nonlocal checks
   path.write_text(json.dumps(config));p=subprocess.run([exe,'--config',str(path),*flags],capture_output=True,text=True,timeout=15)
   assert p.returncode==code,(p.returncode,p.stderr);checks+=1
   return json.loads(p.stdout) if code==0 else None
  golden=[]
  for i in range(17):
   x=mix(42^((i*0x9e3779b97f4a7c15)&MASK))
   for j in range(3*(9 if i<17//8 else 1)):x=mix((x+j+(x<<1))&MASK)
   golden.append(x)
  h=14695981039346656037
  for x in golden:
   for b in x.to_bytes(8,'little'):h=((h^b)*1099511628211)&MASK
  expected=f'{h:016x}'
  for executor in ('serial','static','central','worksteal'):
   for n in (0,1,2,17):
    j=copy.deepcopy(base);j['executor']=executor;j['workers']=1 if executor=='serial' else 4;j['workload']['elements']=n
    r=run(j);assert r['correctness']['pass'];assert len(r['epochs'])==3
    if n==17:assert all(x['correctness']['output_hash_fnv1a64']==expected for x in r['epochs'])
    if executor!='serial':assert all(x['correctness']['exact_once'] for x in r['epochs'])
    for epoch in r['epochs']:
     assert sum(epoch['execution']['worker_cost_units'])==epoch['identity']['total_cost_units']
     assert sum(epoch['execution']['worker_elements'])==n
  for field,value in [('workers',0),('workers',-1),('executor','unknown'),('unexpected',True)]:
   j=copy.deepcopy(base);j[field]=value;run(j,2);run(j,2,flags=('--validate-config',))
  for section,field,value in [('partition','grain',0),('partition','name','unknown'),('migration','cap',0),('victim','unexpected',1)]:
   j=copy.deepcopy(base);j['policies'][section][field]=value
   if section=='migration':j['policies'][section]['name']='capped_half'
   run(j,2)
  j=copy.deepcopy(base);j['policies']['affinity']={'name':'explicit','cpus':[0,0,1,2]};run(j,2)
  j=copy.deepcopy(base);j['steal_enabled']=False;run(j,2)
  j=copy.deepcopy(base);j['measurement']['throw_task']=0;run(j,3)
  j=copy.deepcopy(base);j['policies']['victim']['name']='test_reverse';r=run(j,exe=extension);assert r['correctness']['pass']
  # Force the 4/8-lane paths, skew boundaries and tails against a separate
  # Python recurrence (the original grain5 golden did not exercise lane8).
  for name in ('compute_uniform','compute_skewed'):
   for n in (7,8,9,31,64,65):
    h=14695981039346656037
    for i in range(n):
     x=mix(42^((i*0x9e3779b97f4a7c15)&MASK))
     for step in range(3*(9 if name=='compute_skewed' and i<n//8 else 1)):
      x=mix((x+step+(x<<1))&MASK)
     for byte in x.to_bytes(8,'little'):h=((h^byte)*1099511628211)&MASK
    for grain in (1,7,8,17,128):
     j=copy.deepcopy(base);j['workload'].update(name=name,elements=n);j['policies']['partition']['grain']=grain
     j['measurement']={'mode':'timing','epochs':2};r=run(j)
     assert all(e['correctness']['output_hash_fnv1a64']==f'{h:016x}' for e in r['epochs'])
  for executor in ('static','central','worksteal'):
   hashes=[]
   for target in (0,1):
    j=copy.deepcopy(base);j['executor']=executor;j['workload'].update(name='memory_reuse',elements=1,bytes_per_element=1024,passes=2)
    j['measurement'].update(home_worker=0,controlled_worker=target)
    r=run(j)
    assert all(x['execution']['task_executor']==[target] for x in r['epochs'])
    hashes.append(r['epochs'][0]['pretouch_hash_fnv1a64'])
   assert hashes[0]==hashes[1]
  # Independent Python oracle on the real parallel reference path, not just
  # comparing two C++ implementations that could share the same mistake.
  for name in ('compute_uniform','compute_skewed','memory_reuse'):
   for n in ((17,) if name=='memory_reuse' else (0,1,257,513)):
    h=14695981039346656037
    for i in range(n):
     x=mix(42^((i*0x9e3779b97f4a7c15)&MASK))
     if name=='memory_reuse':
      for r in range(2):
       for word in range(16):x=(((x+mix(42+i*16+word)+r)&MASK)^(x>>7))&MASK
     else:
      for step in range(3*(9 if name=='compute_skewed' and i<n//8 else 1)):x=mix((x+step+(x<<1))&MASK)
     for byte in x.to_bytes(8,'little'):h=((h^byte)*1099511628211)&MASK
    for workers in (1,4,16):
     j=copy.deepcopy(base);j['workload'].update(name=name,elements=n,bytes_per_element=128,passes=2)
     j['measurement']={'mode':'timing','epochs':2,'reference_workers':workers};r=run(j)
     for epoch in r['epochs']:
      c=epoch['correctness'];tile=1 if name=='memory_reuse' else 256
      assert c['pass'] and c['compared_elements']==n and c['mismatches']==0
      assert c['output_hash_fnv1a64']==f'{h:016x}'
      assert c['reference_workers_used']==min(workers,(n+tile-1)//tile)
      assert c['reference_tile_elements']==tile
     assert all(v>=0 for v in r['phase_seconds'].values())
     assert sum(r['phase_seconds'].values())<=r['timing']['end_to_end_seconds']+1e-9
   for invalid in (0,-1,129,1.5,True,'4'):
    j=copy.deepcopy(base);j['measurement']['reference_workers']=invalid
    run(j,2);run(j,2,flags=('--validate-config',))
  print(json.dumps({'status':'pass','checks':checks,'golden_output_hash':expected}))
if __name__=='__main__':main()
