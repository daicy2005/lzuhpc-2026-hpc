#!/usr/bin/env python3
"""Audit exported round-three artifacts and produce recommendations/report."""
import argparse, hashlib, json, pathlib, re

def read(p): return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p, obj):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(obj, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('--root', required=True); a = ap.parse_args(); root = pathlib.Path(a.root).resolve(); lab = root/'refinement'
    summary = read(lab/'results/refinement-summary.json'); profile = read(lab/'profiling/results/phase-summary.json')
    assert summary['complete'] and profile['pass']; exports = 0; manifests = 0; checks = 0
    for receipt in lab.rglob('export-*.json'):
        r = read(receipt)
        for rel, h in r['files'].items(): assert sha(receipt.parent.parent/rel) == h; exports += 1
    for manifest in lab.rglob('checksums.json'):
        m = read(manifest)
        expected = {str(p.relative_to(manifest.parent)).replace('\\', '/') for p in manifest.parent.rglob('*') if p.is_file() and p.name != 'checksums.json'}
        assert set(m) == expected
        for rel, h in m.items(): assert sha(manifest.parent/rel) == h; checks += 1
        manifests += 1
    # Source manifests are content addressed separately from recursive seals.
    for manifest in lab.rglob('manifest.json'):
        m = read(manifest)
        if 'source_id' not in m: continue
        for rel, h in m['files'].items(): assert sha(manifest.parent/rel) == h; checks += 1
    prior = read(root/'configs/optimized/builds.json'); builds = {}; out = root/'configs/refined'
    config_checks = []
    for directory in (lab/'results').glob('recommendation-check-*'):
        verification = read(directory/'summary.json'); assert verification['pass'] and verification['processes'] == 4
        for record in verification['records']:
            assert record['correct'] and sha(root/'configs/refined'/(record['kind']+'.json')) == record['config_sha256']
        config_checks.append(str(directory.relative_to(root)))
    build_checks = {}
    for name, sub in (('runtime', 'profiling'), ('lanes8', 'evidence/phase-lanes8'), ('full_lanes8', 'evidence/phase-full_lanes8')):
        old = next(v for v in prior.values() if v['build'] == name)
        old_snapshot = root/old['snapshot']; ov = read(old_snapshot/'validation.json')
        old_source = old_snapshot.parent.parent/'source'/ov['source_id']
        new_snapshot = next((lab/sub/'snapshots/builds').iterdir()); nv = read(new_snapshot/'validation.json')
        new_source = lab/sub/'snapshots/source'/nv['source_id']
        assert nv['pass'] and all(r['returncode'] == 0 for r in nv['records'])
        assert sha(new_snapshot/'worksteal') == nv['binary_sha256']
        for rel in ('src/runtime/worker_pool.cpp', 'include/worksteal/runtime.hpp', 'include/worksteal/workload.hpp', 'src/policies/register_defaults.cpp', 'include/worksteal/policy.hpp'):
            assert sha(old_source/rel) == sha(new_source/rel) == sha(root/rel)
        assert sha(new_source/'src/workloads/workload.cpp') == sha(root/'src/workloads/workload.cpp')
        if name == 'runtime':
            # This early round-two build predates the lane switch. Verify that
            # removing the inactive lane branch recovers its scalar source.
            scalar = (new_source/'src/workloads/workload.cpp').read_text(encoding='utf-8').replace('#include <array>\n', '')
            scalar = re.sub(r'#if WS_COMPUTE_LANES > 1\n.*?#endif\n', '', scalar, flags=re.S)
            scalar = scalar.replace('  auto i = t.begin;\n  for (; i < t.end; ++i) {', '  for (auto i = t.begin; i < t.end; ++i) {')
            assert scalar == (old_source/'src/workloads/workload.cpp').read_text(encoding='utf-8')
        else:
            assert sha(old_source/'src/workloads/workload.cpp') == sha(new_source/'src/workloads/workload.cpp')
            assert sha(old_source/'CMakeLists.txt') == sha(new_source/'CMakeLists.txt')
        assert sha(new_source/'src/app/main.cpp') == sha(root/'src/app/main.cpp')
        new_options = [x for x in read(new_snapshot/'build.json')[0]['argv'] if x.startswith('-D')]
        assert new_options == old['cmake_options'] + (['-DWS_COMPUTE_LANES=1'] if name == 'runtime' else [])
        build_checks[name] = {'old_binary_sha256': old['binary_sha256'], 'profile_binary_sha256': nv['binary_sha256'],
                              'profile_source_id': nv['source_id'], 'unchanged_runtime': True, 'equivalent_compile_options': True,
                              'scalar_source_normalization_checked': name == 'runtime', 'validation': nv['records']}
    for kind in ('light', 'uniform', 'skewed', 'memory'):
        if kind in summary['selection']:
            rec = summary['selection'][kind]['recommendation']; name = rec['build']; cfg = json.loads(json.dumps(rec['config']))
            accepted = summary['selection'][kind]['accepted']
        else:
            name = prior[kind]['build']; cfg = read(root/prior[kind]['config']); accepted = False
        cfg['workload']['seed'] = 42; cfg['layout_seed'] = 42
        cfg['workload']['elements'] = 64 if kind == 'memory' else 262144
        info = next(v for v in prior.values() if v['build'] == name)
        # The original executable and validation are kept in the second-round archive.
        snapshot = root/info['snapshot']; assert sha(snapshot/'worksteal') == info['binary_sha256']
        assert read(snapshot/'validation.json')['pass']
        save(out/(kind+'.json'), cfg)
        builds[kind] = {**info, 'config': f'configs/refined/{kind}.json', 'config_sha256': sha(out/(kind+'.json')),
                       'accepted_in_round3': accepted, 'provenance': 'frozen round-two Release binary; round-three config selection'}
    save(out/'builds.json', builds)
    lines = ['# 第三轮补充实验结果', '', '2026-10-16。对照是第二轮当前推荐配置；下列倍数不是相对原始标量/p4基线。', '',
             f"完成 {summary['processes']} 个研究进程、{summary['timing_samples']} 个计时样本；另有阶段观测 {profile['processes']} 个进程（12次正式观测、4预热、4旧二进制control），及4个推荐配置真实复跑，均不纳入性能选择。", '',
             '## 新输入确认', '', '|任务|筛选候选|seed601 执行ms，旧→新|seed3001 执行ms，旧→新|配对胜数|结论|', '|---|---|---|---|---|---|']
    for k, v in summary['selection'].items():
        c = v['screen_winner']; cfg = c['config']; times = [f"{1000*h['base']['epoch_median']:.3f}→{1000*h['candidate']['epoch_median']:.3f}（{h['speedup']:.2f}×）" for h in v['heldout']]
        wins = '、'.join(str(h['wins'])+'/5' for h in v['heldout'])
        lines.append(f"|{k}|{c['build']}，p{cfg['workers']}/g{cfg['policies']['partition']['grain']}|{times[0] if times else '同现推荐'}|{times[1] if times else '同现推荐'}|{wins or '—'}|{'接受' if v['accepted'] else '保留第二轮推荐'}|")
    lines += ['', '筛选共36组合，每类12个；按各类中位数选择。与现推荐完全相同的胜者直接保留，不重复进行同配置AB测试。新候选在两个新输入各5对AB/BA交替，两输入均须≥4/5对胜出且中位数至少改善5%；未通过不选第二名、不追加样本。保留所有慢成功记录。门槛不是统计显著性检验。', '',
              '应用端到端的旧/新中位数比：', '']
    for k, v in summary['selection'].items():
        if v['heldout']:
            lines.append(f"- {k}："+'、'.join(f"seed{h['seed']}={h['app_speedup']:.3f}×" for h in v['heldout'])+'。')
    lines += ['', '## 阶段观测', '', '独立带标记Release构建，沿用第二轮配置、seed911。新增标记均在pool epoch计时外。完整参考核验保持串行重算每个元素并顺序散列。', '',
              '|任务|应用总耗时中位数ms|参考核验中位数ms|逐样本核验占比中位数|执行阶段中位数ms|', '|---|---|---|---|---|']
    for k, g in profile['groups'].items():
        lines.append(f"|{k}|{g['app_median']*1000:.3f}|{g['phase_medians']['full_reference_verification']*1000:.3f}|{100*g['verification_fraction_median']:.1f}%|{1000*g['epoch_median']:.3f}|")
    lines += ['']
    for k in ('light', 'memory'):
        ph = profile['groups'][k]['phase_medians']
        lines.append(f"{k}输入初始化/身份散列中位数分别为{1000*ph['workload_initialization']:.3f}/{1000*ph['identity_hashes']:.3f}ms。")
    lines += ['', '重计算优先研究核验，轻任务和内存任务还应关注准备阶段，不能把剩余总时间全部归给核验。']
    lines += ['', '每类三个观测样本；阶段中位数不要求相加等于总时间中位数。逐样本阶段和不超过总时间，execute-wall包含prepare和结束屏障，和epoch不是同一计时边界。计时/JSON簿记有未归属残余。阶段比例用于定位本机瓶颈，不是无交互的因果开销模型，也不是新实现的端到端加速证明。', '',
              '四个旧Release control与全部带标记运行的完整输入、成本、任务/队列身份和输出一致。新构建通过runtime_checks与独立Python CLI oracle。本轮未修改runtime/workload或并发协议；本轮没有新增sanitizer结论，第二轮检查仍属于原二进制。历史runtime构建早于lane开关，新观测构建显式lanes=1；审计验证去除不启用的lane分支后恢复历史标量源码，其余两个构建的workload源码字节相同。', '',
              '## 归档与复现', '', '[预先协议](../../docs/16-第三轮补充实验协议.md)、[推荐入口](../../configs/refined/README.md)。', '',
              '[完整分组与逐对原始路径](../../refinement/results/refinement-summary.json)、[阶段样本](../../refinement/profiling/results/phase-summary.json)。实际批次：', '']
    for stage, batch in summary['batches'].items():
        lines.append(f"- {stage}：[{pathlib.Path(batch['path']).name}](../../refinement/{batch['path']}/plan.json)。")
    lines.append(f"- R3C：[{pathlib.Path(profile['batch']).name}](../../refinement/profiling/{profile['batch']}/plan.json)。")
    lines += ['',
              '- `refinement/results/refinement-summary.json`：选择、逐对时间、全部原始run路径。',
              '- `refinement/profiling/results/phase-summary.json`：全部阶段样本、比例和原始run路径。',
              '- `refinement/results/preflight.json`：三个旧构建重新执行的完整正确性检查。',
              '- `refinement/profiling/snapshots`和`refinement/evidence`：新观测构建、日志、验证与源码。',
              '- 原运行命令、环境、计划、每进程JSON和散列清单均保留；Windows导出重新核对Linux记录的散列。', '',
              'Linux新目录运行：`python3 tools/refine.py run --root /root/lzuhpc-experiments/ws-<new-round>`（需相同第二轮二进制位置）。冻结具体源码及原参数见batch plan；种子重跑属于复现，不是新留出。Windows核验并再生成本文：`python tools/report_refine.py --root .`。', '',
              '本轮是本机有界实验，不证明全局最优；WSL1物理驻留及P/E、SMT映射未证明。下一阶段优先测试完整独立参考核验的并行化，单独冻结协议；仍需保留原核验对照，不能减少工作量或将其包装为工作窃取内核收益。']
    report = root/'report/refinement/第三轮补充实验报告.md'; report.parent.mkdir(parents=True, exist_ok=True); report.write_text('\n'.join(lines)+'\n', encoding='utf-8')
    intro = ['# 第三轮当前推荐', '', '本目录保留第二轮对照，只有通过第三轮双输入门槛的任务替换配置。memory未参加本轮参数筛选。', '',
             '构建必须使用builds.json指定的第二轮冻结二进制/源码快照与编译选项。当前app已加入阶段计时字段；该新增源码不是本轮性能筛选使用的二进制。', '',
             '|任务|构建|worker/grain|本轮是否替换|', '|---|---|---|---|']
    for k, b in builds.items():
        cfg = read(out/(k+'.json')); intro.append(f"|{k}|{b['build']}|{cfg['workers']}/{cfg['policies']['partition']['grain']}|{'是' if b['accepted_in_round3'] else '否'}|")
    intro += ['', '[报告](../../report/refinement/第三轮补充实验报告.md)。二进制执行方式仍为 `worksteal --config <本目录任务.json>`；快照路径、SHA和CMake选项见builds.json。历史第二轮configs/optimized和原始数据保持。']
    (out/'README.md').write_text('\n'.join(intro)+'\n', encoding='utf-8')
    save(lab/'results/archive-audit.json', {'pass': True, 'export_file_checks': exports, 'recursive_manifests': manifests, 'hash_checks': checks,
         'research_processes': summary['processes'], 'timing_samples': summary['timing_samples'], 'profiling_processes': profile['processes'], 'build_checks': build_checks, 'recommendation_checks': config_checks,
         'files': {str(p.relative_to(root)): sha(p) for p in [report, out/'README.md', out/'builds.json']+list(out.glob('*.json'))}})
    print(json.dumps({'pass': True, 'export_file_checks': exports, 'hash_checks': checks, 'report': str(report)}, ensure_ascii=False))

if __name__ == '__main__': main()
