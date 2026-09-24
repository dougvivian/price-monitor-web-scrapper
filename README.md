# Monitor de Precos de Concorrentes

Ferramenta em Python que coleta automaticamente os precos de produtos em sites de
concorrentes do varejo de materiais de construcao, guarda o historico e gera um
relatorio HTML para consulta.

Nasceu de um problema real do meu trabalho: pesquisar precos da concorrencia manualmente,
produto por produto. O projeto tambem e um estudo de automacao, coleta e tratamento de dados.

## O que ele faz hoje

- Le a lista de produtos a monitorar em `dados/produtos.csv`.
- Acessa a pagina de cada produto e extrai nome, preco e disponibilidade dos
  dados estruturados da pagina (JSON-LD).
- Salva cada coleta em um banco de dados SQLite (`dados/monitor.db`), montando um
  historico de precos.
- Registra falhas (site fora do ar, preco nao encontrado etc.) na tabela `erros`,
  sem interromper a coleta dos outros produtos.
- Valida cada preco antes de salvar: se ele variar mais de 50% em relacao a ultima
  coleta do produto, vira um registro na tabela `alertas` e nao entra no historico.
  Se o mesmo preco aparecer de novo na coleta seguinte, ele e considerado confirmado e
  e salvo (assim um aumento real nao fica bloqueado para sempre).
- Gera `relatorios/relatorio.html` com os alertas de variacao de preco, o ultimo preco
  de cada produto, historico, busca e filtro por disponibilidade.

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
uma loja VTEX, e nao acessam a internet.

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
                       tabelas: coletas, erros, alertas
relatorios/
  relatorio.html       relatorio gerado
tests/
  test_extracao.py     testes da extracao de dados da pagina
  test_validacao.py    testes das regras de validacao de preco
  test_coleta.py       teste do fluxo completo, sem acessar o site
  test_coleta_diaria.py testes do script de coleta diaria e do log
  test_banco.py        testes das consultas SQL (banco em memoria)
  test_relatorio.py    testes do relatorio HTML
  paginas/             paginas HTML sinteticas usadas nos testes
```

## Coleta responsavel

- Pausa entre uma requisicao e outra, para nao sobrecarregar o site.
- Poucas execucoes por dia, apenas para produtos cadastrados.
- Respeito ao `robots.txt` e aos termos de uso dos sites (em implementacao).

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

Em lojas da plataforma VTEX, a pagina tambem traz um objeto
`__STATE__` com os dados de cada variacao. O monitor usa esse objeto como complemento,
para pegar o nome completo da variacao (ex.: `Telha ... 2,13 x 1,10m`). Se ele nao
existir, o nome vem do JSON-LD.

## Limitacoes conhecidas

- O EAN (codigo de barras), necessario para casar produtos entre lojas na v2, nao vem
  no JSON-LD dessas lojas. Ele existe nos dados VTEX da pagina, mas ainda nao e salvo.

## Roadmap

- **v1 (concluida):** 1 site, execucao manual.
  - [x] Coleta com tratamento de erros e historico em CSV
  - [x] Relatorio HTML
  - [x] Testes automatizados com paginas HTML sinteticas (sem acessar o site)
  - [x] Extracao via dados estruturados da pagina (JSON-LD / schema.org)
  - [x] Validacao dos dados (preco vazio ou variacao absurda gera alerta)
  - [x] Historico em SQLite
- **v2 (em andamento):**
  - [x] Execucao agendada diaria (Agendador de Tarefas do Windows)
  - [ ] Guardar o EAN dos produtos
  - [ ] Mais concorrentes, com produtos casados entre lojas pelo EAN
- **v3:** painel com graficos e alertas de mudanca de preco (Telegram/e-mail).

## Tecnologias

Python, requests, BeautifulSoup, SQLite (SQL), pytest, HTML/CSS/JavaScript.
