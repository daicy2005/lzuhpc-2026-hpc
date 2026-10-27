#!/usr/bin/env python3
"""V13 fixed off/on mechanism study; no source changes or recommendation search."""
import argparse
import collections
import copy
import hashlib
import json
import pathlib
import random
import shutil
import statistics
import threading
import uuid

import confirm_idle as guard
import lab
import memory_tuning_study as numeric

PROTOCOL = 'docs/37-第十三轮窃取粒度与布局协议.md'
INPUTS = ((100003, 65536), (106013, 98304))
GRAINS = (8, 256, 16384)
LAYOUTS = ('concentrated', 'spread')
EXE = '/root/lzuhpc-experiments/ws-20261022-fill-interleaved-release/build-none/worksteal'
SHA = '3992f3db54f07de09e3fd8510463e6fb6458473340a9428e14e33723b6a97caf'


def read(path):
    return json.loads(pathlib.Path(path).read_text(encoding='utf-8-sig'))


def design():
    cases, controls, pairs = [], [], []
    for seed, n, k, small in ((99041, 1031, 7, True), *((s,n,256,False) for s,n in INPUTS)):
        for grain in GRAINS:
            for layout in LAYOUTS:
                pair = []
                for mode in ('off','on'):
                    cid = f's{seed}-g{grain}-{layout}-{mode}'
                    c = lab.config(mode,16,grain,k,n,seed,'compute_skewed',layout=layout)
                    c['measurement'].update(reference_workers=16)
                    if small: c['measurement']['mode'] = 'diagnostic'
                    cases.append({'id': cid, 'config': c, 'small': small, 'mode': mode})
                    pair.append(cid)
                if small: controls.extend(pair)
                else: pairs.append(pair)
    random.Random(2026102213).shuffle(pairs)
    order = [('control',0,cid) for cid in controls]
    order += [('diagnostic',0,cid) for pair in pairs for cid in pair]
    order += [('warmup',0,cid) for pair in pairs for cid in pair]
    for rep in range(1,6):
        shift = (rep-1)*len(pairs)//5
        rotated = pairs[shift:]+pairs[:shift]
        order += [('timing',rep,cid) for pair in rotated for cid in (pair if rep%2 else pair[::-1])]
    return {'stage': 'V13-stealing-boundary', 'conditions': cases, 'pairs': pairs, 'order': order,
            'max_processes': 180, 'timing_samples': 120, 'no_recommendation_search': True}


def task_model(config):
    n, k = config['workload']['elements'], config['workload']['iterations']
    grain, p = config['policies']['partition']['grain'], config['workers']
    tasks = [(i,b,min(n,b+grain),i%p) for i,b in enumerate(range(0,n,grain))]
    costs = [(end-begin+8*max(0,min(end,n//8)-begin))*k for _,begin,end,_ in tasks]
    ids = sorted(range(len(tasks)),key=lambda i:-costs[i])  # Stable ties by TaskId.
    capacity = (len(tasks)+p-1)//p if tasks else 1
    lists = [[] for _ in range(p)]
    for rank, tid in enumerate(ids):
        owner = min(p-1,rank//capacity) if config['layout']=='concentrated' else rank%p
        lists[owner].append(tid)
    initial = [sum(costs[i] for i in q) for q in lists]
    return tasks,costs,lists,initial


def identities(config, input_cache):
    w = config['workload']
    n,k,seed = w['elements'],w['iterations'],w['seed']
    key = (seed,n,k)
    if key not in input_cache:
        input_cache[key] = {
            'input_hash_fnv1a64': numeric.fnv(numeric.mix(seed ^ ((i*0x9e3779b97f4a7c15)&numeric.MASK)) for i in range(n)),
            'cost_hash_fnv1a64': numeric.fnv(k*(9 if i<n//8 else 1) for i in range(n))}
    tasks,costs,lists,initial = task_model(config)
    return {**input_cache[key], 'task_hash_fnv1a64':numeric.fnv(x for task in tasks for x in task),
        'queue_hash_fnv1a64':numeric.fnv(x for worker,q in enumerate(lists) for x in (worker,len(q),*q)),
        'data_hash_fnv1a64':None, 'initial_cost_units':initial, 'total_cost_units':sum(costs),
        'max_task_cost_units':max(costs), 'task_count':len(tasks), 'per_element_bytes':8,'total_data_bytes':0}


def small_output(config):
    w = config['workload']
    values = []
    for i in range(w['elements']):
        x = numeric.mix(w['seed'] ^ ((i*0x9e3779b97f4a7c15)&numeric.MASK))
        for j in range(w['iterations']*(9 if i<w['elements']//8 else 1)):
            x = numeric.mix((x+j+(x<<1))&numeric.MASK)
        values.append(x)
    return numeric.fnv(values)


def diagnostic(config, epoch, enabled):
    tasks,costs,lists,initial = task_model(config)
    execution, stats = epoch['execution'], epoch['worker_stats']
    owners = execution['task_executor']
    assert len(owners)==len(tasks) and len(stats)==16
    initial_owner = {tid:worker for worker,q in enumerate(lists) for tid in q}
    work, elements, count = [0]*16,[0]*16,[0]*16
    home_mismatch, relocated = 0,0
    for (tid,begin,end,home),cost,owner in zip(tasks,costs,owners):
        assert type(owner) is int and 0<=owner<16
        work[owner]+=cost
        elements[owner]+=end-begin
        count[owner]+=1
        home_mismatch+=(end-begin)*(owner!=home)
        relocated+=owner!=initial_owner[tid]
        if not enabled: assert owner==initial_owner[tid]
    assert execution=={'worker_cost_units':work,'worker_elements':elements,'task_executor':owners,
                      'element_home_mismatches':home_mismatch,'cost_unit':'mix_iterations'}
    assert [s['tasks'] for s in stats]==count
    steals,moved = sum(s['steals'] for s in stats),sum(s['moved'] for s in stats)
    assert steals==moved==relocated
    if not enabled: assert steals==0 and all(s['attempts']==0 for s in stats)
    finish = [s['last_finish_seconds'] for s in stats if s['tasks']]
    return {'initial_cost_units':initial, 'actual_cost_units':work,
        'initial_cost_balance':sum(initial)/(16*max(initial)),
        'actual_cost_balance':sum(work)/(16*max(work)), 'steals':steals,'relocated_tasks':relocated,
        'home_mismatched_elements':home_mismatch, 'worker_last_finish_span_seconds':max(finish)-min(finish),
        'task_count':len(tasks),'total_cost_units':sum(costs),'max_task_cost_units':max(costs),
        'ideal_equal_speed_unit_bound':max(sum(costs)/16,max(costs)),
        'note':'unit balance is not utilization; diagnostic times excluded from timing'}


def prepare(root):
    origin = lab.ROOT
    root.mkdir(parents=True,exist_ok=False)
    for src in lab.source_files():
        dest=root/src.relative_to(origin);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
    lab.ROOT=root
    source=lab.snapshot()
    exe=pathlib.Path(EXE)
    v=read(exe.parent/'validation.json')
    assert v['pass'] and v['binary_sha256']==lab.digest(exe)==SHA
    assert all(r['returncode']==0 and not r['stderr'] for r in v['records'])
    assert 'warning:' not in (exe.parent/'build-1.log').read_text().lower()
    old=read(exe.parent.parent/'snapshots/source'/v['source_id']/'manifest.json')
    for name,sha in old['files'].items():
        if name.startswith(('src/','include/')) or name in ('CMakeLists.txt','CMakePresets.json'):
            assert lab.digest(root/name)==sha
    for folder,identifier in (('source',v['source_id']),('builds',SHA)):
        shutil.copytree(exe.parent.parent/'snapshots'/folder/identifier,root/'snapshots'/folder/identifier)
    lab.write(root/'results/frozen-plan.json',{'created':lab.now(),'collector_source_id':source,
        'protocol':PROTOCOL,'protocol_sha256':lab.digest(root/PROTOCOL), 'study':design(),
        'build':{'exe':EXE,'binary_sha256':SHA,'source_id':v['source_id']},
        'consistent_epoch_gain':'both inputs on wins>=4/5 and on epoch median<=0.95 off; descriptive, not acceptance'})
    lab.write(root/'results/preparation.json',{'plan_sha256':lab.digest(root/'results/frozen-plan.json'),'created':lab.now()})
    print(json.dumps({'prepared':str(root),'source_id':source,'processes':180}),flush=True)


def load(root):
    path=root/'results/frozen-plan.json'
    assert lab.digest(path)==read(root/'results/preparation.json')['plan_sha256']
    p=read(path)
    assert p['study']==json.loads(json.dumps(design()))
    assert lab.digest(root/'snapshots/source'/p['collector_source_id']/PROTOCOL)==p['protocol_sha256']
    return p


def run(root,wait_seconds):
    p=load(root)
    assert not list((root/'runs').glob('*')),'never retry a started batch'
    assert len(list((root/'results').glob('availability-*.json')))<2
    assert lab.digest(pathlib.Path(EXE))==SHA
    status,receipt=guard.availability(root,wait_seconds)
    if status!='ready':return 3
    b,stage=p['build'],p['study']
    batch=lab.Batch(stage['stage'],{**stage,'build':b,'availability_receipt':receipt.relative_to(root).as_posix(),
        'frozen_plan_sha256':lab.digest(root/'results/frozen-plan.json')},pathlib.Path(EXE),budget=600)
    batch.source,batch.binary=b['source_id'],b['binary_sha256']
    own,stop,samples,lock=guard.ancestors(),threading.Event(),[],threading.Lock()
    def check():
        with lock:
            sample=guard.observe(own);samples.append(sample)
        return all(s['clear'] for s in samples)
    def monitor():
        while not stop.wait(.5):
            if not check():break
    thread=threading.Thread(target=monitor,daemon=True);thread.start()
    state,reason='completed',None
    try:
        cases={c['id']:c for c in stage['conditions']}
        cache,expected,diagnosed,outputs={},{},{},{}
        for purpose,rep,cid in stage['order']:
            if not check():raise RuntimeError('resource_contamination')
            c=copy.deepcopy(cases[cid]['config'])
            if purpose=='diagnostic':c['measurement']['mode']='diagnostic'
            r=batch.run(c,cid,purpose,rep,timeout=90)
            e=r['epochs'][0]
            key=(c['workload']['seed'],c['workload']['elements'])
            if purpose in ('control','diagnostic'):
                assert e['correctness']['exact_once'] is True
                assert e['identity']==identities(c,cache)
                if purpose=='control':
                    if key not in expected:expected[key]=small_output(c)
                    assert e['correctness']['output_hash_fnv1a64']==expected[key]
                if key not in outputs:outputs[key]=e['correctness']['output_hash_fnv1a64']
                assert outputs[key]==e['correctness']['output_hash_fnv1a64']
                cpus=c['policies']['affinity']['cpus']
                assert r['affinity']['actual_workers']==[[cpu] for cpu in cpus]
                diagnosed[(cid,purpose)]=diagnostic(c,e,cases[cid]['mode']=='on')
            if not check():raise RuntimeError('resource_contamination')
        lab.write(batch.path/'diagnostic-reconstruction.json',[
            {'condition':cid,'purpose':purpose,**v} for (cid,purpose),v in diagnosed.items()])
    except Exception as exc:
        reason=str(exc);state='contaminated' if reason=='resource_contamination' else 'failed'
    finally:
        stop.set();thread.join(timeout=15)
        if thread.is_alive():state,reason='failed','monitor_did_not_stop'
        lab.write(batch.path/'resource-observations.json',{'samples':samples,'clean':all(s['clear'] for s in samples),
            'interval_seconds':.5,'scope':'known WSL processes; not physical exclusivity'})
        batch.finish(state,reason)
    print(json.dumps({'status':state,'batch':str(batch.path),'processes':len(batch.records)}),flush=True)
    return 0 if state=='completed' else 4


def audit(root):
    p=load(root)
    checked=0
    for manifest in (root/'snapshots/source').glob('*/manifest.json'):
        m=read(manifest)
        assert hashlib.sha256(json.dumps(m['files'],sort_keys=True).encode()).hexdigest()==m['source_id']==manifest.parent.name
        for rel,sha in m['files'].items():assert lab.digest(manifest.parent/rel)==sha;checked+=1
    build=root/'snapshots/builds'/SHA
    v=read(build/'validation.json')
    assert v['pass'] and v['binary_sha256']==lab.digest(build/'worksteal')==SHA
    assert v['source_id']==p['build']['source_id']
    manifests=list((root/'snapshots/builds').glob('*/checksums.json'))
    dirs=list((root/'runs').iterdir());assert len(dirs)==1
    directory=dirs[0]
    rows,done,plan=read(directory/'records.json'),read(directory/'completion.json'),read(directory/'plan.json')
    assert plan['build']==p['build'] and plan['source_id']==p['collector_source_id']
    assert {k:plan[k] for k in p['study']}==p['study']
    assert plan['frozen_plan_sha256']==lab.digest(root/'results/frozen-plan.json')
    assert len(rows)==done['processes'] and len({r['run_id'] for r in rows})==len(rows)
    assert [(r['purpose'],r['repeat'],r['condition']) for r in rows]==[tuple(s) for s in p['study']['order'][:len(rows)]]
    assert {d.name for d in directory.iterdir() if d.is_dir()}=={r['run_id'] for r in rows}
    manifests += [directory/'checksums.json']+list(directory.glob('*/checksums.json'))
    for manifest in manifests:
        hashes=read(manifest)
        assert set(hashes)=={f.relative_to(manifest.parent).as_posix() for f in manifest.parent.rglob('*') if f.is_file() and f.name!='checksums.json'}
        for rel,sha in hashes.items():assert lab.digest(manifest.parent/rel)==sha;checked+=1
    cases={c['id']:c for c in p['study']['conditions']}
    cache,identity_cache,small,outputs,timing,diag={},{},{},{},{},[]
    signatures=collections.defaultdict(set)
    for row in rows:
        rd=directory/row['run_id'];item=cases[row['condition']];c=copy.deepcopy(item['config'])
        if row['purpose']=='diagnostic':c['measurement']['mode']='diagnostic'
        assert read(rd/'metadata.json')==row and read(rd/'config.json')==c
        assert row['source_id']==p['build']['source_id'] and row['binary_sha256']==SHA
        assert row['collector_sha256']==lab.digest(root/'snapshots/source'/p['collector_source_id']/'tools/lab.py')
        command=read(rd/'command.txt');original=pathlib.PurePosixPath(command['cwd'])/'runs'/directory.name/row['run_id']
        assert command['argv']==[EXE,'--config',str(original/'config.json'),'--output',str(original/'result.json')]
        assert not command['explicit_environment']
        if row['status']!='completed':
            assert done['status']!='completed' and not row['included'];continue
        assert row['exit_code']==0 and not (rd/'stderr.log').read_bytes()
        r=read(rd/'result.json');assert json.loads((rd/'stdout.log').read_bytes())==r
        assert r['correctness']['pass'] and len(r['epochs'])==1
        resolved=copy.deepcopy(c);resolved['steal_enabled']=item['mode']=='on'
        assert r['resolved_config']==resolved
        assert r['timing']==row['timing'] and row['included']==(row['purpose']=='timing')
        e,cc=r['epochs'][0],r['epochs'][0]['correctness']
        w=c['workload'];key=(w['seed'],w['elements'],w['iterations'])
        ikey=(*key,c['policies']['partition']['grain'],c['layout'])
        if ikey not in identity_cache:identity_cache[ikey]=identities(c,cache)
        assert e['identity']==identity_cache[ikey]
        assert cc['pass'] and cc['mismatches']==0 and cc['compared_elements']==w['elements']
        assert cc['reference_tile_elements']==256 and cc['reference_workers_used']==min(16,(w['elements']+255)//256)
        if key not in outputs:outputs[key]=cc['output_hash_fnv1a64']
        assert cc['output_hash_fnv1a64']==outputs[key]
        # compute_skewed has no memory pre-read; Workload::pretouch_hash()
        # returns Json(nullptr). The frozen collector's audit incorrectly
        # expected the FNV of zero words; only this read-only audit is repaired.
        assert e['pretouch_hash_fnv1a64'] is None
        assert not e['local_only']
        if item['small']:
            if key not in small:small[key]=small_output(c)
            assert cc['output_hash_fnv1a64']==small[key]
        signatures[ikey].add(json.dumps(e['identity'],sort_keys=True))
        cpus=c['policies']['affinity']['cpus']
        assert r['affinity']['requested']==cpus and r['affinity']['actual_workers']==[[cpu] for cpu in cpus]
        assert r['initialization']['workers_used']==0 and r['initialization']['data_allocation_used']=='none'
        assert r['data_fill']['lanes_used']==0 and r['data_identity']['used']=='none' and r['execution_kernel']['memory_lanes_used']==0
        assert all(t>=0 for t in r['phase_seconds'].values())
        assert sum(r['phase_seconds'].values())<=r['timing']['end_to_end_seconds']+1e-9
        diagnostic_mode=c['measurement']['mode']=='diagnostic'
        assert cc['exact_once']==(True if diagnostic_mode else None)
        if diagnostic_mode:
            d=diagnostic(c,e,item['mode']=='on')
            diag.append({'condition':row['condition'],'purpose':row['purpose'],**d})
        else:assert e['execution'] is None and e['worker_stats'] is None
        if row['included']:
            timing[(row['condition'],row['repeat'])]={'epoch':r['timing']['epoch_seconds'],
                'app':r['timing']['end_to_end_seconds'],'process':row['elapsed_process_seconds'],
                'run_path':rd.relative_to(root).as_posix()}
    assert all(len(s)==1 for s in signatures.values())
    resource=read(directory/'resource-observations.json');assert resource['samples']
    assert resource['clean']==all(s['clear'] for s in resource['samples'])
    av=read(root/plan['availability_receipt'])
    assert av['status']=='ready' and all(s['clear'] for s in av['observations'][-3:])
    clean=done['status']=='completed' and resource['clean']
    groups=[]
    if clean:
        assert len(rows)==180 and len(timing)==120 and len(diag)==36
        assert read(directory/'diagnostic-reconstruction.json')==diag
        for off,on in p['study']['pairs']:
            c=cases[off]['config'];key=(c['workload']['seed'],c['workload']['elements'],c['workload']['iterations'],c['policies']['partition']['grain'],c['layout'])
            paired=[{'repeat':rep,'off':timing[(off,rep)],'on':timing[(on,rep)]} for rep in range(1,6)]
            medians={mode:{metric:statistics.median(t[mode][metric] for t in paired) for metric in ('epoch','app','process')} for mode in ('off','on')}
            wins=sum(t['on']['epoch']<t['off']['epoch'] for t in paired)
            groups.append({'seed':key[0],'elements':key[1],'grain':key[3],'layout':key[4],
                'identity':identity_cache[key], 'medians':medians,'epoch_wins':wins,
                'epoch_speedup':medians['off']['epoch']/medians['on']['epoch'],
                'app_speedup':medians['off']['app']/medians['on']['app'],
                'consistent_input_gain':wins>=4 and medians['on']['epoch']<=.95*medians['off']['epoch'],
                'pairs':paired,'diagnostic':{mode:next(d for d in diag if d['condition']==cid and d['purpose']=='diagnostic') for mode,cid in (('off',off),('on',on))}})
    repeated=[{'grain':grain,'layout':layout,'both_inputs_epoch_gain':all(g['consistent_input_gain'] for g in groups if g['grain']==grain and g['layout']==layout)} for grain in GRAINS for layout in LAYOUTS] if clean else []
    result={'audit_pass':True,'complete':clean,'accepted':None,'scope':'mechanism only; no recommendation selection',
        'batch':directory.name,'processes':len(rows),'timing_samples':len(timing),'diagnostic_samples':len(diag),
        'hash_checks':checked,'resource_samples':len(resource['samples']),'groups':groups,'repeated_observations':repeated,'created':lab.now()}
    path=root/'results'/('audit-'+uuid.uuid4().hex+'.json');lab.write(path,result)
    print(json.dumps({'audit':str(path),'complete':clean,'processes':len(rows),'timing_samples':len(timing),'hash_checks':checked}),flush=True)
    return result,path


def report(root):
    receipts=list((root/'results').glob('export-*.json'));assert len(receipts)==1
    receipt=read(receipts[0])
    for rel,sha in receipt['files'].items():assert lab.digest(root/rel)==sha
    a,path=audit(root)
    target=lab.ROOT/'report/stealing-boundary'/('第十三轮窃取边界报告-'+uuid.uuid4().hex[:8]+'.md')
    lines=['# 第十三轮：优化后运行时的窃取边界','','固定二进制/16worker/K256，off/on仅改disabled/immediate。空闲方式也随策略变化，是组合策略净影响。无新推荐。', '',
        f"批次`{a['batch']}`，{a['processes']}进程/{a['timing_samples']}正式计时，complete={a['complete']}；所有慢成功样本保留。",'',
        '|seed/N|grain/任务数|布局|off epoch ms|on epoch ms|off/on|on胜对|app off/on|本输入收益观察|',
        '|---|---|---|---:|---:|---:|---:|---:|---|']
    for g in sorted(a['groups'],key=lambda g:(g['seed'],g['grain'],g['layout'])):
        m=g['medians']
        lines.append(f"|{g['seed']}/{g['elements']}|{g['grain']}/{g['identity']['task_count']}|{g['layout']}|{m['off']['epoch']*1000:.4f}|{m['on']['epoch']*1000:.4f}|{g['epoch_speedup']:.3f}|{g['epoch_wins']}/5|{g['app_speedup']:.3f}|{g['consistent_input_gain']}|")
    lines += ['', '上述标记为预声明4/5胜且中位数至少快5%，不是显著性或采用门槛。粗粒度4/6任务小于16worker，两布局实际队列相同，不当独立重复。理想工作单位界不是本机时间下界；无物理核或缓存因果结论。', '',
        f"[独立审计及完整配对](../../stealing-boundary/{path.relative_to(root).as_posix()})；[冻结计划](../../stealing-boundary/results/frozen-plan.json)；[全部run索引](../../stealing-boundary/runs/{a['batch']}/records.json)。",'', '## 诊断关联（不作正式时间分解）','',
        '|seed|grain|布局|初始单位均衡度|on实际单位均衡度|off/on steals|Cmax/(W/16)|',
        '|---|---:|---|---:|---:|---|---:|']
    for g in a['groups']:
        off,on=g['diagnostic']['off'],g['diagnostic']['on']
        lines.append(f"|{g['seed']}|{g['grain']}|{g['layout']}|{off['initial_cost_balance']:.4f}|{on['actual_cost_balance']:.4f}|{off['steals']}/{on['steals']}|{on['max_task_cost_units']/(on['total_cost_units']/16):.2f}|")
    lines += ['', '## 全部正式配对','']
    for g in a['groups']:
        lines += [f"### seed{g['seed']} grain{g['grain']} {g['layout']}",'']
        for pair in g['pairs']:
            off,on=pair['off'],pair['on']
            lines.append(f"- 第{pair['repeat']}对：[off](../../stealing-boundary/{off['run_path']}/result.json) {off['epoch']*1000:.4f}ms → [on](../../stealing-boundary/{on['run_path']}/result.json) {on['epoch']*1000:.4f}ms。")
        lines.append('')
    target.parent.mkdir(parents=True,exist_ok=True)
    with target.open('x',encoding='utf-8') as f:f.write('\n'.join(lines)+'\n')
    print(json.dumps({'report':str(target),'exported_files_verified':len(receipt['files'])},ensure_ascii=False),flush=True)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('action',choices=('prepare','run','audit','export','report'))
    parser.add_argument('--root',required=True);parser.add_argument('--target');parser.add_argument('--wait-seconds',type=int,default=600)
    args=parser.parse_args();root=pathlib.Path(args.root).resolve()
    if args.action=='prepare':prepare(root)
    else:
        if args.action!='report':lab.ROOT=root
        if args.action=='run':return run(root,args.wait_seconds)
        if args.action=='audit':audit(root)
        if args.action=='export':lab.export(argparse.Namespace(target=args.target))
        if args.action=='report':report(root)
    return 0


if __name__=='__main__':raise SystemExit(main())
