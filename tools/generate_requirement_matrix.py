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

def generate(source,output):
    rows=[]
    for p in Document(source).paragraphs:
        match=re.match(r'^(R\d{3})\.\s*(.+)',p.text.strip(),flags=re.S)
        if not match:continue
        rid,description=match.groups();proof=LOCAL.get(rid,[])
        rows.append(dict(id=rid,requirement=description,
                         status='PARCIAL_PROBADO_LOCALMENTE' if proof else 'NO_VERIFICADO_INTEGRALMENTE',
                         evidence=proof,windows_verified=False,mt5_demo_verified=False,
                         complete=False))
    if len(rows)!=232 or len({r['id'] for r in rows})!=232:
        raise RuntimeError('Documento maestro incompleto: no se identificaron los 232 requisitos')
    extra=[dict(id=rid,requirement=description,
                status='PARCIAL_PROBADO_LOCALMENTE' if rid in EXTRA_EVIDENCE else 'NO_VERIFICADO_INTEGRALMENTE',
                evidence=EXTRA_EVIDENCE.get(rid,[]),windows_verified=False,mt5_demo_verified=False,
                complete=False) for rid,description in EXTRA]
    obj={'source':Path(source).name,'scope':'R001-R232 y E01-E16',
         'release':'R8 Studio Rev4 · source only','rows':rows,'extra_requests':extra,
         'rule':'Evidence from Linux mocks/tests is partial; no item marked fully complete until user-acceptance on delivered Windows installer.',
         'counts':{'master':len(rows),'extras':len(extra),'partial_local':sum(x['status'].startswith('PARCIAL') for x in rows+extra),
                    'fully_validated':0,'need_windows_acceptance':len(rows)+len(extra)}}
    out=Path(output);out.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    with out.with_suffix('.csv').open('w',newline='',encoding='utf-8-sig') as handle:
        w=csv.DictWriter(handle,fieldnames=('id','requirement','status','evidence','windows_verified','mt5_demo_verified','complete'))
        w.writeheader()
        for row in rows+extra:w.writerow({**row,'evidence':'; '.join(row['evidence'])})
    return obj['counts']

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('source');parser.add_argument('output');args=parser.parse_args()
    print(json.dumps(generate(args.source,args.output),ensure_ascii=False))
