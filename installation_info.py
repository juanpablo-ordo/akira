"""Identify the executable and data directory without starting trading or AI."""
from pathlib import Path
import sys


def describe_installation():
    from akira_version import BUILD_ID
    from windows_identity import application_root
    from settings import load_config
    root=application_root();path=root/'akira_config.json';present=path.is_file()
    cfg=load_config(path) if present else None
    preferences=None
    if cfg:
        preferences={'risk':{key:cfg['risk'][key] for key in ('max_trade_money','max_trade_pct','portfolio_money_cap','portfolio_capital_pct')},
            'brand_name':cfg['studio']['brand_name'],'language_ui':cfg['studio']['language_ui'],'privacy':cfg['desktop']['privacy']}
    return {'status':'PASSED','build':BUILD_ID,'frozen':bool(getattr(sys,'frozen',False)),
        'executable':str(Path(sys.executable if getattr(sys,'frozen',False) else sys.argv[0]).resolve()),
        'application_data_root':str(root),'config_present':present,'preferences':preferences,
        'broker_started':False,'model_started':False,'credentials_included':False}
