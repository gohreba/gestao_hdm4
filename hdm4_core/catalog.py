"""Catálogo EXAUSTIVO das entradas relevantes do padrão SC-110.

Uma referência origem -> destino CANDIDATO não constitui autorização para gravar.
O status de cada item deixa claro o nível de comprovação; nunca iguala
condição pós-obra a condição inicial. Nenhum valor é fabricado.
"""
from __future__ import annotations
from collections import Counter
import csv
from io import StringIO
import math

RODOVIA='Características das rodovias'
ECONOMIA='Dados Econômicos'
TRAFEGO='Taxas de crescimento e VMD'
CUSTOS='Custos de Manutenção'
ORCAMENTO='Orçamento'

# (linha, descricão, campo/estrutura candidato, nota; '' significa sem destino inequívoco)
ROAD={
 6: ('Tipo de superfície','SECTIONS.SURF_CLASS','codificação do HDM-4, não usar texto diretamente'),
 7: ('Extensão','SECTIONS.LENGTH','identificador de segmento S1/S2'),
 8: ('Largura de pista','SECTIONS.CWAY_WIDTH','planilha parece largura por faixa: conferir multiplicação pelo nº de faixas'),
 9: ('Largura de acostamento','SECTIONS.SHLD_WIDTH','- pode significar 0; conferir definição e lado'),
10: ('Número de faixas','SECTIONS.MTLANES','conferir se o campo representa as faixas motorizadas totais'),
12: ('Aclive/declive','SECTIONS / geometria vertical','campo não identificado univocamente'),
13: ('Curvacidade','SECTIONS.CURVATURE','confirmar unidades de graus/km'),
14: ('Velocidade diretriz','SECTIONS.SPEED_LIM','velocidade de projeto não é necessariamente speed limit'),
15: ('Altitude','SECTIONS.ALTITUDE','correspondência direta provável, verificar registros'),
16: ('Subidas e descidas','SECTIONS.NUM_RFS','confirmar se campo é por km ou contagem total'),
17: ('Superelevação','SECTIONS.SUPERELEV','confirmar unidade %'),
19: ('CBR do subleito','SECTIONS.SUBB_STREN','0,08 na planilha significa 8%; não copiar diretamente'),
20: ('Sub-base: material','SECTIONS.SUBG_MATRL','codificação de material do modelo'),
21: ('Sub-base: espessura','SECTIONS.HSUBBASE','confirmar unidade cm/mm e campo'),
23: ('Base: material','SECTIONS / padrão de melhoria','mapeamento construtivo pendente'),
24: ('Base: espessura','SECTIONS.HBASE','confirmar unidade e cenário'),
26: ('Revestimento: material','SECTIONS.SURF_CLASS; Improves','mapeamento de tipo de superfície/obra'),
27: ('Revestimento: espessura','SECTIONS.SURF_THICK; Improves','"5+5" é texto composto; decompor estruturalmente'),
29: ('Área total trincada','SECTIONS.CRACKS_ACA / CRACKS_ACW','"all structural cracks" x tipo de trincamento'),
30: ('IRI','SECTIONS.ROUGHNESS','validação real por importação HDM-4 obtida na SC-110'),
31: ('Desagregação','SECTIONS.RAVEL_AREA','condição BASE'),
32: ('Panelas','SECTIONS.PHOLE_NUM','condição BASE'),
33: ('Bordo quebrado','SECTIONS.EDGEBREAK','condição BASE'),
34: ('Afundamento médio','SECTIONS.RUT_DEPTH','condição BASE'),
}

VERIFIED_BASE_FIELDS={7,30,31,32,33,34}
FLEET_ROWS={
 7:('Equivalente de eixo AASHTO','VEHICLES.ESAL'),
 8:('Equivalência PCSE','VEHICLES.PCSE'),
 9:('Peso bruto','VEHICLES.WEIGHT_OP'),
10:('Número de eixos','VEHICLES.NUM_AXLES'),
11:('Número de pneus','VEHICLES.NUM_WHEELS'),
12:('Passageiros por veículo','VEHICLES / pax occupancy (verificar)'),
17:('Vida de serviço','VEHICLES.LIFE0 / OPTLIFE'),
18:('Quilometragem média anual','VEHICLES.AKM0'),
19:('Utilização anual em horas','VEHICLES.HRWK0 (verificar)'),
20:('Percentual de viagens a trabalho','VEHICLES / WORK (verificar)'),
25:('Veículo novo','VEHICLES.FUC_VEH / EUC_VEH'),
26:('Pneu novo','VEHICLES.FUC_TYRE / EUC_TYRE'),
27:('Mão de obra manutenção','VEHICLES.FUC_LABOUR / EUC_LABOUR'),
28:('Tripulação','VEHICLES.FUC_CREW / EUC_CREW'),
29:('Gasolina','VEHICLES.FUC_FUEL / EUC_FUEL'),
30:('Diesel','VEHICLES.FUC_FUEL / EUC_FUEL'),
31:('Lubrificante','VEHICLES.FUC_OIL / EUC_OIL'),
32:('Tempo passageiro trabalho','VEHICLES.EUC_WORK'),
33:('Tempo passageiro passeio','VEHICLES.EUC_NONWRK'),
34:('Atraso de carga','VEHICLES.EUC_CARGO'),
}
COST_ROWS={5:('Pavimentada: conservação', 'Works.FIN_COST / ECON_COST'),
6:('Pavimentada: tapa buracos', 'Works.FIN_COST / ECON_COST'),
7:('Pavimentada: recapeamento', 'Works.FIN_COST / ECON_COST'),
11:('Não pavimentada: conservação','Works.FIN_COST / ECON_COST'),
12:('Não pavimentada: patrolagem','Works.FIN_COST / ECON_COST'),
13:('Não pavimentada: recomposição','Works.FIN_COST / ECON_COST'),
19:('Pavimentada: conservação (atual)','Works.FIN_COST / ECON_COST'),
20:('Pavimentada: tapa buracos (atual)','Works.FIN_COST / ECON_COST'),
21:('Pavimentada: recapeamento (atual)','Works.FIN_COST / ECON_COST'),
25:('Não pavimentada: conservação (atual)','Works.FIN_COST / ECON_COST'),
26:('Não pavimentada: patrolagem (atual)','Works.FIN_COST / ECON_COST'),
27:('Não pavimentada: recomposição (atual)','Works.FIN_COST / ECON_COST'),
}
BUDGET_ROWS={6:'Terraplanagem',7:'Pavimentação',8:'Drenagem',9:'Sinalização',10:'Obras complementares',11:'Meio ambiente',12:'Ligantes betuminosos',13:'Mobilização e desmobilização',14:'Serviços auxiliares',15:'Obra total',22:'Supervisão',23:'Supervisão total',26:'Custo financeiro da obra',28:'Custo financeiro da supervisão',30:'Custo financeiro global',33:'Custo econômico da obra',35:'Custo econômico da supervisão',37:'Custo econômico global'}

# statuses represent evidence, not inferred proof
STATUS_VALID='VALIDADO_IRI_NO_HDM4' # somente campo IRI foi reimportado e conferido pelo usuário
STATUS_PILOT='HABILITADO_PILOTO' # demais campos do piloto ainda precisam de reimportação
STATUS_CAND='CANDIDATO_REVISAR' # storage field identified, semantics/joins require test
STATUS_PENDING='ESTRUTURA_PENDENTE' # field unverified
STATUS_REFERENCE='REFERENCIA_NAO_IMPORTAR' # duplicate, totals, historic support

def _row(sheet,addr,group,description,value,target='',status=STATUS_PENDING,section='',scenario='',unit='',note=''):
    return {'Grupo':group,'Aba':sheet,'Célula':addr,'Seção':section,'Cenário':scenario,
            'Parâmetro':description,'Valor na planilha':value,'Unidade':unit,
            'Destino candidato':target,'Situação':status,'Observação':note}

def _nonempty(v): return v is not None and v!='' and v!='-'

def build_catalog(excel):
    records=[]
    def add(sh,addr,group,name,target='',status=STATUS_PENDING,section='',scenario='',unit='',note='',empty=False):
        val=excel.cell(sh,addr)
        if not empty and not _nonempty(val): return
        if isinstance(val,str) and val.startswith(('#DIV/0!','#REF!','#VALUE!','#NAME?')):
            return
        records.append(_row(sh,addr,group,name,val,target,status,section,scenario,unit,note))

    for sec, columns in [('S1',('C','D')),('S2',('H','I'))]:
        for scenario,col in zip(('BASE','PÓS-OBRA'),columns):
            for r,(label,target,note) in ROAD.items():
                status = (STATUS_VALID if r == 30 else STATUS_PILOT) if (scenario=='BASE' and r in VERIFIED_BASE_FIELDS) else (
                    STATUS_CAND if target.startswith('SECTIONS.') and scenario=='BASE' else STATUS_PENDING)
                if scenario=='PÓS-OBRA':
                    target='ImprovStds.mdb / Improves; Prj_sectOptImp (validar gatilho e ano)'
                    note='Não sobrescrever condição inicial em SECTIONS. '+note
                add(RODOVIA,f'{col}{r}','Rede / pavimento',label,target,status,sec,scenario,note=note)

    for i,vehicle in enumerate(['VL','ON','VC1','VC2']):
        for row,(label,target) in FLEET_ROWS.items():
            # C:F originais, J:M monetários reindexados. Não misturar com custos econômicos.
            if row <= 20:
                add(ECONOMIA,f'{"CDEF"[i]}{row}','Frota',label,target,STATUS_CAND,vehicle,'REFERÊNCIA ORIGINAL',note='Validar VEH_ID e unidade HDM-4')
            else:
                for col,state in [("CDEF"[i],'BASE FINANCEIRA'),("JKLM"[i],'ATUALIZADO FINANCEIRO')]:
                    add(ECONOMIA,f'{col}{row}','Frota',label,target,STATUS_CAND if col in 'JKLM' else STATUS_REFERENCE,vehicle,state,
                        'R$','Identificar VEH_ID e distinguir campos FUC_ (financeiro) e EUC_ (econômico)')

    for r,(label,target) in COST_ROWS.items():
        state='ATUALIZADO' if r>=19 else 'REFERÊNCIA ORIGINAL'
        for col,currency in [('D','FINANCEIRO'),('E','ECONÔMICO')]:
            add(CUSTOS,f'{col}{r}','Manutenção',label,target,STATUS_CAND if r>=19 else STATUS_REFERENCE,'',f'{state} / {currency}',
                'R$', 'Relacionar o item exato de Works aos padrões usados pela restauração; preços são compartilhados')

    add(RODOVIA,'A35','Referências','Ano de condição da rodovia',
        'SECTIONS.COND_YEAR',STATUS_CAND,'S1/S2','BASE','ano',
        'Ano registrado no cabeçalho de condição; confirmar aplicação às duas seções')

    # 4 growth parameters
    for r,veh in [(5,'VL'),(6,'ON'),(7,'VC1'),(8,'VC2')]:
        add(TRAFEGO,f'C{r}','Tráfego','Taxa de crescimento anual',
            'Prj_vehGrowths / Prj_secGrowths / TRAFFIC_GROWTHS',STATUS_CAND,veh,'ANUAL','fração/ano',
            '0,015 corresponde a 1,5% a.a.; validar período, veículo e cenário')

    # Series for 2021-2043. Growth table: rows 21-24 S1,29-32 S2; totals 25,33.
    vehs=['VL','ON','VC1','VC2']
    for sec,head,first,total in [('S1',20,21,25),('S2',28,29,33)]:
        for c in ('C','D','E','F','G','I',*tuple(chr(x) for x in range(ord('K'),ord('Z')+1)),'AA','AB','AC','AD'):
            year=excel.cell(TRAFEGO,f'{c}{head}')
            if year is None: continue
            for i,veh in enumerate(vehs):
                add(TRAFEGO,f'{c}{first+i}','Tráfego',f'VMD {veh} · {year}',
                    'TRAFFIC.AADT / Prj_vehGrowths / Prj_generatedTraffic',STATUS_CAND,
                    sec,str(year),'veículos/dia',
                    'Série derivada; separar sem obra, normal e tráfego atraído e confrontar YEAR_IDX')
            add(TRAFEGO,f'{c}{total}','Tráfego',f'VMD TOTAL · {year}',
                '',STATUS_REFERENCE,sec,str(year),'veículos/dia',
                'Total de conferência; não atualizar registro de veículo com total agregado')
        # Quadro 2022, normal 2024, atraído 2024 e total 2024 (tabela de 100-110)
        begin=103 if sec=='S1' else 107
        for off,scenario in [(0,'NORMAL 2022'),(1,'NORMAL 2024'),(2,'ATRAÍDO 2024'),(3,'TOTAL 2024')]:
            for j,v in enumerate(vehs):
                add(TRAFEGO,f'{"EFGH"[j]}{begin+off}','Tráfego',f'{v} {scenario}',
                    'TRAFFIC.AADT / Prj_generatedTraffic / Prj_secGrowths',STATUS_CAND,sec,scenario,
                    'veículos/dia','Não aplicar volumes atraídos como tráfego normal')
            add(TRAFEGO,f'I{begin+off}','Tráfego',f'Total {scenario}', '',STATUS_REFERENCE,sec,scenario,'veículos/dia')

    add(ORCAMENTO,'H1','Orçamento','Extensão de rateio', '',STATUS_REFERENCE,'','RATEIO','km',
        'Difere da extensão física (11,04 versus 11,00 km)')
    for row,label in BUDGET_ROWS.items():
        for col,state in [('C','CONTRATUAL'),('F','BASE FINANCEIRA DO HDM')]:
            target='ImprovStds.mdb / Improves; Prj_sectOptImp' if row<30 else 'Padrões e parâmetros de projeto (a validar)'
            add(ORCAMENTO,f'{col}{row}','Orçamento',label,target,STATUS_CAND if row in (15,22,23) else STATUS_REFERENCE,
                '',state,'R$','Custos agregados não equivalem a custo por unidade do HDM; definir cronograma e opção')
        # rateios financeiros apenas auditoria, sem alterar HDM
        for col in ('D','G'):
            add(ORCAMENTO,f'{col}{row}','Orçamento',f'{label}: por km','',STATUS_REFERENCE,'','RATEIO','R$/km')

    # Inputs temporais / índices monetários, explícitos embora não necessariamente implementáveis
    for sh,addr,name in [(ECONOMIA,'C2','Data-base original frota'),(ECONOMIA,'J18','Data-base atualização frota'),
                         (ECONOMIA,'I20','IGP-DI original'),(ECONOMIA,'J20','IGP-DI novo'),(ECONOMIA,'K20','Fator IGP-DI'),
                         (CUSTOS,'B1','Data-base custos manutenção'),(CUSTOS,'B15','Data-base manutenção atualizada'),
                         (ORCAMENTO,'C3','Data-base da obra'),(ORCAMENTO,'C19','Data-base supervisão')]:
        add(sh,addr,'Referências','Referência temporal/índice: '+name,'',STATUS_REFERENCE,'','REFERÊNCIA',note='Metadado para rastreabilidade; não há destino direto validado')
    return records


def catalog_csv(rows):
    with StringIO() as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]) if rows else ['Aba','Célula'])
        writer.writeheader()
        writer.writerows(rows)
        return '\ufeff'+f.getvalue()


def catalog_summary(rows):
    return {'itens_total':len(rows),'por_grupo':dict(Counter(r['Grupo'] for r in rows)),
            'por_status':dict(Counter(r['Situação'] for r in rows))}
