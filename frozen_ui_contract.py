"""Critical modules and executable render checks shared by builder and app."""
UI_CHECK_VERSION=8
UI_MODULES=('tk_runtime','desktop_qt','studio_controller','studio_widgets','studio_settings_qt','studio_background','studio_translations','strategy_choice','sprite_recognition','native_studio_check','PySide6.QtWidgets','PySide6.QtGui','PySide6.QtCore','studio_theme','localized_navigation','operation_health','activity_watchdog','desktop','desktop_services','security_details','settings_effects',
    'youtube_support','strategy_adaptation','local_components','avatar_animation','connectivity','language_normalization','local_inference','ui_updates',
    'akira_studio','akira_studio_ui','akira_expressions','akira_live2d','expression_gallery','desktop_layout','cyber_ui','chart_render','chart_indicators','analysis_details','operation_report',
    'risk_reservations','operation_verifier','pending_verification','selection_trials','paired_study','quality_study',
    'trade_quality_gate','strategy_lab','strategy_directory','application_management','position_events','native_ui_check','tests.fake_mt5')

REQUIRED_RENDER_CHECKS=('orders','positions','charts','analysis','sources','context','privacy','visible_amounts',
    'closure_notifications','live_cycle','loop_alive','no_broker_requests','pending_verification',
    'verification_bar','verification_controls','strategy_directory','uninstall_control',
    'expression_catalog','avatar_artwork','avatar_sync','source_access_controls','compact_controls','resizable_layout',
    'operation_mode_visible','private_avatar_controls','state_animation','settings_navigation')

def require_render_check(report):
    check=report.get('render_check') or {}
    if check.get('status')!='PASSED' or check.get('version')!=UI_CHECK_VERSION:
        raise RuntimeError('El ejecutable no comprobó sus paneles con datos completos; se conserva la versión anterior.')
    for key in REQUIRED_RENDER_CHECKS:
        if check.get(key) is not True:raise RuntimeError('La comprobación del ejecutable falló en '+key+'. Se conserva la versión anterior.')
    return check
