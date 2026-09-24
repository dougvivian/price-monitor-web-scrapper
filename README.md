# Monitor de Precos de Concorrentes

Ferramenta em Python que coleta automaticamente os precos de produtos em sites de
concorrentes do varejo de materiais de construcao, guarda o historico e gera um
relatorio HTML para consulta.

Nasceu de um problema real do meu trabalho: pesquisar precos da concorrencia manualmente,
produto por produto. O projeto tambem e um estudo de automacao, coleta e tratamento de dados.

## O que ele faz hoje

- Le a lista de produtos a monitorar em `dados/produtos.csv`.
- Acessa a pagina de cada produto e extrai nome, preco e disponibilidade.
- Salva cada coleta em `dados/coletas.csv`, montando um historico de precos.
- Registra falhas (site fora do ar, preco nao encontrado etc.) em `dados/erros.csv`,
  sem interromper a coleta dos outros produtos.
- Gera `relatorios/relatorio.html` com o ultimo preco de cada produto, historico,
  busca e filtro por disponibilidade.

Concorrente suportado no momento: **Loja A**.

## Como rodar

Requisitos: Python 3.10 ou superior.

```bash
# 1. Instalar as dependencias
pip install -r requirements.txt

# 2. Coletar os precos (acessa o site dos concorrentes)
python src/main.py

# 3. Gerar o relatorio HTML a partir das coletas salvas
python src/gerar_relatorio.py
```

Depois, abra `relatorios/relatorio.html` no navegador.

## Estrutura

```text
src/
  main.py              coleta os precos
  gerar_relatorio.py   gera o relatorio HTML
dados/
  produtos.csv         cadastro dos produtos monitorados (editavel no Excel)
  coletas.csv          historico de precos coletados
  erros.csv            falhas de coleta
relatorios/
  relatorio.html       relatorio gerado
aprendizado.md         diario do desenvolvimento e conceitos aprendidos
```

## Coleta responsavel

- Pausa entre uma requisicao e outra, para nao sobrecarregar o site.
- Poucas execucoes por dia, apenas para produtos cadastrados.
- Respeito ao `robots.txt` e aos termos de uso dos sites (em implementacao).

## Limitacoes conhecidas

- A extracao usa seletores CSS do HTML, que quebram quando o site muda o layout.
- Em produtos com variacoes (links com `?skuId=`), o site pode devolver o preco de
  outra variacao. Sera resolvido na troca para dados estruturados (JSON-LD).

## Roadmap

- **v1 (em andamento):** 1 site, 10 produtos, execucao manual.
  - [x] Coleta com tratamento de erros e historico em CSV
  - [x] Relatorio HTML
  - [ ] Testes automatizados com paginas HTML salvas (sem acessar o site)
  - [ ] Extracao via dados estruturados da pagina (JSON-LD / schema.org)
  - [ ] Validacao dos dados (preco vazio ou variacao absurda gera alerta)
  - [ ] Historico em SQLite
- **v2:** mais concorrentes, produtos casados entre lojas pelo EAN, execucao agendada diaria.
- **v3:** painel com graficos e alertas de mudanca de preco (Telegram/e-mail).

## Tecnologias

Python, requests, BeautifulSoup, CSV, HTML/CSS/JavaScript.
