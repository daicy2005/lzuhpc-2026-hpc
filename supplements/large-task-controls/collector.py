#!/usr/bin/env python3
"""Additional preregistered per-task 8x-LLC controls; reuse the validated executable."""
import argparse
import copy
import json
import pathlib
import shutil
import statistics
import sys

import confirm_idle as guard
import lab
import mechanism_controls as shared

PROTOCOL='docs/53-单任务大于LLC补测协议.md'
ORIGIN=pathlib.Path('/root/lzuhpc-experiments/ws-20261027-mechanism-controls-v3')
read=shared.read


def design():
    cases,groups=[],[]
    def config(p,home):
        c=lab.config('on',p,1,1,4,194033,'memory_reuse')
        c['workload'].update(bytes_per_element=288*1024*1024,passes=4)
        c['policies']['placement']['name']='home'
        c['measurement'].update(home_worker=home,reference_workers=4)
        return c
    for target in (0,1):
        group=[]
        for label,home in (('same',target),('other',1-target)):
            c=config(2,home);c['measurement']['controlled_worker']=target
            cid=f'large-preread-target{target}-{label}'
            cases.append({'id':cid,'group':f'preread-target{target}','label':label,'config':c});group.append(cid)
        groups.append(group)
    group=[]
    for mode in ('off','on'):
        c=config(4,0)
        if mode=='off':c['policies']['steal_timing']['name']='disabled_yield'
        cid='large-dynamic-'+mode
        cases.append({'id':cid,'group':'dynamic','label':mode,'config':c});group.append(cid)
    groups.append(group)
    order=[(purpose,0,cid) for purpose in ('diagnostic','warmup') for group in groups for cid in group]
    for rep in range(1,6):
        shift=(rep-1)%3
        order += [('timing',rep,cid) for g in groups[shift:]+groups[:shift] for cid in (g if rep%2 else g[::-1])]
    assert len(cases)==6 and len(order)==42
    return {'experiment':'large-task-controls','conditions':cases,'groups':groups,'order':order,
        'processes':42,'timing_samples':30,'protocol':PROTOCOL,'per_task_bytes':288*1024*1024,
        'total_data_bytes':1152*1024*1024,'task_to_reported_llc':8,'no_adaptation':True}


def prepare(root):
    origin=lab.ROOT
    root.mkdir(parents=True,exist_ok=False)
    for f in lab.source_files():
        dest=root/f.relative_to(origin);dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(f,dest);assert lab.digest(f)==lab.digest(dest)
    lab.ROOT=root
    prior=read(ORIGIN/'results/frozen-plan.json')
    build=root/'build-mechanism';build.mkdir()
    for name in ('worksteal_mechanism','host_probe','validation.json','CMakeCache.txt'):
        shutil.copy2(ORIGIN/'build-mechanism'/name,build/name)
    assert lab.digest(build/'worksteal_mechanism')==prior['binary_sha256']
    for folder in ('include','src'):
        for f in (root/folder).rglob('*'):
            if f.is_file():assert lab.digest(f)==lab.digest(ORIGIN/f.relative_to(root)),str(f)
    assert lab.digest(root/'tools/register_disabled_yield.cpp')==lab.digest(ORIGIN/'tools/register_disabled_yield.cpp')
    (root/'results').mkdir()
    for i in range(4):shutil.copy2(ORIGIN/f'results/build-{i}.json',root/f'results/build-{i}.json')
    plan=design()
    plan.update(source_id=lab.snapshot(),binary_sha256=prior['binary_sha256'],
        binary_source_id=prior['source_id'],protocol_sha256=lab.digest(root/PROTOCOL),
        reused_validated_binary=True)
    lab.write(root/'results/frozen-plan.json',plan)
    print(json.dumps({'prepared':str(root),'reused_binary_verified':True,'planned_runs':42}),flush=True)


def validate(c,r,purpose):
    # Reuse all full-verification and controlled-executor checks.
    if c['policies']['steal_timing']['name']=='disabled_yield' and purpose=='diagnostic':
        # Dynamic off still uses the ordinary pool epoch, with no local_only override.
        assert r['correctness']['pass'] and r['metrics_mode']=='diagnostic'
        e=r['epochs'][0]
        assert e['correctness']['exact_once'] is True and not e['local_only']
        assert sum(s['steals'] for s in e['worker_stats'])==0
        assert set(e['execution']['task_executor'])=={0}
        assert sum(e['execution']['worker_cost_units'])==e['identity']['total_cost_units']
    else:
        shared.validate(c,r,purpose)
    assert r['affinity']['actual_workers']==[[cpu] for cpu in c['policies']['affinity']['cpus']]
    assert r['epochs'][0]['identity']['total_data_bytes']==1152*1024*1024
    assert r['epochs'][0]['identity']['task_count']==4
    assert r['epochs'][0]['correctness']['compared_elements']==4


def run(root):
    lab.ROOT=root
    plan=read(root/'results/frozen-plan.json');exe=root/'build-mechanism/worksteal_mechanism'
    assert not list((root/'runs').glob('*'))
    assert lab.snapshot()==plan['source_id'] and lab.digest(exe)==plan['binary_sha256']
    memory_info={s.split(':',1)[0]:int(s.split()[1])*1024 for s in pathlib.Path('/proc/meminfo').read_text().splitlines() if ':' in s}
    # WSL1 lacks MemAvailable; MemFree is a conservative fallback, not a cache estimate.
    memory_metric='MemAvailable' if 'MemAvailable' in memory_info else 'MemFree'
    available=memory_info[memory_metric]
    assert available>=3*1024**3
    status,receipt=guard.availability(root,300)
    if status!='ready':raise RuntimeError('resource window busy; no experiment started')
    batch=lab.Batch('large-task-controls',{**plan,'availability_receipt':receipt.relative_to(root).as_posix(),
        'available_memory_before':available,'memory_metric':memory_metric},exe,budget=900)
    cases={c['id']:c for c in plan['conditions']}
    state,reason='completed',None
    checks=[];hashes=None
    try:
        own=guard.ancestors()
        for purpose,rep,cid in plan['order']:
            sample=guard.observe(own);checks.append(sample)
            if not sample['clear']:raise RuntimeError('competing Linux task detected')
            c=copy.deepcopy(cases[cid]['config'])
            if purpose=='diagnostic':c['measurement']['mode']='diagnostic'
            r=batch.run(c,cid,purpose,rep,timeout=90)
            validate(c,r,purpose)
            e=r['epochs'][0]
            current=[e['identity'][key] for key in ('input_hash_fnv1a64','cost_hash_fnv1a64','data_hash_fnv1a64')]
            current += [e['correctness']['output_hash_fnv1a64'],e['pretouch_hash_fnv1a64']]
            if hashes is not None:assert hashes==current
            hashes=current
    except Exception as error:
        import traceback
        state,reason='failed',repr(error)
        lab.write(batch.path/'collector-error.json',{'error':reason,'traceback':traceback.format_exc()})
    finally:
        lab.write(batch.path/'resource-samples.json',checks)
        batch.finish(state,reason)
    print(json.dumps({'batch':str(batch.path),'status':state,'reason':reason}),flush=True)
    if state!='completed':raise RuntimeError(reason)


def audit(root):
    lab.ROOT=root
    plan=read(root/'results/frozen-plan.json');batches=list((root/'runs').glob('*'))
    assert len(batches)==1
    batch=batches[0];assert read(batch/'completion.json')['status']=='completed'
    checks=0
    for folder in (batch,*[x for x in batch.iterdir() if x.is_dir()]):
        for name,expected in read(folder/'checksums.json').items():
            assert lab.digest(folder/name)==expected;checks+=1
    records=read(batch/'records.json')
    assert len(records)==42
    assert [(r['purpose'],r['repeat'],r['condition']) for r in records]==[tuple(x) for x in plan['order']]
    cases={c['id']:c for c in plan['conditions']};times={};diagnostics={};hashes=None
    for rec in records:
        rd=batch/rec['run_id'];c=read(rd/'config.json');r=read(rd/'result.json');e=r['epochs'][0]
        validate(c,r,rec['purpose'])
        assert rec['status']=='completed' and rec['binary_sha256']==plan['binary_sha256']
        identity=[e['identity'][k] for k in ('input_hash_fnv1a64','cost_hash_fnv1a64','data_hash_fnv1a64')]
        identity += [e['correctness']['output_hash_fnv1a64'],e['pretouch_hash_fnv1a64']]
        if hashes is not None:assert hashes==identity
        hashes=identity
        if rec['purpose']=='timing':
            times[(rec['condition'],rec['repeat'])]={'epoch':e['epoch_seconds'],
                'app':r['timing']['end_to_end_seconds'],'run_path':(rd/'result.json').relative_to(root).as_posix()}
        elif rec['purpose']=='diagnostic':
            diagnostics[rec['condition']]={'steals':sum(s['steals'] for s in e['worker_stats']),
                'execution':e['execution'],'identity':e['identity'],'run_path':(rd/'result.json').relative_to(root).as_posix()}
    assert len(times)==30
    groups=[]
    for ids in plan['groups']:
        rows=[]
        for cid in ids:
            samples=[times[(cid,rep)] for rep in range(1,6)]
            rows.append({'condition':cid,'label':cases[cid]['label'],'samples':samples,
                'epoch_median':statistics.median(s['epoch'] for s in samples),
                'app_median':statistics.median(s['app'] for s in samples)})
        groups.append({'group':cases[ids[0]]['group'],'conditions':rows,
            'ratio':rows[0]['epoch_median']/rows[1]['epoch_median'],
            'second_faster_pairs':sum(b['epoch']<a['epoch'] for a,b in zip(rows[0]['samples'],rows[1]['samples']))})
    summary={'batch':batch.name,'source_id':plan['source_id'],'binary_sha256':plan['binary_sha256'],
        'binary_source_id':plan['binary_source_id'],'processes':42,'timing_samples':30,'hash_checks':checks,
        'groups':groups,'diagnostics':diagnostics,'all_correct':True,
        'per_task_bytes':288*1024*1024,'total_data_bytes':1152*1024*1024,'task_to_reported_llc':8}
    lab.write(root/'results/summary.json',summary)
    lines=['# 单任务大于 LLC 的补测','','每任务 288 MiB（报告 LLC 的 8 倍），4 个任务共 1152 MiB，每条件五次计时。',
        '','|对照|配置|epoch 中位数 / ms|','|---|---|---|']
    for group in groups:
        for row in group['conditions']:lines.append(f"|{group['group']}|{row['label']}|{row['epoch_median']*1000:.4f}|")
    d=diagnostics['large-dynamic-on']
    lines+=['',f"动态诊断成功窃取 {d['steals']} 次，{d['execution']['element_home_mismatches']}/4 个任务由非 home 执行。",'',
        '预读对照不能直接等同于纯缓存损失；工作窃取开关的时间差包含并行度和调度等共同影响。']
    (root/'results/report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'audit':'pass','processes':42,'timing_samples':30,'hash_checks':checks}),flush=True)


def main():
    p=argparse.ArgumentParser();p.add_argument('action',choices=('prepare','run','audit','export'))
    p.add_argument('--root',required=True);p.add_argument('--target');a=p.parse_args();root=pathlib.Path(a.root)
    if a.action=='export':shared.export(root,pathlib.Path(a.target))
    else:{'prepare':prepare,'run':run,'audit':audit}[a.action](root)


if __name__=='__main__':main()
