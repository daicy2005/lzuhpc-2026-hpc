#!/usr/bin/env python3
"""Extend the immutable v1 exporter for a visible async question's UI record."""
import collections
import hashlib
import json
import re

import export_prompt_session as v1


def extract(data,expected):
    assert data.endswith(b'\n'),'capture must end at a complete source record'
    messages,events,sessions=[],[],[]
    counts=collections.Counter()
    for lineno,line in enumerate(data.splitlines(),1):
        row=json.loads(line);payload=row.get('payload',{});item=payload.get('item',{})
        if row.get('type')=='session_meta':sessions.append(payload['id'])
        if row.get('type')=='event_msg' and payload.get('type')=='item_completed' and item.get('type') in ('UserMessage','AgentMessage'):
            role='user' if item['type']=='UserMessage' else 'assistant'
            text='\n'.join(b.get('text','') for b in item.get('content',[]))
            events.append((lineno,row.get('timestamp'),role,hashlib.sha256(text.encode()).hexdigest(),item))
        if row.get('type')!='response_item' or payload.get('type')!='message':
            counts[row.get('type','unknown')]+=1
            continue
        role,channel=payload.get('role'),payload.get('channel')
        if role not in ('user','assistant') or channel not in (None,'final','commentary'):
            counts['nonvisible_message']+=1
            continue
        blocks=payload.get('content',[])
        assert all(b.get('type') in ('input_text','output_text','input_image') for b in blocks),'unknown visible content block'
        messages.append({'source_line':lineno,'timestamp':row.get('timestamp'),'role':role,'channel':channel,'content':blocks})
    assert sessions==[expected],'must export exactly one requested Session'
    represented=collections.Counter((m['role'],hashlib.sha256('\n'.join(b.get('text','') for b in m['content']).encode()).hexdigest()) for m in messages)
    missing=collections.Counter((e[2],e[3]) for e in events)-represented
    original_missing=sum(missing.values())
    imported=0
    # Only the established UI-only async question format is supported. Any other
    # unmatched message still stops export; no model summaries or tool logs fill it.
    for lineno,timestamp,role,digest,item in events:
        key=(role,digest)
        if not missing[key]:continue
        assert item['type']=='AgentMessage' and item.get('delivery')=='async' and item.get('questions') and item.get('phase')=='final_answer', 'unsupported unmatched visible UI message'
        assert item.get('content') and all(b.get('type')=='Text' and isinstance(b.get('text'),str) for b in item['content'])
        messages.append({'source_line':lineno,'timestamp':timestamp,'role':role,'channel':'final',
            'content':[{'type':'output_text','text':b['text']} for b in item['content']],
            'source_record_type':'event_msg.item_completed.AgentMessage',
            'source_item_id':item['id'],'source_visible_blocks':item['content'],
            'format_mapping':'UI Text -> output_text, exact text preserved; visible async question only'})
        missing[key]-=1;imported+=1
    assert not +missing,'a visible UI message remains unrepresented'
    messages.sort(key=lambda m:m['source_line'])
    assert messages and messages[0]['role']=='user'
    counts['ui_visible_message_events']=len(events)
    counts['ui_message_events_missing_in_response_items']=original_missing
    counts['ui_only_async_questions_preserved_from_original_events']=imported
    counts['ui_visible_messages_unrepresented_after_export']=0
    text=json.dumps(messages,ensure_ascii=False)
    patterns=(r'\bsk-[A-Za-z0-9_-]{20,}',r'\bgh[pousr]_[A-Za-z0-9]{20,}',r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')
    assert not any(re.search(p,text) for p in patterns),'possible credential in visible transcript; inspect privately before export'
    return messages,dict(counts)


if __name__=='__main__':
    v1.extract=extract
    v1.main()
