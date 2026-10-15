"""Source-attributed, prospective filters for already valid MT5 candidates.

Only bounded selection rules can graduate. Geometry, size, management and risk
remain owned by the existing engine. No model-generated Python is executed.
"""
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
import copy
import hashlib
import json
import math
import re
import sqlite3
import threading
import time

from trade_quality_gate import family, num, value

RULE_VERSION = 1
RULES = {
    'H1_ALIGNMENT': {'name': 'Confirmar dirección H1', 'terms': ('h1', 'tendencia', 'trend', 'temporalidad', 'timeframe'), 'rule': 'side * trend H1 >= 0.35'},
    'VOLUME': {'name': 'Confirmar volumen M15', 'terms': ('volumen', 'volume'), 'rule': 'volume_ratio M15 >= 1'},
    'RSI': {'name': 'Evitar extensión RSI M15', 'terms': ('rsi', 'sobrecompra', 'sobreventa'), 'rule': 'LONG: RSI 40–65; SHORT: RSI 35–60'},
}
MAX_TRIALS = 100000


def digest(data):
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False, default=str, separators=(',', ':')).encode()).hexdigest()


def execution_identity(account, build, configuration):
    return digest({'account': list(account or ()), 'build': build, 'configuration': configuration})


def condition(code, plan, frames):
    side = int(value(plan, 'side', 0))
    if side not in (-1, 1): return None
    frame = frames.get('H1' if code == 'H1_ALIGNMENT' else 'M15') or {}
    field = 'trend' if code == 'H1_ALIGNMENT' else 'volume_ratio' if code == 'VOLUME' else 'rsi'
    raw = frame.get(field)
    if not isinstance(raw, (float, int)) or isinstance(raw, bool) or not math.isfinite(raw): return None
    if code == 'H1_ALIGNMENT': return side * raw >= .35
    if code == 'VOLUME': return raw >= 1
    if code == 'RSI': return 40 <= raw <= 65 if side == 1 else 35 <= raw <= 60
    return None


def frame_features(frames):
    return {tf: {key: value(frame, key) for key in ('trend', 'rsi', 'volume_ratio')}
            for tf, frame in frames.items()}


def advance(case, bid, ask, stamp):
    row = copy.deepcopy(case)
    if row['state'] not in ('WAITING', 'OPEN') or stamp <= row['last_quote']: return row
    if not all(math.isfinite(x) for x in (bid, ask, stamp)) or bid <= 0 or ask < bid: return row
    if stamp - row['last_quote'] > 60:
        row.update(state='GAP', net_r=None, closed_at=stamp); return row
    row['last_quote'] = stamp
    plan = row['plan']; side = plan['side']; entry = plan['entry']
    if row['state'] == 'WAITING':
        if stamp >= row['created'] + 7200:
            row.update(state='EXPIRED', net_r=None, closed_at=stamp); return row
        trigger = ask if side == 1 else bid
        touched = side * (trigger - entry) <= 0 if plan['kind'] == 'LIMIT' else side * (trigger - entry) >= 0
        if not touched: return row
        fill = entry if plan['kind'] == 'LIMIT' else (max(entry, ask) if side == 1 else min(entry, bid))
        if side * (plan['tp'] - fill) <= 0:
            row.update(state='INVALID_FILL', net_r=None, closed_at=stamp); return row
        row.update(state='OPEN', fill=fill, opened_at=stamp)
    price = bid if side == 1 else ask
    sl_hit = side * (price - plan['sl']) <= 0
    tp_hit = side * (price - plan['tp']) >= 0
    expired = stamp >= row.get('opened_at', row['created']) + 86400
    if sl_hit or tp_hit or expired:
        # Sampled stops use the worse observed quote; no invented favorable fill.
        exit_price = plan['tp'] if tp_hit and not sl_hit else price
        row.update(state='CLOSED', closed_at=stamp,
                   net_r=side * (exit_price - row['fill']) / row['risk'] - row['fee_r'])
    return row


def measured(rows):
    kept = [r for r in rows if r['passed']]
    rejected = [r for r in rows if not r['passed']]
    by_day = defaultdict(list)
    for row in rows:
        day = datetime.fromtimestamp(row['created'], timezone.utc).date().isoformat()
        by_day[day].append(0.0 if row['passed'] else -row['net_r'])
    days = [sum(v) / len(v) for v in by_day.values()]
    mean = sum(days) / len(days) if days else 0
    variance = sum((x - mean) ** 2 for x in days) / (len(days) - 1) if len(days) > 1 else math.inf
    lower = mean - 4.5 * math.sqrt(variance / len(days)) if len(days) > 1 else -math.inf
    baseline = sum(r['net_r'] for r in rows)
    filtered = sum(r['net_r'] for r in kept)
    return {'n': len(rows), 'kept': len(kept), 'rejected': len(rejected), 'days': len(days),
            'baseline_net_r': baseline, 'filtered_net_r': filtered,
            'improvement_net_r': filtered - baseline,
            'day_cluster_lower_r': lower if math.isfinite(lower) else None}


def holdout_passes(metrics):
    return (metrics.get('n', 0) >= 100 and metrics.get('days', 0) >= 20
            and metrics.get('kept', 0) >= 30 and metrics.get('rejected', 0) >= 30
            and num(metrics.get('filtered_net_r')) > 0 and num(metrics.get('improvement_net_r')) > 0
            and num(metrics.get('day_cluster_lower_r')) > .02)


def report_text(summary):
    lines=[summary.get('state','ESPERANDO DATOS'),summary.get('scope','Todavía no hay observaciones.'),
           'Filtros aplicables: '+str(len(summary.get('policies') or [])),
           'Una hipótesis nueva requiere 40 cierres de entrenamiento y 100 posteriores repartidos en al menos 20 días. Se comparan costes y abstenciones contra la base.']
    for profile in summary.get('profiles') or []:
        lines.extend(['',profile['name']+' · '+profile['rule']])
        for source in profile.get('sources',[])[-3:]:
            lines.append(str(source.get('title',''))+' · '+str(source.get('author',''))+'\n'+source['url']+'\nSHA-256: '+source['sha256'])
    for study in summary.get('studies') or []:
        metrics=study['holdout']
        lines.extend(['',' / '.join(map(str,study['group']))+' · '+study['code']+' · '+study['state'],
            'Entrenamiento: '+str((study.get('train') or {}).get('n',0))+' cierres. Posteriores: '+str(metrics['n'])+' en '+str(metrics['days'])+' días.',
            'Base neta: '+str(round(metrics['baseline_net_r'],3))+' R. Filtrada: '+str(round(metrics['filtered_net_r'],3))+' R.',
            'Evidencia: '+study['id']])
    return '\n'.join(lines)


def candidate_decision(plan, frames, context, now):
    """Hot path: cached evidence only, never disk, inference, HTTP or MT5 calls."""
    summary = ((context or {}).get('strategy_lab') or {}).get('adaptation') or {}
    updated = num(summary.get('updated'))
    if not updated or not 0 <= now - updated <= 120: return True, ''
    if not context.get('execution_identity') or summary.get('identity') != context['execution_identity']: return True, ''
    key = (family(plan), value(plan, 'symbol'), int(value(plan, 'side', 0)))
    # Exactly one filter per group, selected by fixed RULES order, never a new
    # untested AND-combination of individually successful rules.
    for policy in summary.get('policies') or []:
        if tuple(policy.get('group') or ()) != key: continue
        if policy.get('rule_version') != RULE_VERSION or policy.get('code') not in RULES: continue
        if not holdout_passes(policy.get('holdout') or {}): continue
        if not policy.get('train_passed') or not 0 <= now - num(policy.get('last_closed')) <= 7 * 86400: continue
        accepted = condition(policy['code'], plan, frames)
        if accepted is None: return True, ''
        return accepted, 'Filtro validado ' + policy['code'] + ' · evidencia ' + str(policy.get('id', ''))[:16]
    return True, ''


class StrategyAdaptation:
    def __init__(self, root, cfg, clock=time.time):
        self.path = Path(root) / 'state/strategy_adaptation.sqlite3'
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.cfg, self.clock = cfg, clock
        self.lock = threading.RLock(); self._summary = {'updated': 0, 'profiles': [], 'studies': [], 'policies': []}
        self._due = 0
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS profiles(id TEXT PRIMARY KEY,body TEXT)')
            db.execute('CREATE TABLE IF NOT EXISTS trials(id TEXT PRIMARY KEY,cohort TEXT,group_key TEXT,state TEXT,created REAL,body TEXT)')
            db.execute('CREATE INDEX IF NOT EXISTS adaptation_active ON trials(cohort,state)')
            db.execute('CREATE INDEX IF NOT EXISTS adaptation_created ON trials(created)')
            db.execute('CREATE TABLE IF NOT EXISTS evaluations(id TEXT PRIMARY KEY,body TEXT)')

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path, timeout=3)
        try:
            with connection: yield connection
        finally: connection.close()

    def ingest_source(self, row):
        body = str(row.get('body') or '')
        host = (urlsplit(str(row.get('url') or '')).hostname or '').lower()
        if host not in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'youtu.be') or row.get('complete') is not True or len(body) < 1000: return []
        source = {k: row.get(k, '') for k in ('url', 'title', 'author', 'caption_type', 'language')}
        source.update(sha256=hashlib.sha256(body.encode()).hexdigest(), excerpt=body[:1000], observed=self.clock())
        added = []
        with self.db() as db:
            for code, rule in RULES.items():
                if not any(re.search(r'\b' + re.escape(term) + r'\b', body, re.I) for term in rule['terms']): continue
                previous = db.execute('SELECT body FROM profiles WHERE id=?', (code,)).fetchone()
                sources = json.loads(previous[0])['sources'] if previous else []
                sources = [s for s in sources if s['sha256'] != source['sha256']][-29:] + [source]
                profile = {'id': code, 'rule_version': RULE_VERSION, 'name': rule['name'], 'rule': rule['rule'],
                           'sources': sources, 'state': 'HIPÓTESIS · SIN VALIDAR'}
                db.execute('INSERT OR REPLACE INTO profiles VALUES (?,?)', (code, json.dumps(profile, ensure_ascii=False)))
                added.append(code)
        return added

    def read(self):
        with self.lock: return copy.deepcopy(self._summary)

    def observe(self, snapshot):
        now = self.clock()
        identity = execution_identity(snapshot.get('learning_account'), snapshot.get('build'), snapshot.get('selection_configuration'))
        cohort = digest({'identity': identity, 'costs': snapshot.get('paper_costs'), 'rule_version': RULE_VERSION})
        with self.db() as db:
            profiles = [json.loads(r[0]) for r in db.execute('SELECT body FROM profiles')]
            active = db.execute("SELECT id,body FROM trials WHERE cohort=? AND state IN ('OPEN','WAITING')", (cohort,)).fetchall()
            for tid, raw in active:
                case = json.loads(raw); info = (snapshot.get('symbols') or {}).get(case['plan']['symbol']) or {}
                stamp = num(info.get('quote_time'))
                updated = advance(case, num(info.get('bid')), num(info.get('ask')), stamp)
                if updated != case: db.execute('UPDATE trials SET state=?,body=? WHERE id=?', (updated['state'], json.dumps(updated), tid))
            for symbol, info in (snapshot.get('symbols') or {}).items():
                stamp = num(info.get('quote_time')); bid = num(info.get('bid')); ask = num(info.get('ask'))
                costs = (snapshot.get('paper_costs') or {}).get(symbol) or {}
                unit = num(costs.get('profit_per_price_unit')); fee = num(costs.get('round_turn_fee'), -1)
                if not 0 <= now - stamp <= 10 or bid <= 0 or ask < bid or unit <= 0 or fee < 0: continue
                best = {}
                for candidate in info.get('adaptation_candidates') or []:
                    if candidate.get('confirmed'): continue
                    key = (family(candidate), candidate.get('side'))
                    if key not in best or num(candidate.get('score')) > num(best[key].get('score')): best[key] = candidate
                for (fam, side), plan in best.items():
                    if side not in (-1, 1): continue
                    entry, sl, tp = [num(plan.get(k)) for k in ('entry', 'sl', 'tp')]
                    risk = side * (entry - sl); reward = side * (tp - entry)
                    period = {'M1':60,'M5':300,'M15':900,'M30':1800,'H1':3600,'H4':14400,'D1':86400}.get(plan.get('signal_timeframe'),900)
                    if risk <= 0 or reward <= 0 or not 0 <= stamp - (num(plan.get('bar_time')) + period) <= period * 2: continue
                    runner = plan.get('lane') == 'RUNNER'
                    quote = ask if side == 1 else bid
                    if runner and abs(quote - entry) > max(ask - bid, num(plan.get('atr')) * .1): continue
                    for profile in profiles:
                        code = profile['id']; passed = condition(code, plan, info.get('frames') or {})
                        if passed is None: continue
                        group = [fam, symbol, side]; group_key = json.dumps([*group, code])
                        tid = digest([cohort, group_key, plan['bar_time']])
                        case = {'id': tid, 'cohort': cohort, 'group': group, 'code': code, 'rule_version': RULE_VERSION,
                                'created': now, 'last_quote': stamp, 'plan': {k:plan.get(k) for k in ('symbol','side','lane','kind','entry','sl','tp','bar_time','atr')}, 'passed': passed, 'risk': risk,
                                'fee_r': fee / (unit * risk), 'state': 'OPEN' if runner else 'WAITING',
                                'net_r': None, 'sources': [{k:s.get(k,'') for k in ('url','title','author','sha256','caption_type')} for s in profile['sources'][-3:]]}
                        if runner: case.update(fill=quote, opened_at=stamp)
                        db.execute('INSERT OR IGNORE INTO trials VALUES (?,?,?,?,?,?)', (tid, cohort, group_key, case['state'], now, json.dumps(case)))
            db.execute('DELETE FROM trials WHERE id NOT IN (SELECT id FROM trials ORDER BY created DESC LIMIT ?)', (MAX_TRIALS,))
        if now >= self._due:
            self._due = now + 60
            self.evaluate(cohort, identity, profiles, now)

    def evaluate(self, cohort, identity, profiles, now):
        groups = defaultdict(list); studies = []; policies = []
        with self.db() as db:
            for group_key, raw in db.execute("SELECT group_key,body FROM trials WHERE cohort=? AND state='CLOSED' ORDER BY created,id", (cohort,)):
                row = json.loads(raw)
                if row.get('net_r') is not None and math.isfinite(row['net_r']): groups[group_key].append(row)
            for group_key, rows in groups.items():
                eid = digest([cohort, group_key]); saved = db.execute('SELECT body FROM evaluations WHERE id=?', (eid,)).fetchone()
                study = json.loads(saved[0]) if saved else {'id': eid, 'group': rows[0]['group'], 'code': rows[0]['code'], 'rule_version': RULE_VERSION}
                if not study.get('frozen_at') and len(rows) >= 40:
                    training = rows[:40]; metrics = measured(training)
                    study.update(frozen_at=now, train_ids=[r['id'] for r in training], train=metrics,
                                 train_passed=metrics['kept'] >= 10 and metrics['rejected'] >= 10 and metrics['filtered_net_r'] > 0 and metrics['improvement_net_r'] > 0,
                                 sources=training[0]['sources'])
                holdout = [r for r in rows if r['created'] > study.get('frozen_at', math.inf)]
                metrics = measured(holdout); last_closed = max((r['closed_at'] for r in holdout), default=0)
                study.update(holdout=metrics, last_closed=last_closed, total_closed=len(rows))
                valid = study.get('train_passed') and holdout_passes(metrics) and 0 <= now - last_closed <= 7 * 86400
                study['state'] = 'VALIDADA' if valid else 'VALIDANDO EN DATOS POSTERIORES' if study.get('frozen_at') else 'REUNIENDO 40 CIERRES DE ENTRENAMIENTO'
                if valid: policies.append(copy.deepcopy(study))
                studies.append(study)
                db.execute('INSERT OR REPLACE INTO evaluations VALUES (?,?)', (eid, json.dumps(study)))
            db.execute('DELETE FROM evaluations WHERE id NOT IN (SELECT id FROM evaluations ORDER BY rowid DESC LIMIT 300)')
        priority = {code: i for i, code in enumerate(RULES)}; selected = {}
        for policy in sorted(policies, key=lambda p: priority[p['code']]): selected.setdefault(tuple(policy['group']), policy)
        summary = {'updated': now, 'identity': identity, 'cohort': cohort, 'profiles': profiles, 'studies': studies,
                   'policies': list(selected.values()), 'state': 'FILTROS VALIDADOS APLICABLES' if selected else 'APRENDIENDO · SIN FILTROS NUEVOS ACTIVADOS',
                   'scope': '40 cierres de entrenamiento y al menos 100 posteriores en 20 días con costes. Solo filtra nuevas candidatas válidas. No cambia lotes, niveles, riesgo ni gestión.'}
        with self.lock: self._summary = summary
