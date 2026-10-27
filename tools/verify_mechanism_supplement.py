"""Verify the extra experiment independently of the original materials manifest."""
import hashlib
import json
from pathlib import Path
import statistics
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if (ROOT/'github-materials').is_dir():
    ROOT = ROOT/'github-materials'
AREA = ROOT/'supplements/mechanism-controls'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def main():
    manifest = json.loads((AREA/'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['files'].items():
        data = (AREA/name).read_bytes()
        assert len(data) == expected['bytes'] and sha(data) == expected['sha256'], name
    summary = json.loads((AREA/'summary.json').read_text(encoding='utf-8'))
    with zipfile.ZipFile(AREA/'experiment.zip') as z:
        names = z.namelist()
        assert len(names) == len(set(names)) == manifest['archive_members']
        assert all(not n.startswith('/') and '..' not in Path(n).parts for n in names)
        export = json.loads(z.read('export-manifest.json'))
        assert set(names) == set(export['files']) | {'export-manifest.json'}
        for name, expected in export['files'].items():
            assert sha(z.read(name)) == expected, name
        assert json.loads(z.read('results/summary.json')) == summary
        batch = 'runs/' + summary['batch']
        records = json.loads(z.read(batch+'/records.json'))
        assert len(records) == manifest['processes'] == 245
        assert len({r['run_id'] for r in records}) == 245
        formal = {batch+'/'+r['run_id']+'/result.json' for r in records if r['purpose'] == 'timing'}
        assert len(formal) == manifest['timing_samples'] == 175
        linked = set()
        for group in summary['groups']:
            for row in group['conditions']:
                times = []
                for sample in row['samples']:
                    assert sample['run_path'] in formal
                    linked.add(sample['run_path'])
                    r = json.loads(z.read(sample['run_path']))
                    assert r['correctness']['pass'] and r['metrics_mode'] == 'timing'
                    assert r['timing']['epoch_seconds'] == sample['epoch']
                    times.append(sample['epoch'])
                assert len(times) == 5 and statistics.median(times) == row['epoch_median']
        assert linked == formal
        for cid, d in summary['diagnostics'].items():
            if cid.startswith('dynamic-'):
                assert d['steals'] > 0 and d['execution']['element_home_mismatches'] > 0
    with zipfile.ZipFile(AREA/'preflight.zip') as z:
        preflight=json.loads(z.read('export-manifest.json'))
        assert preflight['formal_runs']==0 and preflight['diagnostic_runs']==4
        assert len(z.namelist())==manifest['preflight_archive_members']
        for name,expected in preflight['files'].items():
            assert sha(z.read(name))==expected,name
    print(json.dumps({'pass':True,'processes':245,'formal_runs':175,'hash_checked_files':len(export['files'])}))


if __name__=='__main__':
    main()
