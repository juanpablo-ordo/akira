"""Versioned place codes for presentation preferences."""
from functools import lru_cache
import json
from pathlib import Path
import sys


@lru_cache(maxsize=1)
def catalog():
    root=Path(getattr(sys,'_MEIPASS',Path(__file__).resolve().parent))
    return json.loads((root/'assets'/'locale_catalog.json').read_text(encoding='utf-8'))


def continent_for(country):
    return next((code for code,row in catalog()['continents'].items()
                 if country in row['countries']),'other')


def countries(continent,language='es'):
    data=catalog()
    names=data['countries_en' if language=='en' else 'countries']
    codes=data['continents'].get(continent,{}).get('countries')
    if codes is None:
        codes=[code for code in data['subdivisions'] if continent_for(code)=='other']
    return sorted(((code,names.get(code,code)) for code in codes),key=lambda item:item[1].casefold())


def divisions(country):
    return sorted(catalog()['subdivisions'].get(country,{}).items(),key=lambda item:item[1].casefold())


def subdivision_code(country,value):
    return next((code for code,name in divisions(country)
                 if value.casefold() in (name.casefold(),code.casefold())),value)


def division_label(country):
    return {'GT':'Departamento','SV':'Departamento','HN':'Departamento','NI':'Departamento',
            'CO':'Departamento','UY':'Departamento','US':'Estado','MX':'Estado','BR':'Estado',
            'AU':'Estado','IN':'Estado','CA':'Provincia','AR':'Provincia','PA':'Provincia',
            'EC':'Provincia','CR':'Provincia','ES':'Comunidad autónoma'}.get(country,'División administrativa')
