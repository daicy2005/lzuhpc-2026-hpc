"""Read-only integrity and arithmetic checks for the 8x-LLC experiment."""
import hashlib
import json
from pathlib import Path
import statistics
import zipfile

ROOT=Path(__file__).resolve().parents[1]
if (ROOT/'github-materials').is_dir():ROOT=ROOT/'github-materials'
AREA=ROOT/'supplements/large-task-controls'
def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    m=json.loads((AREA/'manifest.json').read_text(encoding='utf-8'))
    for name,info in m['files'].items():
        data=(AREA/name).read_bytes();assert len(data)==info['bytes'] and sha(data)==info['sha256'],name
    summary=json.loads((AREA/'summary.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(AREA/'experiment.zip') as z:
        names=z.namelist();assert len(names)==len(set(names))==m['archive_members']
        export=json.loads(z.read('export-manifest.json'))
        assert set(names)==set(export['files'])|{'export-manifest.json'}
        for name,expected in export['files'].items():assert sha(z.read(name))==expected,name
        assert json.loads(z.read('results/summary.json'))==summary
        batch='runs/'+summary['batch'];records=json.loads(z.read(batch+'/records.json'))
        assert len(records)==42 and len({r['run_id'] for r in records})==42
        formal={batch+'/'+r['run_id']+'/result.json' for r in records if r['purpose']=='timing'}
        assert len(formal)==30
        linked=set()
        for g in summary['groups']:
            for row in g['conditions']:
                times=[]
                for sample in row['samples']:
                    assert sample['run_path'] in formal;linked.add(sample['run_path'])
                    r=json.loads(z.read(sample['run_path']))
                    assert r['metrics_mode']=='timing' and r['correctness']['pass']
                    assert r['epochs'][0]['identity']['per_element_bytes']==288*1024**2
                    assert r['timing']['epoch_seconds']==sample['epoch'];times.append(sample['epoch'])
                assert len(times)==5 and statistics.median(times)==row['epoch_median']
        assert linked==formal
        d=summary['diagnostics']['large-dynamic-on']
        assert d['steals']>0 and d['execution']['element_home_mismatches']>0
    print(json.dumps({'pass':True,'formal_runs':30,'all_runs':42,'per_task_to_llc':8,'files_checked':len(export['files'])}))
if __name__=='__main__':main()
