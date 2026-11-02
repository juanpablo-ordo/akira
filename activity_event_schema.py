"""Stable, evidence-addressable activity events; backwards compatible with JSONL.

No ticket, confirmation, or retcode is invented when MT5 has not provided one.
"""
import uuid
from activity_events import category_for_event

def normalize_event(row):
    item=dict(row)
    msg=str(item.get('message') or item.get('detail') or '')
    state=str(item.get('state') or (msg.partition(' | ')[0] if ' | ' in msg else '')).strip()
    if state:item.setdefault('state',state)
    item.setdefault('event_id',uuid.uuid4().hex)
    item.setdefault('timestamp_utc',str(item.get('utc') or ''))
    item['category']=category_for_event(item)
    item.setdefault('severity','ERROR' if item['category']=='ERROR' else
                    'WARNING' if item['category']=='AVISO' else 'INFO')
    item.setdefault('ticket',None)
    item.setdefault('action',item.get('operation') or state or '')
    item.setdefault('technical_details',str(item.get('detail') or item.get('reason') or '')[:4000])
    item.setdefault('correlation_id',str(item.get('ticket') or item.get('order') or item.get('deal') or
                                     item.get('event_id')))
    if 'confirmation' not in item:
        action=str(item.get('operation') or '')
        item['confirmation']='CONFIRMED_MT5' if action.startswith('confirmed_') else (
            'PENDING_MT5_RECONCILIATION' if 'retcode' in item else 'NOT_APPLICABLE')
    return item
