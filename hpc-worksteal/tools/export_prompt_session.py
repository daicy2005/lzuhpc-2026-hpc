#!/usr/bin/env python3
"""Export actual visible messages from one continuous local Session, never reasoning."""
import argparse
import collections
import datetime
import hashlib
import json
import pathlib
import re

import lab


def extract(data, expected):
    assert data.endswith(b'\n'), 'capture must end at a complete source record'
    messages, counts, sessions, visible_events = [], collections.Counter(), [], []
    for lineno, line in enumerate(data.splitlines(), 1):
        row = json.loads(line)
        payload = row.get('payload', {})
        item = payload.get('item', {})
        if row.get('type') == 'event_msg' and payload.get('type') == 'item_completed' and item.get('type') in ('UserMessage', 'AgentMessage'):
            role = 'user' if item['type'] == 'UserMessage' else 'assistant'
            text = '\n'.join(b.get('text', '') for b in item.get('content', []))
            visible_events.append((role, hashlib.sha256(text.encode()).hexdigest()))
        if row.get('type') == 'session_meta':
            sessions.append(payload['id'])
        if row.get('type') != 'response_item' or payload.get('type') != 'message':
            counts[row.get('type', 'unknown')] += 1
            continue
        role, channel = payload.get('role'), payload.get('channel')
        if role not in ('user', 'assistant') or channel not in (None, 'final', 'commentary'):
            counts['nonvisible_message'] += 1
            continue
        # Preserve original visible blocks. Image blocks stay attachments, not invented OCR.
        blocks = payload.get('content', [])
        assert all(b.get('type') in ('input_text', 'output_text', 'input_image') for b in blocks), 'unknown visible content block'
        messages.append({'source_line': lineno, 'timestamp': row.get('timestamp'),
                         'role': role, 'channel': channel, 'content': blocks})
    assert sessions == [expected], 'must export exactly one requested Session'
    assert messages and messages[0]['role'] == 'user'
    represented = collections.Counter((m['role'], hashlib.sha256(
        '\n'.join(b.get('text', '') for b in m['content']).encode()).hexdigest()) for m in messages)
    assert not (collections.Counter(visible_events) - represented), 'a visible UI message is missing from response items'
    counts['ui_visible_message_events'] = len(visible_events)
    counts['ui_message_events_missing_in_response_items'] = 0
    # Refuse to publish common credential forms; never print matched values.
    text = json.dumps(messages, ensure_ascii=False)
    patterns = (r'\bsk-[A-Za-z0-9_-]{20,}', r'\bgh[pousr]_[A-Za-z0-9]{20,}',
                r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
    assert not any(re.search(p, text) for p in patterns), 'possible credential in visible transcript; inspect privately before export'
    return messages, dict(counts)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--source', required=True)
    p.add_argument('--session-id', required=True)
    p.add_argument('--out', required=True)
    args = p.parse_args()
    source, target = pathlib.Path(args.source), pathlib.Path(args.out)
    size = source.stat().st_size
    with source.open('rb') as f:
        data = f.read(size)
    assert len(data) == size
    # A running Session may append after this prefix; it is explicitly an as-of export.
    messages, excluded = extract(data, args.session_id)
    digest = hashlib.sha256(data).hexdigest()
    with source.open('rb') as f:
        assert hashlib.sha256(f.read(size)).hexdigest() == digest
    target.mkdir(parents=True, exist_ok=False)
    export = {'session_id': args.session_id, 'scope': 'all actual visible user/assistant messages from Session start through captured prefix; no reasoning, tools, system/developer messages or other Sessions',
              'captured_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'messages': messages}
    lab.write(target/'prompt-response.json', export)
    lines = ['# 完整连续 Session 的可见 Prompt / Agent Response', '',
             f"Session：`{args.session_id}`。从原始Session起点连续导出至 {messages[-1]['timestamp']}；这是进行中Session的截至时刻快照，后续新增消息不在本快照内。", '',
             '只提取原始用户消息和可见Agent响应；排除思维链、工具内部记录、系统/开发者消息与其他Session。未用摘要补写、删选实验轮次或拼接对话。结构化原件为同目录prompt-response.json，逐消息保留来源行号。', '']
    for index, message in enumerate(messages, 1):
        lines += [f"## {index}. {message['role']} | {message['timestamp']} | source line {message['source_line']}", '']
        for block in message['content']:
            if block['type'] in ('input_text', 'output_text'):
                lines += [block['text'], '']
            else:
                lines += ['[原始图片附件：结构化文件保留原始input_image块；此处不替换为OCR或文字描述。]', '']
    (target/'prompt-response.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    manifest = {'session_id': args.session_id, 'source_filename': source.name,
        'source_prefix_bytes': size, 'source_prefix_sha256': digest, 'source_lines': len(data.splitlines()),
        'first_message_timestamp': messages[0]['timestamp'], 'last_message_timestamp': messages[-1]['timestamp'],
        'visible_messages': len(messages), 'roles': dict(collections.Counter(m['role'] for m in messages)),
        'excluded_record_counts': excluded, 'no_reasoning_exported': True,
        'files': {f.name: lab.digest(f) for f in target.iterdir() if f.is_file()}}
    lab.write(target/'manifest.json', manifest)
    reread = json.loads((target/'prompt-response.json').read_text(encoding='utf-8'))
    assert reread['messages'] == extract(data, args.session_id)[0]
    assert [m['source_line'] for m in reread['messages']] == sorted(m['source_line'] for m in messages)
    for rel, sha in manifest['files'].items():
        assert lab.digest(target/rel) == sha
    print(json.dumps({'output': str(target), 'visible_messages': len(messages),
        'roles': manifest['roles'], 'source_prefix_sha256': digest, 'verified': True}, ensure_ascii=False))


if __name__ == '__main__':
    main()
