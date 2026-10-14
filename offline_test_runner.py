"""Run installer tests without DNS lookups or network connections."""
import argparse
import json
import os
import re
from pathlib import Path
import socket
import time
import tempfile
import unittest
from unittest.mock import patch
from akira_version import BUILD_ID


def denied(*args,**kwargs):
    raise PermissionError('Las pruebas del instalador no permiten acceso a la red')

def failure_details(result):
    rows=[]
    for kind,errors in (('failure',result.failures),('error',result.errors)):
        for test,trace in errors:
            lines=[line.strip() for line in trace.splitlines() if line.strip()]
            message=next((line for line in reversed(lines) if re.match(r'\w*(?:Error|Exception):',line)),lines[-1] if lines else 'Sin detalle')
            rows.append({'test':test.id(),'kind':kind,'exception':message[:700]})
    return rows


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--pattern',default='test*.py')
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    root=Path(__file__).resolve().parent
    if args.report:
        args.report=args.report.resolve()
        args.report.parent.mkdir(parents=True,exist_ok=True)
        args.report.unlink(missing_ok=True)
    os.chdir(root)
    started=time.perf_counter()
    # Never read or overwrite a customer's shared Windows preparation profile.
    # Scope this before discovery as well, so imports use the same isolation.
    with tempfile.TemporaryDirectory(prefix='AkiraValidacion_') as appdata, \
         patch.dict(os.environ,{'LOCALAPPDATA':appdata}), \
         patch.object(socket,'getaddrinfo',denied), \
         patch.object(socket.socket,'connect',denied), \
         patch.object(socket.socket,'connect_ex',denied), \
         patch.object(socket,'create_connection',denied):
        suite=unittest.defaultTestLoader.discover(str(root/'tests'),pattern=args.pattern,top_level_dir=str(root))
        collected=suite.countTestCases()
        result=unittest.TextTestRunner(verbosity=2).run(suite)
    if args.report:
        summary={'build':BUILD_ID,'collected':collected,'tests_run':result.testsRun,
                 'successful':result.wasSuccessful(),'failures':len(result.failures),
                 'errors':len(result.errors),'skipped':len(result.skipped),
                 'expected_failures':len(result.expectedFailures),
                 'unexpected_successes':len(result.unexpectedSuccesses),
                 'failed_tests':[test.id() for test,_ in result.failures+result.errors],
                 'failure_details':failure_details(result),
                 'skipped_tests':[{'test':test.id(),'reason':reason} for test,reason in result.skipped],
                 'seconds':round(time.perf_counter()-started,3),'network':'blocked'}
        temp=args.report.with_suffix('.tmp')
        temp.write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
        temp.replace(args.report)
    return 0 if result.wasSuccessful() and collected>0 else 1


if __name__=='__main__':
    raise SystemExit(main())
