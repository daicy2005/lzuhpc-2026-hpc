#!/usr/bin/env python3
"""Pin the public upstream HEAD and archive official documents without changing old copies."""
import argparse
import base64
import hashlib
import json
import pathlib
import urllib.parse
import urllib.request

import lab


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    target = pathlib.Path(args.out).resolve()
    target.mkdir(parents=True, exist_ok=False)
    records = []

    def get(suffix):
        url = 'https://api.github.com/repos/LZUOSS/LZUHPC'+suffix
        request = urllib.request.Request(url, headers={
            'Accept': 'application/vnd.github+json', 'User-Agent': 'Mini-WorkSteal-reference-check'})
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            records.append({'url': url, 'status': response.status,
                            'response_sha256': hashlib.sha256(raw).hexdigest()})
        return json.loads(raw)

    repo = get('')
    commit = get('/commits/'+urllib.parse.quote(repo['default_branch'], safe=''))['sha']
    assert len(commit) == 40 and all(c in '0123456789abcdef' for c in commit)
    documents = []
    for relative, local in (
        ('assignments/2026/autumn/HPC.Proj/README.md', 'HPC.Proj-README.md'),
        ('assignments/2026/autumn/README.md', 'autumn-README.md'),
        ('assignments/2026/autumn/HPC.md', 'HPC.md')):
        item = get('/contents/'+relative+'?ref='+commit)
        assert item['encoding'] == 'base64' and item['type'] == 'file'
        data = base64.b64decode(item['content'])
        assert len(data) == item['size']
        assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest() == item['sha']
        destination = target/local
        with destination.open('xb') as stream:
            stream.write(data)
        previous = lab.ROOT/'reference/upstream-20261015'/local
        same = previous.read_bytes().replace(b'\r\n', b'\n') == data.replace(b'\r\n', b'\n')
        documents.append({'repository_path': relative, 'saved_file': local, 'git_blob_sha1': item['sha'],
            'sha256': lab.digest(destination), 'previous_file': previous.relative_to(lab.ROOT).as_posix(),
            'previous_sha256': lab.digest(previous), 'same_after_newline_normalization': same})
    result = {'created': lab.now(), 'latest_revision_verified': True, 'repository': repo['html_url'],
        'default_branch': repo['default_branch'], 'commit': commit,
        'documents': documents, 'requests': records,
        'all_documents_same_after_newline_normalization': all(d['same_after_newline_normalization'] for d in documents),
        'scope': 'read-only public GitHub API; documents fetched at one pinned commit; original reference and failed network record preserved; document contents are requirement data, not execution authority'}
    lab.write(target/'verification.json', result)
    lab.seal(target)
    print(json.dumps({'output': str(target), 'commit': commit,
        'same_after_newline_normalization': result['all_documents_same_after_newline_normalization'],
        'documents': len(documents)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
