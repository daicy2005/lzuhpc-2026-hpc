#!/usr/bin/env python3
"""Regenerate evidence-linked statistics without modifying sealed raw records."""
import argparse, collections, hashlib, json, math, pathlib, statistics, sys

def load(path):return json.loads(path.read_text(encoding='utf-8-sig'))
def quantile(v,q):
    v=sorted(v);t=(len(v)-1)*q;lo=math.floor(t);hi=math.ceil(t);return v[lo]+(v[hi]-v[lo])*(t-lo)
def stats(values):return {'n':len(values),'median':statistics.median(values),'min':min(values),'max':max(values),'iqr':quantile(values,.75)-quantile(values,.25),'values':values}

def audit_plan(directory,plan,done,records):
    """Check exact frozen order, repeats, effective configs and process coverage."""
    assert done['status']=='completed' and done['processes']==len(records)
    assert len({r['run_id'] for r in records})==len(records)
    run_dirs={p.name for p in directory.iterdir() if p.is_dir() and (p/'metadata.json').exists()}
    assert run_dirs=={r['run_id'] for r in records}
    planned=[tuple(x) for x in plan['order']]
    actual=[(r['purpose'],r['repeat'],r['condition']) for r in records if r['purpose'] in ('warmup','timing')]
    assert actual==planned, 'frozen execution order mismatch'
    assert len(planned)==len(set(planned)), 'duplicate planned repeat'
    configs={c['id']:c['config'] for c in plan['conditions']}
    diagnostics={c['id']:c['config'] for c in plan.get('diagnostics',[])}
    calibration=None
    if plan['experiment']=='W00_W01':
        calibration=load(directory/'calibration_selection.json')['selected_k']
        expected_dev=[f'W00-{m}-n{n}-g{g}' for m in ('serial','static','central','off','on') for n,g in ((0,1),(1,1),(3,64),(31,7))]
        candidates=plan['calibration_candidates'];idx=candidates.index(calibration)
        expected_dev += ['calibration-K'+str(k) for k in candidates[:idx+1]]
        assert [r['condition'] for r in records if r['purpose']=='development']==expected_dev
        expected_diag=[f'diag-{m}-p4-g{g}' for m in ('off','on') for g in (1,4096)]
        assert [r['condition'] for r in records if r['purpose']=='diagnostic']==expected_diag
        last=next(r for r in records if r['condition']=='calibration-K'+str(calibration))
        lo,hi=plan['calibration_target'];assert lo<=last['timing']['epoch_seconds']<=hi
    else:
        assert [r['condition'] for r in records if r['purpose']=='diagnostic']==list(diagnostics)
        checks={c['id']:c['config'] for c in plan.get('checks',[])}
        assert [r['condition'] for r in records if r['purpose']=='development']==list(checks)
    for rec in records:
        assert rec['purpose'] in ('warmup','timing','diagnostic','development')
        assert rec['included']==(rec['purpose']=='timing')
        assert rec['binary_sha256']==plan['binary_sha256'] and rec['source_id']==plan['source_id']
        actual_config=load(directory/rec['run_id']/'config.json')
        if rec['purpose'] in ('warmup','timing'):
            expected=json.loads(json.dumps(configs[rec['condition']]))
            if calibration is not None:expected['workload']['iterations']=calibration
            assert actual_config==expected, 'effective config differs from frozen plan'
        elif rec['purpose']=='diagnostic' and diagnostics:
            expected=json.loads(json.dumps(diagnostics[rec['condition']]));expected['measurement']['mode']='diagnostic'
            assert actual_config==expected
        elif rec['purpose']=='development' and plan.get('checks'):
            assert actual_config==checks[rec['condition']]
    validation=load(directory/'validation.json');assert validation['pass'] and validation['binary_sha256']==plan['binary_sha256']
    return {'batch':directory.name,'exact_order':True,'unique_run_ids':True,'planned_processes':len(records),'pass':True}
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',required=True);ap.add_argument('--out',required=True);a=ap.parse_args();root=pathlib.Path(a.root);out=pathlib.Path(a.out);out.mkdir(parents=True,exist_ok=True)
    batches={};groups=[];integrity=[];raw_records=[];plan_audits=[]
    for directory in sorted((root/'runs').iterdir()):
        if not (directory/'completion.json').exists():continue
        plan=load(directory/'plan.json');done=load(directory/'completion.json');experiment=plan['experiment']
        if experiment in batches:raise ValueError('more than one batch for experiment; explicitly curate an index before comparing')
        records=load(directory/'records.json');condition_groups=collections.defaultdict(list);details={};identities={}
        plan_audits.append(audit_plan(directory,plan,done,records))
        for rec in records:
            rd=directory/rec['run_id'];metadata=load(rd/'metadata.json');assert metadata==rec
            if rec['status']!='completed':raise ValueError('failed formal batch not eligible: '+str(directory))
            result=load(rd/'result.json');assert result['correctness']['pass']
            for epoch in result['epochs']:assert epoch['correctness']['pass']
            if rec['purpose']=='timing' and rec['included']:
                signature={'resolved_config':result['resolved_config'],'identity':result['epochs'][0]['identity'],'output':[e['correctness'] for e in result['epochs']]}
                if rec['condition'] in identities:assert signature==identities[rec['condition']], 'within-group identity drift'
                identities[rec['condition']]=signature
                condition_groups[rec['condition']].append(rec);details[rec['condition']]=result
            raw_records.append({'path':str(rd.relative_to(root)),**rec})
        manifest=load(directory/'checksums.json')
        for rel,expected in manifest.items():
            actual=hashlib.sha256((directory/rel).read_bytes()).hexdigest()
            if actual!=expected:raise ValueError('checksum mismatch '+str(directory/rel))
        for nested in directory.glob('*/checksums.json'):
            inner=load(nested)
            for rel,expected in inner.items():assert hashlib.sha256((nested.parent/rel).read_bytes()).hexdigest()==expected
            assert set(inner)=={str(p.relative_to(nested.parent)).replace('\\','/') for p in nested.parent.iterdir() if p.is_file() and p.name!='checksums.json'}
        actual_files={str(p.relative_to(directory)).replace('\\','/') for p in directory.rglob('*') if p.is_file() and p.name!='checksums.json'}
        assert actual_files=={p.replace('\\','/') for p in manifest}, 'unsealed or missing batch file'
        integrity.append({'batch':directory.name,'verified_files':len(manifest),'pass':True})
        batch={'id':directory.name,'path':str(directory.relative_to(root)),'plan':plan,'completion':done,'groups':{},'diagnostics':{}}
        for cid,recs in condition_groups.items():
            hashes={r['binary_sha256'] for r in recs};assert len(hashes)==1
            result=details[cid];g={'batch_id':directory.name,'experiment':experiment,'condition':cid,'binary_sha256':next(iter(hashes)),
               'resolved_config':result['resolved_config'],'identity':result['epochs'][0]['identity'],
               'epoch_seconds':stats([r['timing']['epoch_seconds'] for r in recs]),
               'end_to_end_seconds':stats([r['timing']['end_to_end_seconds'] for r in recs]),
               'run_paths':[str((directory/r['run_id']).relative_to(root)) for r in recs]}
            groups.append(g);batch['groups'][cid]=g
        for rec in records:
            if rec['purpose']=='diagnostic':batch['diagnostics'][rec['condition']]=load(directory/rec['run_id']/'result.json')
        assert done['status']=='completed';batches[experiment]=batch
    required={'W00_W01','W02','W03','W04','W05-confirm'};missing=sorted(required-set(batches))
    claims=[];selection={}
    if 'W00_W01' in batches:
        b=batches['W00_W01'];base=b['groups']['S0'];identity=[g['identity'] for g in b['groups'].values()]
        assert len({(i['input_hash_fnv1a64'],i['cost_hash_fnv1a64'],i['total_cost_units']) for i in identity})==1
        best=min((g for g in b['groups'].values() if g['resolved_config']['workers']==4),key=lambda g:g['epoch_seconds']['median'])
        claims.append({'id':'W01_best_observed','text':'best observed screening condition only, not confirmed optimum','condition':best['condition'],'speedup_vs_S0':base['epoch_seconds']['median']/best['epoch_seconds']['median'],'groups':[base['condition'],best['condition']],'batch':b['id']})
    if 'W02' in batches:
        b=batches['W02'];identity=[g['identity'] for g in b['groups'].values()]
        assert len({(i['input_hash_fnv1a64'],i['cost_hash_fnv1a64'],i['total_cost_units']) for i in identity})==1
        for layout in ('concentrated','spread','shuffled'):
            off=b['groups'][layout+'-off'];on=b['groups'][layout+'-on'];assert off['identity']['queue_hash_fnv1a64']==on['identity']['queue_hash_fnv1a64']
            claims.append({'id':'W02_'+layout,'speedup_off_over_on':off['epoch_seconds']['median']/on['epoch_seconds']['median'],'off_seconds':off['epoch_seconds']['median'],'on_seconds':on['epoch_seconds']['median'],'groups':[off['condition'],on['condition']],'batch':b['id']})
    if 'W03' in batches:
        b=batches['W03']
        for scale in ('small','middle','large'):
            for layout in ('policy','concentrated'):
                off=b['groups'][f'{scale}-{layout}-off'];on=b['groups'][f'{scale}-{layout}-on'];assert off['identity']==on['identity']
                claims.append({'id':f'W03_{scale}_{layout}','speedup_off_over_on':off['epoch_seconds']['median']/on['epoch_seconds']['median'],'off_seconds':off['epoch_seconds']['median'],'on_seconds':on['epoch_seconds']['median'],'groups':[off['condition'],on['condition']],'batch':b['id'],'causal_limit':'worker migration/time association, no PMU or verified physical residency'})
            for home in (0,1):
                same=b['groups'][f'{scale}-controlled-h{home}-e{home}'];foreign=b['groups'][f'{scale}-controlled-h{home}-e{1-home}']
                claims.append({'id':f'W03a_{scale}_home{home}','foreign_over_home':foreign['epoch_seconds']['median']/same['epoch_seconds']['median'],'home_seconds':same['epoch_seconds']['median'],'foreign_seconds':foreign['epoch_seconds']['median'],'groups':[same['condition'],foreign['condition']],'batch':b['id'],'causal_limit':'no stable physical affinity; not a cache-miss causal estimate'})
    if 'W05-confirm' in batches:
        b=batches['W05-confirm'];recs=load(root/b['path']/'records.json');selected=b['plan']['selected']
        for kind,candidate in selected.items():
            inputs=[]
            for seed in (73,991):
                base=b['groups'][f'{kind}-s{seed}-base'];cand=b['groups'][f'{kind}-s{seed}-candidate'];off=b['groups'][f'{kind}-s{seed}-off']
                rr={}
                for r in recs:
                    if r['purpose']=='timing':rr[(r['condition'],r['repeat'])]=r['timing']['epoch_seconds']
                wins=sum(rr[(f'{kind}-s{seed}-candidate',r)]<rr[(f'{kind}-s{seed}-base',r)] for r in range(1,6))
                ratio=base['epoch_seconds']['median']/cand['epoch_seconds']['median'];accept=candidate!='base' and wins>=4 and cand['epoch_seconds']['median']<=.95*base['epoch_seconds']['median']
                inputs.append({'seed':seed,'candidate':candidate,'wins_of_5':wins,'base_over_candidate':ratio,'accepted':accept,'base_median_seconds':base['epoch_seconds']['median'],'candidate_median_seconds':cand['epoch_seconds']['median'],'off_over_default':off['epoch_seconds']['median']/base['epoch_seconds']['median'],'groups':[base['condition'],cand['condition'],off['condition']]})
            final=candidate if all(x['accepted'] for x in inputs) else 'base'
            selection[kind]={'screening_candidate':candidate,'selected':final,'heldout':inputs,'reason':'accepted on both held-out inputs' if final!='base' else 'retain simpler default; candidate did not meet every predeclared gate','batch':b['id']}
    result={'complete':not missing,'missing_experiments':missing,'batches':{key:{'id':b['id'],'completion':b['completion'],'plan':b['plan']} for key,b in batches.items()},'integrity':integrity,'plan_audits':plan_audits,'groups':groups,'claims':claims,'selection':selection,'total_formal_processes':len(raw_records),'limits':['WSL1 logical masks; physical placement unproven','36 MiB LLC from CPUID and Windows total, no PMU','finite predeclared search, no global optimum claim','screening n=3; held-out n=5; engineering gate is not significance test']}
    (out/'study-summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    (out/'runs.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in raw_records),encoding='utf-8')
    print(json.dumps({'complete':result['complete'],'missing':missing,'processes':len(raw_records),'selection':selection},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
