from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import load_workbook
from pypdf import PdfReader

from operation_report import build_report, export_report
from report_filter import ReportFilter
from studio_presenter import report_html, rich_text


class FilteredReportTests(unittest.TestCase):
    def test_same_capture_for_preview_pdf_xlsx_and_json(self):
        utc=datetime.fromisoformat('2026-11-14T20:00:00+00:00')
        now=utc.timestamp()
        scope=ReportFilter.dates('2026-11-14','2026-11-14','America/New_York',
                                 symbol='XAUUSDm',strategy='estructural',side='SELL')
        snapshot={
            'as_of_utc':now,'connected':True,'build':'build de prueba','account_origin':'mt5_demo',
            'account_ref':'demo-test','account':{'login':70122901,'server':'Servidor-Senuelo','equity':12766.51,'currency':'EUR'},
            'locale':{'timezone':'America/New_York','date_format':'%Y-%m-%d','time_format':'%I:%M:%S %p'},
            'markets':{'XAUUSDm':{'scheduled_closed':True}},
            'position_journal':{'41':{'plan':{'strategy_id':'estructural'}}},
            'history_deals':[
                {'position_id':41,'symbol':'XAUUSDm','time':now-500,'type':1,'entry':0,'price':2500,'volume':.01,'commission':-.15},
                {'position_id':41,'symbol':'XAUUSDm','time':now-450,'type':0,'entry':1,'price':2498,'volume':.01,'profit':.25,'fee':-.10},
            ],
            'portfolio_risk':{'reserved_usd':0,'rows':[{'symbol':'XAUUSDm','ticket':51,'kind':'pending','reserved_usd':0}]},
            'operational_events':[
                {'utc':utc.isoformat(),'account_ref':'other-account','operation':'cancel','message':'Other account'},
                {'utc':utc.isoformat(),'account_ref':'demo-test','operation':'cancel','symbol':'XAUUSDm','side':'SELL',
                 'strategy_id':'estructural','message':'Servidor-Senuelo 70122901 sk-security-probe-09876'},
            ],
        }
        model=build_report(snapshot,report_filter=scope)
        self.assertAlmostEqual(model['closed'][0]['net_usd'],0)
        self.assertEqual(model['tables']['Riesgo'][0][7],0)
        self.assertIn('Neto EUR',report_html(model))
        self.assertEqual(rich_text(0),'0')
        self.assertIn('sin dato',rich_text(None).lower())
        with TemporaryDirectory() as folder:
            root=Path(folder)
            export_report(model,root/'same.pdf')
            export_report(model,root/'same.xlsx',format='xlsx')
            newsheet=load_workbook(root/'same.xlsx',data_only=True)
            self.assertEqual(newsheet['Cierres']['J5'].value,'Neto EUR')
            self.assertIsInstance(newsheet['Cierres']['E6'].value,datetime)
            self.assertEqual(newsheet['Riesgo']['H6'].value,0)
            self.assertNotIn('Servidor-Senuelo',newsheet['Decisiones']['E6'].value)
            pdf=' '.join(page.extract_text() for page in PdfReader(root/'same.pdf').pages)
            self.assertIn('America/New_York',pdf)
            self.assertIn('0.00 EUR',pdf)
            data=(root/'same_datos.json').read_text(encoding='utf-8')
            for marker in ('70122901','Servidor-Senuelo','sk-security-probe','Other account'):
                self.assertNotIn(marker,pdf+data)
            self.assertEqual(json.loads(data)['as_of_utc'],now)
            hidden=build_report(snapshot,report_filter=scope,hide_amounts=True)
            self.assertIsNone(hidden['closed'][0]['net_usd'])
            self.assertNotIn('12766.51',json.dumps(hidden))

    def test_calendar_filter_has_correct_length_on_dst_boundary(self):
        scope=ReportFilter.dates('2026-11-01','2026-11-01','America/New_York')
        self.assertEqual(scope.end_utc-scope.start_utc,25*3600)
        self.assertTrue(scope.matches({},stamp=scope.start_utc))
        self.assertFalse(scope.matches({},stamp=scope.end_utc))
