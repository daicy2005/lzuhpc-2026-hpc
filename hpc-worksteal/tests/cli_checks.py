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
  # Check every generated data word through an independent Python FNV oracle,
  # including seed+index uint64 wraparound and blocks uneven across workers.
  def fnv(values):
   h=14695981039346656037
   for value in values:
    for byte in value.to_bytes(8,'little'):h=((h^byte)*1099511628211)&MASK
   return f'{h:016x}'
  for seed in (42,MASK-2):
   for n in (0,1,3,9):
    identity=None;output=None;pretouch=None
    for count,allocation in ((c,a) for c in (1,2,4,8,128) for a in ('zeroed','overwrite')):
     j=copy.deepcopy(base);j['workload'].update(name='memory_reuse',elements=n,seed=seed,bytes_per_element=136,passes=2)
     j['measurement']={'mode':'timing','epochs':2,'reference_workers':4,'initialization_workers':count,'data_allocation':allocation}
     r=run(j);assert r['initialization']['workers_used']==min(count,n)
     assert r['initialization']['data_allocation_requested']==allocation
     assert r['initialization']['data_allocation_used']==(allocation if n else 'none')
     values=[];touch=[]
     for i in range(n):
      x=mix(seed^((i*0x9e3779b97f4a7c15)&MASK));words=[mix((seed+i*17+w)&MASK) for w in range(17)]
      touch.append(sum(words)&MASK)
      for step in range(2):
       for word in words:x=((x+word+step)&MASK)^(x>>7)
      values.append(x)
     for epoch in r['epochs']:
      assert epoch['identity']['data_hash_fnv1a64']==fnv(mix((seed+i)&MASK) for i in range(n*17))
      assert epoch['identity']['input_hash_fnv1a64']==fnv(mix(seed^((i*0x9e3779b97f4a7c15)&MASK)) for i in range(n))
      assert epoch['correctness']['output_hash_fnv1a64']==fnv(values)
      assert epoch['pretouch_hash_fnv1a64']==fnv(touch)
      if identity is None:
       identity=epoch['identity'];output=epoch['correctness']['output_hash_fnv1a64'];pretouch=epoch['pretouch_hash_fnv1a64']
      assert epoch['identity']==identity and epoch['correctness']['output_hash_fnv1a64']==output
      assert epoch['pretouch_hash_fnv1a64']==pretouch and epoch['correctness']['compared_elements']==n
  for invalid in (0,-1,129,1.5,True,'4'):
   j=copy.deepcopy(base);j['measurement']['initialization_workers']=invalid
   run(j,2);run(j,2,flags=('--validate-config',))
  for invalid in ('unknown','',1,True,None,[]):
   j=copy.deepcopy(base);j['measurement']['data_allocation']=invalid
   run(j,2);run(j,2,flags=('--validate-config',))
  for name in ('compute_uniform','compute_skewed'):
   j=copy.deepcopy(base);j['workload']['name']=name;j['measurement']['data_allocation']='overwrite'
   r=run(j);assert r['initialization']['data_allocation_used']=='none'
  for width,n in ((8,3),(8192,2)):
   for count in (1,4):
    for allocation in ('zeroed','overwrite'):
     j=copy.deepcopy(base);j['workload'].update(name='memory_reuse',elements=n,bytes_per_element=width,passes=2)
     j['measurement'].update(initialization_workers=count,data_allocation=allocation)
     r=run(j)
     assert all(e['identity']['data_hash_fnv1a64']==fnv(mix(42+i) for i in range(n*width//8)) for e in r['epochs'])
  # Independent memory oracle for lanes4, including tasks with scalar tails,
  # nonzero starts, wide/narrow blocks, uint64 wrap and repeated epochs.
  for width in (8,136,8192):
   for n in (0,1,3,4,5,9):
    seed=MASK-2;words=width//8;values=[];touch=[]
    for i in range(n):
     data=[mix((seed+i*words+w)&MASK) for w in range(words)]
     x=mix(seed^((i*0x9e3779b97f4a7c15)&MASK));touch.append(sum(data)&MASK)
     for step in range(3):
      for word in data:x=((x+word+step)&MASK)^(x>>7)
     values.append(x)
    for grain in (3,4,5,8):
     j=copy.deepcopy(base);j['workload'].update(name='memory_reuse',elements=n,seed=seed,bytes_per_element=width,passes=3)
     j['policies']['partition']['grain']=grain
     j['measurement']={'mode':'diagnostic','epochs':2,'memory_lanes':4,'reference_workers':4,'data_allocation':'overwrite' if grain%2 else 'zeroed'}
     r=run(j);assert r['execution_kernel']['memory_lanes_used']==(4 if n else 0)
     for e in r['epochs']:
      assert e['correctness']['output_hash_fnv1a64']==fnv(values)
      assert e['correctness']['exact_once'] and e['correctness']['compared_elements']==n
      assert e['pretouch_hash_fnv1a64']==fnv(touch)
      assert e['identity']['data_hash_fnv1a64']==fnv(mix((seed+w)&MASK) for w in range(n*words))
  for invalid in (0,-1,2,8,1.0,4.0,True,'4',None):
   j=copy.deepcopy(base);j['measurement']['memory_lanes']=invalid
   run(j,2);run(j,2,flags=('--validate-config',))
  for name in ('compute_uniform','compute_skewed'):
   j=copy.deepcopy(base);j['workload']['name']=name;j['measurement']['memory_lanes']=4
   r=run(j);assert r['execution_kernel']['memory_lanes_used']==0
  # Blocked FNV reads every stored byte in order. Probe exact block boundaries,
  # partial blocks crossing element boundaries, empty data and wrapped seeds.
  for width,n in ((8,0),(8,1),(136,3),(262136,1),(262144,1),(262152,3)):
   seed=MASK-2;words=width//8
   data=[mix((seed+i)&MASK) for i in range(n*words)]
   values=[];touch=[]
   for i in range(n):
    x=mix(seed^((i*0x9e3779b97f4a7c15)&MASK));touch.append(sum(data[i*words:(i+1)*words])&MASK)
    for step in range(2):
     for word in data[i*words:(i+1)*words]:x=((x+word+step)&MASK)^(x>>7)
    values.append(x)
   for allocation in ('zeroed','overwrite'):
    reference=None
    for mode in ('separate','blocked'):
     j=copy.deepcopy(base);j['workload'].update(name='memory_reuse',elements=n,seed=seed,bytes_per_element=width,passes=2)
     j['measurement']={'mode':'diagnostic','epochs':2,'memory_lanes':4,'reference_workers':4,'data_allocation':allocation,'data_identity':mode}
     r=run(j);meta=r['data_identity']
     assert meta['requested']==mode and meta['used']==(mode if n else 'none')
     assert meta['block_bytes']==(262144 if mode=='blocked' and n else 0)
     for e in r['epochs']:
      assert e['identity']['data_hash_fnv1a64']==fnv(data)
      assert e['correctness']['output_hash_fnv1a64']==fnv(values)
      assert e['pretouch_hash_fnv1a64']==fnv(touch)
      assert e['correctness']['exact_once'] and e['correctness']['compared_elements']==n
      if reference is None:reference=e['identity']
      assert e['identity']==reference
  for invalid in ('unknown','',1,True,None,[]):
   j=copy.deepcopy(base);j['measurement']['data_identity']=invalid
   run(j,2);run(j,2,flags=('--validate-config',))
  for name in ('memory_reuse','compute_uniform','compute_skewed'):
   for count in (2,128):
    j=copy.deepcopy(base);j['workload']['name']=name
    j['measurement'].update(data_identity='blocked',initialization_workers=count)
    run(j,2);run(j,2,flags=('--validate-config',))
   if name!='memory_reuse':
    j=copy.deepcopy(base);j['workload']['name']=name;j['measurement']['data_identity']='blocked'
    assert run(j)['data_identity']['used']=='none'
  for width in (8,136,8192):
   for n in (0,1,2,3,4,5,9):
    seed=MASK-2;words=width//8;data=[mix((seed+i)&MASK) for i in range(n*words)]
    values=[];touch=[]
    for i in range(n):
     x=mix(seed^((i*0x9e3779b97f4a7c15)&MASK));touch.append(sum(data[i*words:(i+1)*words])&MASK)
     for step in range(2):
      for word in data[i*words:(i+1)*words]:x=((x+word+step)&MASK)^(x>>7)
     values.append(x)
    for allocation in ('zeroed','overwrite'):
     j=copy.deepcopy(base);j['workload'].update(name='memory_reuse',elements=n,seed=seed,bytes_per_element=width,passes=2)
     j['measurement']={'mode':'diagnostic','epochs':2,'memory_lanes':4,'reference_workers':4,'data_allocation':allocation,'data_fill_lanes':4}
     r=run(j);assert r['data_fill']['lanes_requested']==4 and r['data_fill']['lanes_used']==(4 if n else 0)
     for e in r['epochs']:
      assert e['identity']['data_hash_fnv1a64']==fnv(data) and e['pretouch_hash_fnv1a64']==fnv(touch)
      assert e['correctness']['output_hash_fnv1a64']==fnv(values)
      assert e['correctness']['compared_elements']==n and e['correctness']['exact_once']
  for invalid in (0,-1,2,8,1.0,4.0,True,'4',None):
   j=copy.deepcopy(base);j['measurement']['data_fill_lanes']=invalid
   run(j,2);run(j,2,flags=('--validate-config',))
  for name in ('memory_reuse','compute_uniform','compute_skewed'):
   for count,identity in ((2,'separate'),(128,'separate'),(1,'blocked')):
    j=copy.deepcopy(base);j['workload']['name']=name;j['measurement'].update(data_fill_lanes=4,initialization_workers=count,data_identity=identity)
    run(j,2);run(j,2,flags=('--validate-config',))
   if name!='memory_reuse':
    j=copy.deepcopy(base);j['workload']['name']=name;j['measurement']['data_fill_lanes']=4
    assert run(j)['data_fill']['lanes_used']==0
  print(json.dumps({'status':'pass','checks':checks,'golden_output_hash':expected}))
if __name__=='__main__':main()
