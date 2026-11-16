"""Opt-in HTTPS companion on a private LAN. Only named, approved actions exist."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime,timedelta,timezone
import hashlib
import hmac
import ipaddress
import json
import os
import secrets
import sqlite3
import ssl
import subprocess
import threading
import time
import uuid
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


PERMISSIONS = frozenset({'status', 'open_website', 'open_application'})


def private_ipv4(address):
    ip=ipaddress.IPv4Address(address)
    return any(ip in ipaddress.IPv4Network(network) for network in
               ('127.0.0.0/8','10.0.0.0/8','172.16.0.0/12','192.168.0.0/16'))


def official_site(value):
    url=urlsplit(value)
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.port not in (None,443):
        raise ValueError('Guarda una dirección HTTPS oficial sin credenciales.')
    if url.query or url.fragment or url.hostname in ('localhost','127.0.0.1') or '.' not in url.hostname:
        raise ValueError('La dirección aprobada debe ser pública y evitar parámetros privados.')
    try:
        ipaddress.ip_address(url.hostname)
    except ValueError:
        return url.geturl()
    raise ValueError('Usa el nombre oficial del sitio, no una dirección IP.')


def lan_identity(root,address):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes,serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import ExtendedKeyUsageOID,NameOID

    ip=ipaddress.IPv4Address(address)
    if not private_ipv4(address):raise ValueError('La identidad requiere una dirección IPv4 privada.')
    root=Path(root)
    root.mkdir(parents=True,exist_ok=True)
    certificate,key=root/'certificate.pem',root/'identity.pem'
    now=datetime.now(timezone.utc)
    if key.is_file() and certificate.is_file():
        existing=x509.load_pem_x509_certificate(certificate.read_bytes())
        sans=existing.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
        if ip in sans.get_values_for_type(x509.IPAddress) and existing.not_valid_after_utc>now+timedelta(days=7):
            return certificate,key,existing.fingerprint(hashes.SHA256()).hex()
    private=ec.generate_private_key(ec.SECP256R1())
    subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'AKIRA en red local')])
    cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(private.public_key())
          .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=5))
          .not_valid_after(now+timedelta(days=365))
          .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip)]),critical=False)
          .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]),critical=True)
          .sign(private,hashes.SHA256()))
    for path,content in ((key,private.private_bytes(serialization.Encoding.PEM,
                         serialization.PrivateFormat.PKCS8,serialization.NoEncryption())),
                         (certificate,cert.public_bytes(serialization.Encoding.PEM))):
        temp=path.with_suffix('.tmp')
        fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
        with os.fdopen(fd,'wb') as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp,path)
    return certificate,key,cert.fingerprint(hashes.SHA256()).hex()


class Companion:
    def __init__(self, root, emit=lambda kind,data:None, clock=time.time):
        self.root=Path(root)
        self.root.mkdir(parents=True,exist_ok=True)
        self.database=self.root/'mobile.sqlite'
        self.emit,self.clock=emit,clock
        self.lock=threading.RLock()
        self.pending={}
        self.pair_code=''
        self.code_expires=0
        self.failed_pairs=0
        self.address=None
        self.fingerprint=None
        self.server=None
        self.actions={}
        with self.db() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS devices (id TEXT PRIMARY KEY, name TEXT NOT NULL,
                    verifier TEXT NOT NULL, scope TEXT NOT NULL, expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS receipts (device TEXT NOT NULL, request TEXT NOT NULL,
                    at REAL NOT NULL, action TEXT NOT NULL, status TEXT NOT NULL,
                    PRIMARY KEY(device, request));''')

    @contextmanager
    def db(self):
        db=sqlite3.connect(self.database,timeout=3)
        try:
            with db:
                yield db
        finally:
            db.close()

    def pair(self):
        with self.lock:
            self.pair_code=f'{secrets.randbelow(100_000_000):08d}'
            self.code_expires=self.clock()+120
            self.failed_pairs=0
            self.pending.clear()
            return self.pair_code

    def request_pairing(self,code,name):
        with self.lock:
            if (not self.pair_code or self.failed_pairs>=5 or self.clock()>=self.code_expires
                    or not hmac.compare_digest(self.pair_code,str(code))):
                self.failed_pairs+=1
                raise PermissionError('Código incorrecto o caducado.')
            self.pair_code=''
            ticket=secrets.token_urlsafe(32)
            device=uuid.uuid4().hex
            name=' '.join(str(name).split())[:60] or 'Teléfono'
            self.pending[device]={'ticket':ticket,'name':name,'expires':self.clock()+120,
                                  'status':'WAITING'}
        self.emit('mobile_pair',{'id':device,'name':name})
        return {'id':device,'ticket':ticket}

    def approve(self,device,scope):
        if not set(scope)<=PERMISSIONS:
            raise ValueError('Permisos de dispositivo no válidos.')
        with self.lock:
            pending=self.pending.get(device)
            if not pending or pending['expires']<=self.clock():return False
            pending['status']='APPROVED' if scope else 'REJECTED'
            pending['scope']=sorted(scope)
            return True

    def paired(self,device,ticket):
        with self.lock:
            pending=self.pending.get(device)
            if not pending or self.clock()>=pending['expires'] or not hmac.compare_digest(pending['ticket'],str(ticket)):
                raise PermissionError('La solicitud de emparejamiento caducó.')
            if pending['status']!='APPROVED':return {'status':pending['status']}
            token=secrets.token_urlsafe(36)
            with self.db() as db:
                db.execute('INSERT INTO devices VALUES (?,?,?,?,?)',
                           (device,pending['name'],self.digest(token),json.dumps(pending['scope']),self.clock()+30*86400))
            self.pending.pop(device,None)
            return {'status':'APPROVED','authorization':device+'.'+token}

    @staticmethod
    def digest(value):
        return hashlib.sha256(value.encode('ascii')).hexdigest()

    def devices(self):
        with self.db() as db:
            return db.execute('SELECT id,name,expires FROM devices ORDER BY name').fetchall()

    def revoke(self,device):
        with self.lock,self.db() as db:
            db.execute('DELETE FROM devices WHERE id=?',(device,))
            db.execute('DELETE FROM receipts WHERE device=?',(device,))

    def authorize(self,db,authorization,now):
        device,_,token=authorization.partition('.')
        row=db.execute('SELECT verifier,scope,expires FROM devices WHERE id=?',(device,)).fetchone()
        if (not row or row[2]<=now or not re_full_token(token)
                or not hmac.compare_digest(self.digest(token),row[0])):
            raise PermissionError('El teléfono no tiene un emparejamiento vigente.')
        return device,json.loads(row[1])

    def receipt(self,authorization,identifier):
        identifier=str(uuid.UUID(identifier))
        now=self.clock()
        with self.lock,self.db() as db:
            device,_=self.authorize(db,authorization,now)
            row=db.execute('SELECT status,at FROM receipts WHERE device=? AND request=?',
                           (device,identifier)).fetchone()
        if not row:raise PermissionError('No se encontró ese recibo.')
        status=row[0]
        if status=='Esperando confirmación en la PC' and now-row[1]>90:status='Solicitud caducada'
        return {'id':identifier,'status':status}

    def request(self,authorization,body):
        action=body.get('action')
        identifier=str(uuid.UUID(body.get('id','')))
        expiry=float(body.get('expires',0))
        now=self.clock()
        if action not in PERMISSIONS or not now<=expiry<=now+90:
            raise PermissionError('La acción o vigencia solicitada es inválida.')
        with self.lock,self.db() as db:
            device,scope=self.authorize(db,authorization,now)
            if action not in scope:
                raise PermissionError('El teléfono no tiene permiso vigente para esta acción.')
            earlier=db.execute('SELECT action,status FROM receipts WHERE device=? AND request=?',
                               (device,identifier)).fetchone()
            if earlier:
                if earlier[0]!=action:raise PermissionError('La solicitud debe tener un identificador nuevo.')
                return {'status':earlier[1],'id':identifier}
            status='AKIRA activo' if action=='status' else 'Esperando confirmación en la PC'
            target=self.actions.get(action)
            if action!='status' and not target:raise PermissionError('La acción requiere un destino configurado en la PC.')
            db.execute('DELETE FROM receipts WHERE at<?',(now-86400,))
            db.execute('INSERT INTO receipts VALUES (?,?,?,?,?)',(device,identifier,now,action,status))
        if action!='status':
            self.emit('mobile_action',{'device':device,'id':identifier,'action':action,'target':target,'expires':expiry})
        return {'status':status,'id':identifier}

    def confirm(self,request,approved):
        device,identifier=request['device'],request['id']
        with self.lock,self.db() as db:
            row=db.execute('SELECT action,status FROM receipts WHERE device=? AND request=?',(device,identifier)).fetchone()
            if not row or row[1]!='Esperando confirmación en la PC':return
            action=row[0]
            auth=db.execute('SELECT scope,expires FROM devices WHERE id=?',(device,)).fetchone()
            target=request['target']
            ready=(approved and self.clock()<request['expires'] and auth is not None and auth[1]>self.clock()
                   and action in json.loads(auth[0]) and self.actions.get(action)==target and self.server is not None)
            status='Confirmada' if ready else 'No autorizada'
            db.execute('UPDATE receipts SET status=? WHERE device=? AND request=?',(status,device,identifier))
        if ready:
            try:
                if action=='open_website':
                    if not webbrowser.open_new_tab(official_site(target)):raise RuntimeError('Navegador no disponible')
                    status='Página abierta en el navegador'
                else:
                    path=Path(target).resolve(strict=True)
                    if path.suffix.lower()!='.exe':raise ValueError('La aplicación configurada debe ser un ejecutable de Windows.')
                    subprocess.Popen([str(path)],cwd=str(path.parent),shell=False)
                    status='Aplicación abierta'
            except (OSError,ValueError,RuntimeError):
                status='Windows no pudo abrir el destino aprobado'
            with self.db() as db:
                db.execute('UPDATE receipts SET status=? WHERE device=? AND request=?',(status,device,identifier))

    def start(self,address,port,certificate,key):
        if self.server:raise RuntimeError('El asistente móvil ya está activo.')
        if not private_ipv4(address):raise ValueError('Selecciona una IPv4 privada de tu PC.')
        context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.minimum_version=ssl.TLSVersion.TLSv1_2
        context.load_cert_chain(certificate,key)
        companion=self
        slots=threading.BoundedSemaphore(8)
        class Server(ThreadingHTTPServer):
            def process_request(self,request,client):
                if not slots.acquire(blocking=False):
                    self.shutdown_request(request)
                    return
                try:
                    super().process_request(request,client)
                except Exception:
                    slots.release()
                    raise

            def process_request_thread(self,request,client):
                try:
                    super().process_request_thread(request,client)
                finally:
                    slots.release()

            def handle_error(self,request,client):
                pass

        class Handler(BaseHTTPRequestHandler):
            def setup(self):
                self.request.settimeout(5)
                super().setup()
            def log_message(self,*_):
                pass
            def do_POST(self):
                try:
                    if not private_ipv4(self.client_address[0]):raise PermissionError('Red no autorizada.')
                    size=int(self.headers.get('Content-Length',0))
                    if not 0<size<=4096 or self.headers.get_content_type()!='application/json':
                        raise ValueError('Solicitud JSON inválida.')
                    body=json.loads(self.rfile.read(size))
                    if not isinstance(body,dict):raise ValueError('Solicitud inválida.')
                    if self.path=='/pair':
                        result=companion.request_pairing(body.get('code',''),body.get('name',''))
                    elif self.path=='/pair/status':
                        result=companion.paired(body.get('id',''),body.get('ticket',''))
                    elif self.path=='/action':
                        result=companion.request(self.headers.get('Authorization','').removeprefix('Bearer '),body)
                    elif self.path=='/action/status':
                        result=companion.receipt(self.headers.get('Authorization','').removeprefix('Bearer '),body.get('id',''))
                    else:
                        self.send_error(404)
                        return
                    code=200
                except PermissionError as error:
                    code,result=403,{'error':str(error)}
                except (ValueError,TypeError,UnicodeError,KeyError,AttributeError):
                    code,result=400,{'error':'Solicitud inválida.'}
                except OSError:
                    code,result=503,{'error':'Servicio temporalmente no disponible.'}
                data=json.dumps(result,ensure_ascii=False).encode('utf-8')
                self.send_response(code)
                for header,value in (('Content-Type','application/json; charset=utf-8'),
                                     ('Cache-Control','no-store'),('Content-Length',str(len(data))),
                                     ('X-Content-Type-Options','nosniff')):
                    self.send_header(header,value)
                self.end_headers()
                self.wfile.write(data)
        server=Server((address,int(port)),Handler,bind_and_activate=True)
        try:server.socket=context.wrap_socket(server.socket,server_side=True,do_handshake_on_connect=False)
        except OSError:server.server_close();raise
        self.server=server
        self.address=f'https://{address}:{server.server_port}'
        threading.Thread(target=server.serve_forever,name='AkiraMobile',daemon=True).start()
        return self.address

    def close(self):
        server,self.server=self.server,None
        self.address=None
        self.fingerprint=None
        if server:
            server.shutdown()
            server.server_close()
        with self.lock:
            self.pair_code=''
            self.pending.clear()


def re_full_token(token):
    return len(token)==48 and all(c.isascii() and (c.isalnum() or c in '_-') for c in token)
