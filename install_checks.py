"""Validate before replacing Akira, with a real exit code and durable diagnostics."""
import argparse
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import traceback

from akira_version import BUILD_ID
from validate_install import validate


def write_json(path,data):
    temp=path.with_suffix('.tmp')
    temp.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    temp.replace(path)


def text_output(value):
    if isinstance(value,bytes):return value.decode('utf-8',errors='replace')
    return value or ''


def run_checks(root,log_dir,config=None,timeout=300):
    root=Path(root).resolve();log_dir=Path(log_dir).resolve()
    log_dir.mkdir(parents=True,exist_ok=True)
    result_path=log_dir/'INSTALL_RESULT_AKIRA.json'
    test_path=log_dir/'INSTALL_TESTS_RESULT.json'
    failure_path=log_dir/'ERROR_AKIRA.txt'
    # A prior successful report must never authorize a new installation.
    test_path.unlink(missing_ok=True)
    failure_path.unlink(missing_ok=True)
    result={'build':BUILD_ID,'status':'RUNNING','exit_code':None,
            'started':datetime.now(timezone.utc).isoformat(),
            'python':sys.version,'platform':platform.platform(),
            'tests_run':0,'message':'Validación aún sin completar'}
    write_json(result_path,result)
    stdout='';stderr='';exit_code=2
    try:
        validate(root,config)
        manifest=json.loads((root/'VALIDACION_V12.json').read_text(encoding='utf-8-sig'))
        expected=manifest['tests'];expected_skipped=manifest.get('skipped',0)
        if manifest['build']!=BUILD_ID or type(expected) is not int or expected<=0:
            raise ValueError('Manifiesto de pruebas inválido para este build')
        if type(expected_skipped) is not int or not 0<=expected_skipped<expected:
            raise ValueError('Recuento de pruebas omitidas inválido')
        env=os.environ.copy();env.update(PYTHONUTF8='1',PYTHONIOENCODING='utf-8')
        process=subprocess.run([sys.executable,'-X','utf8',str(root/'offline_test_runner.py'),
                                '--report',str(test_path)],cwd=root,env=env,
                               capture_output=True,encoding='utf-8',errors='replace',timeout=timeout)
        stdout=process.stdout;stderr=process.stderr
        result['child_exit_code']=process.returncode
        summary=json.loads(test_path.read_text(encoding='utf-8')) if test_path.is_file() else {}
        result.update({k:summary.get(k) for k in ('collected','tests_run','failures','errors','skipped','failed_tests','failure_details')})
        complete=(summary.get('build')==BUILD_ID and summary.get('network')=='blocked'
                  and summary.get('successful') is True
                  and type(summary.get('collected')) is int and summary['collected']==expected
                  and type(summary.get('tests_run')) is int and summary['tests_run']==expected
                  and summary.get('failures')==0 and summary.get('errors')==0
                  and summary.get('skipped')==expected_skipped
                  and summary.get('expected_failures')==0 and summary.get('unexpected_successes')==0)
        if process.returncode!=0:
            exit_code=1
            failed=summary.get('failed_tests') or []
            names='; '.join(str(name) for name in failed[:8])
            result['message']='Hay pruebas fallidas'+(': '+names if names else '')+'. El registro conserva sus errores completos.'
            causes=list(dict.fromkeys(str(row.get('exception','')) for row in (summary.get('failure_details') or []) if row.get('exception')))
            if causes:result['message']+=' Causa detectada: '+'; '.join(causes[:3])
        elif not complete:
            result['message']=f'Validación incompleta: se esperaban {expected} pruebas y {expected_skipped} omitidas. No autoriza reemplazo.'
        else:
            exit_code=0
            result['message']=f'{expected} pruebas completadas; payload y configuración válidos.'
    except subprocess.TimeoutExpired as e:
        exit_code=124;stdout=text_output(e.stdout);stderr=text_output(e.stderr)
        result['message']=f'Las pruebas excedieron {timeout} segundos; se detuvo el proceso de validación.'
    except Exception as e:
        stderr+=traceback.format_exc()
        result['message']=type(e).__name__+': '+str(e)
    result.update(status='PASSED' if exit_code==0 else 'FAILED',exit_code=exit_code,
                  finished=datetime.now(timezone.utc).isoformat())
    (log_dir/'INSTALL_TESTS_OUT.log').write_text(stdout,encoding='utf-8')
    (log_dir/'INSTALL_TESTS_ERR.log').write_text(stderr,encoding='utf-8')
    if exit_code!=0:
        result['failure_file']=str(failure_path)
        failure_path.write_text(
            'AKIRA - ERROR COMPLETO DE INSTALACION\n\n'
            +json.dumps(result,ensure_ascii=False,indent=2)
            +'\n\nSALIDA DE VALIDACION\n'+stdout
            +'\n\nERRORES COMPLETOS\n'+stderr,encoding='utf-8-sig')
    write_json(result_path,result)
    # Send test output through stdout. unittest's normal stderr is not a
    # PowerShell NativeCommandError and must not interrupt success reporting.
    for output in (stdout,stderr):
        if output:print(output,end='' if output.endswith('\n') else '\n',flush=True)
    print(result['message'],flush=True)
    print('Diagnóstico conservado: '+str(log_dir),flush=True)
    if exit_code!=0:print('Archivo para revisar o adjuntar: '+str(failure_path),flush=True)
    return exit_code


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--log-dir',required=True,type=Path)
    parser.add_argument('--config',type=Path)
    args=parser.parse_args()
    return run_checks(Path(__file__).parent,args.log_dir,args.config)


if __name__=='__main__':
    raise SystemExit(main())
