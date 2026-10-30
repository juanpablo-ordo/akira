"""Pure configured limits shared by execution and presentation. No broker IO."""
import math


def portfolio_cap(rules,balance,equity,protection=None):
    capital=max(0.0,min(float(equity),float(balance)))
    cap=capital*float(rules['portfolio_capital_pct'])/100
    cap=min(cap,float(rules['portfolio_money_cap'])) if float(rules['portfolio_money_cap'])>0 else cap
    if protection and protection.get('enabled'):cap=min(cap,capital*float(protection['portfolio_pct'])/100)
    return cap


def trade_cap(rules,equity,protection=None):
    base=min(float(rules['max_trade_money']),float(equity)*float(rules['max_trade_pct'])/100)
    if bool(rules.get('min_lot_structural_override_enabled',False)):
        pct=float(rules.get('min_lot_structural_override_max_pct',rules['max_trade_pct']))
        money=float(rules.get('min_lot_structural_override_money_cap',rules['max_trade_money']))
        base=max(base,min(money,float(equity)*pct/100))
    if protection and protection.get('enabled'):base=min(base,max(0,float(equity))*float(protection['trade_pct'])/100)
    return base


def configured_limits(config,account):
    rules=config['risk'];runner=config.get('runner') or {}
    from capital_guard import rules as protection_rules
    protection=protection_rules(config)
    currency=str(account.get('currency') or 'USD')
    raw={'trade_money':float(rules['max_trade_money']),'trade_pct':float(rules['max_trade_pct']),
         'portfolio_money':float(rules['portfolio_money_cap']),'portfolio_pct':float(rules['portfolio_capital_pct']),
         'runner_pct':float(runner.get('max_trade_budget_pct',50)),'currency':currency}
    try:
        balance=float(account['balance']);equity=float(account['equity'])
        if not all(math.isfinite(v) for v in (balance,equity)):raise ValueError()
    except (KeyError,TypeError,ValueError):return {**raw,'ready':False}
    basis=max(0.0,min(balance,equity));trade=trade_cap(rules,equity,protection);total=portfolio_cap(rules,balance,equity,protection)
    return {**raw,'capital_protection':protection,'ready':True,'balance':balance,'equity':equity,'capital_basis':basis,
        'per_trade':trade,'runner':trade*max(0,min(1,raw['runner_pct']/100)),
        'portfolio':total,'portfolio_capital_pct':min(100,max(0,total/basis*100)) if basis>0 else 0,
        'override':bool(rules.get('min_lot_structural_override_enabled',False)),
        'explanation':EffectiveRiskResolver.explain(config,equity,balance)}


class EffectiveRiskResolver:
    """The same arithmetic and rule provenance consumed by Gateway and UI."""
    @staticmethod
    def explain(config,equity,balance):
        from capital_guard import rules as protection_rules
        r=config['risk'];p=protection_rules(config)
        constraints=[{'rule':'risk.max_trade_money','label':'Tope monetario','amount':float(r['max_trade_money'])},
                     {'rule':'risk.max_trade_pct','label':'Porcentaje del patrimonio','amount':float(equity)*float(r['max_trade_pct'])/100}]
        normal=min(x['amount'] for x in constraints)
        if r.get('min_lot_structural_override_enabled',False):
            extra=min(float(r.get('min_lot_structural_override_money_cap',r['max_trade_money'])),float(equity)*float(r.get('min_lot_structural_override_max_pct',r['max_trade_pct']))/100)
            constraints.append({'rule':'risk.min_lot_structural_override','label':'Permiso adicional de lote mínimo','amount':extra,'operation':'MAX_AFTER_BASE'})
            normal=max(normal,extra)
        if p['enabled']:constraints.append({'rule':'capital_protection.trade_pct','label':'Tope protegido','amount':max(0,float(equity))*p['trade_pct']/100})
        final=trade_cap(r,equity,p)
        winners=[c['rule'] for c in constraints if abs(c['amount']-final)<1e-9]
        return {'constraints':constraints,'effective':final,'binding_rules':winners,
            'formula':'menor(tope monetario, patrimonio × porcentaje), permiso adicional explícito si existe, luego tope protegido',
            'portfolio_effective':portfolio_cap(r,balance,equity,p)}
    @staticmethod
    def profile(config,account):
        chosen=config.get('operation_profile','AUTO');mode=account.get('trade_mode')
        actual='DEMO_EXPERIMENT' if mode==0 else 'REAL_CAPITAL' if mode==2 else 'UNKNOWN'
        allowed=not (chosen=='DEMO_EXPERIMENT' and actual!='DEMO_EXPERIMENT') and chosen!='HISTORICAL'
        return {'configured':chosen,'effective':actual if chosen=='AUTO' else chosen,'account_type':actual,
                'allows_broker_orders':allowed,'reason':('El perfil de simulación histórica nunca envía a MT5' if chosen=='HISTORICAL' else
                'El perfil demo requiere una cuenta identificada por MT5 como demo' if not allowed else ''),
                'optional_rules_explicit':True,'broker_checks_always_required':True}
