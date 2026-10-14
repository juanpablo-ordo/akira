"""Validate optional OpenAI without creating a billable model response."""
import json
from urllib.request import Request,urlopen
from akira_secrets import get_secret

def verify_cloud(opener=urlopen):
 key=get_secret('OPENAI_API_KEY')
 if not key:return {'ok':False,'detail':'Falta OPENAI_API_KEY. La casilla autoriza el servicio; no crea una cuenta ni una clave.'}
 try:
  request=Request('https://api.openai.com/v1/models',headers={'Authorization':'Bearer '+key,'Accept':'application/json'})
  with opener(request,timeout=8) as response:data=json.loads(response.read(1000000))
  if not isinstance(data.get('data'),list):raise ValueError('Respuesta de disponibilidad no reconocida')
  return {'ok':True,'models':sorted(str(r['id']) for r in data['data'] if isinstance(r,dict) and r.get('id')),'detail':'Conexión autenticada. La lista de modelos no verifica saldo ni autoriza todos los tipos de respuesta. Las respuestas OpenAI pueden tener coste en tu cuenta API.'}
 except Exception as exc:
  code=getattr(exc,'code',None)
  kind=''
  try:kind=str(json.loads(exc.read(20000)).get('error',{}).get('code') or '')
  except Exception:pass
  if kind in ('insufficient_quota','credit_balance_exhausted'):detail='Créditos API agotados. Revisa la facturación de tu cuenta OpenAI.'
  elif kind in ('project_spend_limit_exceeded','organization_spend_limit_exceeded'):detail='Se alcanzó el límite de gasto del proyecto u organización.'
  elif code==401:detail='Clave no válida, vencida o proyecto/IP sin autorización. Reemplaza la clave o revisa sus permisos.'
  elif code==403:detail='El proyecto, los permisos o la región no permiten esta solicitud.'
  elif code==429:detail='Límite de solicitudes alcanzado. Espera antes de volver a verificar.'
  elif code==404:detail='Modelo o endpoint no disponible para tu proyecto.'
  elif code and code>=500:detail='OpenAI está temporalmente indisponible. Reintenta más tarde.'
  else:detail='No se confirmó la conexión. Revisa tu acceso a Internet y la configuración.'
  return {'ok':False,'http_code':code,'detail':detail+' AKIRA continúa con sus otros recursos.'}
