"""Recompute preread contrasts from archived results without running benchmarks."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import statistics
import zipfile


def digest(data):
    return hashlib.sha256(data).hexdigest()


def analyze(repository):
    groups, inputs, binaries, code = [], {}, set(), {}
    for area in ('mechanism-controls', 'large-task-controls'):
        folder = repository / 'supplements' / area
        summary_bytes = (folder / 'summary.json').read_bytes()
        summary = json.loads(summary_bytes)
        inputs[area] = {'summary_sha256': digest(summary_bytes),
                        'archive_sha256': digest((folder / 'experiment.zip').read_bytes())}
        with zipfile.ZipFile(folder / 'experiment.zip') as archive:
            exports = json.loads(archive.read('export-manifest.json'))['files']

            def read(name):
                raw = archive.read(name)
                assert digest(raw) == exports[name], name
                return json.loads(raw)

            assert read('results/summary.json') == summary
            batch = 'runs/' + summary['batch']
            records = {entry['run_id']: entry for entry in read(batch + '/records.json')}
            source = 'snapshots/source/' + summary['source_id'] + '/'
            inputs[area]['source_files'] = {}
            for rel in ('src/app/main.cpp', 'src/workloads/workload.cpp'):
                raw = archive.read(source + rel)
                assert digest(raw) == exports[source + rel]
                inputs[area]['source_files'][rel] = digest(raw)
                if rel in code:
                    assert code[rel] == raw, rel
                code[rel] = raw
            for group in summary['groups']:
                if not group['group'].startswith('preread'):
                    continue
                rows, base_config, identity = {}, None, None
                for row in group['conditions']:
                    samples = {}
                    for sample in row['samples']:
                        path = sample['run_path']
                        record = records[Path(path).parent.name]
                        assert record['purpose'] == 'timing' and record['included']
                        assert record['status'] == 'completed' and record['exit_code'] == 0
                        binaries.add(record['binary_sha256'])
                        result = read(path)
                        assert result == json.loads(archive.read(str(Path(path).with_name('stdout.log')).replace('\\', '/')))
                        assert result['correctness']['pass'] and result['metrics_mode'] == 'timing'
                        epoch = result['epochs'][0]
                        assert epoch['local_only'] and epoch['worker_stats'] is None
                        config = copy.deepcopy(result['resolved_config'])
                        home = config['measurement'].pop('home_worker')
                        target = config['measurement']['controlled_worker']
                        assert home == (target if row['label'] == 'same' else 1 - target)
                        assert config['workers'] == 2 and config['workload']['passes'] == 4
                        assert result['affinity']['actual_workers'] == [[0], [1]]
                        if base_config is None:
                            base_config = config
                        assert config == base_config, group['group']
                        current_identity = [epoch['identity'][k] for k in
                            ('input_hash_fnv1a64', 'data_hash_fnv1a64', 'cost_hash_fnv1a64',
                             'queue_hash_fnv1a64', 'total_cost_units', 'total_data_bytes', 'task_count')]
                        current_identity += [epoch['correctness']['output_hash_fnv1a64'], epoch['pretouch_hash_fnv1a64']]
                        if identity is None:
                            identity = current_identity
                        assert identity == current_identity, path
                        seconds = result['timing']['epoch_seconds']
                        assert seconds == sample['epoch'] == epoch['epoch_seconds']
                        rep = record['repeat']
                        assert rep not in samples
                        samples[rep] = {'repeat': rep, 'seconds': seconds, 'run_path': path,
                                        'result_sha256': exports[path]}
                    assert set(samples) == set(range(1, 6))
                    assert statistics.median(s['seconds'] for s in samples.values()) == row['epoch_median']
                    rows[row['label']] = samples
                assert set(rows) == {'same', 'other'}
                pairs = []
                for rep in range(1, 6):
                    same, other = rows['same'][rep], rows['other'][rep]
                    pairs.append({'repeat': rep, 'same': same, 'other': other,
                                  'other_over_same': other['seconds'] / same['seconds'],
                                  'difference_ms': (other['seconds'] - same['seconds']) * 1000})
                same_med = statistics.median(p['same']['seconds'] for p in pairs)
                other_med = statistics.median(p['other']['seconds'] for p in pairs)
                per_task = base_config['workload']['bytes_per_element']
                groups.append({'area': area, 'group': group['group'], 'executor': target,
                               'per_task_bytes': per_task,
                               'total_data_bytes': per_task * base_config['workload']['elements'],
                               'task_count': base_config['workload']['elements'], 'passes': 4,
                               'same_median_ms': same_med * 1000, 'other_median_ms': other_med * 1000,
                               'ratio_of_medians': other_med / same_med,
                               'paired_ratio_range': [min(p['other_over_same'] for p in pairs),
                                                      max(p['other_over_same'] for p in pairs)],
                               'other_slower_pairs': sum(p['difference_ms'] > 0 for p in pairs),
                               'paired_difference_median_ms': statistics.median(p['difference_ms'] for p in pairs),
                               'pairs': pairs})
    assert len(binaries) == 1 and len(groups) == 8
    assert sum(len(g['pairs']) * 2 for g in groups) == 80
    groups.sort(key=lambda g: (g['per_task_bytes'], g['executor']))
    return {'scope': 'Descriptive reanalysis of 80 existing timing runs; no new benchmark runs.',
            'formal_runs_analyzed': 80, 'paired_blocks': 40, 'groups': groups,
            'input_sha256': inputs, 'binary_sha256': next(iter(binaries)),
            'range_definition': 'Observed minimum and maximum within-block other/same ratios, not a confidence interval.',
            'causal_scope': 'Preread-thread contrast; neither isolated cache loss nor a population equivalence test.'}


def size_label(n):
    return f'{n / 1024**2:g} MiB' if n >= 1024**2 else f'{n / 1024:g} KiB'


def table(data):
    lines = ['|每任务 / 总数据|执行线程|same / ms|other / ms|中位数比|逐对比值范围|other 更慢|',
             '|---|---|---|---|---|---|---|']
    for g in data['groups']:
        lo, hi = g['paired_ratio_range']
        lines.append(f"|{size_label(g['per_task_bytes'])} / {size_label(g['total_data_bytes'])}|"
                     f"{g['executor']}|{g['same_median_ms']:.4f}|{g['other_median_ms']:.4f}|"
                     f"{g['ratio_of_medians']:.3f}|{lo:.3f}-{hi:.3f}|{g['other_slower_pairs']}/5|")
    return '\n'.join(lines)


def document(data):
    return '''# 局部性：预读对照能说明什么

我把两组补测中与预读有关的 80 次计时重新按原来的重复编号配对，检查中位数以外的变化。这里没有新增实验；WorkSteal 的正式计时总数仍为 868。

## 固定了什么

每组固定输入、任务数、任务大小、执行线程、线程绑定、队列和计算内核，只改变预读线程。same 表示由执行线程自己预读，other 表示由另一线程预读。两个执行方向分别比较，不能直接把执行0和执行1当成同一种条件。每个条件五次计时，预热和诊断不计入。

表中“中位数比”为 other 中位数 / same 中位数。“逐对比值”则用原实验同一重复编号下的两次运行计算；这两种统计量不同。范围是五对的实际最小值和最大值，不是置信区间。没有把不同规模、不同执行线程的样本合并做显著性检验。

''' + table(data) + '''

## 结果里需要多看一步的地方

最小数据组中，执行0的两个中位数为 0.1957 和 0.1998 ms，只差 4.1 μs；五对比值却从 0.802 到 1.283，方向并不完全一致。执行1的中位数比又降到 0.956。因此，单看 1.021 这个比值，不足以说明已经测到了稳定的迁移代价。

每任务 288 MiB 的两个方向，中位数比分别为 1.009 和 0.988；other 更慢分别为 4/5 和 2/5 对，逐对比值范围也都跨过 1。每任务 72 KiB 的执行1还有一个例子：中位数比略大于1，但五对中只有两对 other 更慢。中位数之比与逐对差值描述的不是同一件事，不能互相替代。

八组的逐对范围都跨过1。这个结果支持“目前没有观察到跨规模、跨执行方向一致的变慢”，不支持“已经证明两者等价”。每组只有五对，且只测了指定输入与线程组合，也没有事先设定等价界限，不能把这几个百分点当作其他机器或任务的缓存损失上限。

## 为什么这个实验不一定能放大缓存差异

1. **线程不同不保证私有缓存不同。**记录确认了工作线程的逻辑 CPU 掩码是0和1，但 WSL1 下没有确认它们对应不同物理核。若两个逻辑线程共享L1/L2，换线程也未必丢失这部分数据。这个可能性还没有验证，不能写成实际原因。
2. **预读完成不等于任务执行时仍然命中缓存。**程序先预读完整任务集，再准备执行队列。总数据为288 MiB或1152 MiB时，超过报告的36 MiB LLC；数据可能在正式执行前已被后续预读或执行挤出。这里的 home 是预读归属，不是NUMA页归属，也不搬运数据页。
3. **四遍扫描混合了首次访问和后续复用。**内核对一个元素的数组顺序扫描四遍，首次跨核获取若有额外代价，可能被后续计算和访问摊薄。计时没有逐遍拆分，不能把总差值当作首次访问代价，更不能直接乘四来反推。
4. **内存负载不等于已经证实带宽受限。**标量内核逐字递推 `x = (x + data[...] + r) ^ (x >> 7)`，存在计算依赖，顺序访问也可能被预取。没有可靠PMU和独立带宽测量，不能仅凭工作集大就断言DRAM带宽是瓶颈。

这些判断来自实验程序的封存源码和测量方式，是对灵敏度的分析；当前记录没有验证哪一项实际主导了结果。

## 怎样与工作窃取的结果联系

执行线程固定的预读对照关闭了动态窃取，目的是减少负载均衡和迁移调度变化。另做的动态诊断确认三种规模各有46、47、48个任务由非home线程执行；大任务组有3/4个任务被其他线程执行。这些诊断只能证明发生了窃取，不能证明正式计时中每次都具有相同的缓存状态或迁移次数。

大任务的动态 off/on 中位数耗时比约3.60，是并行分担、调度和内存访问的共同结果。它与固定执行线程对照使用的并行度和执行路径不同，不能从中减去1.009或0.988，就算出负载均衡或纯缓存的份额。三个效应之间有交互，不直接相加。

## 下一轮应怎样改

若要继续单独研究缓存，先在原生Linux确认物理核、SMT和缓存共享关系，分别测同核逻辑线程与不同物理核。随后固定执行线程和相同工作量，让一个数据块预读后立即交给执行线程，分别记录首次扫描与后续扫描；同时增加经过检查的热、冷缓存参考，确认探针确实对驻留状态敏感。扫描任务大小时，既覆盖远小于/远大于LLC，也覆盖私有缓存与共享缓存之间的中间区间。

这些是后续改进方向，没有列入本次已完成实验。当前结论仍是：补齐了工作集两端、预读对照和实际窃取检查，但尚未得到可信的纯缓存损失估计。

## 重算与源码

在仓库根目录运行 `python3 tools/analyze_locality.py --check`，可从两组 experiment.zip 的原始 result.json 重算本表，检查同对配置只改变预读归属，核对输入、输出和二进制身份。逐次结果、原始路径和SHA256见 [locality-analysis.json](locality-analysis.json)。封存的 `src/app/main.cpp` 包含预读与执行的先后顺序，`src/workloads/workload.cpp` 包含预读和四遍扫描内核；二者分别保存在两组压缩包的 snapshots/source/ 目录。
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    repo = root / 'github-materials' if (root / 'github-materials').is_dir() else root
    data = analyze(repo)
    outputs = {'locality-analysis.json': json.dumps(data, ensure_ascii=False, indent=2) + '\n',
               'locality-analysis.md': document(data)}
    for name, value in outputs.items():
        path = repo / 'docs' / name
        if args.check:
            assert path.read_text(encoding='utf-8') == value, path
        else:
            path.write_text(value, encoding='utf-8', newline='\n')
    assert all(g['paired_ratio_range'][0] < 1 < g['paired_ratio_range'][1] for g in data['groups'])
    print(json.dumps({'pass': True, 'groups': 8, 'paired_blocks': 40,
                      'existing_timing_runs_analyzed': 80, 'new_experiments': 0}))


if __name__ == '__main__':
    main()
