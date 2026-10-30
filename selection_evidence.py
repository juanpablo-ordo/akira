"""Small, deterministic features and independently validated selector priors.

This module never trains, downloads data, calls MT5, or authorizes an order.
An external-venue study is evidence about that study, not a live probability.
"""
from pathlib import Path
import json, math

FEATURE_VERSION = 'pending_choice_v1'
FEATURE_NAMES = (
    'quality', 'activation', 'rr', 'distance_source', 'stop_source', 'target_source',
    'spread_risk', 'side_m15', 'side_h1', 'side_h4', 'side_d1', 'limit',
    'h1_origin', 'h4_origin', 'age_source', 'first_obstacle_rr',
    'm15_h1_atr_ratio', 'm15_volume_ratio', 'm15_efficiency', 'source_rsi',
    'hour_sin', 'hour_cos', 'stop_wick_ratio', 'opposing_m15_impulse',
)

def number(value, default=0.0):
    try:
        x = float(value)
        return x if math.isfinite(x) else default
    except (TypeError, ValueError):
        return default

def bounded(x, lo=-3.0, hi=3.0):
    return max(lo, min(hi, number(x)))

def origin(plan):
    key = str(getattr(plan, 'key', '')).upper()
    for tf in ('H4', 'H1', 'M30', 'M15', 'M5'):
        if ':' + tf + ':' in key:
            return tf
    return str(getattr(plan, 'signal_timeframe', 'M15') or 'M15').upper()

def candidate_features(plan, frames, quote, now):
    """Features use only the supplied closed-bar snapshot and current quote."""
    side = int(plan.side)
    source_tf = origin(plan)
    source = frames.get(source_tf)
    source_atr = number(getattr(source, 'atr', 0)) or number(getattr(plan, 'horizon_atr', 0)) or number(plan.atr, 1)
    source_atr = max(source_atr, 1e-9)
    risk = max(side * (number(plan.entry) - number(plan.sl)), 1e-9)
    reward = max(side * (number(plan.tp) - number(plan.entry)), 0)
    spread = max(number(getattr(quote, 'spread', 0)), 0)
    ref = number(quote.ask if side == 1 else quote.bid)
    distance = abs(ref - number(plan.entry))
    rr = reward / risk
    # Count only observed, confirmed pivots, outside the entry's noise band.
    obstacle = rr
    for tf in ('M15', 'M30', 'H1', 'H4'):
        f = frames.get(tf)
        if f is None:
            continue
        for level, _ in (f.highs if side == 1 else f.lows):
            gap = side * (number(level) + (spread if side == -1 else 0) - number(plan.entry))
            if max(spread * 2, number(f.atr) * .15) < gap < reward:
                obstacle = min(obstacle, gap / risk)
    def trend(tf):
        return bounded(side * number(getattr(frames.get(tf), 'trend', 0)), -1, 1)
    m15 = frames.get('M15')
    h1 = frames.get('H1')
    bars = tuple(getattr(m15, 'bars', ()))[-14:]
    movement = sum(abs(b.close - a.close) for a, b in zip(bars, bars[1:]))
    efficiency = abs(bars[-1].close - bars[0].close) / max(movement, 1e-9) if bars else 0
    wicks = sorted((b.open - b.low if side == 1 else b.high - b.open) for b in bars)
    wick = wicks[int((len(wicks) - 1) * .75)] if wicks else source_atr
    impulse = 0.0
    if bars:
        b = bars[-1]
        impulse = max(0.0, -side * (b.close - b.open) / max(number(getattr(m15, 'atr', 0)), 1e-9))
    seconds = {'M5': 300, 'M15': 900, 'M30': 1800, 'H1': 3600, 'H4': 14400}.get(source_tf, 900)
    age = max(0, number(now) - number(plan.bar_time)) / seconds
    angle = (number(now) % 86400) / 86400 * 2 * math.pi
    values = (
        bounded(number(plan.quality_score or plan.score) / 100, 0, 1),
        bounded(number(plan.activation_score) / 100, 0, 1),
        bounded(rr / 4, 0, 2), bounded(distance / source_atr, 0, 5),
        bounded(risk / source_atr, 0, 4), bounded(reward / source_atr, 0, 8),
        bounded(spread / risk, 0, 1), trend('M15'), trend('H1'), trend('H4'), trend('D1'),
        float(str(plan.kind).upper() == 'LIMIT'), float(source_tf == 'H1'), float(source_tf == 'H4'),
        bounded(math.log1p(age) / 4, 0, 2), bounded(obstacle / 4, 0, 2),
        bounded(number(getattr(m15, 'atr', 0)) / max(number(getattr(h1, 'atr', 0)), 1e-9), 0, 2),
        bounded(number(getattr(m15, 'volume_ratio', 1)), 0, 3), bounded(efficiency, 0, 1),
        bounded((number(getattr(source, 'rsi', 50), 50) - 50) * side / 50, -1, 1),
        math.sin(angle), math.cos(angle), bounded(risk / max(wick, 1e-9) / 4, 0, 3),
        bounded(impulse, 0, 3),
    )
    return tuple(values)

class SelectorEvidence:
    def __init__(self, path=None):
        self.path = Path(path) if path else Path(__file__).with_name('selector_validation.json')
        self.document = {}
        self.error = ''
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
            if (not isinstance(data, dict) or data.get('feature_version') != FEATURE_VERSION
                    or data.get('feature_names') != list(FEATURE_NAMES) or not isinstance(data.get('models'), dict)
                    or any(not isinstance(row, dict) for row in data.get('models', {}).values())):
                raise ValueError('Incompatible selection evidence')
            self.document = data
        except (OSError, ValueError, TypeError) as exc:
            self.error = str(exc)

    def usable(self, symbol, now, enabled=True):
        model = (self.document.get('models') or {}).get(symbol) or {}
        if not isinstance(model, dict):
            return None
        if not enabled or model.get('promoted') is not True:
            return None
        # Evidence must explicitly name both development and unseen evaluation.
        train_end = number(model.get('training_end'))
        test_start = number(model.get('evaluation_start'))
        test_end = number(model.get('evaluation_end'))
        if not (0 < train_end < test_start <= test_end <= number(now)):
            return None
        if number(now) - test_end > 90 * 86400:
            return None
        if number(model.get('evaluation_days')) < 20 or number(model.get('evaluation_pairs')) < 50:
            return None
        evaluation = model.get('evaluation') or {}
        if not isinstance(evaluation, dict):
            return None
        ci = evaluation.get('paired_daily_bootstrap_ci95_r') or []
        cost_ci = evaluation.get('double_cost_improvement_ci95_r') or []
        intervals=(ci,cost_ci)
        if any(not isinstance(values,(list,tuple)) or len(values)!=2 or
               not all(isinstance(x,(int,float)) and math.isfinite(x) for x in values) or
               values[0]<=0 or values[1]<values[0] for values in intervals):return None
        if (not model.get('external_venue') or not model.get('evaluation_passed') or not model.get('validation_passed')
                or number(evaluation.get('activation_delta'), -1) < 0 or number(evaluation.get('win_rate_delta'), -1) < 0
                or number((evaluation.get('challenger') or {}).get('mean_net_r_per_proposal')) <= 0):
            return None
        return model

    def adjustment(self, symbol, features, now, enabled=True):
        model = self.usable(symbol, now, enabled)
        if model is None:
            return 0.0
        weights = model.get('weights') or []
        if not isinstance(weights, (list, tuple)) or len(weights) != len(FEATURE_NAMES) or len(features) != len(weights):
            return 0.0
        if not all(isinstance(x, (int, float)) and math.isfinite(x) for x in (*weights, *features)):
            return 0.0
        strength = bounded(model.get('strength', 0), 0, 12)
        prediction = sum(w * x for w, x in zip(weights, features))
        return strength * math.tanh(prediction)

    def summary(self):
        return {'status': 'ESTUDIO DISPONIBLE' if self.document.get('models') else 'PROBABILIDAD NO CALIBRADA',
                'source': self.document.get('provider', ''),
                'scope': 'Selección de pendientes en datos externos; no es rentabilidad ni probabilidad en la cuenta MT5.',
                'period': self.document.get('evaluation_period', []),
                'human_superiority_confirmed': False,
                'models': {symbol: {k: v for k, v in row.items() if k != 'weights'}
                           for symbol, row in (self.document.get('models') or {}).items()},
                'error': self.error if not self.document else ''}

def quality_rows(summary):
    """Measured denominators and scope accompany every displayed percentage."""
    summary = summary or {}
    rows = [['Calidad', 'Alcance', summary.get('status', 'Sin estudio'),
             summary.get('scope', 'No hay comparación histórica disponible.')]]
    for symbol, model in (summary.get('models') or {}).items():
        evaluation = model.get('evaluation') or {}
        baseline = evaluation.get('baseline') or {}; challenger = evaluation.get('challenger') or {}
        ci = evaluation.get('paired_daily_bootstrap_ci95_r') or [None, None]
        if not isinstance(ci,(list,tuple)):ci=[None,None]
        rows.append(['Calidad', symbol, model.get('verdict', 'Sin conclusión'),
                     f"Datos externos {summary.get('period', [])}; {int(number(evaluation.get('pairs')))} propuestas emparejadas en {int(number(evaluation.get('days')))} días. No son ganancias de la cuenta MT5."])
        for key, label in (('activation_rate', 'Activación'), ('win_rate_when_activated', 'Ganadoras entre activadas')):
            a, b = baseline.get(key), challenger.get(key)
            value = f'{100*a:.1f}% → {100*b:.1f}%' if isinstance(a, (int, float)) and isinstance(b, (int, float)) else 'Sin muestra'
            rows.append(['Calidad', symbol + ' · ' + label, value,
                         f"15.3 / variante evaluada. Activadas {baseline.get('activated', 0)}/{baseline.get('proposals', 0)} y {challenger.get('activated', 0)}/{challenger.get('proposals', 0)}; las no activadas cuentan en el estudio."])
        a, b = baseline.get('mean_net_r_per_proposal'), challenger.get('mean_net_r_per_proposal')
        rows.append(['Calidad', symbol + ' · Resultado por propuesta',
                     f'{a:+.3f}R → {b:+.3f}R' if isinstance(a, (int, float)) and isinstance(b, (int, float)) else 'Sin muestra',
                     'Incluye spread y costes de referencia. Intervalo diario del cambio: ' +
                     (f'[{ci[0]:+.3f}, {ci[1]:+.3f}]R' if len(ci) == 2 and all(isinstance(x, (int, float)) for x in ci) else 'Sin intervalo')])
    rows.append(['Calidad', 'Comparación con ChatGPT', 'No confirmada',
                 'Este estudio compara selectores mecánicos con los mismos datos. No sustituye una comparación prospectiva con recomendaciones reales del chat.'])
    return rows

def quality_text(summary):
    lines = ['AKIRA · CALIDAD Y EVIDENCIA',
             'Comparación por separado para BTC y oro. Los porcentajes siguientes pertenecen al estudio externo.', '']
    for row in quality_rows(summary):
        lines.extend([str(row[1]) + ': ' + str(row[2]), str(row[3]), ''])
    lines.append('No se afirma que estas sean las mejores órdenes posibles ni se estima una probabilidad de beneficio para una orden individual.')
    return '\n'.join(lines)
