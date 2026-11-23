"""Cadastro auditável de referências monetárias da frota e da manutenção.

Histórico portátil JSON (download/upload) para protótipo sem banco persistente.
Não atualiza o workbook original nem grava VEHICLES/Works nos MDBs.
"""
from __future__ import annotations
from datetime import datetime, timedelta
from math import isfinite
import json
from .layout import valid_number

ECONOMIA='Dados Econômicos'
MANUT='Custos de Manutenção'
VEHICLES=('VL','ON','VC1','VC2')
FLEET={25:('Veículo novo','R$/veículo'),26:('Pneu novo','R$/pneu'),
 27:('Mão de obra de manutenção','R$/h'),28:('Mão de obra da tripulação','R$/h'),
 29:('Gasolina','R$/litro'),30:('Óleo diesel','R$/litro'),31:('Lubrificante','R$/litro'),
 32:('Tempo do passageiro (trabalho)','R$/h'),33:('Tempo do passageiro (passeio)','R$/h'),
 34:('Atraso da carga','R$/h')}
MAINT=[(5,19,'Pavimentada · conservação','R$/km/ano'),
       (6,20,'Pavimentada · tapa-buracos','R$/m²'),
       (7,21,'Pavimentada · recapeamento','R$/m²'),
       (11,25,'Não pavimentada · conservação','R$/km/ano'),
       (12,26,'Não pavimentada · patrolagem','R$/km'),
       (13,27,'Não pavimentada · recomposição','R$/m³')]


def _month(serial):
    if isinstance(serial,str):
        if len(serial)>=7 and serial[4]=='-':return serial[:7]
        raise ValueError(f'Mês/ano não identificado: {serial}')
    if not valid_number(serial):raise ValueError('Data-base monetária ausente na planilha')
    return (datetime(1899,12,30)+timedelta(days=float(serial))).strftime('%Y-%m')


def _n(v):
    return float(v) if valid_number(v) and float(v)>=0 else None


def build_reference_templates(excel):
    base_month=_month(excel.cell(ECONOMIA,'C2'))
    newer_month=_month(excel.cell(ECONOMIA,'J18'))
    month_cost1=_month(excel.cell(MANUT,'B1'))
    month_cost2=_month(excel.cell(MANUT,'B15'))
    if base_month!=month_cost1 or newer_month!=month_cost2:
        raise ValueError('Datas de frota e manutenção divergem. Criar referências separadas antes de unificá-las.')
    fields=[];original={};updated={}
    for row,(label,unit) in FLEET.items():
        for i,vehicle in enumerate(VEHICLES):
            old=_n(excel.cell(ECONOMIA,f"{'CDEF'[i]}{row}"))
            new=_n(excel.cell(ECONOMIA,f"{'JKLM'[i]}{row}"))
            if old is None and new is None:continue
            key=f'FROTA:{vehicle}:{row}'
            fields.append({'id':key,'grupo':'Frota','parametro':label,'categoria':vehicle,
                    'unidade':unit,'origem_original':f'{ECONOMIA}!{"CDEF"[i]}{row}',
                    'origem_atualizada':f'{ECONOMIA}!{"JKLM"[i]}{row}'})
            original[key]=old;updated[key]=new
    for older,newer,label,unit in MAINT:
        for col,currency in [('D','Financeiro'),('E','Econômico')]:
            old=_n(excel.cell(MANUT,f'{col}{older}'))
            new=_n(excel.cell(MANUT,f'{col}{newer}'))
            if old is None and new is None:continue
            key=f'MANUT:{older}:{currency.upper()}'
            fields.append({'id':key,'grupo':'Manutenção','parametro':label,'categoria':currency,
                   'unidade':unit,'origem_original':f'{MANUT}!{col}{older}',
                   'origem_atualizada':f'{MANUT}!{col}{newer}'})
            original[key]=old;updated[key]=new
    if not fields:raise ValueError('Nenhum custo de frota/manutenção encontrado.')
    if base_month==newer_month:
        raise ValueError('As datas-base históricas estão iguais; requer revisão.')
    refs={base_month:{'periodo':base_month,'valores':original,'origem':'Excel original','observacao':'Histórico importado'},
          newer_month:{'periodo':newer_month,'valores':updated,'origem':'Excel original','observacao':'Histórico importado'}}
    return {'schema':1,'campos':fields,'referencias':refs}


def compare_reference(previous, candidate, fields):
    changes=[]; errors=[]
    for field in fields:
        k=field['id']
        old=previous.get(k)
        new=candidate.get(k)
        if old is None and new is None:continue
        if new is None:
            errors.append(f'Valor obrigatório ausente para {field["parametro"]} / {field["categoria"]}')
            continue
        if not valid_number(new) or float(new)<0:
            errors.append(f'Valor inválido ou negativo para {field["parametro"]} / {field["categoria"]}')
            continue
        if old is None or abs(float(old)-float(new))>1e-9:
            changes.append({'campo':k,'grupo':field['grupo'],'parametro':field['parametro'],
                           'categoria':field['categoria'],'unidade':field['unidade'],
                           'anterior':old,'novo':float(new)})
    return changes,errors


def validate_archive(payload,expected_fields=None):
    """Refuse arbitrary extra identifiers or impossible revisions."""
    if not isinstance(payload,dict) or payload.get('schema')!=1:
        raise ValueError('Arquivo de referências incompatível.')
    fields=payload.get('campos'); refs=payload.get('referencias')
    if not isinstance(fields,list) or not isinstance(refs,dict):
        raise ValueError('Catálogo de referências inválido.')
    ids={f.get('id') for f in fields if isinstance(f,dict)}
    if len(ids)!=len(fields) or not all(isinstance(x,str) for x in ids):
        raise ValueError('Identificadores duplicados ou inválidos.')
    if expected_fields is not None and ids!={f['id'] for f in expected_fields}:
        raise ValueError('O histórico não corresponde aos campos da planilha atual.')
    if len(refs)>300:raise ValueError('Limite de referências excedido.')
    for period,ref in refs.items():
        try:datetime.strptime(period,'%Y-%m')
        except Exception as exc:raise ValueError(f'Referência inválida: {period}') from exc
        if not isinstance(ref,dict) or not isinstance(ref.get('valores'),dict):
            raise ValueError(f'Referência sem valores: {period}')
        for key,value in ref['valores'].items():
            if key not in ids or (value is not None and (not valid_number(value) or float(value)<0)):
                raise ValueError(f'Campo/custo inválido em {period}: {key}')
    return payload


def export_archive(data):
    validate_archive(data)
    return json.dumps(data,ensure_ascii=False,indent=2,sort_keys=True).encode('utf-8')
