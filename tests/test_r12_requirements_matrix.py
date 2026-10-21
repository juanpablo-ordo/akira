import unittest,json
from pathlib import Path

class TraceabilityTests(unittest.TestCase):
    def test_232_requirements_and_16_conversation_requests_are_accounted_for(self):
        doc=json.loads((Path(__file__).resolve().parents[1]/'REQUISITOS_232_ESTADO.json').read_text(encoding='utf-8'))
        self.assertEqual([r['id'] for r in doc['rows']],[f'R{i:03d}' for i in range(1,233)])
        self.assertEqual(len(doc['extra_requests']),16)
        self.assertFalse(any(r['complete'] for r in doc['rows']+doc['extra_requests']))
        self.assertEqual(doc['counts']['need_windows_acceptance'],248)

if __name__=='__main__':unittest.main()
