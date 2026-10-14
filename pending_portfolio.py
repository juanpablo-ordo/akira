"""Bounded, deterministic selection of already-qualified pending proposals.

No broker, network, price or risk-cap changes occur here. Alternative entries in
one structural slot compete before the account's remaining budget is allocated.
"""
import math

def pending_overlap(a,b):
    """Same-side entries sharing an invalidation zone AND target are one thesis.

    Distinct entries can still be duplicates: dividing one scenario into tickets
    does not diversify its risk. Opposite sides are retained for OCO management.
    """
    if int(a.side)!=int(b.side): return False
    ra=abs(float(a.entry)-float(a.sl)); rb=abs(float(b.entry)-float(b.sl))
    reward=max(abs(float(a.tp)-float(a.entry)),abs(float(b.tp)-float(b.entry)),1e-9)
    atr=max(float(getattr(a,'atr',0) or 0),float(getattr(b,'atr',0) or 0),1e-9)
    same_target=abs(float(a.tp)-float(b.tp))<=max(reward*.08,atr*.08)
    lo=max(min(a.entry,a.sl),min(b.entry,b.sl))
    hi=min(max(a.entry,a.sl),max(b.entry,b.sl))
    overlap=max(0.0,hi-lo)/max(min(ra,rb),1e-9)
    return bool(same_target and (overlap>=.50 or abs(a.entry-b.entry)<=max(ra,rb)*.50))

def pending_priority(plan):
    """Rank already-qualified plans by fused context and reachable activation.

    This is a utility score, not a claimed probability. Uncalibrated R:R cannot
    manufacture an edge, and a distant high-quality zone cannot consume the
    whole portfolio solely because it has a higher geometry ratio.
    """
    score = float(plan.score)
    quality = float(getattr(plan, 'quality_score', 0) or score)
    activation = float(getattr(plan, 'activation_score', 0) or 0)
    if not all(math.isfinite(x) for x in (score, quality, activation)):
        return 0.0
    # V12.1: calidad estructural domina. Activación solo desempata entre tesis
    # que ya sobrevivieron estructura, invalidación, MTF y riesgo.
    value = .30 * score + .55 * quality + .15 * activation
    samples = int(getattr(plan, 'empirical_samples', 0) or 0)
    if samples >= 20:
        value += max(-5.0, min(5.0, float(plan.empirical_expectancy) * 2.0))
    # Only a validated, bounded selector prior may adjust ordering. Runners,
    # malformed values and ordinary plans have no adjustment. It never alters
    # levels, sizing, budget, compatibility or execution authorization.
    adjustment = float(getattr(plan, 'selection_adjustment', 0) or 0)
    if (getattr(plan, 'lane', '') == 'PENDING' and math.isfinite(adjustment)
            and getattr(plan, 'selection_feature_version', '') == 'pending_choice_v1'):
        value += max(-12.0, min(12.0, adjustment))
    return max(0.0, min(100.0, value))


def compatible(a,b,spacing):
    if a.side!=b.side:return True
    if pending_overlap(a,b):return False
    return abs(a.entry-b.entry)>=max(float(a.atr),float(b.atr),1e-9)*spacing


def select_portfolio(options,budget,maximum,per_side,existing=(),represented=(),spacing=.18,
                     preserve_opposite=True,opposite_quality=72.0,beam_width=128):
    """Return a feasible subset, using a bounded beam across all alternatives."""
    if budget<=0 or maximum<=0:return []
    options=sorted(options,key=lambda r:(r['value'],-r['risk'],r['plan'].key),reverse=True)[:40]
    counts={s:sum(p.side==s for p in existing) for s in (1,-1)}
    # (indices, spent, utility, buy_count, sell_count, occupied_slots)
    states=[((),0.0,0.0,counts[1],counts[-1],frozenset(represented))]
    for i,row in enumerate(options):
        p=row['plan'];risk=float(row['risk']);slot=row['slot']
        if risk<=0 or risk>budget+1e-9 or row['value']<=0:continue
        if any(not compatible(p,old,spacing) for old in existing):continue
        expanded=list(states)
        for ids,spent,value,buys,sells,slots in states:
            count=buys if p.side==1 else sells
            if len(ids)>=maximum or count>=per_side or slot in slots or spent+risk>budget+1e-9:continue
            if any(not compatible(p,options[j]['plan'],spacing) for j in ids):continue
            bonus=9.0 if preserve_opposite and count==0 and float(p.quality_score or p.score)>=opposite_quality else 0.0
            expanded.append((ids+(i,),spent+risk,value+row['value']+bonus,
                             buys+(p.side==1),sells+(p.side==-1),slots|{slot}))
        states=sorted(expanded,key=lambda st:(st[2],-st[1],len(st[0])),reverse=True)[:beam_width]
    winner=max(states,key=lambda st:(st[2],-st[1],len(st[0])))
    return sorted([options[i] for i in winner[0]],key=lambda r:(r['value'],-r['risk']),reverse=True)
