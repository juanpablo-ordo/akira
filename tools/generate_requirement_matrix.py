"""Generate a conservative per-requirement checklist from the owner document.

Only names explicitly tested in this build receive local-evidence labels. The
report NEVER infers that an end-to-end Windows/MT5 requirement is complete.
"""
import argparse,csv,json,re
from pathlib import Path
from docx import Document

LOCAL={
 'R015':['operation_health.py','tests/test_r11_operation_health.py'],
 'R020':['operation_health.py','tests/test_r11_operation_health.py'],
 'R021':['studio_theme.py','tests/test_r12_studio_theme.py'],
 'R036':['activity_watchdog.py','tests/test_r11_activity_watchdog.py'],
 'R037':['activity_watchdog.py','tests/test_r11_activity_watchdog.py'],
 'R038':['operation_health.py','tests/test_r11_operation_health.py'],
 'R041':['operation_health.py','tests/test_r11_operation_health.py'],
 'R045':['operation_health.py','tests/test_r11_operation_health.py'],
 'R047':['operation_health.py','tests/test_r11_operation_health.py'],
 'R048':['pending_verification.py','tests/test_v1626_verification.py'],
 'R058':['desktop.py','tests/test_r11_pending_ui.py'],
 'R060':['execution.py','tests/test_v1626_verification.py'],
 'R103':['pending_verification.py','tests/test_v1626_verification.py'],
 'R136':['akira_live2d.py','tests/test_r8_ui_reactions.py'],
 'R138':['akira_studio.py','tests/test_akira_studio.py'],
 'R139':['akira_studio.py','tests/test_akira_studio.py'],
 'R142':['akira_live2d.py','tests/test_r8_ui_reactions.py'],
 'R151':['desktop.py','tests/test_r11_pending_ui.py'],
 'R153':['desktop.py','tests/test_r11_pending_ui.py'],
 'R154':['desktop.py','tests/test_r11_pending_ui.py'],
 'R159':['studio_theme.py','tests/test_r12_studio_theme.py'],
 'R161':['settings_effects.py','tests/test_akira_studio.py'],
 'R172':['cyber_ui.py','tests/test_r12_studio_theme.py'],
 'R178':['activity_watchdog.py','tests/test_r11_activity_watchdog.py'],
 'R198':['activity_watchdog.py','tests/test_r11_activity_watchdog.py'],
 'R207':['operation_health.py','tests/test_r11_operation_health.py'],
 'R214':['activity_watchdog.py','tests/test_r11_activity_watchdog.py'],
 'R228':['tools/generate_requirement_matrix.py','REQUISITOS_232_ESTADO.json'],
}

EXTRA=[
 ('E01','Recrear con fidelidad las ocho pantallas y todos los modales de las capturas'),
 ('E02','Personalizar nombres visibles y, de ser apropiado, marca de ejecutable/instalador'),
 ('E03','Cambiar colores principales y fondos visuales'),
 ('E04','Cambiar familia y escala tipográfica'),
 ('E05','Cambiar idioma de todas las pantallas, alertas y textos dinámicos'),
 ('E06','Elegir idiomas de entrada y salida de voz, con STT/TTS funcionales'),
 ('E07','Importar sprites propios y ordenar casillas libremente'),
 ('E08','Reconocer automáticamente cualquier expresión de un sprite por visión'),
 ('E09','Crear y editar secuencias animadas de fotogramas'),
 ('E10','Importar wallpapers en video o imagen; movimiento global tras los paneles'),
 ('E11','Recortar, rotar, desplazar y adaptar wallpapers a la ventana'),
 ('E12','Elegir frecuencia, calidad y límites efectivos de CPU/RAM/GPU del fondo'),
 ('E13','Conservar el diseño original como predeterminado'),
 ('E14','Resolver velocidad/precisión y rentabilidad neta de pendientes y runners'),
 ('E15','IA conversacional capaz de entender coloquialismos, faltas y temas actuales'),
 ('E16','Un único instalador nativo comprobado en Windows y MT5 demo'),
]
EXTRA_EVIDENCE={'E03':['studio_theme.py','tests/test_r12_studio_theme.py'],
 'E04':['studio_theme.py','tests/test_r12_studio_theme.py'],
 'E07':['akira_studio.py','tests/test_akira_studio.py'],
 'E09':['akira_studio.py','tests/test_akira_studio.py'],
 'E11':['akira_studio.py','tests/test_akira_studio.py'],
 'E13':['studio_theme.py','tests/test_r12_studio_theme.py']}

# Rev5 records only local component evidence, never Windows/demo acceptance.
LOCAL.update({
 'R003':['settings.py','runner.py','tests/test_studio_rev5.py'],
 'R018':['akira_local_ai.py','tests/test_r8_assistant_protocol.py'],
 'R021':['studio_settings_qt.py','studio_controller.py','tests/test_studio_rev5.py'],
 'R058':['desktop_qt.py','tests/test_studio_rev5.py'],
 'R136':['studio_widgets.py','tests/test_r8_ui_reactions.py'],
 'R138':['studio_widgets.py','tests/test_studio_rev5.py'],
 'R139':['studio_widgets.py','tests/test_r8_ui_reactions.py'],
 'R140':['studio_widgets.py','native_studio_check.py'],
 'R141':['studio_widgets.py','tests/test_r8_ui_reactions.py'],
 'R142':['desktop_qt.py','tests/test_studio_rev5.py'],
 'R143':['studio_widgets.py','native_studio_check.py'],
 'R151':['desktop_qt.py','studio_widgets.py','VERIFICACION_STUDIO_REV5/NATIVE_STUDIO.json'],
 'R153':['desktop_qt.py','VERIFICACION_STUDIO_REV5/NATIVE_STUDIO.json'],
 'R154':['desktop_qt.py','tests/test_studio_rev5.py'],
 'R155':['desktop_qt.py','VERIFICACION_STUDIO_REV5/NATIVE_STUDIO.json'],
 'R159':['studio_settings_qt.py','tests/test_studio_rev5.py'],
 'R161':['studio_controller.py','tests/test_studio_rev5.py'],
 'R162':['studio_controller.py','tests/test_studio_rev5.py'],
 'R165':['akira_secrets.py','tests/test_studio_rev5.py'],
 'R166':['akira_secrets.py','tests/test_studio_rev5.py'],
 'R170':['akira_secrets.py','tests/test_studio_rev5.py'],
 'R171':['studio_settings_qt.py','tests/test_studio_rev5.py'],
 'R172':['studio_widgets.py','VERIFICACION_STUDIO_REV5/CARGA_INTERFAZ.json'],
})
EXTRA_EVIDENCE.update({
 'E01':['desktop_qt.py','studio_widgets.py','VERIFICACION_STUDIO_REV5/NATIVE_STUDIO.json'],
 'E02':['desktop_qt.py','studio_settings_qt.py','native_studio_check.py'],
 'E03':['studio_background.py','studio_settings_qt.py','tests/test_studio_rev5.py'],
 'E04':['desktop_qt.py','studio_settings_qt.py','assets/fonts','native_studio_check.py'],
 'E05':['studio_translations.py','tests/test_studio_rev5.py'],
 'E06':['voice_session.py','studio_controller.py','studio_settings_qt.py'],
 'E07':['akira_studio.py','studio_settings_qt.py','tests/test_studio_rev5.py'],
 'E08':['sprite_recognition.py','installer/prepare_sprite_ai.py','tests/test_studio_rev5.py'],
 'E09':['akira_studio.py','studio_settings_qt.py','tests/test_studio_rev5.py'],
 'E10':['studio_background.py','tests/test_studio_rev5.py'],
 'E11':['studio_background.py','tests/test_studio_rev5.py'],
 'E12':['studio_background.py','tests/test_studio_rev5.py'],
 'E13':['akira_studio.py','studio_background.py','native_studio_check.py'],
 'E14':['engine.py','strategy_choice.py','VERIFICACION_STUDIO_REV5/CARGA_INTERFAZ.json'],
 'E15':['akira_local_ai.py','akira_model_runtime.py','language_normalization.py','web_facts.py','tests/test_studio_rev5.py'],
 'E16':['.github/workflows/build-windows.yml','build_windows.py','installer/check_installed_ai.py'],
})
NOTES={
 'R003':'Modo nuevo permite pendientes y runners normales. Una elección previa explícita de solo pendientes se conserva. Sin operaciones reales en esta validación.',
 'R140':'Reacción acotada al puntero y reducción de movimiento implementadas; aceptación visual personal pendiente.',
 'R156':'No se ha probado DPI real de Windows ni traslado entre monitores físicos.',
 'R174':'El presupuesto del modelo es orientativo. Los límites duros del decodificador propio requieren verificar Windows Job Objects.',
 'R177':'Prueba Linux de 12,34 s con FakeMT5 y chat simulado; sin voz física ni inferencia real simultáneas.',
 'R191':'CI prepara el modelo y sus componentes. No hay un instalador nuevo compilado ni inferencia GGUF real comprobada aquí.',
 'R214':'Pruebas de watchdog disponibles; sesión demo de seis horas pendiente.',
 'R226':'Adaptive selecciona entre reglas existentes. No demuestra una estrategia inédita superior ni incorpora automáticamente cualquier estrategia de video.',
 'E01':'Nueva interfaz nativa predeterminada con ocho pestañas; fidelidad exacta de todos los modales y pantallas de Windows pendiente.',
 'E02':'Nombre visible configurable. Identidad binaria y del instalador AKIRA conservada.',
 'E05':'Paquetes de idioma y generación local implementados. Persisten motivos técnicos dinámicos en español; traducción universal pendiente.',
 'E06':'Selecciones persistentes y sesiones conectadas al avatar. Catálogos limitan idiomas/voz disponibles; micrófono y reproducción físicos no probados.',
 'E08':'Clasificador CLIP opcional y componentes fijados. Pesos no disponibles aquí; sin inferencia semántica real validada. Las sugerencias ambiguas requieren revisión.',
 'E12':'FPS, calidad y búfer acotados. Límites duros CPU/RAM solo para decodificador Windows propio, sin validar aquí. No existe límite duro GPU ni de toda la aplicación.',
 'E14':'Ejecución y rechazo se confirman por resultado, sin cuotas de entradas. Latencia bróker real, sesión prolongada y rentabilidad neta no verificadas.',
 'E15':'Contrato, contexto exacto del servidor, historial acotado, cancelación, escritura y selección de fuentes cubiertos por pruebas; modelo GGUF real y respuesta actual en Windows pendientes.',
 'E16':'Publicación bloqueada por GitHub HTTP 403: Resource not accessible by integration. EXE, instalación Windows y MT5 demo pendientes.',
}

def generate(source,output):
    rows=[]
    for p in Document(source).paragraphs:
        match=re.match(r'^(R\d{3})\.\s*(.+)',p.text.strip(),flags=re.S)
        if not match:continue
        rid,description=match.groups();proof=LOCAL.get(rid,[])
        rows.append(dict(id=rid,requirement=description,
                         status='PARCIAL_PROBADO_LOCALMENTE' if proof else 'NO_VERIFICADO_INTEGRALMENTE',
                         evidence=proof,windows_verified=False,mt5_demo_verified=False,
                         complete=False, acceptance_pending=NOTES.get(rid,'La evidencia local cubre componentes; falta aceptación integral Windows/MT5 demo.')))
    if len(rows)!=232 or len({r['id'] for r in rows})!=232:
        raise RuntimeError('Documento maestro incompleto: no se identificaron los 232 requisitos')
    extra=[dict(id=rid,requirement=description,
                status='PARCIAL_PROBADO_LOCALMENTE' if rid in EXTRA_EVIDENCE else 'NO_VERIFICADO_INTEGRALMENTE',
                evidence=EXTRA_EVIDENCE.get(rid,[]),windows_verified=False,mt5_demo_verified=False,
                complete=False, acceptance_pending=NOTES.get(rid,'Falta aceptación integral del instalador Windows.')) for rid,description in EXTRA]
    obj={'source':Path(source).name,'scope':'R001-R232 y E01-E16',
         'release':'AKIRA 16.4.0 Studio Rev5 · código verificado; Windows pendiente','rows':rows,'extra_requests':extra,
         'rule':'Evidence from Linux mocks/tests is partial; no item marked fully complete until user-acceptance on delivered Windows installer.',
         'counts':{'master':len(rows),'extras':len(extra),'partial_local':sum(x['status'].startswith('PARCIAL') for x in rows+extra),
                    'fully_validated':0,'need_windows_acceptance':len(rows)+len(extra)}}
    out=Path(output);out.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with out.with_suffix('.csv').open('w',newline='',encoding='utf-8-sig') as handle:
        w=csv.DictWriter(handle,fieldnames=('id','requirement','status','evidence','windows_verified','mt5_demo_verified','complete','acceptance_pending'))
        w.writeheader()
        for row in rows+extra:w.writerow({**row,'evidence':'; '.join(row['evidence'])})
    return obj['counts']

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('output');args=parser.parse_args()
    print(json.dumps(generate(args.source,args.output),ensure_ascii=False))
