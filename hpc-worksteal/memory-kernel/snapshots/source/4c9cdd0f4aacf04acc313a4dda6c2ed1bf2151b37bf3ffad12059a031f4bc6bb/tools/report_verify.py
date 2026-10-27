#!/usr/bin/env python3
"""Recompute and audit round-four decisions, then emit configs and report."""
import argparse, collections, copy, hashlib, json, pathlib
from analyze_opt import stats

def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,j):
    p.parent.mkdir(parents=True,exist_ok=True); p.write_text(json.dumps(j,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--root',required=True); a=ap.parse_args(); root=pathlib.Path(a.root).resolve(); area=root/'verification'
    s=read(area/'results/verification-summary.json'); assert s['complete']; export_checks=0; hash_checks=0
    for receipt in area.rglob('export-*.json'):
        for rel,h in read(receipt)['files'].items(): assert sha(receipt.parent.parent/rel)==h; export_checks+=1
    for manifest in area.rglob('checksums.json'):
        m=read(manifest)
        assert set(m)=={str(p.relative_to(manifest.parent)).replace('\\','/') for p in manifest.parent.rglob('*') if p.is_file() and p.name!='checksums.json'}
        for rel,h in m.items(): assert sha(manifest.parent/rel)==h; hash_checks+=1
    for manifest in area.rglob('manifest.json'):
        m=read(manifest)
        if 'source_id' in m:
            for rel,h in m['files'].items(): assert sha(manifest.parent/rel)==h; hash_checks+=1
    builds={}
    for name in ('full_lanes8','lanes8','asan','tsan'):
        snapshot=next((area/'evidence'/name/'snapshots/builds').iterdir()); validation=read(snapshot/'validation.json')
        assert validation['pass'] and validation['binary_sha256']==sha(snapshot/'worksteal')
        assert all(r['returncode']==0 for r in validation['records'])
        source=area/'evidence'/name/'snapshots/source'/validation['source_id']
        for rel in ('src/app/main.cpp','src/workloads/workload.cpp','src/runtime/worker_pool.cpp','include/worksteal/workload.hpp','include/worksteal/runtime.hpp','tests/cli_checks.py','tests/runtime_checks.cpp','CMakeLists.txt'):
            assert sha(source/rel)==sha(root/rel)
        logs=read(snapshot/'build.json'); assert all(r['returncode']==0 for r in logs)
        builds[name]={'snapshot':str(snapshot.relative_to(root)).replace('\\','/'),'source_id':validation['source_id'],
                      'binary_sha256':validation['binary_sha256'],'cmake_options':[x for x in logs[0]['argv'] if x.startswith('-D')],
                      'validation':validation['records']}
    # Confirm the measured scheduler stayed byte-identical to the previous build.
    prior=read(root/'configs/refined/builds.json'); old_snapshot=root/pathlib.Path(prior['skewed']['snapshot'])
    old_v=read(old_snapshot/'validation.json'); old_source=old_snapshot.parent.parent/'source'/old_v['source_id']
    for rel in ('src/runtime/worker_pool.cpp','include/worksteal/runtime.hpp'):
        assert sha(old_source/rel)==sha(root/rel)
    identities=collections.defaultdict(set); records_by_stage={}; host_overlap={}; ids=set(); processes=0; timing_count=0
    for stage,batch in s['batches'].items():
        directory=area/batch['path']; plan=read(directory/'plan.json'); done=read(directory/'completion.json'); rows=read(directory/'records.json')
        assert plan==batch['plan'] and done==batch['completion'] and done['status']=='completed' and done['processes']==len(rows)
        assert [(r['purpose'],r['repeat'],r['condition']) for r in rows]==[tuple(x) for x in plan['order']]
        assert len({tuple(x) for x in plan['order']})==len(rows)
        assert {p.name for p in directory.iterdir() if p.is_dir()}=={r['run_id'] for r in rows}
        cs={c['id']:c for c in plan['conditions']}; assert len(cs)==len(plan['conditions'])
        environment=read(directory/'environment.json')
        host_overlap[stage]={'observed_at':environment['time'],'other_raytracing_process_present':'RayTracing' in environment['processes']['stdout'],
                             'evidence':str((directory/'environment.json').relative_to(root)).replace('\\','/')}
        observed=collections.defaultdict(list)
        for r in rows:
            assert r['run_id'] not in ids; ids.add(r['run_id'])
            d=directory/r['run_id']; c=cs[r['condition']]; build=plan['builds'][c['build']]
            assert read(d/'metadata.json')==r and read(d/'config.json')==c['config']
            assert r['status']=='completed' and r['included']==(r['purpose']=='timing')
            assert r['binary_sha256']==build['binary_sha256'] and r['source_id']==build['source_id'] and build['validation']['pass']
            assert read(d/'command.txt')['argv'][0]==build['exe']
            if c['build'].startswith('verify-'): assert build['binary_sha256']==builds[c['build'][7:]]['binary_sha256']
            result=read(d/'result.json'); assert result['correctness']['pass'] and r['timing']==result['timing']
            cfg=copy.deepcopy(c['config']); cfg['steal_enabled']=True
            assert result['resolved_config']==cfg and len(result['epochs'])==1
            e=result['epochs'][0]; cr=e['correctness']; n=cfg['workload']['elements']
            assert cr['pass'] and cr['compared_elements']==n and cr['mismatches']==0
            identities[(c['kind'],cfg['workload']['seed'])].add((json.dumps(e['identity'],sort_keys=True),cr['output_hash_fnv1a64']))
            if r['purpose']!='control':
                ref=cfg['measurement']['reference_workers']; tile=1 if c['kind']=='memory' else 256
                assert cr['reference_workers_used']==min(ref,(n+tile-1)//tile) and cr['reference_tile_elements']==tile
                assert all(v>=0 for v in result['phase_seconds'].values()) and sum(result['phase_seconds'].values())<=r['timing']['end_to_end_seconds']+1e-9
            if r['included']: observed[r['condition']].append((r,result))
        for cid,rr in observed.items():
            g=s['groups'][stage][cid]; assert all(g[f]==cs[cid][f] for f in ('kind','build','config','id'))
            assert sorted(r['repeat'] for r,_ in rr)==list(range(1,4 if stage=='V4A-reference-screen' else 6))
            for key,values in (('app',[r['timing']['end_to_end_seconds'] for r,_ in rr]),('epoch',[r['timing']['epoch_seconds'] for r,_ in rr]),
                               ('reference',[x['phase_seconds']['full_reference_verification'] for _,x in rr]),('process',[r['elapsed_process_seconds'] for r,_ in rr])):
                assert g[key]==stats(values)
            assert g['run_paths']==[str((directory/r['run_id']).relative_to(area)).replace('\\','/') for r,_ in rr]
        assert set(observed)==set(s['groups'][stage]); records_by_stage[stage]=rows; processes+=len(rows); timing_count+=sum(r['included'] for r in rows)
    assert all(len(v)==1 for v in identities.values()) and processes==s['processes'] and timing_count==s['timing_samples']
    screen=s['groups']['V4A-reference-screen']; assert len(screen)==20
    for k,v in s['selection'].items():
        eligible=[g for g in screen.values() if g['kind']==k]
        assert {g['config']['measurement']['reference_workers'] for g in eligible}=={1,4,8,16,32}
        winner=min(eligible,key=lambda g:(g['app']['median'],g['id'])); assert all(winner[f]==v['screen_winner'][f] for f in ('kind','build','config','id'))
        lookup={(r['condition'],r['repeat']):r for r in records_by_stage.get('V4B-heldout',[]) if r['included']}
        for h in v['heldout']:
            bg=s['groups']['V4B-heldout'][h['base']['id']]; cg=s['groups']['V4B-heldout'][h['candidate']['id']]
            assert bg==h['base'] and cg==h['candidate']
            pairs=[{'repeat':rep,'base':lookup[(bg['id'],rep)]['timing']['end_to_end_seconds'], 'candidate':lookup[(cg['id'],rep)]['timing']['end_to_end_seconds']} for rep in range(1,6)]
            wins=sum(p['candidate']<p['base'] for p in pairs)
            assert pairs==h['pairs'] and wins==h['wins'] and h['app_speedup']==bg['app']['median']/cg['app']['median']
            assert h['accepted']==(wins>=4 and cg['app']['median']<=.95*bg['app']['median'])
        accepted=winner['config']['measurement']['reference_workers']!=1 and len(v['heldout'])==2 and all(h['accepted'] for h in v['heldout'])
        assert accepted==v['accepted'] and v['reference_workers']==(winner['config']['measurement']['reference_workers'] if accepted else 1)
    # Deliver new configs with exact new binary/source provenance.
    out=root/'configs/verified'; recommendations={}
    for k,v in s['selection'].items():
        cfg=read(root/prior[k]['config']); cfg['measurement']['reference_workers']=v['reference_workers']; save(out/(k+'.json'),cfg)
        name=prior[k]['build']; b=builds[name]
        recommendations[k]={'build':name,'config':f'configs/verified/{k}.json','config_sha256':sha(out/(k+'.json')),
             'binary_sha256':b['binary_sha256'],'source_id':b['source_id'],'snapshot':b['snapshot'], 'cmake_options':b['cmake_options'],
             'reference_workers':v['reference_workers'],'accepted_parallel_reference':v['accepted'], 'evidence_scope':'shared WSL1 host; independent reference verification only'}
    save(out/'builds.json',recommendations)
    lines=['# 第四轮：完整参考核验的并行化','', '2026-10-16。以同一新Release二进制的串行参考核验为对照，优化应用end_to_end_seconds。工作窃取执行epoch仍按原边界单独记录。','',
           f"完成{s['processes']}个研究进程、{s['timing_samples']}个计时样本，包括4个旧Release结果control；另有4个交付配置真实复跑（见recommendation-check目录），不参与选择。",'',
           '运行期间发现另一个32线程光追实验。各批环境快照保留了进程证据；未干预其他任务，全部慢成功样本保留。因此这些是共享主机下的局部结果，不是独占CPU性能验收。','',
           '## 新输入结果','', '|任务|候选核验线程|seed1709 应用ms，串行→并行|seed4001 应用ms，串行→并行|配对胜数|采用|', '|---|---|---|---|---|---|']
    for k,v in s['selection'].items():
        times=[f"{h['base']['app']['median']*1000:.2f}→{h['candidate']['app']['median']*1000:.2f}（{h['app_speedup']:.2f}×）" for h in v['heldout']]
        wins='、'.join(f"{h['wins']}/5" for h in v['heldout'])
        lines.append(f"|{k}|{v['screen_winner']['config']['measurement']['reference_workers']}|{times[0] if times else '同串行'}|{times[1] if times else '同串行'}|{wins or '—'}|{'并行' if v['accepted'] else '串行'}|")
    lines+=['','每类先在seed1237上筛选1/4/8/16/32核验线程，一预热三计时；按应用总耗时中位数选一个候选。新输入seed1709/4001的compute规模196608/393216，memory48/96块。每输入5对AB/BA交替，均需≥4/5对更快且应用中位数至少改善5%；没有选第二名、追跑或修改门槛。该门槛不是显著性检验。', '',
            'light两输入均只有3/5对胜出，第一个输入也未达到5%改善门槛，因此保留串行。uniform/skewed核验32线程，memory核验4线程；它们和被测运行时worker数是不同配置。', '',
            '## 实现与验证', '',
            '每个元素仍由原标量value(i)完整重算；compute固定256元素/tile，memory固定1块/tile，按worker编号条带分配。核验线程只读输入和已完成输出，在64B对齐的私有槽内记录比较/错误数，join后按槽编号归并；最终FNV输出散列始终顺序执行。核验不调用被测Pool，也不复用execute的交错内核或预计算参考结果。线程创建、join和顺序散列全部计入核验及应用时间。', '',
            'reference_workers默认1，只接受整数1..128；活跃线程不超过tile数。新jthread继承控制线程的允许CPU掩码，不沿用被测Pool的逐worker绑定，物理核心驻留未证实。线程创建失败依靠jthread析构join，worker异常保存在私有槽中，join后重抛。运行时源码与上一轮逐字节一致。', '',
            '两个Release、ASan+UBSan和TSan构建均实际通过runtime_checks及独立Python CLI oracle。新增检查覆盖零/单元素、tile边界与尾部、重复核验、多epoch、未执行和部分执行输出的错误检测、非法配置；三个workload的serial/parallel比较数、错误数与散列相同。', '',
            '## 证据与复现', '', '[执行前协议](../../docs/18-第四轮并行核验协议.md)、[完整分组/逐对值](../../verification/results/verification-summary.json)、[新配置](../../configs/verified/README.md)。', '']
    for stage,b in s['batches'].items():
        directory=pathlib.Path(b['path']); lines.append(f"- {stage}：[{directory.name}](../../verification/{directory.as_posix()}/plan.json)，[环境](../../{host_overlap[stage]['evidence']})。")
    lines+=['','原始run路径逐组保存于summary；保存n/median/min/max/IQR、完整时间数组和逐对值，另有epoch、reference及外层process时间。归档保留构建日志、CMakeCache、源码/二进制SHA和原始验证。Windows重新核对Linux导出散列，并从每个结果JSON重算全部选择及门槛。', '',
            '交付配置必须与builds.json指定的新二进制/源码快照配对；configs/refined保留旧版本。新配置执行：`worksteal --config configs/verified/uniform.json`。编译flags见builds.json。重算Linux数据：`python tools/verify_study.py analyze --root /root/lzuhpc-experiments/ws-20261016-verification-study`；核对导出并生成本文：`python tools/report_verify.py --root .`。', '',
            '本轮收益是完整参考核验并行化带来的应用端到端变化，不是工作窃取策略或epoch的倍数提升，不与历史倍数相乘。共享主机、有限样本和WSL1拓扑限制仍存在。轻任务若继续优化，应先研究初始化和身份散列；下一轮独占资源确认应使用新协议和新输入，不改写本轮结果。']
    report=root/'report/verification/第四轮并行核验报告.md'; report.parent.mkdir(parents=True,exist_ok=True); report.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    intro=['# 第四轮当前配置', '', '默认仍串行核验；下表显式设置measurement.reference_workers。性能证据来自共享WSL1主机，存在其他32线程实验干扰；应在独占资源上重新确认。', '',
           '|任务|执行构建|执行worker/grain|核验线程|', '|---|---|---|---|']
    for k,b in recommendations.items():
        c=read(out/(k+'.json')); intro.append(f"|{k}|{b['build']}|{c['workers']}/{c['policies']['partition']['grain']}|{b['reference_workers']}|")
    intro+=['', '使用builds.json记录的verification/evidence源码/二进制快照及CMake选项重新构建；核验线程数是运行时配置。构建后直接运行 `worksteal --config configs/verified/<任务>.json`。', '',
            '[完整报告](../../report/verification/第四轮并行核验报告.md)。每个元素完整重算，最后顺序散列。此改进针对应用核验阶段；执行epoch计时边界不变。历史configs/refined和原始实验保持。']
    (out/'README.md').write_text('\n'.join(intro)+'\n',encoding='utf-8')
    config_checks=[]
    for d in (area/'results').glob('recommendation-check-*'):
        check=read(d/'summary.json'); assert check['pass'] and check['processes']==4
        for r in check['records']:
            assert r['correct'] and r['config_sha256']==recommendations[r['kind']]['config_sha256'] and r['binary_sha256']==recommendations[r['kind']]['binary_sha256']
        config_checks.append(str(d.relative_to(root)).replace('\\','/'))
    audit={'pass':True,'export_file_checks':export_checks,'hash_checks':hash_checks,'processes':processes,'timing_samples':timing_count,
           'builds':builds,'host_overlap':host_overlap,'recommendation_checks':config_checks,
           'files':{str(p.relative_to(root)).replace('\\','/'):sha(p) for p in [report,out/'README.md',out/'builds.json']+list(out.glob('*.json'))}}
    save(area/'results/archive-audit.json',audit)
    print(json.dumps({'pass':True,'hash_checks':hash_checks,'processes':processes,'timing_samples':timing_count,'report':str(report)},ensure_ascii=False))

if __name__=='__main__': main()
