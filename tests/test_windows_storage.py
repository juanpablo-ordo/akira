"""Connections must close deterministically; Windows cannot remove an open SQLite file."""
from pathlib import Path
import copy,sqlite3,tempfile,threading,unittest
from unittest.mock import patch
from chat_store import ChatStore
from quality_study import QualityStudy
from settings import DEFAULT

class Connection(sqlite3.Connection):
    closed=False
    def close(self):
        try:return super().close()
        finally:self.closed=True

class WindowsStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='AKIRA memoria y estudio ')
        self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.connections=[];original=sqlite3.connect
        def connect(*args,**kwargs):
            kwargs['factory']=Connection;value=original(*args,**kwargs)
            self.connections.append(value);return value
        patched=patch('sqlite3.connect',side_effect=connect);patched.start()
        self.addCleanup(patched.stop);self.addCleanup(self.close_connections)
    def close_connections(self):
        for connection in self.connections:
            if not connection.closed:connection.close()
    def released(self):
        self.assertTrue(self.connections)
        self.assertTrue(all(connection.closed for connection in self.connections),'SQLite connection kept a Windows file open')
        for connection in self.connections:
            with self.assertRaises(sqlite3.ProgrammingError):connection.execute('SELECT 1')
    def test_chat_operations_close_connections_and_keep_persisted_messages(self):
        store=ChatStore(self.root);store.append('user','Tema anterior');store.append('assistant','Respuesta anterior')
        old=store.active;store.remember('Preferencia persistente');new=store.create('Tema nuevo')
        store.rename(new,'Tema renombrado');store.select(old);store.list();store.related('anterior')
        self.assertEqual(ChatStore(self.root).history()[0]['text'],'Tema anterior')
        self.assertEqual(store.memories()[0]['body'],'Preferencia persistente')
        store.delete(new);store.clear();self.assertFalse(store.history());self.released()
    def test_chat_failed_transaction_rolls_back_and_releases_windows_file(self):
        store=ChatStore(self.root)
        with self.assertRaisesRegex(RuntimeError,'interrumpido'):
            with store.db() as db:
                db.execute("INSERT INTO memories(body,at) VALUES ('No guardar',1000)")
                raise RuntimeError('interrumpido')
        self.assertFalse(store.memories());self.released()
    def test_study_capture_import_measure_and_report_release_every_connection(self):
        study=QualityStudy(self.root);self.addCleanup(study.close)
        plan={'side':1,'kind':'LIMIT','lane':'PENDING','entry':100,'sl':98,'tp':104}
        for at,bid,ask in [(1000,101,101.1),(1030,99.9,100),(1060,104,104.1)]:
            study.capture({'connected':True,'as_of_utc':at,'account':{'login':123,'server':'Prueba'},'symbols':{'BTCUSDm':{'bid':bid,'ask':ask,'quote_time':at,'frames':{'M15':{'last_bar':900}},'scenario_book':[plan]}}})
        cid=study.cases()[0]['id'];path=self.root/'referencia.csv'
        path.write_text('case_id,symbol,source,created_utc,side,kind,entry,sl,tp\n'+cid+',BTCUSDm,Referencia de prueba,1000,BUY,LIMIT,100,98,104\n',encoding='utf-8')
        study.import_references(path);result=study.evaluate_recorded(.1)
        self.assertTrue(result['paired'][0]['complete']);study.export_comparison(self.root/'resultado.csv')
        self.assertEqual(QualityStudy(self.root).summary()['comparisons'],1);self.released()
    def test_study_failed_transaction_rolls_back_and_releases_windows_file(self):
        study=QualityStudy(self.root)
        with self.assertRaisesRegex(RuntimeError,'interrumpido'):
            with study.db() as db:
                db.execute("INSERT INTO meta VALUES ('no_guardar','valor')")
                raise RuntimeError('interrumpido')
        with study.db() as db:self.assertIsNone(db.execute("SELECT value FROM meta WHERE key='no_guardar'").fetchone())
        self.released()
    def test_assistant_and_research_initialization_leave_no_database_files_open(self):
        from assistant_akira import AkiraAssistant
        from research import ContextWorker
        cfg=copy.deepcopy(DEFAULT);bot=AkiraAssistant(cfg,self.root)
        self.assertIn('akira',bot.reply('Cómo te llamas',{}).casefold())
        worker=ContextWorker(cfg,self.root);worker.close();self.released()
    def test_close_waits_for_inflight_study_database_operation(self):
        study=QualityStudy(self.root);entered=threading.Event();release=threading.Event()
        def capture(_):
            with study.db() as db:
                db.execute("INSERT INTO meta VALUES ('trabajo','terminado')");entered.set();release.wait(2)
        study.capture=capture;study.start();study.submit({'connected':True})
        self.assertTrue(entered.wait(1));timer=threading.Timer(.08,release.set);timer.start()
        try:
            study.close();self.assertFalse(study.thread.is_alive());self.released()
        finally:release.set();timer.join();study.close()
    def test_powershell_script_preserves_spanish_in_windows_powershell(self):
        root=Path(__file__).resolve().parents[1]
        for name in ('INSTALL_AKIRA.ps1','PREPARAR_OLLAMA.ps1'):
            data=(root/name).read_bytes();self.assertTrue(data.startswith(b'\xef\xbb\xbf'),name)
            self.assertNotIn('configuraciÃ',data.decode('utf-8-sig'))

if __name__=='__main__':unittest.main()
