#!/usr/bin/env python3
"""Read verified Foxmail 7.2 text indexes; never decrypt account credentials."""
from __future__ import annotations
import argparse
import hashlib
import json
import re
import struct
from datetime import datetime, timedelta
from pathlib import Path
from read_mail import initialize, output_dir, read_json, write_json, utc_now, DATA_NAME, history_cutoff


def stable_read(path):
    before = path.stat()
    data = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise ValueError('Foxmail changed a source file during reading; retry after synchronization finishes')
    return data


def read_text_index(root, stem):
    table = stable_read(root / (stem + '.map'))
    data = stable_read(root / (stem + '.rec0'))
    if table[:16] != bytes.fromhex('4b564c53000100020000000400000008') or data[:4] != b'RECF':
        raise ValueError('Unsupported Foxmail text index layout')
    count = struct.unpack_from('>I', table, 24)[0]
    if count > (len(table)-32)//16:
        raise ValueError('Invalid index count')
    result = {}
    for pos in range(32, 32+count*16, 16):
        if table[pos:pos+4] != bytes.fromhex('a1c23fae'):
            raise ValueError('Unsupported index entry marker')
        ident, offset, size = struct.unpack_from('>III', table, pos+4)
        if ident in result or offset < 128 or size % 2 or offset+12+size > len(data):
            raise ValueError('Invalid text record bounds or duplicate identifier')
        if data[offset:offset+2] not in (b'\xf4\xea', b'\xf7\xea'):
            raise ValueError('Unsupported text record marker')
        result[ident] = data[offset+12:offset+12+size].decode('utf-16-le', errors='strict')
    return result


ATTACHMENT_SUFFIXES = ('.pdf', '.xlsx', '.xls', '.docx', '.doc', '.pptx', '.ppt',
                       '.eml', '.html', '.htm', '.zip', '.rar', '.png', '.jpg', '.jpeg')


def read_attachment_mail_ids(root):
    """Return mail IDs and attachment counts from Foxmail's verified KV list."""
    path = root / 'Indexes/attach/attach.idx'
    table = stable_read(path)
    if table[:16] != bytes.fromhex('4b564c53000100020000000800000008'):
        raise ValueError('Unsupported Foxmail attachment index layout')
    keys = set()
    for pos in range(32, len(table) - 19, 20):
        link, mail_id, attachment_index, _value, _row = struct.unpack_from('>IIIII', table, pos)
        if not any((link, mail_id, attachment_index, _value, _row)):
            break
        if link not in (0xffffffff, 0xa1c23fae) or not mail_id:
            raise ValueError('Unsupported Foxmail attachment index entry')
        keys.add((mail_id, attachment_index))
    counts = {}
    for mail_id, _attachment_index in keys:
        counts[mail_id] = counts.get(mail_id, 0) + 1
    return counts


def read_attachment_metadata(root):
    """Read canonical filenames and byte ranges from attachment metadata records."""
    data = stable_read(root / 'Indexes/attach/attachInfo.rec0')
    if data[:4] != b'RECF':
        raise ValueError('Unsupported Foxmail attachment metadata layout')
    offsets = [offset for offset in range(128, len(data), 128)
               if data[offset:offset + 2] in (b'\xf4\xea', b'\xf7\xea')]
    metadata = []
    for number, offset in enumerate(offsets):
        end = offsets[number + 1] if number + 1 < len(offsets) else len(data)
        record = data[offset:end]
        needle = b'\x04\x00\x00\x00name\x08\x00\x00\x00'
        marker = record.find(needle)
        if marker < 0:
            continue
        length_at = marker + len(needle)
        character_count = struct.unpack_from('<I', record, length_at)[0]
        text_at = length_at + 4
        text_end = text_at + character_count * 2
        if text_end > len(record):
            raise ValueError('Invalid Foxmail attachment name bounds')
        item = {'name': record[text_at:text_end].decode('utf-16-le', errors='strict')}
        for key in (b'index', b'pos', b'size'):
            value_marker = struct.pack('<I', len(key)) + key + b'\x03\x00\x00\x00'
            value_at = record.find(value_marker)
            if value_at < 0 or value_at + len(value_marker) + 4 > len(record):
                raise ValueError('Incomplete Foxmail attachment metadata record')
            item[key.decode()] = struct.unpack_from('<I', record, value_at + len(value_marker))[0]
        metadata.append(item)
    return metadata


def indexed_attachment_names(text):
    return [line.strip() for line in text.splitlines()
            if line.strip().casefold().endswith(ATTACHMENT_SUFFIXES)]


def canonical_attachment(indexed_name, canonical_items, used):
    folded = indexed_name.casefold()
    for position, item in enumerate(canonical_items):
        if position not in used and item['name'].casefold() == folded:
            used.add(position)
            return item
    suffix = Path(indexed_name).suffix.casefold()
    tokens = set(re.findall(r'[a-z0-9]+', folded))
    choices = []
    for position, item in enumerate(canonical_items):
        name = item['name']
        if position in used or Path(name).suffix.casefold() != suffix:
            continue
        score = len(tokens & set(re.findall(r'[a-z0-9]+', name.casefold())))
        choices.append((score, -abs(len(indexed_name) - len(name)), -position, position, name))
    if choices:
        _score, _length, _order, position, _name = max(choices)
        used.add(position)
        return canonical_items[position]
    return {'name': indexed_name, 'index': None, 'pos': None, 'size': None}


def inspect(root):
    text_stems = ('Indexes/subject/subject_txt', 'Indexes/msgBody/bodytxt_txt',
                  'Indexes/msgExt/exttxt_txt')
    paths = [root/'Mails/Index', root/'Indexes/attach/attach.idx',
             root/'Indexes/attach/attachInfo.rec0'] + [root/(stem+ext) for stem in
        text_stems for ext in ('.map','.rec0')]
    stamps = [(p.stat().st_size,p.stat().st_mtime_ns) for p in paths]
    index = stable_read(paths[0])
    if index[:8] != bytes.fromhex('4658495302000100') or len(index)%512:
        raise ValueError('Unsupported Foxmail mail header layout')
    subjects = read_text_index(root,'Indexes/subject/subject_txt')
    bodies = read_text_index(root,'Indexes/msgBody/bodytxt_txt')
    extended = read_text_index(root,'Indexes/msgExt/exttxt_txt')
    attachment_counts = read_attachment_mail_ids(root)
    canonical_items = read_attachment_metadata(root)
    used_attachment_names = set()
    records = []
    seen = set()
    for pos in range(512,len(index),512):
        block = index[pos:pos+512]
        ident = struct.unpack_from('<I',block)[0]
        if not ident: continue
        if ident in seen: raise ValueError('Duplicate local mail ID')
        seen.add(ident)
        if ident not in subjects or ident not in bodies: continue
        lengths = list(block[45:49])+[struct.unpack_from('<H',block,49)[0]]
        if block[44]!=3 or sum(lengths)+51>512:
            raise ValueError('Unsupported mail header string layout')
        fields=[]; cursor=51
        for length in lengths:
            fields.append(block[cursor:cursor+length].decode('utf-8',errors='strict'))
            cursor += length
        if fields[4] != subjects[ident]:
            raise ValueError('Subject/header cross-check failed; refusing to join message records')
        date = datetime(1899,12,30)+timedelta(days=struct.unpack_from('<d',block,8)[0])
        if not 1990<=date.year<=2100: raise ValueError('Invalid cached message date')
        indexed_names = indexed_attachment_names(extended.get(ident, ''))
        expected_count = attachment_counts.get(ident, 0)
        indexed_names = indexed_names[-expected_count:] if expected_count else []
        attachments = []
        container = f'Mails/{ident % 32}/{ident // 32}/{ident}'
        for attachment_index, indexed_name in enumerate(indexed_names):
            item = canonical_attachment(indexed_name, canonical_items, used_attachment_names)
            if item['pos'] is not None and item['size'] is not None:
                container_size = (root / container).stat().st_size
                if item['pos'] + item['size'] > container_size:
                    raise ValueError('Foxmail attachment byte range exceeds its mail container')
            attachments.append({'name': item['name'], 'indexed_name': indexed_name,
                'attachment_index': attachment_index, 'foxmail_container': container,
                'container_position': item['pos'], 'encoded_size': item['size'],
                'binary_status': 'stored_in_foxmail_container_not_exported'})
        records.append({'local_id':ident,'sender':f'{fields[0]} <{fields[1]}>',
            'recipients':f'{fields[2]} <{fields[3]}>','subject':fields[4],
            'received_at':date.isoformat(),'body_text':bodies[ident],
            'attachment_index_text':extended.get(ident, ''),
            'attachments':attachments, 'tasks':[], 'source_type':'foxmail_text_index',
            'content_scope':'cached_search_text_and_attachment_metadata',
            'attachments_status':('metadata_indexed_binary_in_foxmail_container'
                                  if expected_count else 'none_indexed'),
            'date_timezone':'unknown', 'review_required':True})
    if stamps != [(p.stat().st_size,p.stat().st_mtime_ns) for p in paths]:
        raise ValueError('Foxmail indexes changed during snapshot; retry later')
    if not records: raise ValueError('No cross-validated cached messages found')
    return index[16:24].hex(), records, len(seen)


def sync(project, root, latest, include_baseline=False, history_months=None):
    generation, records, headers = inspect(root)
    initialize(project)
    path = output_dir(project)/DATA_NAME
    state=read_json(path)
    source=hashlib.sha256(str(root.resolve()).casefold().encode()).hexdigest()[:16]
    sources=state.setdefault('local_sources',{})
    previous=sources.get(source)
    if previous and previous['generation']!=generation:
        raise ValueError('Local store generation changed; inspect migration before importing')
    for record in state['messages']:
        record['is_new']=False
        for task in record.get('tasks',[]): task['is_new']=False
    box=previous or {'generation':generation,'processed':{},'baseline_ids':[]}
    if previous is None:
        ordered=sorted(records,key=lambda r:(r['received_at'],r['local_id']))
        cutoff = history_cutoff(history_months or 1)
        selected = [r for r in ordered if r['received_at'][:10] >= cutoff]
        if latest:
            selected = selected[-latest:]
        chosen={r['local_id'] for r in selected}
        box['baseline_ids']=[r['local_id'] for r in records if r['local_id'] not in chosen]
    if include_baseline:
        box['baseline_ids'] = []
    elif history_months is not None:
        cutoff = history_cutoff(history_months)
        eligible = {r['local_id'] for r in records if r['received_at'][:10] >= cutoff}
        box['baseline_ids'] = [ident for ident in box['baseline_ids'] if ident not in eligible]
    new=0; changed=0
    for record in records:
        ident=str(record['local_id'])
        if record['local_id'] in box['baseline_ids']: continue
        fingerprint=hashlib.sha256(json.dumps(record,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
        if box['processed'].get(ident)==fingerprint: continue
        key=f'foxmail:{source}:{generation}:{ident}'
        existing=next((r for r in state['messages'] if r['message_key']==key),None)
        record.update(message_key=key,source_id=source,uid=None,uidvalidity=None,
            is_new=existing is None,recorded_at=utc_now(),content_sha256=fingerprint)
        if existing:
            record['tasks']=existing.get('tasks',[])
            state['messages'].remove(existing); changed+=1
        else: new+=1
        state['messages'].insert(0,record)
        box['processed'][ident]=fingerprint
    sources[source]=box
    state['sync']={'status':'local_cache_synced','updated_at':utc_now(),
        'message':f'Cross-validated {len(records)}/{headers} cached headers; new={new}, changed={changed}. Attachment metadata indexed; binary files remain in Foxmail containers; agent task review required.',
        'new_message_count':new,'new_task_count':0,'changed_message_count':changed}
    write_json(path,state)
    return state['sync']


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account-dir',required=True)
    parser.add_argument('--project-dir',default='.')
    parser.add_argument('--sync',action='store_true')
    parser.add_argument('--initial-latest',type=int,default=0)
    parser.add_argument('--history-months', type=int, help='Read/backfill this many months; first import defaults to one')
    parser.add_argument('--include-baseline', action='store_true',
                        help='import historical local IDs previously recorded as the first-run baseline')
    args=parser.parse_args()
    if args.initial_latest<0: parser.error('initial-latest must be nonnegative')
    if args.history_months is not None and args.history_months < 1:
        parser.error('history-months must be positive')
    root=Path(args.account_dir).resolve()
    try:
        if args.sync: result=sync(Path(args.project_dir).resolve(),root,args.initial_latest,args.include_baseline,args.history_months)
        else:
            generation,records,total=inspect(root)
            result={'validated_messages':len(records),'header_records':total,
                    'body_characters':sum(len(r['body_text']) for r in records),
                    'indexed_attachments':sum(len(r['attachments']) for r in records),
                    'attachments_status':'metadata_indexed_binary_in_foxmail_container','writes':False}
        print(json.dumps(result,ensure_ascii=True))
    except (ValueError,OSError,struct.error) as error:
        parser.exit(1,f'Error: {error}\n')
