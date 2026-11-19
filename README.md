# Plataforma Integrada SC — módulo HDM-4 (v0.2.1)

Aplicativo Streamlit de **inventário, conferência e preparação de MDBs** para importação nativa no HDM-4 v2.12.02. Não modifica `objects.dat`/`objects.idx`; ainda não cria um workspace nativo pronto para rodar.

## O que mudou na v0.2.0

- **Aba 2 · Mapeamento completo:** catálogo por célula das entradas materiais das cinco abas do Excel, com destino MDB candidato, cenário, categoria de veículo, status de evidência e observações. Exportação de CSV. O catálogo é um inventário *para homologação*, não uma promessa de que todos os campos já são graváveis.
- **Aba 3 · Conferência:** mantém seis campos da condição BASE autorizados no piloto (`LENGTH`, `ROUGHNESS`, `RAVEL_AREA`, `PHOLE_NUM`, `EDGEBREAK`, `RUT_DEPTH`). Apenas o IRI já foi comprovado pelo usuário após importação com overwrite no HDM-4. Campos adicionais (`ALTITUDE`, `CURVATURE`, `SUPERELEV`, `MTLANES`, `CRACKS_ACA` e `CWAY_WIDTH` com hipótese de multiplicação por faixas) exigem *opt-in* explícito para testes.
- **Aba 4 · Explorar MDBs:** selecionar qualquer um dos `.mdb` da pasta `Exports`; listar tabelas e colunas reais usando metadados JDBC; amostrar até 200 registros e exportar JSON. A inspeção é somente leitura e serve para confirmar IDs/chaves antes de implementar gravação transacional de frota, manutenção, projeto e melhorias.
- **Aba 5 · Gerar pacote:** a leitura, comparação, gravação com pré-condição de valor antigo e verificação pós-gravação continuam usando cópia da rede MDB; o ZIP inclui o CSV de mapeamento.

## Escopo técnico e segurança

| Grupo Excel | Destino possível no HDM-4 | Situação |
|---|---|---|
| Rodovia — BASE | `SECTIONS` em `SC-110, ...mdb` | Seis campos habilitados; IRI testado na importação; outros candidatos opt-in |
| Rodovia — pós-obra | `Improves`, `Prj_sectOptImp` | Inventariado; escrita bloqueada |
| VMD normal, atraído, desviado, crescimento | `TRAFFIC` e `Prj_*Growths`, `Prj_generatedTraffic` | Inventariado; escrita bloqueada até identificar ano/categoria/chaves |
| Frota e custos monetários | `VEHICLES`, campos `FUC_*` e `EUC_*` | Inventariado; escrita bloqueada até conferir `VEH_ID` e diferença financeira/econômica |
| Manutenção | `Works`, `FIN_COST`, `ECON_COST` | Inventariado; escrita bloqueada até confirmar os itens e padrões compartilhados |
| Obra, orçamento e programação | `Improves` e `Prj_*` | Inventariado; escrita bloqueada até confirmar unidades de serviços e cronologia |

**Fatos conhecidos:** a planilha de origem tem cinco abas, erros `#DIV/0!` em blocos auxiliares e diferença entre 11,00 km de seções e 11,04 km de rateio orçamentário. Há referência à condição da rodovia em 2013 e diferentes bases monetárias (2019 e 2021). Não se deve substituir os dados BASE pelos dados pós-obra nem assumir que valores atualizados para julho de 2021 sejam preços atuais de 2026.

## Como instalar no Streamlit

1. Extraia este ZIP. No repositório GitHub `gestao_hdm4`, substitua todos os arquivos indicados (preserve os mesmos caminhos e a pasta `java`).
2. `packages.txt` precisa conter `default-jdk-headless` (Debian Linux atual). `requirements.txt` inclui Streamlit.
3. Publique `app.py` no Streamlit Community Cloud.
4. Carregue **o ZIP do workspace que contém `objects.dat`, `objects.idx` e a pasta `Exports` com MDBs exportados do HDM-4**, e carregue a planilha padrão Excel.
5. Analise os status na aba Mapeamento. Para investigar outra tabela, vá à aba Explorar MDBs, escolha o arquivo, clique em “Listar tabelas e colunas do MDB”, e depois abra `VEHICLES`, `Works`, `Improves` ou `Prj_*` conforme necessário.
6. Para simulações, só use MDB alterado após reimportar/overwrite no HDM-4 em **cópia de backup** e conferir os valores. A importação pode afetar outros projetos se a frota e os standards forem objetos compartilhados.

## Diagnóstico necessário para liberar outras atualizações

Exportar os inventários JSON de:

- `Frota de Veículos.mdb` → `VEHICLES` (confirmar `VEH_ID`, `VEH_NAME`, `FUC_*` e `EUC_*`).
- `WorkStds.mdb` → `Works` e tabelas de manutenção (códigos e vínculos a standards).
- `ImprovStds.mdb` → `Improves` (intervenções e custos por unidade).
- `Restauração SC-110, Pomerode - Pé da Serra.mdb` → `Project`, `Prj_selSections`, `Prj_secGrowths`, `Prj_generatedTraffic`, `Prj_sectOptImp`, `Prj_sectOptMaint`.
- `SC-110, Pomerode - Pé da Serra.mdb` → `TRAFFIC` (vínculo `SEC_ID` + veículo + ano).

Apenas depois de verificar que cada linha do Excel aponta para **um registro inequívoco** e sua unidade/semântica é consistente liberaremos sua atualização em lote. O botão de inspeção foi desenvolvido para obter essa evidência sem presumir relacionamentos.

## Organização do código

- `app.py`: interface Streamlit.
- `hdm4_core/excel_reader.py`: leitura conservadora de XLSX (valores em cache).
- `hdm4_core/catalog.py`: inventário da planilha e mapeamento por grupo.
- `hdm4_core/validation.py`: comparação e bloqueios de escrita.
- `hdm4_core/mdb_bridge.py`: launcher Java/UCanAccess e verificação.
- `java/HdmMdbBridge.java`: JDBC, consultas, metadados e alterações parametrizadas com rollback.
- `hdm4_core/package.py`: montagem de ZIP de **importação**, não workspace nativo.
- `tests/`: testes com planilha fictícia, sem projetos reais de Santa Catarina.

## Testar o código

```bash
python -m unittest discover -s tests -v
python -m compileall -q app.py hdm4_core
javac java/HdmMdbBridge.java
streamlit run app.py
```

A abertura real de `.mdb` requer o driver UCanAccess (`ucanaccess-5.3.0-uber.jar`) obtido em execução no Streamlit. Os testes automatizados locais não reproduzem a importação no HDM-4; a prova feita pelo usuário para o IRI confirma apenas aquele caso.


## Correção de instalação v0.2.1

Esta edição é **um pacote integral**, não um patch incremental. Foi preparado para corrigir a
inconsistência entre arquivos do repositório detectada pelos erros de importação
`REVIEW_FIELDS` e `No module named hdm4_core.excel_reader`.

**Instalação:** extraia o ZIP e faça upload do **conteúdo** na **raiz do repositório GitHub**,
preservando exatamente `app.py`, `hdm4_core/`, `java/`, `packages.txt`,
`requirements.txt`, `tests/`, e `.streamlit/`. Não coloque todos dentro de uma nova pasta.
No GitHub, verifique se `hdm4_core/excel_reader.py` e `hdm4_core/validation.py` existem.

**Atenção:** confirmar pela interface do GitHub que todos os arquivos estão no commit
é necessário: o ZIP não altera automaticamente o GitHub. Na aba **Actions** do GitHub,
a verificação `Verificar estrutura HDM-4` deve passar antes de testar a implantação do Streamlit.
A verificação cobre importações Python e testes unitários, mas não garante a disponibilidade
do driver Java no Streamlit nem a reimportação no HDM-4.

**Importante:** não publique `HDM4.zip`, os MDBs reais ou a planilha operacional no repositório público.
