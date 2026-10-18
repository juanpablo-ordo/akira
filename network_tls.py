"""Verified HTTPS for source and frozen builds, using system and bundled roots.

Never weakens hostname/chain checks. The cached context is immutable after setup;
loading the Windows certificate stores for every RSS request is expensive.
"""
from functools import lru_cache
import ssl
from urllib import request


@lru_cache(maxsize=1)
def https_context():
    context = ssl.create_default_context()
    import certifi
    context.load_verify_locations(cafile=certifi.where())
    return context


def urlopen(url, data=None, timeout=10, **kwargs):
    # An explicit context is also needed after an HTTP -> HTTPS redirect.
    if data is not None:kwargs['data']=data
    return request.urlopen(url, timeout=timeout,context=https_context(), **kwargs)


def connection_message(error):
    """Public message only; the original exception stays in diagnostics."""
    text = str(error).lower()
    if any(s in text for s in ('certificate_verify_failed','certificate verify failed','local issuer certificate')):
        return ('CONEXIÓN SEGURA PENDIENTE',
                'No se pudo verificar el certificado de esta fuente. Comprueba la fecha de Windows y sus certificados. Akira reintentará automáticamente; las demás fuentes siguen activas.')
    if any(s in text for s in ('no tiene un asistente','modelo no disponible','motor local','llama.cpp')):
        return ('IA PENDIENTE',
                'La revisión de IA aún no está disponible. Akira intentará iniciar el modelo instalado. Si falta un componente, usa Reparar IA en Ajustes → IA y voz. No se considera aprobada ninguna revisión pendiente.')
    if any(s in text for s in ('timeouterror','timed out','timeout','tiempo de espera')):
        return ('REINTENTO PROGRAMADO', 'La fuente tardó demasiado. Akira conserva los datos vigentes y reintentará en segundo plano.')
    if any(s in text for s in ('urlerror','connectionerror','connection refused','getaddrinfo','name resolution')):
        return ('SIN CONEXIÓN CON LA FUENTE', 'Esta fuente no respondió. Las demás fuentes siguen activas y se reintentará automáticamente.')
    return ('NO DISPONIBLE', 'Esta consulta no pudo completarse. Se reintentará en segundo plano. Puedes consultar el diagnóstico en Terminal.')


def check_packaged_https():
    import certifi,os
    from pathlib import Path
    from urllib.parse import urlsplit
    context=https_context()
    checks={'bundled_ca_present':Path(certifi.where()).is_file(),
            'trusted_roots':context.cert_store_stats()['x509_ca'],
            'certificate_required':context.verify_mode==ssl.CERT_REQUIRED,
            'hostname_required':context.check_hostname}
    for name in ('GOOD','BAD_HOST','BAD_CHAIN'):
        url=os.environ.get('AKIRA_TEST_HTTPS_'+name)
        if not url:raise ValueError('La comprobación necesita su servidor TLS de prueba')
        if urlsplit(url).hostname not in ('127.0.0.1','localhost'):raise ValueError('La prueba TLS requiere localhost')
        try:
            with urlopen(url,timeout=5) as response:body=response.read(100)
        except Exception as error:
            if name=='GOOD':raise
            reason=getattr(error,'reason',error)
            if not isinstance(reason,ssl.SSLCertVerificationError):raise
            checks[name.lower()+'_rejected']=True
        else:
            if name!='GOOD':raise AssertionError('Se aceptó un certificado inválido')
            checks['trusted_https']=body==b'AKIRA TLS OK'
    if not all(checks.values()) or checks['trusted_roots']<100:raise AssertionError('Configuración HTTPS incompleta')
    return {'status':'PASSED',**checks}
