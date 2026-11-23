"""Descoberta de seções e blocos VMD no layout HDM-4 de SC.

Não assume 2 seções nem posições de linha fixas. As seções da rodovia
começam A3, F3, K3 ...; na aba VMD, cada bloco é identificado pelo
cabeçalho de anos e quatro categorias VL/ON/VC1/VC2 abaixo dele.
Blocos vazios do modelo de até dez seções não são seções operacionais.
"""
from __future__ import annotations
from dataclasses import dataclass, field
import re
from math import isfinite
from typing import Any

ROAD = 'Características das rodovias'
TRAFFIC = 'Taxas de crescimento e VMD'
VEHICLES=('VL','ON','VC1','VC2')
SEC_RE = re.compile(r'\bS\s*0*(\d+)\b', re.IGNORECASE)
COL_RE = re.compile(r'([A-Z]+)(\d+)')

def to_col(number:int)->str:
    result=''
    while number:
        number,rem=divmod(number-1,26)
        result=chr(65+rem)+result
    return result

def col_num(letter:str)->int:
    n=0
    for char in letter.upper(): n=n*26+ord(char)-64
    return n

def valid_number(v)->bool:
    return isinstance(v,(int,float)) and not isinstance(v,bool) and isfinite(v)

@dataclass(frozen=True)
class RoadSection:
    id: str
    title: str
    start_col: str
    base_col: str
    project_col: str
    start_index: int

@dataclass
class TrafficSection:
    id: str
    heading_row: int
    first_vehicle_row: int
    total_row: int
    label: str
    populated: bool
    series: list[dict]=field(default_factory=list)
    errors: list[str]=field(default_factory=list)
    summaries: list[dict]=field(default_factory=list)


def discover_road_sections(excel, max_sections=150)->list[RoadSection]:
    if not excel.has_sheet(ROAD):return []
    result=[]
    for i in range(max_sections):
        start=1+5*i
        title=excel.cell(ROAD,f'{to_col(start)}3')
        if title is None or str(title).strip()=='':
            # Reserve 5-column blocks, but don't stop at first blank.
            continue
        match=SEC_RE.search(str(title))
        if not match:
            # Hard-fail rather than attaching values to a guessed section ID.
            raise ValueError(f'Bloco {to_col(start)}3 não tem ID S1/S2/...: {title!r}')
        result.append(RoadSection(f'S{int(match.group(1))}',str(title).strip(),to_col(start),
             to_col(start+2),to_col(start+3),start))
    ids=[r.id for r in result]
    if len(ids)!=len(set(ids)):
        raise ValueError('IDs de seções repetidos na aba Características das rodovias.')
    return result


def _vmd_value(excel,col:str,row:int):
    v=excel.cell(TRAFFIC,f'{col}{row}')
    if valid_number(v):return float(v)
    return None


def _year_labels(excel,header_row:int,max_columns=65):
    result=[]
    for i in range(3,max_columns+1):
        col=to_col(i)
        label=excel.cell(TRAFFIC,f'{col}{header_row}')
        if label is None: continue
        if valid_number(label) and 1900<=label<=2200 and int(label)==label:
            result.append((col,int(label),'NORMAL_SERIE'))
        elif isinstance(label,str) and re.search(r'\bnovo\b',label,re.I):
            y=re.search(r'\b(20\d{2})\b',label)
            if y:result.append((col,int(y.group(1)),'PROJETO_TOTAL'))
        elif isinstance(label,str) and re.search(r'\bvaria[cç][aã]o\b',label,re.I):
            y=re.search(r'\b(20\d{2})\b',label)
            if y:result.append((col,int(y.group(1)),'NORMAL_REFERENCIA'))
    return result


def discover_traffic_sections(excel, roads=None, max_rows=1500)->list[TrafficSection]:
    """Inspect header-year rows and category rows; infer S-index only for populated blocks.

    The ten prepared slots B20,B28,B36,... are not all active. A populated
    anonymous block gets its ordinal section ID (never silently joins other IDs).
    """
    if not excel.has_sheet(TRAFFIC):return []
    roads=roads if roads is not None else discover_road_sections(excel)
    result=[]
    used=set()
    ordinal=0
    for r in range(19,max_rows):
        labels=[excel.cell(TRAFFIC,f'B{r+i}') for i in range(1,5)]
        if tuple(str(v).strip().upper() if v is not None else '' for v in labels)!=VEHICLES:
            continue
        years=_year_labels(excel,r)
        if not years:continue
        ordinal+=1
        heading=excel.cell(TRAFFIC,f'B{r}')
        found=SEC_RE.search(str(heading)) if heading is not None else None
        id_=f'S{int(found.group(1))}' if found else f'S{ordinal}'
        if id_ in used:
            raise ValueError(f'Identificador de seção duplicado em VMD: {id_} (linha {r})')
        used.add(id_)
        block=TrafficSection(id_,r,r+1,r+5,str(heading or ''),False)
        for col,year,scenario in years:
            vector=[_vmd_value(excel,col,r+1+i) for i in range(4)]
            total=_vmd_value(excel,col,r+5)
            meaningful=any(v is not None and abs(v)>1e-9 for v in vector) or (total is not None and abs(total)>1e-9)
            if meaningful:
                block.populated=True
                if any(v is None for v in vector) or total is None:
                    block.errors.append(f'{id_}: valores ausentes/inválidos em {col}{r+1}:{col}{r+5}')
                elif abs(sum(vector)-total)>0.03:
                    block.errors.append(f'{id_}: total {col}{r+5}={total:g} difere da soma das classes {sum(vector):g}')
                for name,value in zip(VEHICLES,vector):
                    block.series.append({'secao':id_,'ano':year,'cenario':scenario,'veiculo':name,
                         'valor':value,'celula':f'{col}{r+1+VEHICLES.index(name)}'})
                block.series.append({'secao':id_,'ano':year,'cenario':scenario,'veiculo':'TOTAL',
                     'valor':total,'celula':f'{col}{r+5}'})
        if block.populated:
            result.append(block)
    return result


def discover_traffic_summary(excel, max_rows=1600)->dict[str,list[dict]]:
    """Find the summary after B100 and associate each four-row group with S-index.

    In unused slots the first B cell may be the number 0 rather than 'S3'.
    Therefore we NEVER carry the previous section ID across group boundaries.
    """
    out={}
    start=None
    for r in range(80,min(130,max_rows)):
        if str(excel.cell(TRAFFIC,f'B{r}') or '').casefold().strip()=='trecho' and \
           'tráfego' in str(excel.cell(TRAFFIC,f'C{r}') or '').casefold():
            start=r+1;break
    if start is None:return out
    first=None
    for r in range(start,max_rows):
        text=str(excel.cell(TRAFFIC,f'C{r}') or '').strip().casefold()
        if text=='normal' and valid_number(excel.cell(TRAFFIC,f'D{r}')):
            first=r;break
    if first is None:return out
    # The template uses 4 rows per section (normal base, normal 2024,
    # attracted 2024, total 2024). A later extension may retain this pattern.
    for group_index, r0 in enumerate(range(first,max_rows,4),1):
        if group_index>200:break
        first_type=str(excel.cell(TRAFFIC,f'C{r0}') or '').strip().casefold()
        if first_type!='normal':
            # Stop at the first non-section block, don't borrow a prior ID.
            break
        heading=excel.cell(TRAFFIC,f'B{r0}')
        matched=SEC_RE.search(str(heading)) if heading is not None else None
        sec=f'S{int(matched.group(1))}' if matched else f'S{group_index}'
        if matched and sec!=f'S{group_index}':
            raise ValueError(f'Quadro resumo B{r0} fora da ordem: {sec} no grupo {group_index}')
        for r in range(r0,min(r0+4,max_rows)):
            type_=str(excel.cell(TRAFFIC,f'C{r}') or '').strip()
            if not (type_.casefold().startswith('normal') or type_.casefold() in ('total','atraído / desviado','atraido / desviado')):
                raise ValueError(f'Linha {r} não corresponde ao padrão do resumo para {sec}: {type_!r}')
            vals=[_vmd_value(excel,c,r) for c in 'EFGHI']
            if not any(v is not None and abs(v)>1e-9 for v in vals):continue
            year=excel.cell(TRAFFIC,f'D{r}')
            if not valid_number(year) or any(v is None for v in vals):
                raise ValueError(f'{sec}: dados de resumo incompletos na linha {r}')
            if abs(sum(vals[:4])-vals[4])>0.03:
                raise ValueError(f'{sec}: soma de VMD incorreta no quadro resumo linha {r}')
            out.setdefault(sec,[]).append({'secao':sec,'linha':r,'tipo':type_,
                  'ano':int(year),'VL':vals[0],'ON':vals[1],'VC1':vals[2],
                  'VC2':vals[3],'TOTAL':vals[4]})
    return out


def audit_traffic(excel, roads=None)->dict:
    roads=roads if roads is not None else discover_road_sections(excel)
    blocks=discover_traffic_sections(excel,roads)
    summaries=discover_traffic_summary(excel)
    road_ids={x.id for x in roads}
    errors=[];warnings=[]
    for block in blocks:
        errors+=block.errors
        if block.id not in road_ids:
            errors.append(f'VMD de {block.id} não tem seção correspondente na aba de características.')
        quad=summaries.get(block.id,[])
        block.summaries=quad
        if not quad:
            warnings.append(f'Sem quadro resumo preenchido para {block.id}.')
        # Cross-check observed total-2024 on I vs table 100+ total 2024.
        comp=next((s['valor'] for s in block.series if s['veiculo']=='TOTAL' and s['ano']==2024 and s['cenario']=='PROJETO_TOTAL'),None)
        totals=[s['TOTAL'] for s in quad if s['tipo'].casefold()=='total' and s['ano']==2024]
        if totals and comp is not None and abs(comp-totals[0])>0.03:
            errors.append(f'{block.id}: VMD 2024 (série={comp:g}) diverge do quadro resumo ({totals[0]:g}).')
        normal=next((s for s in quad if s['tipo'].casefold()=='normal' and s['ano']==2024),None)
        atraido=next((s for s in quad if 'atra' in s['tipo'].casefold()),None)
        total=next((s for s in quad if s['tipo'].casefold()=='total' and s['ano']==2024),None)
        if normal and atraido and total:
            for key in (*VEHICLES,'TOTAL'):
                if abs(normal[key]+atraido[key]-total[key])>0.03:
                    errors.append(f'{block.id}: normal + atraído ≠ total 2024 em {key}.')
    for sec, values in summaries.items():
        if values and sec not in road_ids:
            errors.append(f'Quadro resumo contém {sec}, mas essa seção não existe em Características das rodovias.')
        if values and sec not in {b.id for b in blocks}:
            warnings.append(f'Quadro resumo de {sec} contém dados, mas falta bloco VMD correspondente.')
    missing=sorted(road_ids-{b.id for b in blocks},key=lambda x:int(x[1:]))
    if missing: warnings.append('Seções sem VMD preenchido: '+', '.join(missing))
    return {'secoes_rodovia':roads,'blocos':blocks,'resumos':summaries,
            'erros':errors,'alertas':warnings,'vmd_2024':{
            b.id:next((s['valor'] for s in b.series if s['veiculo']=='TOTAL' and s['ano']==2024 and s['cenario']=='PROJETO_TOTAL'),None) for b in blocks}}
