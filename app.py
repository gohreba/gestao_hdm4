"""Protótipo piloto da Plataforma de Gestão Integrada de SC — HDM-4.

Limitação explícita: gera MDB para importação no HDM-4, NÃO altera objects.dat/.idx.
"""
from __future__ import annotations
from io import BytesIO
from pathlib import Path
import hashlib
import tempfile

import streamlit as st

from hdm4_core.excel_reader import read_excel
from hdm4_core.validation import build_validation,attach_old_values,SAFE_FIELDS,REVIEW_FIELDS
from hdm4_core.workspace import inspect_zip,network_bytes
from hdm4_core.mdb_bridge import MDBError,snapshot,update_and_verify,inspect_tables
from hdm4_core.package import build_import_package
from hdm4_core.catalog import build_catalog,catalog_csv,catalog_summary
from hdm4_core.layout import discover_road_sections, audit_traffic
from hdm4_core.references import build_reference_templates, compare_reference, validate_archive, export_archive

st.set_page_config(page_title="HDM-4 | Gestão Integrada SC", page_icon="🛣️", layout="wide", initial_sidebar_state="expanded")
st.markdown('''<style>
[data-testid="stAppViewContainer"] {background: #f7f9fc;}
[data-testid="stSidebar"] {background: #edf2f8;}
.block-container {padding-top:1.5rem;max-width:1350px;}
h1,h2,h3{color:#18365c;}
.note {padding:12px 15px;border-left:4px solid #de9b32;background:#fffaf0;border-radius:4px;color:#474747;}
</style>''', unsafe_allow_html=True)

st.sidebar.markdown("## Plataforma Integrada SC")
st.sidebar.caption("Módulo · Avaliação Econômica / HDM-4")
st.sidebar.markdown("**Versão:** 0.3.0 — Seções dinâmicas + referências econômicas")
st.sidebar.info("HDM-4 continua responsável por executar as simulações econômicas. Este módulo prepara a atualização de dados.")

st.title("🛣️ HDM-4 | Atualização de Projetos")
st.write("Importe o workspace e a planilha padrão, confira os parâmetros e gere um pacote de atualização auditado para o HDM-4.")
st.warning("**Estado desta versão:** o pacote contém um MDB atualizado para **reimportação** no HDM-4. Ele **ainda não gera** um `objects.dat` / `objects.idx` modificado e pronto para simulação. A integração nativa está pendente de validação.", icon="⚠️")

step1, stepmap, step2, stepdiag, step3, stepref = st.tabs([
    "1 · Arquivos", "2 · Mapeamento completo", "3 · Conferência", "4 · Explorar MDBs", "5 · Gerar pacote", "6 · Referências econômicas"])
with step1:
    a,b=st.columns(2,gap="large")
    with a:
        workspace_file=st.file_uploader("Workspace HDM-4 original (.zip)",type=["zip"],key="workspace")
    with b:
        excel_file=st.file_uploader("Planilha padrão SC-110 (.xlsx)",type=["xlsx"],key="xlsx")

if not workspace_file or not excel_file:
    with step1:
        st.info("Envie os dois arquivos para começar a validação. Nada será alterado nos originais.")
    st.stop()

try:
    workspace=workspace_file.getvalue()
    excel_bytes=excel_file.getvalue()
    manifest=inspect_zip(workspace)
    excel=read_excel(excel_bytes)
except Exception as e:
    st.error("Falha na validação dos arquivos: " + str(e))
    st.stop()

identifier=hashlib.sha256(workspace+excel_bytes).hexdigest()
try:
    road_sections=discover_road_sections(excel)
    traffic_audit=audit_traffic(excel, road_sections)
except Exception as exc:
    st.error('Não foi possível identificar as seções da planilha: '+str(exc))
    st.stop()
if not road_sections:
    st.error('A planilha não contém seções identificadas em A3, F3, K3 etc.')
    st.stop()
if st.session_state.get("files_id") != identifier:
    st.session_state["files_id"] = identifier
    st.session_state.pop("network_snapshot",None)
    st.session_state.pop("pkg",None)
    st.session_state.pop("diagnostic",None)

with step1:
    col1,col2,col3=st.columns(3)
    col1.metric("Objetos MDB exportados",len(manifest["exports"]))
    col2.metric("Abas Excel",len(excel.sheets))
    col3.metric("Seções na planilha",len(road_sections))
    st.caption(f"{manifest['file_count']} arquivos no workspace; {len(traffic_audit['blocos'])} seções com tráfego preenchido.")
    for issue in traffic_audit['erros']:
        st.error('Validação VMD: '+issue)
    for issue in traffic_audit['alertas']:
        st.warning(issue)
    with st.expander('Seções e VMDs identificados',expanded=False):
        st.dataframe([{'Seção':r.id,'Descrição':r.title,'BASE':r.base_col,
          'PROJETO':r.project_col,'VMD total 2024':traffic_audit['vmd_2024'].get(r.id)}
          for r in road_sections],hide_index=True,use_container_width=True)
    if traffic_audit['blocos']:
        st.download_button('⬇️ Baixar diagnóstico de VMD (JSON)',
          __import__('json').dumps({'rodovias':[r.__dict__ for r in road_sections],
          'blocos':[{'secao':t.id,'cabecalho':t.heading_row,'serie':t.series,'resumo':t.summaries}
          for t in traffic_audit['blocos']],
          'alertas':traffic_audit['alertas'],'erros':traffic_audit['erros']},
          ensure_ascii=False,indent=2).encode('utf-8'),
          file_name='HDM4_Diagnostico_Trafego.json',mime='application/json')
    st.success(f"Rede SC-110 detectada: `{manifest['network']}`")
    with st.expander("Conteúdo e integridade",expanded=False):
        st.code(f"objects.dat: {manifest['dat']}\nobjects.idx: {manifest['idx']}\nSHA256 do MDB da rede: {manifest['original_sha256']}")
        st.write("Abas:",", ".join(excel.sheets.keys()))
    if excel.formula_errors:
        st.warning(f"Foram identificadas {len(excel.formula_errors)} células de erro na planilha. O aplicativo somente utilizará os campos explicitamente mapeados e válidos.")

# Catálogo de TODOS os grupos de entrada, sem misturar validação com
# autorização de escrita. Os registros com destino candidato são leitura apenas.
catalog=build_catalog(excel)
catalog_text=catalog_csv(catalog)
catalog_info=catalog_summary(catalog)
with stepmap:
    st.subheader("Inventário de parâmetros da planilha padrão")
    st.info("O catálogo inventaria as entradas técnicas, séries e custos das cinco abas. 'CANDIDATO' **não significa** que o aplicativo esteja autorizado a gravar o campo no HDM-4.")
    k1,k2,k3=st.columns(3)
    k1.metric("Entradas inventariadas",catalog_info['itens_total'])
    k2.metric("Campos BASE no piloto",catalog_info['por_status'].get('VALIDADO_IRI_NO_HDM4',0)+catalog_info['por_status'].get('HABILITADO_PILOTO',0))
    k3.metric("Entradas aguardando associação",catalog_info['por_status'].get('CANDIDATO_REVISAR',0)+catalog_info['por_status'].get('ESTRUTURA_PENDENTE',0))
    groups=sorted({r['Grupo'] for r in catalog})
    chosen_groups=st.multiselect("Grupos de dados",groups,default=groups)
    statuses=sorted({r['Situação'] for r in catalog})
    chosen_status=st.multiselect("Situação do mapeamento",statuses,default=statuses)
    filtered=[r for r in catalog if r['Grupo'] in chosen_groups and r['Situação'] in chosen_status]
    st.dataframe(filtered,hide_index=True,use_container_width=True,height=450)
    st.download_button("⬇️ Baixar mapeamento completo (CSV)",catalog_text.encode('utf-8'),
                      file_name="SC110_Mapeamento_Excel_MDB.csv",mime="text/csv")
    st.caption("BASE = estado inicial em SECTIONS; PÓS-OBRA = efeito de padrão de melhoria. As projeções de tráfego, custos monetários e dados de projeto exigem joins e premissas próprias.")

with step2:
    st.subheader("Seleção e validação")
    all_ids=[r.id for r in road_sections]
    sel=st.multiselect("Seções",all_ids,default=all_ids,key="sel_sections")
    c1,c2=st.columns([3,2])
    with c1:
        field_options={f[0]:f[1] for f in SAFE_FIELDS}
        chosen=st.multiselect("Campos a atualizar (condição inicial / BASE)",list(field_options.keys()),
                              default=["LENGTH","ROUGHNESS","RAVEL_AREA","PHOLE_NUM","EDGEBREAK","RUT_DEPTH"],
                              format_func=lambda f: f"{field_options[f]}  [{f}]", key="sel_fields")
    with c2:
        st.markdown("**Escopo de gravação**")
        st.caption("Há seis campos BASE habilitados no piloto; apenas a gravação e reimportação do IRI foi demonstrada no HDM-4. Os campos de geometria abaixo são hipóteses explícitas para teste em cópia. Frota, tráfego e custos continuam bloqueados até validação relacional.")
    confirm_review=st.checkbox("Habilitar campos experimentais somente para workspace de TESTE", value=False)
    extra=[]
    if confirm_review:
        st.warning("Os campos abaixo ainda não foram confirmados por reimportação. Não aplicar automaticamente ao workspace operacional.")
        review_options={f[0]:f[1] for f in REVIEW_FIELDS}
        extra=st.multiselect("Campos experimentais de SECTIONS (desmarcados por padrão)",
            list(review_options),default=[],format_func=lambda f:review_options[f])
    selected_fields=chosen+extra
    planned, errs, details=build_validation(excel,sections=sel,fields=selected_fields)
    plan_id=hashlib.sha256((identifier+"/"+"|".join(sorted(sel))+"/"+"|".join(sorted(selected_fields))).encode()).hexdigest()
    if st.session_state.get("plan_id")!=plan_id:
        st.session_state["plan_id"]=plan_id
        st.session_state.pop("pkg",None)
    s=details.get("resumo",{})
    m1,m2,m3=st.columns(3)
    m1.metric('Extensão de todas as seções',f"{s.get('extensao_modelo_km',0):.2f} km")
    m2.metric('Seções detectadas',str(s.get('quantidade_secoes',len(road_sections))))
    m3.metric('Seções com VMD',str(s.get('secoes_vmd_com_dados',0)))
    for x in errs: st.error(x)
    for x in details.get("alertas",[]): st.info(x)
    st.dataframe([{"Seção":v.secao,"Parâmetro":v.nome,"Campo MDB":v.campo,"Origem":v.origem,"Novo valor":v.valor,"Unidade":v.unidade} for v in planned],hide_index=True,use_container_width=True)
    st.caption("As condições PROJETO do Excel não substituem a condição BASE da rede. O mapeamento de standards de melhoria foi inventariado mas a escrita não está habilitada.")

with stepdiag:
    st.subheader("Inspeção de tabelas e relacionamentos reais")
    st.write("Use o explorador para identificar as chaves `VEH_ID`, `WORK_ID`, `MAINT_CODE`, `IMP_CODE`, `SECTION_ID` e demais campos efetivamente presentes nos arquivos exportados. Essa inspeção não modifica o MDB.")
    target=st.selectbox("Arquivo MDB exportado",manifest['exports'],
                        format_func=lambda x:Path(x).name,key='diag_file')
    if st.button("🔎 Listar tabelas e colunas do MDB",key='inspect_meta'):
        with st.spinner("Consultando metadados via JDBC..."):
            try:
                with tempfile.TemporaryDirectory(prefix="hdm4_metadata_") as tmp:
                    mdb=Path(tmp)/"inspect.mdb"
                    mdb.write_bytes(network_bytes(workspace,target))
                    info=inspect_tables(mdb,allow_download=True)
                st.session_state['diagnostic']={'identifier':identifier,'path':target,'metadata':info,'sample':None}
                st.success(f"Banco lido: {info.get('count',0)} tabelas de usuário.")
            except Exception as e:
                st.error("Não foi possível inspecionar o MDB: "+str(e))
    diag=st.session_state.get('diagnostic')
    if diag and diag['identifier']==identifier and diag['path']==target:
        tables=diag['metadata'].get('tables',[])
        st.dataframe([{'Tabela':tab['table'],'Colunas':len(tab.get('columns',[]))} for tab in tables],
                     use_container_width=True,hide_index=True)
        st.download_button("⬇️ Baixar inventário de tabelas (JSON)",
            __import__('json').dumps(diag['metadata'],ensure_ascii=False,indent=2).encode('utf-8'),
            file_name='HDM4_Inventario_Tabelas.json',mime='application/json')
        if tables:
            t=st.selectbox("Tabela para amostragem",[tab['table'] for tab in tables],key='diag_table')
            if st.button("Visualizar até 200 registros",key='diag_rows'):
                with st.spinner("Consultando registros..."):
                    try:
                        with tempfile.TemporaryDirectory(prefix="hdm4_sample_") as tmp:
                            mdb=Path(tmp)/"inspect.mdb"
                            mdb.write_bytes(network_bytes(workspace,target))
                            sample=snapshot(mdb,t,allow_download=True)
                        diag['sample']=sample
                    except Exception as e:
                        st.error("Consulta de registros não concluída: "+str(e))
            sample=diag.get('sample')
            if sample and sample.get('table')==t:
                st.dataframe(sample.get('rows',[]),use_container_width=True,hide_index=True)
                st.download_button("⬇️ Baixar amostra de registros (JSON)",
                    __import__('json').dumps(sample,ensure_ascii=False,indent=2).encode('utf-8'),
                    file_name='HDM4_'+t+'_Amostra.json',mime='application/json')

with step3:
    st.subheader("Leitura do banco e exportação")
    st.markdown("O aplicativo compara os valores com registros reais do MDB, identificando seções pelos respectivos `SECT_ID` na tabela `SECTIONS`.")
    can_inspect = bool(planned) and not bool(errs)
    if st.button("🔎 Inspecionar MDB original",type="primary",disabled=not can_inspect):
        with st.spinner("Abrindo banco Access por JDBC..."):
            try:
                with tempfile.TemporaryDirectory(prefix="hdm4_") as temp:
                    mdb_path=Path(temp)/"SC110.mdb"
                    mdb_path.write_bytes(network_bytes(workspace,manifest["network"]))
                    obj=snapshot(mdb_path, "SECTIONS", allow_download=True)
                st.session_state["network_snapshot"]={"identifier":identifier,"data":obj}
                st.success("Tabela SECTIONS lida do MDB original.")
            except Exception as e:
                st.session_state.pop("network_snapshot",None)
                st.error("Não foi possível abrir o MDB: " + str(e))

    previous=st.session_state.get("network_snapshot")
    bound=[]
    if previous and previous.get("identifier")==identifier:
        snap=previous["data"]
        with st.expander("SECTIONS — registros lidos", expanded=False):
            st.dataframe(snap["rows"],hide_index=True,use_container_width=True)
        try:
            bound=attach_old_values(planned,snap["rows"])
            st.success("Identificadores correspondem às seções do modelo; valores originais carregados.")
            st.dataframe([{"Seção":c.secao,"Campo":c.campo,"Valor no MDB":c.antes,"Valor no Excel":c.valor,"Status":c.status} for c in bound],hide_index=True,use_container_width=True)
        except Exception as e:
            st.error("Impossível ligar planilha e MDB: " + str(e))
    else:
        st.info("Clique em 'Inspecionar MDB original' para habilitar a exportação após validação do driver.")

    eligible=bound and any(c.status=="alterar" for c in bound) and not errs
    if bound and not any(c.status=="alterar" for c in bound):
        st.info("O Excel coincide com os valores atuais dos campos selecionados. Para gerar pacote é necessário haver uma diferença real, ou selecionar outro campo mapeado.")
    if st.button("📦 Gerar pacote de atualização MDB",disabled=not bool(eligible)):
        with st.spinner("Aplicando mudanças em cópia, reabrindo e conferindo o banco..."):
            try:
                orig_mdb=network_bytes(workspace,manifest["network"])
                with tempfile.TemporaryDirectory(prefix="hdm4_") as temp:
                    update_path=Path(temp)/"SC110_atualizado.mdb"
                    update_path.write_bytes(orig_mdb)
                    result=update_and_verify(update_path,bound)
                    modified=update_path.read_bytes()
                pkg=build_import_package(orig_mdb,modified,manifest["network"],excel_bytes,bound,details["resumo"],result,catalog_text)
                st.session_state["pkg"]={"identifier":identifier,"plan_id":plan_id,"data":pkg}
                st.success(f"Pacote de importação gerado: {result['alterados']} alterações gravadas e verificadas.")
            except Exception as e:
                st.session_state.pop("pkg",None)
                st.error("Pacote não gerado. Não foi possível demonstrar a integridade da atualização: " + str(e))

    exported=st.session_state.get("pkg")
    if exported and exported["identifier"]==identifier and exported["plan_id"]==plan_id:
        st.download_button("⬇️ Baixar pacote de importação HDM-4",data=exported["data"],
                           file_name="SC110_Pacote_Importacao_HDM4.zip",mime="application/zip",use_container_width=True)
        st.caption("O ZIP contém MDB atualizado, planilha original, auditoria JSON e instruções de reimportação no HDM-4. Não contém um workspace nativo atualizado.")
    st.divider()
    st.markdown("**Próximo marco:** associar identificadores de `VEHICLES`, `Works`, `Improves` e `Prj_*` a cada grupo do catálogo usando as amostras da aba 4. Somente depois liberar sua gravação e testar importação/overwrite no HDM-4. O workspace nativo `objects.dat`/`.idx` continua fora do escopo.")

with stepref:
    st.subheader('Cadastro de referências econômicas')
    st.caption('Histórico monetário de frota e manutenção. Os valores são cadastrados primeiro no aplicativo, sem gravar diretamente VEHICLES/Works ou modificar o XLSX original.')
    try:
        template=build_reference_templates(excel)
    except ValueError as exc:
        st.error('Datas-base do modelo não puderam ser interpretadas: '+str(exc))
        st.stop()
    reference_hash=hashlib.sha256(excel_bytes).hexdigest()
    if st.session_state.get('reference_source')!=reference_hash:
        st.session_state['reference_source']=reference_hash
        st.session_state['reference_db']=template
        st.session_state['reference_stage']='idle'
        st.session_state['reference_working']=None
        st.session_state['reference_editor_version']=0

    uploaded_archive=st.file_uploader('Restaurar histórico anterior (.json)',type=['json'],key='ref_archive_upload',
                                     help='Utilize o JSON exportado anteriormente. O arquivo deve corresponder aos campos da planilha carregada.')
    if uploaded_archive is not None and st.button('Importar histórico JSON',key='import_references'):
        try:
            payload=__import__('json').loads(uploaded_archive.getvalue().decode('utf-8'))
            if len(uploaded_archive.getvalue())>3_000_000:
                raise ValueError('Histórico maior que 3 MB')
            validate_archive(payload,expected_fields=template['campos'])
            st.session_state['reference_db']=payload
            st.session_state['reference_stage']='idle'
            st.success('Histórico restaurado para a sessão atual.')
        except Exception as exc:
            st.error('O arquivo não pôde ser restaurado: '+str(exc))

    db=st.session_state['reference_db']
    refs=db['referencias']
    months=sorted(refs)
    c1,c2,c3=st.columns([1,1,2])
    c1.metric('Referências cadastradas',len(months))
    c2.metric('Campos monetários',len(db['campos']))
    with c3:
        selected_reference=st.selectbox('Visualizar referência',list(reversed(months)),
                                        format_func=lambda x: f'{x[5:7]}/{x[:4]}',key='current_reference')
    if selected_reference:
        current=refs[selected_reference]['valores']
        view=[{'Grupo':f['grupo'],'Parâmetro':f['parametro'],
               'Categoria':f['categoria'],'Unidade':f['unidade'],
               'Valor':current.get(f['id'])} for f in db['campos']]
        with st.expander('Valores da referência selecionada',expanded=False):
            st.dataframe(view,hide_index=True,use_container_width=True)
    st.download_button('⬇️ Exportar histórico completo (JSON)',data=export_archive(db),
        file_name='HDM4_Historico_Referencias.json',mime='application/json',key='export_references')
    st.info('No Streamlit Community Cloud, o cadastro fica na sessão atual. Baixe o JSON para preservá-lo e reimporte na próxima sessão. Persistência multiusuário requer banco de dados externo.')

    stage=st.session_state.get('reference_stage','idle')
    if stage=='idle':
        if st.button('➕ Cadastrar nova referência',type='primary',key='start_ref'):
            st.session_state['reference_stage']='edit'
            st.session_state['reference_working']=None
            st.rerun()

    if st.session_state.get('reference_stage')=='edit':
        st.markdown('#### Nova referência: edição dos valores')
        cmonth,cyear,cbase=st.columns([1,1,2])
        current_month=__import__('datetime').datetime.now().month
        current_year=__import__('datetime').datetime.now().year
        with cmonth:
            chosen_month=st.selectbox('Mês',list(range(1,13)),index=current_month-1,
                format_func=lambda x: f'{x:02d}',key='ref_new_month')
        with cyear:
            chosen_year=st.number_input('Ano',min_value=1990,max_value=2100,value=current_year,step=1,key='ref_new_year')
        with cbase:
            from_reference=st.selectbox('Copiar valores de',list(reversed(months)),
                format_func=lambda x:f'{x[5:7]}/{x[:4]}',key='ref_previous')
        period=f'{int(chosen_year):04d}-{int(chosen_month):02d}'
        if period in refs:
            st.error('Já existe uma referência para esse mês/ano. Escolha outro período.')
        if period<=from_reference:
            st.warning('A nova referência deve ser posterior à referência escolhida como base.')
        source=st.text_input('Fonte / observação',placeholder='Ex.: pesquisa de preços, SINAPI, ANP, SIE ...',
                             key='ref_source_note')
        previous_values=refs[from_reference]['valores']
        working=st.session_state.get('reference_working')
        if not working or working.get('base')!=from_reference:
            prepared={f['id']:previous_values.get(f['id']) for f in db['campos']}
        else:
            prepared=working['valores']
        input_rows=[]
        for f in db['campos']:
            input_rows.append({'Código':f['id'],'Grupo':f['grupo'],'Parâmetro':f['parametro'],
                    'Categoria':f['categoria'],'Unidade':f['unidade'],
                    'Valor anterior':previous_values.get(f['id']),
                    'Novo valor':prepared.get(f['id'])})
        edit_key=f"reference_grid_{st.session_state.get('reference_editor_version',0)}_{from_reference}"
        edited_rows=st.data_editor(input_rows,hide_index=True,use_container_width=True,num_rows='fixed',
            disabled=['Código','Grupo','Parâmetro','Categoria','Unidade','Valor anterior'],
            column_config={'Novo valor':st.column_config.NumberColumn('Novo valor',min_value=0.0,format='%.6f')},
            key=edit_key)
        colreview,colcancel=st.columns([1,1])
        with colreview:
            review_clicked=st.button('Atualizar valores · Conferir diferenças',type='primary',
                 disabled=(period in refs or period<=from_reference),key='review_reference')
        with colcancel:
            cancel_clicked=st.button('Cancelar cadastro',key='cancel_reference')
        if cancel_clicked:
            st.session_state['reference_stage']='idle'
            st.session_state['reference_working']=None
            st.rerun()
        if review_clicked:
            edited={row['Código']:row['Novo valor'] for row in edited_rows}
            changes,problems=compare_reference(previous_values,edited,db['campos'])
            if problems:
                for issue in problems:st.error(issue)
            elif not changes:
                st.warning('Nenhum valor foi alterado. Faça ao menos uma alteração antes de concluir.')
            else:
                st.session_state['reference_working']={
                    'base':from_reference,'periodo':period,'valores':edited,'alteracoes':changes,
                    'observacao':source}
                st.session_state['reference_stage']='review'
                st.rerun()

    if st.session_state.get('reference_stage')=='review':
        working=st.session_state['reference_working']
        st.markdown(f"#### Conferir alterações — {working['periodo'][5:7]}/{working['periodo'][:4]}")
        st.success(f"Foram modificados {len(working['alteracoes'])} campos; todos os demais foram preservados.")
        st.dataframe(working['alteracoes'],hide_index=True,use_container_width=True)
        left,right=st.columns(2)
        with left:
            if st.button('↩️ Corrigir',key='correct_ref'):
                st.session_state['reference_editor_version']+=1
                st.session_state['reference_stage']='edit'
                st.rerun()
        with right:
            if st.button('✅ Finalizar cadastro',type='primary',key='finish_ref'):
                period=working['periodo']
                if period in refs:
                    st.error('Referência já existe; cadastro não foi salvo.')
                else:
                    refs[period]={'periodo':period,'valores':working['valores'],
                       'origem':'Cadastro no aplicativo','observacao':working['observacao'],
                       'base':working['base'],'alteracoes':working['alteracoes']}
                    st.session_state['reference_stage']='idle'
                    st.session_state['reference_working']=None
                    st.success('Nova referência cadastrada na sessão. Exporte o histórico JSON para preservá-la.')
                    st.rerun()
    st.caption('Os custos inseridos nesta aba ainda não são gravados nos arquivos MDB da frota ou da manutenção. Essa integração depende da validação das chaves de VEHICLES e Works.')
