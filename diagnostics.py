"""Diagnóstico local sin abrir operaciones ni revelar credenciales."""
import importlib,sys
from pathlib import Path
from settings import load_config
from akira_version import BUILD_ID

def main():
    root=Path(__file__).parent;print(BUILD_ID);print('Python',sys.version.split()[0]);cfg=load_config(root/'akira_config.json')
    print('Modo:',cfg['mode'],'Símbolos:',', '.join(s for s,on in cfg['symbols'].items() if on))
    print('Riesgo por pendiente:',cfg['risk']['max_trade_money'],'/ techo conjunto %:',cfg['risk']['portfolio_capital_pct'])
    for module in ('MetaTrader5','yt_dlp','tkinter','PIL','imageio_ffmpeg','assistant_akira','evolution'):
        try:importlib.import_module(module);print(module,'OK')
        except ImportError:print(module,'NO INSTALADO')
    from akira_secrets import get_secret
    for name in ('COINGLASS_API_KEY','YOUTUBE_API_KEY','OPENAI_API_KEY'):print(name,'configurada' if get_secret(name) else 'sin configurar')
    from knowledge import KnowledgeStore
    print('Memoria:',KnowledgeStore(root).stats())
    print('Preferencias IA local:',cfg['assistant']['local_model'],'/ visión:',cfg['assistant']['local_vision_model'])
    print('Recuperación previa:',(root/'RECUPERACION_AKIRA.json').read_text(encoding='utf-8') if (root/'RECUPERACION_AKIRA.json').exists() else 'no se requirió')
    print('No se ha conectado a una cuenta ni enviado órdenes.')

if __name__=='__main__':main()
