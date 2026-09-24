# Monitor de Precos de Concorrentes

![Testes](https://github.com/dougvivian/price-monitor-web-scrapper/actions/workflows/testes.yml/badge.svg)

Ferramenta em Python que coleta automaticamente os precos de produtos em sites de
concorrentes do varejo de materiais de construcao, guarda o historico e gera um
relatorio HTML para consulta.

Nasceu de um problema real do meu trabalho: pesquisar precos da concorrencia manualmente,
produto por produto. O projeto tambem e um estudo de automacao, coleta e tratamento de dados.

## O que ele faz hoje

- Le a lista de produtos a monitorar em `dados/produtos.csv` e confere o cadastro antes
  de comecar (ID repetido, coluna faltando, URL invalida...).
- Respeita o `robots.txt` de cada site: pagina bloqueada nao e acessada.
- Acessa a pagina de cada produto e extrai nome, preco, disponibilidade e EAN dos
  dados estruturados da pagina (JSON-LD).
- Salva cada coleta em um banco de dados SQLite (`dados/monitor.db`), montando um
  historico de precos.
- Registra falhas (site fora do ar, preco nao encontrado etc.) na tabela `erros`,
  sem interromper a coleta dos outros produtos.
- Valida cada preco antes de salvar: se ele variar mais de 50% em relacao a ultima
  coleta do produto, vira um registro na tabela `alertas` e nao entra no historico.
  Se o mesmo preco aparecer de novo na coleta seguinte, ele e considerado confirmado e
  e salvo (assim um aumento real nao fica bloqueado para sempre).
- Roda sozinho todo dia (Agendador de Tarefas do Windows) e grava um log de cada execucao.
- Gera `relatorios/relatorio.html` com:
  - resumo da ultima coleta;
  - alertas de variacao de preco;
  - ultimo preco de cada produto, com a variacao desde a coleta anterior;
  - historico, busca e filtro por disponibilidade;
  - erros da ultima coleta separados dos anteriores.

Funciona com lojas na plataforma **VTEX** que publicam dados estruturados
**schema.org** (JSON-LD) nas paginas de produto, padrao comum no varejo online brasileiro.

## Como rodar

Requisitos: Python 3.10 ou superior.

```bash
# 1. Instalar as dependencias
pip install -r requirements.txt

# 2. Criar o cadastro de produtos a partir do modelo e preencher com os seus produtos
cp dados/produtos.exemplo.csv dados/produtos.csv

# 3. Coletar os precos (acessa o site dos concorrentes)
python src/main.py

# 4. Gerar o relatorio HTML a partir do banco de dados
python src/gerar_relatorio.py
```

Depois, abra `relatorios/relatorio.html` no navegador.

### Coleta automatica diaria

O script `src/coleta_diaria.py` roda a coleta e gera o relatorio em sequencia, gravando
tudo em `logs/coleta_diaria.log`. Para rodar sozinho todo dia no Windows, cadastre no
Agendador de Tarefas (no Prompt de Comando):

```bat
schtasks /Create /TN "Monitor de Precos - coleta diaria" /SC DAILY /ST 09:00 ^
  /TR "\"C:\caminho\para\pythonw.exe\" \"C:\caminho\do\projeto\src\coleta_diaria.py\""
```

`pythonw.exe` e o Python sem janela de terminal, para a coleta rodar em segundo plano.

### Testes

```bash
python -m pytest
```

Os testes usam paginas HTML sinteticas em `tests/paginas/`, que imitam a estrutura de
uma loja VTEX, e nao acessam a internet. Eles tambem rodam automaticamente no
**GitHub Actions** a cada push (`.github/workflows/testes.yml`).

## Estrutura

```text
src/
  main.py              coleta os precos e valida as variacoes
  coleta_diaria.py     roda coleta + relatorio e grava log (usado no agendamento)
  banco.py             acesso ao banco SQLite (todo o SQL do projeto fica aqui)
  gerar_relatorio.py   gera o relatorio HTML
dados/
  produtos.exemplo.csv modelo do cadastro de produtos
  produtos.csv         cadastro real dos produtos monitorados (editavel no Excel, fora do Git)
                       colunas: produto_id, concorrente, url, sku, ativo, categoria, observacao
  monitor.db           banco SQLite, criado na primeira coleta (fora do Git)
                       tabelas: coletas, erros, alertas, execucoes
relatorios/
  relatorio.html       relatorio gerado (fora do Git)
tests/
  test_extracao.py     extracao de dados da pagina (JSON-LD, SKU, EAN)
  test_validacao.py    regras de validacao de preco
  test_cadastro.py     conferencia do cadastro de produtos
  test_coleta.py       fluxo completo sem acessar o site (inclui robots.txt e nova tentativa)
  test_coleta_diaria.py script de coleta diaria e log
  test_banco.py        consultas SQL e migracao do banco (banco em memoria)
  test_relatorio.py    relatorio HTML
  paginas/             paginas HTML sinteticas usadas nos testes
.github/workflows/
  testes.yml           roda os testes no GitHub a cada push
```

## Como o preco e extraido

Em vez de procurar o preco no visual da pagina (seletores CSS, que quebram quando o
layout muda), o monitor le o **JSON-LD**: um bloco de dados estruturados no padrao
[schema.org](https://schema.org/Product) que as lojas publicam para o Google.

Quando o produto tem variacoes (tamanhos, cores), a pagina lista uma oferta por SKU.
O monitor escolhe a oferta certa assim:

1. SKU preenchido na coluna `sku` do `produtos.csv`;
2. senao, o `?skuId=` do link;
3. senao, se a pagina tiver uma oferta so, usa essa;
4. senao, registra o erro "SKU ambiguo" em vez de arriscar um preco errado.

Produto fora de estoque fica como `indisponivel`, sem preco; o preco anunciado vai
para a mensagem, para consulta.

Em lojas da plataforma VTEX, a pagina tambem traz um objeto `__STATE__` com os dados
de cada variacao. O monitor usa esse objeto so como complemento, para o nome completo
da variacao (ex.: `Telha ... 2,13 x 1,10m`) e o EAN. O preco vem sempre do JSON-LD.

## Decisoes tecnicas

**JSON-LD em vez de seletores CSS.** A primeira versao lia o preco pelo HTML visivel.
Em produtos com variacoes, o site devolvia o preco da variacao padrao, e nao a do link:
uma telha de R$87,90 era salva como R$61,90. Com o JSON-LD, que traz uma oferta por SKU,
o erro sumiu. Comparando os dois metodos no mesmo dia, 41 produtos bateram e todas as
diferencas eram casos de variacao que o metodo antigo errava.

**Preco so do JSON-LD, sem "plano B".** Algumas vezes o site entrega a pagina
incompleta, sem JSON-LD. Os dados VTEX da pagina ainda tem o preco, mas nao sao um
padrao. Preferimos registrar o erro (e tentar de novo uma vez) a depender de um formato
proprio da plataforma. Resultado: em alguns dias, alguns produtos ficam sem coleta.

**Erro visivel em vez de preco chutado.** Pagina com varias variacoes e nenhum SKU
informado gera "SKU ambiguo". Produto fora de estoque nao entra com preco. Um erro no
relatorio e melhor que um preco errado salvo em silencio.

**Validacao com confirmacao.** Variacao acima de 50% vira alerta e nao entra no
historico. Mas se so rejeitasse, um aumento real ficaria bloqueado para sempre. Por isso
o mesmo preco, visto em duas coletas seguidas, e aceito.

**SQLite.** O historico comecou em CSV. O SQLite continua sendo um arquivo so, sem
servidor, mas da consultas SQL (ultimo preco de cada produto com `GROUP BY`), tipos de
dados e colunas novas sem quebrar o arquivo. O cadastro de produtos continua em CSV
porque e editado a mao no Excel. Colunas novas sao acrescentadas por uma migracao
automatica (`ALTER TABLE`), sem perder dados.

**Testes sem internet.** As paginas de teste sao sinteticas e o `requests.get` e
trocado por um site falso (`monkeypatch`). Os testes sao rapidos, repetiveis e nao
incomodam o site.

**Coleta educada.** Pausa entre requisicoes, uma unica tentativa extra, execucao uma
vez por dia e respeito ao `robots.txt` seguindo a RFC 9309 (sem robots.txt, tudo
permitido; servidor com erro, nada e acessado).

**Dados reais fora do repositorio.** O cadastro real mostra quais produtos sao
monitorados, uma informacao comercial. Ele, o banco e o relatorio ficam fora do Git; no
repositorio ha so um modelo (`produtos.exemplo.csv`) e paginas de teste ficticias.

## Limitacoes conhecidas

- Paginas incompletas do site: alguns produtos podem ficar sem coleta em certos dias.
- O `robotparser` do Python nao entende curingas (`*`) no meio das regras do
  robots.txt; nesses casos a regra e tratada como texto comum.
- O nome da variacao e o EAN dependem dos dados VTEX; em outras plataformas, o nome
  vem do JSON-LD e o EAN fica vazio.
- A coleta agendada depende do computador ligado (se estiver desligado as 9h, roda
  assim que for ligado).

## Roadmap

- **v1 (concluida):** 1 site, execucao manual.
  - [x] Coleta com tratamento de erros e historico
  - [x] Relatorio HTML
  - [x] Testes automatizados com paginas HTML sinteticas (sem acessar o site)
  - [x] Extracao via dados estruturados da pagina (JSON-LD / schema.org)
  - [x] Validacao dos dados (preco vazio ou variacao absurda gera alerta)
  - [x] Historico em SQLite
- **v2 (em andamento):**
  - [x] Execucao agendada diaria (Agendador de Tarefas do Windows)
  - [x] Respeito automatico ao robots.txt
  - [x] Guardar o EAN dos produtos
  - [x] Testes automaticos no GitHub Actions
  - [ ] Mais concorrentes, com produtos casados entre lojas pelo EAN
- **v3:** painel com graficos e alertas de mudanca de preco (Telegram/e-mail).

## Tecnologias

Python, requests, BeautifulSoup, SQLite (SQL), pytest, GitHub Actions, HTML/CSS/JavaScript.
