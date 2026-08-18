# Este programa gera um relatorio HTML com as ultimas coletas de precos.
import csv
from collections import defaultdict
from datetime import datetime
from html import escape
from pathlib import Path


PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_COLETAS = PASTA_PROJETO / "dados" / "coletas.csv"
ARQUIVO_ERROS = PASTA_PROJETO / "dados" / "erros.csv"
ARQUIVO_RELATORIO = PASTA_PROJETO / "relatorios" / "relatorio.html"


def ler_csv(caminho_arquivo):
    if not caminho_arquivo.exists() or caminho_arquivo.stat().st_size == 0:
        return []

    with open(caminho_arquivo, "r", newline="", encoding="utf-8") as arquivo_csv:
        leitor_csv = csv.DictReader(arquivo_csv, delimiter=";")
        return list(leitor_csv)


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

    return f"""
        <details class="produto-card">
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
            <td>{escape(erro["mensagem"])}</td>
            <td><a href="{escape(erro["url"])}" target="_blank" rel="noopener noreferrer">Ver no site</a></td>
        </tr>
    """


def gerar_html(coletas, erros):
    coletas_por_produto = agrupar_coletas_por_produto(coletas)
    cards_produtos = "\n".join(
        criar_card_produto(produto_id, historico)
        for produto_id, historico in sorted(coletas_por_produto.items())
    )
    linhas_erros = "\n".join(criar_linha_erro(erro) for erro in erros[-20:])
    data_geracao = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if linhas_erros == "":
        linhas_erros = """
            <tr>
                <td colspan="5">Nenhum erro registrado.</td>
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
            grid-template-columns: repeat(3, minmax(0, 1fr));
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

        .secao-erros {{
            margin-top: 32px;
        }}

        @media (max-width: 760px) {{
            header, summary {{
                display: block;
            }}

            .resumo {{
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
        </section>

        <section>
            <h2>Produtos</h2>
            <p class="subtitulo">Clique em um produto para abrir o historico de precos.</p>
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
</body>
</html>
"""


def main():
    coletas = ler_csv(ARQUIVO_COLETAS)
    erros = ler_csv(ARQUIVO_ERROS)
    html = gerar_html(coletas, erros)

    ARQUIVO_RELATORIO.parent.mkdir(exist_ok=True)

    with open(ARQUIVO_RELATORIO, "w", encoding="utf-8") as arquivo_html:
        arquivo_html.write(html)

    print("Relatorio gerado:", ARQUIVO_RELATORIO)


main()
