"""Validación sin conectar a MT5 ni consultar internet."""
import ast,json,sys
from pathlib import Path
from settings import load_config
from akira_version import BUILD_ID

def validate(root,config=None):
    root=Path(root);cfg=load_config(config or root/'akira_config.json')
    if BUILD_ID!='AKIRA_16_5_2_STUDIO_REV17':raise ValueError('Build incorrecto')
    required=('studio_interaction.py','installation_info.py','qa_user_flow_rev16.py','qa_conversation_rev16.py','installer/check_upgrade.py','risk_limits.py','qa_risk_resources_rev14.py','qa_ui_cost_rev14.py','qa_mt5_accounts_rev13.py','mt5_connection.py','qa_mt5_reconnect_rev12.py','runner_protection.py','conversation_intent.py','order_timing.py','qa_conversation_rev11.py','public_derivatives.py','compact_review.py','qa_sources_rev10.py','entry_momentum.py','qa_review_rev10.py','network_tls.py','snapshot_copy.py','qa_low_resource_rev7.py','assets/avatar_states/motion_bounds.json','studio_editors.py','studio_presenter.py','local_ai_repair.py','assets/avatar_states/akira_rev6_motion.png','tk_runtime.py','Akira.py','desktop_qt.py','studio_controller.py','studio_widgets.py','studio_settings_qt.py','studio_background.py','studio_translations.py','native_studio_check.py','sprite_recognition.py','strategy_choice.py','assets/fonts/Rajdhani-Regular.ttf','assets/fonts/Rajdhani-SemiBold.ttf','akira_studio.py','akira_studio_ui.py','engine.py','planner.py','execution.py','research.py','settings.py','default_config.json','youtube_support.py','strategy_adaptation.py','local_components.py',
              'INSTALL_AKIRA.ps1','migrate_v11_settings.py','offline_test_runner.py','install_checks.py','requirements.txt',
              'install_release.py','assistant_akira.py','assistant_startup.py','web_facts.py','video_vision.py','evolution.py','akira_expressions.py','expression_gallery.py','assets/expressions/catalog.json','akira_live2d.py','command_bridge.py','runner.py',
              'conversation_state.py','decision_status.py','decision_brain.py','risk_reservations.py','response_quality.py','mathematical_reference.py','capital_guard.py','mentor_context.py','operation_report.py','trade_review.py','desktop_layout.py','selection_evidence.py','assets/report_template.xlsx',
              'chat_store.py','reference_library.py','global_sources.py','analysis_details.py','quality_study.py','paired_study.py','voice_session.py','windows_identity.py','build_windows.py','cyber_ui.py','windows_version.txt','assets/akira.ico','desktop_services.py','settings_effects.py','notification_center.py','knowledge_update.py','cache_maintenance.py','chart_indicators.py','chart_render.py','operation_verifier.py','selection_trials.py','security_details.py','frozen_ui_contract.py','native_ui_check.py','tests/fake_mt5.py','position_events.py','pending_verification.py','trade_quality_gate.py','strategy_lab.py','strategy_directory.py','application_management.py','DESINSTALAR_AKIRA.ps1','DESINSTALAR_AKIRA.cmd','GESTION_AKIRA.ps1','INSTALAR_AKIRA.cmd')
    for name in required:
        if not (root/name).is_file():raise ValueError('Payload incompleto: '+name)
    if {p.name for p in root.glob('*.bat')}!={'VALIDAR_AKIRA.bat','DIAGNOSTICO_AKIRA.bat'}:raise ValueError('Scripts del instalador no coinciden con el manifiesto V12')
    for p in root.glob('*.py'):ast.parse(p.read_text(encoding='utf-8-sig'),filename=p.name)
    if any('scalp' in p.name.lower() for p in root.iterdir()):raise ValueError('Módulo de entradas eliminado aún presente')
    if any(x in json.dumps(cfg).lower() for x in ('scalp','ticket_control','impulse_runner')):raise ValueError('Configuración aún contiene entradas de la versión anterior')
    from akira_expressions import ExpressionCatalog
    ExpressionCatalog(root).validate_artwork()
    return cfg

if __name__=='__main__':
    validate(Path(__file__).parent,sys.argv[1] if len(sys.argv)>1 else None)
    print('AKIRA · 16.5.1 Studio Rev16 validada · informes PDF/Excel · chats · llamada · pendientes y runners')
