# Este programa gera um relatorio HTML com as ultimas coletas de precos.
from collections import defaultdict
from datetime import datetime
from html import escape
from pathlib import Path

import banco
# Reaproveitamos do main.py o caminho do banco e a formatacao de preco,
# para nao repetir o mesmo codigo em dois lugares.
from main import ARQUIVO_BANCO, formatar_preco


PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_RELATORIO = PASTA_PROJETO / "relatorios" / "relatorio.html"


def preparar_coleta(coleta):
    # O banco guarda o preco como numero (ou None quando indisponivel).
    # O HTML precisa de texto, entao criamos as versoes em texto aqui.
    preco = coleta["preco"]
    coleta["preco_texto"] = formatar_preco(preco) if preco is not None else ""
    coleta["preco_numero"] = str(preco) if preco is not None else ""
    coleta["mensagem"] = coleta["mensagem"] or ""
    return coleta


def agrupar_coletas_por_produto(coletas):
    coletas_por_produto = defaultdict(list)

    for coleta in coletas:
        coletas_por_produto[coleta["produto_id"]].append(coleta)

    for historico in coletas_por_produto.values():
        historico.sort(key=lambda coleta: coleta["data_coleta"], reverse=True)

    return coletas_por_produto


def criar_linha_historico(coleta):
    return f"""
        <tr>
            <td>{escape(coleta["data_coleta"])}</td>
            <td>{escape(coleta["preco_texto"])}</td>
            <td>{escape(coleta["preco_numero"])}</td>
            <td>{escape(coleta["status_produto"])}</td>
            <td>{escape(coleta["mensagem"])}</td>
        </tr>
    """


def criar_card_produto(produto_id, historico):
    ultima_coleta = historico[0]
    linhas_historico = "\n".join(criar_linha_historico(coleta) for coleta in historico)
    status = ultima_coleta["status_produto"]
    classe_status = "status-indisponivel" if status == "indisponivel" else "status-disponivel"
    texto_busca = f"{produto_id} {ultima_coleta['produto_nome']} {ultima_coleta['concorrente']}".lower()

    return f"""
        <details class="produto-card" data-status="{escape(status)}" data-busca="{escape(texto_busca)}">
            <summary>
                <div class="produto-principal">
                    <span class="produto-id">{escape(produto_id)}</span>
                    <span class="produto-nome">{escape(ultima_coleta["produto_nome"])}</span>
                </div>
                <div class="produto-meta">
                    <span class="preco">{escape(ultima_coleta["preco_texto"] or "Sem preco")}</span>
                    <span class="status {classe_status}">{escape(status)}</span>
                    <a href="{escape(ultima_coleta["url"])}" target="_blank" rel="noopener noreferrer">Ver no site</a>
                </div>
            </summary>

            <div class="historico">
                <table>
                    <thead>
                        <tr>
                            <th>Data</th>
                            <th>Preco texto</th>
                            <th>Preco numero</th>
                            <th>Status</th>
                            <th>Mensagem</th>
                        </tr>
                    </thead>
                    <tbody>
                        {linhas_historico}
                    </tbody>
                </table>
            </div>
        </details>
    """


def criar_linha_erro(erro):
    return f"""
        <tr>
            <td>{escape(erro["data_erro"])}</td>
            <td>{escape(erro["produto_id"])}</td>
            <td>{escape(erro["tipo_erro"])}</td>
            <td>{escape(erro["mensagem"] or "")}</td>
            <td><a href="{escape(erro["url"])}" target="_blank" rel="noopener noreferrer">Ver no site</a></td>
        </tr>
    """


def criar_linha_alerta(alerta, nomes_produtos):
    # Seta e cor mostram se o preco subiu ou caiu.
    variacao = alerta["variacao_percentual"]
    classe_variacao = "variacao-alta" if variacao > 0 else "variacao-queda"
    seta = "▲" if variacao > 0 else "▼"

    # Nome do produto a partir das coletas; se o produto nunca foi coletado, fica so o ID.
    nome_produto = nomes_produtos.get(alerta["produto_id"], "")

    return f"""
        <tr>
            <td>{escape(alerta["data_alerta"])}</td>
            <td><strong>{escape(alerta["produto_id"])}</strong> {escape(nome_produto)}</td>
            <td>{escape(formatar_preco(alerta["preco_anterior"]))}</td>
            <td>{escape(formatar_preco(alerta["preco_novo"]))}</td>
            <td class="{classe_variacao}">{seta} {variacao:+.1f}%</td>
            <td><a href="{escape(alerta["url"])}" target="_blank" rel="noopener noreferrer">Ver no site</a></td>
        </tr>
    """


def gerar_html(coletas, erros, alertas):
    coletas_por_produto = agrupar_coletas_por_produto(coletas)
    produtos_ordenados = sorted(
        coletas_por_produto.items(),
        key=lambda item: item[1][0]["produto_nome"].lower(),
    )
    cards_produtos = "\n".join(
        criar_card_produto(produto_id, historico)
        for produto_id, historico in produtos_ordenados
    )
    linhas_erros = "\n".join(criar_linha_erro(erro) for erro in erros[-20:])
    data_geracao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if linhas_erros == "":
        linhas_erros = """
            <tr>
                <td colspan="5">Nenhum erro registrado.</td>
            </tr>
        """

    # Dicionario produto_id -> nome da ultima coleta, usado na tabela de alertas.
    nomes_produtos = {
        produto_id: historico[0]["produto_nome"]
        for produto_id, historico in coletas_por_produto.items()
    }

    # Ultimos 20 alertas, do mais recente para o mais antigo.
    # alertas[-20:] pega os 20 ultimos; reversed() inverte a ordem.
    linhas_alertas = "\n".join(
        criar_linha_alerta(alerta, nomes_produtos) for alerta in reversed(alertas[-20:])
    )

    if linhas_alertas == "":
        linhas_alertas = """
            <tr>
                <td colspan="6">Nenhum alerta de variacao de preco.</td>
            </tr>
        """

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Monitor de Precos</title>
    <style>
        body {{
            margin: 0;
            background: #f4f6f8;
            color: #1f2933;
            font-family: Arial, sans-serif;
        }}

        main {{
            max-width: 1180px;
            margin: 0 auto;
            padding: 32px 20px;
        }}

        header {{
            display: flex;
            justify-content: space-between;
            gap: 16px;
            align-items: flex-end;
            margin-bottom: 24px;
        }}

        h1, h2 {{
            margin: 0;
        }}

        .subtitulo {{
            margin-top: 8px;
            color: #607080;
        }}

        .resumo {{
            display: grid;
            grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 12px;
            margin-bottom: 24px;
        }}

        .indicador {{
            background: #ffffff;
            border: 1px solid #d9e0e7;
            border-radius: 8px;
            padding: 16px;
        }}

        .indicador strong {{
            display: block;
            font-size: 28px;
            margin-bottom: 4px;
        }}

        .controles {{
            display: grid;
            grid-template-columns: minmax(240px, 1fr) auto;
            gap: 12px;
            align-items: center;
            margin: 16px 0;
        }}

        .busca {{
            width: 100%;
            box-sizing: border-box;
            border: 1px solid #c9d3dd;
            border-radius: 8px;
            font-size: 16px;
            padding: 11px 12px;
        }}

        .filtros {{
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
        }}

        .filtro-status {{
            border: 1px solid #c9d3dd;
            border-radius: 8px;
            background: #ffffff;
            color: #1f2933;
            cursor: pointer;
            font-weight: 700;
            padding: 10px 12px;
        }}

        .filtro-status.ativo {{
            background: #1f2933;
            border-color: #1f2933;
            color: #ffffff;
        }}

        .contador-filtro {{
            color: #607080;
            margin-bottom: 12px;
        }}

        .produto-card {{
            background: #ffffff;
            border: 1px solid #d9e0e7;
            border-radius: 8px;
            margin-bottom: 10px;
            overflow: hidden;
        }}

        summary {{
            display: grid;
            grid-template-columns: 1fr auto;
            gap: 16px;
            align-items: center;
            cursor: pointer;
            padding: 14px 16px;
        }}

        summary::marker {{
            display: none;
        }}

        .produto-principal, .produto-meta {{
            display: flex;
            gap: 10px;
            align-items: center;
            flex-wrap: wrap;
        }}

        .produto-id {{
            color: #607080;
            font-weight: 700;
            min-width: 72px;
        }}

        .produto-nome {{
            font-weight: 700;
        }}

        .preco {{
            font-weight: 700;
            font-size: 18px;
        }}

        .status {{
            border-radius: 999px;
            padding: 4px 10px;
            font-size: 13px;
            font-weight: 700;
        }}

        .status-disponivel {{
            background: #e7f7ef;
            color: #177245;
        }}

        .status-indisponivel {{
            background: #fff3d9;
            color: #9a5b00;
        }}

        a {{
            color: #1d5fd1;
            font-weight: 700;
            text-decoration: none;
        }}

        a:hover {{
            text-decoration: underline;
        }}

        .historico {{
            border-top: 1px solid #d9e0e7;
            padding: 0 16px 16px;
            overflow-x: auto;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 14px;
        }}

        th, td {{
            border-bottom: 1px solid #e7ecf1;
            padding: 10px 8px;
            text-align: left;
            vertical-align: top;
        }}

        th {{
            color: #607080;
            font-size: 12px;
            text-transform: uppercase;
        }}

        .secao-erros, .secao-alertas {{
            margin-top: 32px;
        }}

        .secao-alertas {{
            margin-bottom: 32px;
        }}

        /* Preco subiu: vermelho. Preco caiu: verde. */
        .variacao-alta {{
            color: #b42318;
            font-weight: 700;
        }}

        .variacao-queda {{
            color: #177245;
            font-weight: 700;
        }}

        @media (max-width: 760px) {{
            header, summary {{
                display: block;
            }}

            .resumo {{
                grid-template-columns: 1fr;
            }}

            .controles {{
                grid-template-columns: 1fr;
            }}

            .produto-meta {{
                margin-top: 10px;
            }}
        }}
    </style>
</head>
<body>
    <main>
        <header>
            <div>
                <h1>Monitor de Precos</h1>
                <p class="subtitulo">Relatorio gerado em {escape(data_geracao)}</p>
            </div>
        </header>

        <section class="resumo">
            <div class="indicador">
                <strong>{len(coletas_por_produto)}</strong>
                <span>produtos com coleta</span>
            </div>
            <div class="indicador">
                <strong>{len(coletas)}</strong>
                <span>coletas no historico</span>
            </div>
            <div class="indicador">
                <strong>{len(erros)}</strong>
                <span>erros registrados</span>
            </div>
            <div class="indicador">
                <strong>{len(alertas)}</strong>
                <span>alertas de preco</span>
            </div>
        </section>

        <section class="secao-alertas">
            <h2>Alertas de Variacao de Preco</h2>
            <p class="subtitulo">
                Precos que variaram mais de 50% em relacao a ultima coleta. Eles nao entram no
                historico; se o mesmo preco aparecer na coleta seguinte, e confirmado e salvo.
            </p>
            <table>
                <thead>
                    <tr>
                        <th>Data</th>
                        <th>Produto</th>
                        <th>Preco anterior</th>
                        <th>Preco novo</th>
                        <th>Variacao</th>
                        <th>Link</th>
                    </tr>
                </thead>
                <tbody>
                    {linhas_alertas}
                </tbody>
            </table>
        </section>

        <section>
            <h2>Produtos</h2>
            <p class="subtitulo">Clique em um produto para abrir o historico de precos.</p>
            <div class="controles">
                <input class="busca" id="buscaProduto" type="search" placeholder="Buscar por produto, ID ou concorrente">
                <div class="filtros" aria-label="Filtro de status">
                    <button class="filtro-status ativo" type="button" data-status="todos">Todos</button>
                    <button class="filtro-status" type="button" data-status="disponivel">Disponiveis</button>
                    <button class="filtro-status" type="button" data-status="indisponivel">Indisponiveis</button>
                </div>
            </div>
            <p class="contador-filtro" id="contadorFiltro"></p>
            {cards_produtos}
        </section>

        <section class="secao-erros">
            <h2>Ultimos Erros</h2>
            <table>
                <thead>
                    <tr>
                        <th>Data</th>
                        <th>Produto</th>
                        <th>Tipo</th>
                        <th>Mensagem</th>
                        <th>Link</th>
                    </tr>
                </thead>
                <tbody>
                    {linhas_erros}
                </tbody>
            </table>
        </section>
    </main>
    <script>
        const buscaProduto = document.querySelector("#buscaProduto");
        const contadorFiltro = document.querySelector("#contadorFiltro");
        const botoesFiltro = document.querySelectorAll(".filtro-status");
        const cardsProdutos = document.querySelectorAll(".produto-card");
        let statusSelecionado = "todos";

        function aplicarFiltros() {{
            const termoBusca = buscaProduto.value.trim().toLowerCase();
            let totalVisivel = 0;

            cardsProdutos.forEach((card) => {{
                const textoBusca = card.dataset.busca;
                const status = card.dataset.status;
                const combinaBusca = textoBusca.includes(termoBusca);
                const combinaStatus = statusSelecionado === "todos" || status === statusSelecionado;
                const visivel = combinaBusca && combinaStatus;

                card.style.display = visivel ? "" : "none";

                if (visivel) {{
                    totalVisivel += 1;
                }}
            }});

            contadorFiltro.textContent = `${{totalVisivel}} produto(s) encontrado(s)`;
        }}

        buscaProduto.addEventListener("input", aplicarFiltros);

        botoesFiltro.forEach((botao) => {{
            botao.addEventListener("click", () => {{
                statusSelecionado = botao.dataset.status;

                botoesFiltro.forEach((item) => item.classList.remove("ativo"));
                botao.classList.add("ativo");

                aplicarFiltros();
            }});
        }});

        aplicarFiltros();
    </script>
</body>
</html>
"""


def main():
    # Lemos tudo do banco de dados e fechamos a conexao logo em seguida.
    conexao = banco.conectar(ARQUIVO_BANCO)

    try:
        coletas = [preparar_coleta(coleta) for coleta in banco.listar_coletas(conexao)]
        erros = banco.listar_erros(conexao)
        alertas = banco.listar_alertas(conexao)
    finally:
        conexao.close()

    html = gerar_html(coletas, erros, alertas)

    ARQUIVO_RELATORIO.parent.mkdir(exist_ok=True)

    with open(ARQUIVO_RELATORIO, "w", encoding="utf-8") as arquivo_html:
        arquivo_html.write(html)

    print("Relatorio gerado:", ARQUIVO_RELATORIO)


# So gera o relatorio quando rodamos "python src/gerar_relatorio.py" diretamente.
# Se este arquivo for importado (por exemplo, em um teste), nada e executado sozinho.
if __name__ == "__main__":
    main()
