"""Exercise the same child process and result contract used by the installer."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

from akira_version import BUILD_ID
from install_checks import run_checks


ROOT=Path(__file__).resolve().parents[1]


class InstallCheckTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='Akira instalación con espacios ')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)/'payload';self.root.mkdir()
        self.logs=Path(self.temp.name)/'diagnóstico persistente'
        shutil.copyfile(ROOT/'offline_test_runner.py',self.root/'offline_test_runner.py')
        shutil.copyfile(ROOT/'akira_version.py',self.root/'akira_version.py')
        (self.root/'tests').mkdir();(self.root/'tests'/'__init__.py').write_text('',encoding='utf-8')
        self.manifest()
        self.case('self.assertEqual(2+2,4)')

    def manifest(self,tests=1,skipped=0):
        (self.root/'VALIDACION_V12.json').write_text(json.dumps({'build':BUILD_ID,'tests':tests,'skipped':skipped}),encoding='utf-8')

    def case(self,body):
        (self.root/'tests'/'test_example.py').write_text(
            'import unittest,socket,time\nclass Example(unittest.TestCase):\n    def test_example(self):\n        '+body+'\n',encoding='utf-8')

    def run_check(self,timeout=10):
        with patch('install_checks.validate') as validate,redirect_stdout(io.StringIO()):
            code=run_checks(self.root,self.logs,timeout=timeout)
        validate.assert_called_once_with(self.root.resolve(),None)
        return code,json.loads((self.logs/'INSTALL_RESULT_AKIRA.json').read_text(encoding='utf-8'))

    def test_real_child_success_and_unicode_paths(self):
        code,result=self.run_check()
        self.assertEqual(code,0);self.assertEqual(result['status'],'PASSED')
        self.assertEqual((result['tests_run'],result['child_exit_code']),(1,0))
        self.assertIn('OK',(self.logs/'INSTALL_TESTS_ERR.log').read_text(encoding='utf-8'))

    def test_failures_keep_the_test_name_and_full_assertion(self):
        self.case("self.assertEqual('pendiente válida','pendiente inválida')")
        code,result=self.run_check();self.assertEqual(code,1)
        self.assertEqual(result['status'],'FAILED');self.assertEqual(result['failures'],1)
        error=(self.logs/'INSTALL_TESTS_ERR.log').read_text(encoding='utf-8')
        self.assertIn('FAIL: test_example',error);self.assertIn('pendiente válida',error)
        self.assertEqual(result['failed_tests'],['tests.test_example.Example.test_example'])
        shared=Path(result['failure_file']).read_text(encoding='utf-8-sig')
        self.assertIn('FAIL: test_example',shared);self.assertIn('pendiente inválida',shared)
        self.assertIn(result['failed_tests'][0],result['message'])

    def test_errors_are_not_hidden_as_success(self):
        self.case("raise RuntimeError('fallo concreto de prueba')")
        code,result=self.run_check();self.assertEqual(code,1);self.assertEqual(result['errors'],1)
        self.assertIn('RuntimeError: fallo concreto',(self.logs/'INSTALL_TESTS_ERR.log').read_text(encoding='utf-8'))
        self.assertIn('RuntimeError: fallo concreto',Path(result['failure_file']).read_text(encoding='utf-8-sig'))
        self.assertIn('Causa detectada: RuntimeError: fallo concreto de prueba',result['message'])
        self.assertEqual(result['failure_details'][0]['test'],'tests.test_example.Example.test_example')

    def test_test_count_mismatch_blocks_replacement(self):
        self.manifest(tests=2)
        code,result=self.run_check();self.assertEqual(code,2);self.assertEqual(result['tests_run'],1)
        self.assertIn('Validación incompleta',result['message'])

    def test_zero_exit_without_report_cannot_authorize_installation(self):
        (self.root/'offline_test_runner.py').write_text('print("OK falso sin pruebas")\n',encoding='utf-8')
        code,result=self.run_check();self.assertEqual(code,2);self.assertEqual(result['status'],'FAILED')

    def test_old_success_is_removed_before_starting(self):
        self.logs.mkdir();(self.logs/'INSTALL_TESTS_RESULT.json').write_text(
            json.dumps({'build':BUILD_ID,'successful':True,'collected':1,'tests_run':1,
                        'failures':0,'errors':0,'skipped':0,'expected_failures':0,
                        'unexpected_successes':0,'network':'blocked'}),encoding='utf-8')
        (self.root/'offline_test_runner.py').write_text('print("sin resultado nuevo")\n',encoding='utf-8')
        code,_=self.run_check();self.assertEqual(code,2)
        self.assertFalse((self.logs/'INSTALL_TESTS_RESULT.json').exists())

    def test_unexpected_skip_does_not_hide_a_missing_check(self):
        self.case("self.skipTest('no ejecutar comprobación')")
        code,result=self.run_check();self.assertEqual(code,2);self.assertEqual(result['skipped'],1)

    def test_zero_tests_is_an_error(self):
        (self.root/'tests'/'test_example.py').unlink()
        code,result=self.run_check();self.assertNotEqual(code,0);self.assertEqual(result['tests_run'],0)

    def test_timeout_kills_validation_and_preserves_diagnostics(self):
        self.case('print("prueba lenta",flush=True);time.sleep(5)')
        code,result=self.run_check(timeout=.2)
        self.assertEqual(code,124);self.assertEqual(result['status'],'FAILED')
        self.assertIn('excedieron',result['message'])
        self.assertTrue((self.logs/'INSTALL_TESTS_ERR.log').is_file())

    def test_actual_child_blocks_network(self):
        self.case("self.assertRaises(PermissionError,socket.getaddrinfo,'example.invalid',443)")
        code,result=self.run_check();self.assertEqual(code,0)
        self.assertEqual(result['tests_run'],1)

    def test_invalid_payload_never_starts_test_process(self):
        with patch('install_checks.validate',side_effect=ValueError('payload incompleto')), \
             patch('install_checks.subprocess.run') as process,redirect_stdout(io.StringIO()):
            code=run_checks(self.root,self.logs)
        self.assertEqual(code,2);process.assert_not_called()
        self.assertIn('payload incompleto',(self.logs/'INSTALL_TESTS_ERR.log').read_text(encoding='utf-8'))
        self.assertIn('ValueError: payload incompleto',(self.logs/'ERROR_AKIRA.txt').read_text(encoding='utf-8-sig'))

    def test_success_removes_a_previous_failure_file(self):
        self.logs.mkdir();(self.logs/'ERROR_AKIRA.txt').write_text('Fallo anterior',encoding='utf-8')
        code,result=self.run_check();self.assertEqual(code,0)
        self.assertNotIn('failure_file',result);self.assertFalse((self.logs/'ERROR_AKIRA.txt').exists())
