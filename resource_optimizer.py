"""AKIRA UI/AI resource scheduling; never throttles risk, exits, or MT5.

RAM limits are SOFT budgets for Ollama model context and visual caches, not a
Windows kernel guarantee. The user sees this distinction in the optimizer.
"""
from __future__ import annotations
import math

PROFILES = {
    'Rendimiento': {'poll_ms': 120, 'render_seconds': .75, 'assistant_seconds': 1.4, 'chart_resize_ms': 150, 'target_fps': 12, 'avatar_ms': 200},
    'Equilibrado': {'poll_ms': 200, 'render_seconds': 1.2, 'assistant_seconds': 2.0, 'chart_resize_ms': 250, 'target_fps': 7, 'avatar_ms': 320},
    'Ahorro de energía': {'poll_ms': 400, 'render_seconds': 2.3, 'assistant_seconds': 4.0, 'chart_resize_ms': 420, 'target_fps': 3, 'avatar_ms': 800},
}

# Applying a named profile now sets *all* assistant budget knobs, not just
# redraw frequency. These are scheduling/soft-model budgets, not process-wide
# RAM/GPU caps, and are never used to throttle orders or the MT5 risk actor.
PROFILE_BUDGETS = {
    'Rendimiento': {'memory_budget_mb': 4096, 'model_context_tokens': 8192,
                    'model_keep_alive_seconds': 60, 'model_use_gpu': True},
    'Equilibrado': {'memory_budget_mb': 3072, 'model_context_tokens': 4096,
                   'model_keep_alive_seconds': 15, 'model_use_gpu': True},
    'Ahorro de energía': {'memory_budget_mb': 3072, 'model_context_tokens': 2048,
                         'model_keep_alive_seconds': 0, 'model_use_gpu': False},
}

def profile_budget(name):
    return dict(PROFILE_BUDGETS.get(str(name), PROFILE_BUDGETS['Equilibrado']))

LIMITS = {'memory_budget_mb': (512, 16384), 'model_context_tokens': (1024, 16384), 'model_keep_alive_seconds': (0, 600)}
DEFAULTS = {'performance_profile': 'Equilibrado', 'memory_budget_mb': 3072, 'model_context_tokens': 4096,
            'model_keep_alive_seconds': 15, 'model_use_gpu': True, 'pause_hidden_animations': True}

def resolve_profile(value):
    return PROFILES.get(str(value), PROFILES['Equilibrado'])

def get_intervals(config):
    return dict(resolve_profile((config.get('desktop') or {}).get('performance_profile', 'Equilibrado')))

def config_limits(config):
    source = (config.get('desktop') or {}) if isinstance(config, dict) else {}
    limits = dict(DEFAULTS)
    for field, (low, high) in LIMITS.items():
        try:
            v = float(source.get(field, limits[field]))
            if math.isfinite(v): limits[field] = int(max(low, min(high, v)))
        except (ValueError, TypeError): pass
    limits['performance_profile'] = str(source.get('performance_profile', 'Equilibrado')) if source.get('performance_profile') in PROFILES else 'Equilibrado'
    limits['model_use_gpu'] = bool(source.get('model_use_gpu', True))
    limits['pause_hidden_animations'] = bool(source.get('pause_hidden_animations', True))
    return limits

def ollama_limits(config, deep=False):
    """Settings supported by Ollama /api/chat, backed by a testable policy."""
    d = config_limits(config)
    # Context uses model memory quadratic in parts of attention. Extra RAM headroom
    # is left for MT5 and the OS; this does NOT impose a system-wide hard cap.
    tokens = min(d['model_context_tokens'], max(1024, d['memory_budget_mb'] * 2))
    if deep: tokens = min(tokens * 2, 16384)
    return ({'num_ctx': int(tokens), **({'num_gpu': 0} if not d['model_use_gpu'] else {})},
            '0s' if d['model_keep_alive_seconds']==0 else str(d['model_keep_alive_seconds'])+'s')

def process_usage():
    """Diagnostic only; no unexpected process termination or kernel memory caps."""
    try:
        import psutil, os
        me = psutil.Process(os.getpid())
        local = round(me.memory_info().rss/1048576)
        providers={'ollama':0,'llama_server':0}
        for proc in psutil.process_iter(['name']):
            name = str(proc.info.get('name') or '').lower()
            # This is observation only. NEVER terminate another app's model process.
            kind = 'llama_server' if ('llama-server' in name or 'llama_server' in name) else 'ollama' if 'ollama' in name else None
            if kind:
                try:
                    memory=proc.info.get('memory_info') or proc.memory_info()
                    providers[kind] += memory.rss
                except Exception:pass
        return {'akira_mb': local, 'ollama_mb': round(providers['ollama']/1048576),
                'llama_server_mb':round(providers['llama_server']/1048576),
                'system_ram_pct': round(psutil.virtual_memory().percent),
                'akira_cpu_pct': round(me.cpu_percent(interval=None), 1),
                'system_cpu_pct': round(psutil.cpu_percent(interval=None), 1),
                'gpu_pct': None}  # No vendor-neutral per-process GPU meter via psutil.
    except (OSError, ImportError, Exception):
        return {'akira_mb': None, 'ollama_mb': None, 'llama_server_mb': None, 'system_ram_pct': None,
                'akira_cpu_pct': None, 'system_cpu_pct': None, 'gpu_pct': None}
