"""Pure configured limits shared by execution and presentation. No broker IO."""
import math


def portfolio_cap(rules,balance,equity):
    capital=max(0.0,min(float(equity),float(balance)))
    cap=capital*float(rules['portfolio_capital_pct'])/100
    return min(cap,float(rules['portfolio_money_cap'])) if float(rules['portfolio_money_cap'])>0 else cap


def trade_cap(rules,equity):
    base=min(float(rules['max_trade_money']),float(equity)*float(rules['max_trade_pct'])/100)
    if not bool(rules.get('min_lot_structural_override_enabled',False)):return base
    pct=float(rules.get('min_lot_structural_override_max_pct',rules['max_trade_pct']))
    money=float(rules.get('min_lot_structural_override_money_cap',rules['max_trade_money']))
    return max(base,min(money,float(equity)*pct/100))


def configured_limits(config,account):
    rules=config['risk'];runner=config.get('runner') or {}
    currency=str(account.get('currency') or 'USD')
    raw={'trade_money':float(rules['max_trade_money']),'trade_pct':float(rules['max_trade_pct']),
         'portfolio_money':float(rules['portfolio_money_cap']),'portfolio_pct':float(rules['portfolio_capital_pct']),
         'runner_pct':float(runner.get('max_trade_budget_pct',50)),'currency':currency}
    try:
        balance=float(account['balance']);equity=float(account['equity'])
        if not all(math.isfinite(v) for v in (balance,equity)):raise ValueError()
    except (KeyError,TypeError,ValueError):return {**raw,'ready':False}
    basis=max(0.0,min(balance,equity));trade=trade_cap(rules,equity);total=portfolio_cap(rules,balance,equity)
    return {**raw,'ready':True,'balance':balance,'equity':equity,'capital_basis':basis,
        'per_trade':trade,'runner':trade*max(0,min(1,raw['runner_pct']/100)),
        'portfolio':total,'portfolio_capital_pct':min(100,max(0,total/basis*100)) if basis>0 else 0,
        'override':bool(rules.get('min_lot_structural_override_enabled',False))}
