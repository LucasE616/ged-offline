# GED Offline

Consulta ao acervo digitalizado — Despesas, Licitações, Legislações ou qualquer outro tipo — direto no diretório onde os PDFs estão, sem internet e **sem banco de dados**.

Você aponta para a pasta, o programa lê os índices XML que acompanham os documentos, descobre sozinho quais campos de índice existem ali e monta a busca a partir deles. Nada é gravado: os únicos arquivos que saem do programa são os relatórios que você mandar exportar.

## Como rodar

Precisa apenas do Python 3.10+ com `tkinter` (que já vem no instalador padrão do python.org para Windows).

```bash
python main.py
```

Na primeira execução o programa instala sozinho o `PyMuPDF`, usado para ler o texto dos PDFs, contar páginas de arquivos sem índice e gerar a miniatura. Sem internet no momento, ele continua funcionando — a busca por nome e por índice não depende desse pacote.

## Como usar

1. **Escolher...** e selecione a pasta do acervo (normalmente a pasta de um exercício). Deixe *Subpastas* marcado para varrer a árvore inteira.
2. O programa lê o diretório em alguns segundos e monta os campos de busca com os índices que encontrou nos XML daquela pasta.
3. Se houver mais de um tipo de documento na pasta, ele pergunta qual você quer consultar (veja *Tipo de documento* abaixo).
4. Busque por texto livre, pelos campos de índice, por período, ou por tudo junto.
5. **Exportar TXT** ou **Exportar CSV** para levar o resultado embora.

Duplo clique numa linha abre o PDF no visualizador padrão do Windows. O botão direito — ou os botões no painel lateral — também oferece **Abrir pasta do arquivo**, que abre o Explorer já com o documento selecionado, útil quando você precisa copiar o arquivo ou ver o que mais existe naquela pasta.

## Tipo de documento

Toda vez que um diretório é lido, o programa pergunta qual tipo documental você vai consultar:

- **Despesas**, **Licitações** ou **Legislações** — cada um mostra quantos documentos e páginas dele existem na pasta. Um tipo sem nenhum documento aparece apagado. O tipo com mais documentos já vem marcado, então confirmar é só apertar Enter.
- **Outro tipo de documento** — para acervos de outra natureza. Você marca quais índices quer buscar; entre parênteses aparece em quantos documentos cada índice está preenchido. Os índices marcados viram os campos de busca e as colunas, e também definem quais documentos aparecem: os que têm ao menos um deles preenchido. Assim, numa pasta que mistura despesas com contratos, marcar os índices dos contratos traz só os contratos.

O botão **Tipo:** no topo reabre a pergunta a qualquer momento, lembrando a escolha anterior.

Para enquadrar cada documento, as pistas são tentadas da mais específica para a mais genérica: o padrão do nome do arquivo (`despesa_…`, `licitacao_…`), depois o campo *Título* do índice, depois o nome das pastas entre o documento e o diretório escolhido. Pastas acima do diretório escolhido não contam, e palavras curtas precisam aparecer inteiras — "Leilão", que é modalidade de licitação, não é confundido com lei.

## Datas e períodos

Os campos de data são reconhecidos pelo **conteúdo**, não pelo nome: o programa olha os valores e marca como data o campo que contém datas, seja ele `Data de Pagto`, `Data Ass` ou `Data`.

Isso resolve um problema real do acervo: o mesmo arquivo de índice grava `2019-11-29` na maioria dos registros e `01-11-2019` em outros, e o usuário digita `29/11/2019`, que não é nenhum dos dois. Buscar por qualquer um desses formatos encontra os outros. A busca também aceita datas incompletas:

| Você digita | Encontra |
|---|---|
| `2019` | o ano inteiro |
| `11/2019` | o mês inteiro |
| `29/11/2019` | o dia exato |

Os mesmos formatos valem nos dois filtros de **período**:

- **Período do índice** — sobre a data que está no XML (pagamento, assinatura, publicação)
- **Criação do arquivo** — sobre a data em que o PDF foi criado no disco

Digitar `de 2019 até 2019` pega o ano inteiro, não um dia só. Campos que não são datas continuam funcionando como texto comum: digitar `11` num campo procura o trecho "11", e não o mês de novembro.

## Os três escopos de busca

O texto livre é procurado nos escopos que estiverem marcados, em **OU** — um documento entra no resultado se o termo aparecer em qualquer um deles:

| Escopo | Custo | O que encontra |
|---|---|---|
| **nome do arquivo** | instantâneo | o termo no nome do PDF |
| **índice XML** | instantâneo | o termo em qualquer campo de índice |
| **conteúdo do PDF** | abre arquivos | o termo em qualquer página do documento |

Os **campos de índice**, preenchidos abaixo, funcionam ao contrário: restringem, e valem todos ao mesmo tempo.

A busca por conteúdo vem desligada por padrão porque alarga bastante o resultado: procurar "CEMIG" no índice traz as despesas *daquele fornecedor*; no conteúdo traz também toda nota fiscal e empenho que mencione a palavra em qualquer página. Quando ligada, ela abre apenas os PDFs que ainda não casaram pelo nome ou pelo índice, e guarda o texto lido na memória — a segunda busca sobre os mesmos documentos responde na hora.
O botão **Ler conteúdo de todos** antecipa essa leitura de uma vez.

## Contagem de páginas

O rodapé mostra sempre dois pares de números: o total do diretório e o total do resultado. As páginas vêm do campo `Page count in document` do XML quando existe; para PDFs sem índice, são contadas diretamente do arquivo em segundo plano. Se algum documento ficar sem contagem, o rodapé avisa em vez de somar um total incompleto sem dizer nada.

## Índices dinâmicos

Não há tipo de documento escrito no código. O vocabulário de busca vem dos próprios XML: uma pasta de despesas dá Favorecido, Data de Pagto, Valor e Histórico; uma de licitações dá Modalidade, Objeto e Fornecedor; uma de legislações dá Tipo, Número, Ementa e Data. Apontar a ferramenta para um acervo de outra natureza funciona sem alterar nada.

Para documentos cujo índice veio incompleto, os metadados são buscados em três fontes, nesta ordem:

1. **Campos do XML** — `name="Numero" value="12030"`
2. **Nome do arquivo** — `Despesa_2019_06953-…pdf` → ano 2019, nº 06953
3. **Caminho da pasta** — `…\licitacao\2017\licitacao_098_76` → nº 098, 2017

A terceira existe porque acontece de o número faltar no XML *e* no nome do arquivo, sobrando apenas no caminho onde o lote foi digitalizado.

## Linha de comando

Útil para conferência rápida ou para gerar relatório sem abrir a janela:

```bash
python main.py --buscar "D:\ACERVO\2019" --filtro "Favorecido=CEMIG" --txt relatorio.txt
```

Opções: `--termo`, `--filtro CAMPO=VALOR` (repetível), `--conteudo`,
`--tipo despesa|licitacao|legislacao|outro`, `--indices "A,B"` (com `--tipo outro`),
`--indice-de`, `--indice-ate`, `--criacao-de`, `--criacao-ate`,
`--sem-subpastas`, `--csv`, `--txt`, `--limite`.

## Exportação

- **CSV** — uma coluna por índice descoberto, mais arquivo, páginas, origem e caminho. Separador `;` e UTF-8 com BOM, que é o que faz o Excel em português abrir com acentos e colunas corretos sem assistente.
- **TXT** — relatório legível com cabeçalho registrando diretório, data, escopo e critérios usados, e rodapé com os totais. É esse cabeçalho que dá validade ao documento meses depois.

Ambos trazem as ressalvas junto do total: documentos sem PDF localizado, PDFs sem camada de texto, índices XML lidos em modo tolerante.

## Acervos com defeito

Os exports antigos têm problemas que são rotina, não exceção, e o programa atravessa todos sem descartar documento:

- XML que declara UTF-8 mas está gravado em Windows-1252
- XML malformado, com valores longos truncados sem fechar as aspas
- Campos vazios e datas em formatos diferentes no mesmo arquivo
- Texto de reconhecimento óptico ruim
- PDF sem camada de texto

A busca ignora acentuação e caixa nos dois lados: `municipio` encontra `MUNICÍPIO`.

## Estrutura

```
main.py              ponto de entrada, instalação de dependências e CLI
ged/
  catalogo.py        varredura, catálogo em memória e agrupamento por tipo
  xml_parser.py      leitura tolerante dos índices XML
  nomes.py           metadados do nome do arquivo e do caminho
  datas.py           leitura de datas em qualquer formato e períodos
  busca.py           filtros por campo, período e texto livre nos três escopos
  conteudo.py        texto e páginas dos PDFs, com cache de sessão
  exportador.py      relatórios TXT e CSV
  texto.py           normalização para comparação sem acento
  gui.py             interface Tkinter, montada em tempo de execução
tests/selftest.py    testes rápidos: python main.py --selftest
```

A janela se ajusta à tela disponível e a área de filtros rola dentro de uma altura fixa, para que a tabela de resultados não seja empurrada para fora num notebook, por mais campos de índice que o acervo tenha.

## Limitações desta versão

- Perfis de busca salvos (rótulos amigáveis, faixa numérica e somatório de valores) ainda não existem: fora as datas, todo campo é tratado como texto.
- Sem OCR — PDFs que são só imagem não têm o que ser procurado dentro.
- A varredura é refeita a cada abertura do programa, já que nada é guardado. Numa pasta de 2.500 documentos isso leva poucos segundos.
- O filtro por data de criação só alcança documentos cujo PDF está no diretório; registros de índice sem arquivo ficam de fora, porque não há data para comparar.
