# Plataforma Integrada SC — Módulo HDM-4 (v0.1 piloto)

Aplicativo Streamlit para ler a planilha de parâmetros da SC-110, inspecionar a exportação Microsoft Access do HDM-4, preparar diferenças auditáveis e gerar um pacote de importação.

> **Limite técnico importante:** esta versão **NÃO** atualiza `objects.dat`/`objects.idx` e **NÃO** entrega um workspace HDM-4 pronto para rodada. Atualizar um `.mdb` em `Exports` não atualiza o workspace ativo. O objetivo de gerar automaticamente o diretório nativo permanece pendente de um conector comprovado com o próprio HDM-4 2.12.02 (Windows) ou de suporte oficial de API/importação automatizada.

## O que está implementado

- Interface Streamlit com seleção de S1/S2, grupos de parâmetros e visualização das diferenças.
- Leitor XLSX nativo usando biblioteca padrão do Python, inclusive valores armazenados de fórmulas.
- Auditoria da planilha: tipos, limites, séries de VMD, taxa de crescimento, extensão física e base do orçamento.
- Validação do ZIP original, identificando `objects.dat`, `objects.idx` e o MDB de rede correspondente à SC-110.
- Ponte JDBC para abrir e editar cópias de bancos Access Jet (`.mdb`) em Linux/Windows, com UCanAccess 5.3.0.
- Consulta de registros reais `SECTIONS`, associação por identificadores, comparação de valores, escrita transacional com comparação otimista e releitura pós-gravação.
- Exportação em ZIP de **pacote de importação** contendo MDB atualizado, auditoria JSON, planilha original e instruções.
- O próprio ZIP original e seus arquivos `objects.dat`/`objects.idx` jamais são alterados.

## Restrições de escopo

| Grupo | Estado |
|---|---|
| Seções `SECTIONS` — extensão, IRI, desagregação, panelas, bordo quebrado e trilhas | Implementado no código; aguardando teste JDBC e importação do HDM-4 |
| Tráfego por classe/ano; tráfego gerado/atraído/desviado; taxas de crescimento | Leitura e checagens básicas; escrita não habilitada |
| Parâmetros e custos da frota | Leitura de planilha; escrita não habilitada |
| Padrões de manutenção e melhorias; parâmetros da solução de engenharia | Escrita não habilitada |
| Cronograma e custos das obras | Escrita não habilitada |
| Atualização direta do repositório `objects.dat`/`objects.idx` | Não implementada, requer teste de integração nativa |
| Rodada e relatório HDM-4 | Executados exclusivamente no HDM-4 original |

Não há teste positivo do ciclo JDBC e da reimportação no software HDM-4 nesta entrega, pois o ambiente de desenvolvimento não conta com HDM-4 instalado nem com o driver Java baixado. O aplicativo **falhará explicitamente** em vez de fabricar um workspace. A primeira utilização com acesso à internet baixa o JAR do UCanAccess do Maven Central; pode-se especificar o caminho para o JAR previamente instalado pela variável `HDM4_UCANACCESS_JAR`.

## Como publicar no Streamlit (GitHub)

1. Crie um repositório privado no GitHub e envie os arquivos desta pasta (sem dados de produção).
2. Abra [share.streamlit.io](https://share.streamlit.io/), clique em **Create app** e selecione o repositório.
3. Indique `app.py` como arquivo principal. `packages.txt` instala o JDK; `requirements.txt` instala o Streamlit.
4. No aplicativo, carregue o ZIP `HDM4.zip` e a planilha correspondente, **enviados diretamente pelo usuário, sem incluí-los no repositório do GitHub**. Os arquivos enviados não são gravados em banco remoto pelo código; são processados em memória e em pasta temporária do servidor.
5. Clique em **Inspecionar MDB original**. Se houver falha JDBC, a geração é bloqueada.
6. Confira a tabela de diferenças. Clique em **Gerar pacote de atualização MDB** e baixe o resultado.
7. Faça backup do workspace original; reimporte o `.mdb` em um projeto de teste pelo HDM-4. Valide e reexporte antes de simular.

### Execução local

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Java JDK 17+ precisa estar instalado; o aplicativo baixa o `ucanaccess-5.3.0-uber.jar` na primeira leitura. Alternativamente, defina `HDM4_UCANACCESS_JAR=/caminho/ucanaccess-5.3.0-uber.jar`.

## Pipeline de produção e critérios de aceite

1. Teste JDBC no MDB original: listar seções; confirmar chaves `SECT_ID` e tipos das seis colunas propostas.
2. Confirmar unidades no próprio HDM-4 (em especial IRI, percentuais e largura de pista); ajustar mapeamento, caso haja incompatibilidade.
3. Exportar e reimportar rede modificada como objeto **novo** em um workspace de laboratório no HDM-4 v2.12.02.
4. Reexportar e comparar os campos e relacionamentos; fazer um caso-base sem alterações e um caso modificado.
5. Mapear frota, custos e padrões, com clonagem de objetos compartilhados quando necessário.
6. Para **ZIP nativo pronto**, investigar automação de importação via instalação Windows (UI automation/SDK oficial se disponível) e validar novo `objects.dat`/`objects.idx` por abertura e rodada de uma cópia.
7. Integrar o módulo ao login, permissões, armazenamento de versões e trilha de auditoria da futura plataforma de SC.

## Estrutura

```text
app.py                        Interface Streamlit
hdm4_core/excel_reader.py     XLSX, resultados armazenados e checagem de fórmulas
hdm4_core/validation.py       Regras, limites e mapeamento SC-110
hdm4_core/workspace.py        Inspeção do ZIP e identificação do MDB
hdm4_core/mdb_bridge.py       Chamada Java JDBC e verificação pós-escrita
java/HdmMdbBridge.java        Leitura e update parametrizado no Access
hdm4_core/package.py         ZIP de importação e auditoria
examples/Modelo_Ficticio_NAO_USAR_PARA_ESTUDO.xlsx  Planilha sintética para testar a interface
```

### Referências

- HDM-4 Software User Guide, Volume 3 — import/export de objetos como MDB.
- UCanAccess, projeto mantido (JDBC para Microsoft Access): https://spannm.github.io/ucanaccess/10-ucanaccess.html
- Streamlit Community Cloud: https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies

**Proteção de dados:** o repositório de código inclui apenas um XLSX fictício; não inclui o workspace original nem a planilha real, que podem conter dados restritos de projeto. Não publique os anexos de produção em repositórios públicos.
