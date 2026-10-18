"""Exercise the actual packaged HTTPS client with trusted and invalid TLS."""
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
import argparse,json,os,ssl,subprocess,sys,tempfile,threading

ROOT=Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))


@contextmanager
def fixture_server(certificate='localhost'):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200);self.end_headers();self.wfile.write(b'AKIRA TLS OK')
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(ROOT/'tests/tls_fixture'/f'{certificate}.pem',ROOT/'tests/tls_fixture'/f'{certificate}.key')
    server.socket=context.wrap_socket(server.socket,server_side=True)
    thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
    try:yield server.server_port
    finally:server.shutdown();server.server_close();thread.join(5)


def run(executable=None,report=None):
    with fixture_server() as good,fixture_server('untrusted') as bad,tempfile.TemporaryDirectory() as tmp:
        destination=Path(report or Path(tmp)/'https.json').resolve()
        env=os.environ.copy();env.update(SSL_CERT_FILE=str(ROOT/'tests/tls_fixture/localhost.pem'),
            AKIRA_TEST_HTTPS_GOOD=f'https://localhost:{good}',AKIRA_TEST_HTTPS_BAD_HOST=f'https://127.0.0.1:{good}',AKIRA_TEST_HTTPS_BAD_CHAIN=f'https://localhost:{bad}')
        command=[str(executable)] if executable else [sys.executable,str(ROOT/'Akira.py')]
        result=subprocess.run(command+['--https-check',str(destination)],env=env,capture_output=True,text=True,timeout=40)
        if result.returncode:raise RuntimeError('Falló la comprobación TLS: '+(destination.read_text(encoding='utf-8') if destination.exists() else result.stderr))
        return json.loads(destination.read_text(encoding='utf-8'))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--exe',type=Path);parser.add_argument('--report',type=Path,required=True);args=parser.parse_args()
    args.report.parent.mkdir(parents=True,exist_ok=True);print(json.dumps(run(args.exe,args.report),indent=2))
