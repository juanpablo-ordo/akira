"""Aprendizaje de resultados confirmados de pendientes propias por símbolo/lado."""
from collections import defaultdict
import math
from execution import OWN_PENDING,LEGACY_PENDING
from statistical import wilson_lower


class PendingLearner:
    def __init__(self,g):
        self.g=g
        self.records=g.journal.data.setdefault('pending_outcomes',{})
        self._metrics_cache={}

    def update(self):
        g=self.g;g.refresh_history()
        if g.history_error:return False
        groups=defaultdict(list)
        for d in g.history:
            if int(getattr(d,'position_id',0)):
                groups[int(d.position_id)].append(d)
        changed=False
        active={int(getattr(p,'identifier',p.ticket)) for p in g.snapshot().positions}
        allowed={OWN_PENDING}|(LEGACY_PENDING if g.cfg['manage_legacy_akira'] else set())
        for pid,rows in groups.items():
            entries=[d for d in rows if int(getattr(d,'type',-1)) in (0,1) and int(d.entry)==0]
            exits=[d for d in rows if int(getattr(d,'type',-1)) in (0,1) and int(d.entry) in (1,3)]
            # Ownership follows entry deals; a manual close can have magic=0.
            if not entries or not exits or any(int(d.magic) not in allowed for d in entries):continue
            if any(int(getattr(d,'type',-1)) in (0,1) and int(d.entry)==2 for d in rows) or pid in active:continue
            entered=sum(float(d.volume) for d in entries);closed=sum(float(d.volume) for d in exits)
            if entered<=0 or abs(closed-entered)>1e-8:continue
            net=sum(g.pnl(d) for d in rows)
            if not math.isfinite(net):continue
            last=max(exits,key=lambda d:(float(getattr(d,'time_msc',0) or d.time*1000),int(d.ticket)))
            rec={'position_id':pid,'symbol':str(entries[0].symbol),'side':1 if int(entries[0].type)==0 else -1,
                 'pnl':round(net,8),'closed_at':float(last.time),'volume':entered,
                 'deal_ids':sorted(int(d.ticket) for d in rows),'build':'confirmed_pending_outcome_v10'}
            meta=g.journal.data['positions'].get(str(pid),{})
            if not meta:meta=next((m for m in g.journal.data['positions'].values() if int(m.get('identifier',0))==pid),{})
            plan=meta.get('plan') or {}
            if not plan:
                plan=next((g.journal.data['orders'].get(str(getattr(d,'order',0)),{}).get('plan') or {} for d in entries
                           if g.journal.data['orders'].get(str(getattr(d,'order',0)),{}).get('plan')), {})
            from trade_quality_gate import family
            rec.update(opened_at=min(float(d.time) for d in entries),strategy_key=str(plan.get('key','')),
                strategy_id=family(plan) if plan.get('key') else 'SIN_TESIS_REGISTRADA',
                strategy_version=int(plan.get('strategy_version') or 0),
                execution_build=str(plan.get('execution_build') or ''),
                selector_id=str(plan.get('selector_id') or ''),selector_version=int(plan.get('selector_version') or 0))
            if plan.get('learning_feature_version')=='pending_entry_v1' and plan.get('learning_features'):
                rec.update(confirmed=True,lane='PENDING',feature_version='pending_entry_v1',features=list(plan['learning_features']),
                           net=round(net,8),opened_at=min(float(d.time) for d in entries),
                           campaign_id=str(pid),campaign_complete=True)
            if self.records.get(str(pid))!=rec:self.records[str(pid)]=rec;changed=True
        if changed:
            self._metrics_cache.clear()
            g.journal.save();g.log.event('IA','Aprendizaje actualizado con cierres confirmados de pendientes propias',samples=len(self.records))
        return changed

    def metrics(self,symbol,plan=None):
        # Aggregate history remains available for accounting and loss guards.
        # Candidate ranking uses only explicitly attributed, comparable outcomes.
        from trade_quality_gate import family
        from strategy_choice import selected,STRATEGY_VERSION,SELECTOR_VERSION
        from akira_version import BUILD_ID
        cohort=(family(plan),STRATEGY_VERSION,selected(self.g.cfg),SELECTOR_VERSION,BUILD_ID) if plan is not None else None
        cache_key=(symbol,cohort,len(self.records))
        if cache_key in self._metrics_cache:return self._metrics_cache[cache_key]
        rows=sorted((r for r in self.records.values() if r['symbol']==symbol),key=lambda r:(r['closed_at'],r['position_id']))
        historical_samples=len(rows)
        if cohort is not None:
            rows=[r for r in rows if (r.get('strategy_id'),r.get('strategy_version'),r.get('selector_id'),
                r.get('selector_version'),r.get('execution_build'))==cohort]
        rows=rows[-200:]
        n=len(rows);wins=[r['pnl'] for r in rows if r['pnl']>0];losses=[-r['pnl'] for r in rows if r['pnl']<0]
        aw=sum(wins)/len(wins) if wins else 0.0;al=sum(losses)/len(losses) if losses else 0.0
        streak=0
        for r in reversed(rows):
            if r['pnl']>=0:break
            streak+=1
        last=rows[-1] if rows else {}
        out={'samples':n,'usable':n>=20,'win_rate':len(wins)/n if n else .5,'expectancy':sum(r['pnl'] for r in rows)/n if n else 0.0,
             'avg_win':aw,'avg_loss':al,'payoff':aw/al if al else 1.0,'loss_streak':streak,
             'last_side':last.get('side',0),'last_pnl':last.get('pnl',0),'last_close_time':last.get('closed_at',0),
             'side_samples':{},'side_win_rate':{},'side_expectancy':{},'side_wilson_lower':{}}
        out.update(scope='STRATEGY_VERSION_BUILD' if cohort else 'ACCOUNT_HISTORY',
            cohort=list(cohort) if cohort else None,historical_samples=historical_samples,
            excluded_samples=historical_samples-n)
        for side in (1,-1):
            subset=[r for r in rows if r['side']==side];size=len(subset);won=sum(r['pnl']>0 for r in subset)
            out['side_samples'][side]=size;out['side_win_rate'][side]=won/size if size else .5
            out['side_expectancy'][side]=sum(r['pnl'] for r in subset)/size if size else 0.0
            out['side_wilson_lower'][side]=wilson_lower(won,size) if size else 0.0
        self._metrics_cache[cache_key]=out
        return out
