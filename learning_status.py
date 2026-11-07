"""Evidence-backed learning progress; base LLM weights are never called trained."""
def progress(outcomes,daily,account,enabled=True):
    from akira_version import BUILD_ID
    matching=daily.get('account')==list(account or ()) and daily.get('execution_build')==BUILD_ID
    reports=daily.get('family_reports',{}) if matching else {}
    champions=daily.get('family_champions',{}) if matching else {}
    families=[]
    for symbol,models in reports.items():
        for family,row in models.items():
            champion=(champions.get(symbol) or {}).get(family) or {}
            families.append({'symbol':symbol,'family':family,'samples':int(row.get('samples',0)),
                'train_samples':int(row.get('train_samples',0)),'test_samples':int(row.get('test_samples',0)),
                'validated_model':bool(champion.get('promoted')),'reason':row.get('reason','')})
    validated=sum(r['validated_model'] for r in families)
    complete=sum(bool(r.get('confirmed') and r.get('campaign_complete') and r.get('features')) for r in outcomes)
    return {'enabled':bool(enabled),'confirmed_closures':len(outcomes),'complete_featured_campaigns':complete,
        'comparable_campaigns':int(daily.get('comparable_campaigns',0)) if matching else 0,
        'minimum_campaigns_per_family':80,'minimum_days':5,'validated_models':validated,
        'ranking_model_available':bool(enabled and validated),'families':families,
        'stage':'DISABLED' if not enabled else 'VALIDATED' if validated else 'TRAINED_OBSERVATION' if any(r['train_samples'] for r in families) else 'COLLECTING',
        'base_language_model_training':False,
        'detail':('Aprendizaje desactivado.' if not enabled else
            str(len(outcomes))+' cierres propios guardados; '+str(complete)+' campañas completas con variables. '+
            str(validated)+' modelos validados. Se comparan familias y vías por cuenta, con validación cronológica antes de ajustar la selección.')}
