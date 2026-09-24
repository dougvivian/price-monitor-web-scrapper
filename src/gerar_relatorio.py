# Este programa gera um relatorio HTML com as ultimas coletas de precos.
from collections import defaultdict
from html import escape
from pathlib import Path

import banco
# Reaproveitamos do main.py o caminho do banco e a formatacao de preco,
# para nao repetir o mesmo codigo em dois lugares.
from main import ARQUIVO_BANCO, ARQUIVO_PRODUTOS, agora, calcular_variacao, formatar_preco, ler_cadastro


PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_RELATORIO = PASTA_PROJETO / "relatorios" / "relatorio.html"

# O visual (CSS) e a interacao (JavaScript) do relatorio ficam em arquivos proprios,
# para serem editados com a ajuda do editor. Na hora de gerar, o conteudo deles e
# copiado para dentro do HTML: o relatorio final continua sendo um arquivo so, que
# pode ser enviado por e-mail ou WhatsApp sem perder o visual.
PASTA_MODELO = Path(__file__).resolve().parent / "relatorio"
ARQUIVO_ESTILO = PASTA_MODELO / "estilo.css"
ARQUIVO_SCRIPT = PASTA_MODELO / "interacao.js"


def ler_arquivo_modelo(caminho):
    return caminho.read_text(encoding="utf-8")


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


def formatar_variacao(percentual):
    # 211.4 -> "▲ +211,4%"   |   -3.2 -> "▼ -3,2%"   (seta + sinal + formato brasileiro)
    seta = "▲" if percentual > 0 else "▼"
    return f"{seta} {percentual:+.1f}%".replace(".", ",")


def variacao_desde_coleta_anterior(historico):
    # historico esta do mais recente para o mais antigo.
    # Compara o preco mais recente com o preco anterior (ignorando coletas sem preco).
    # Devolve a variacao em % ou None se nao houver dois precos para comparar.
    if historico[0]["preco"] is None:
        return None

    precos = [coleta["preco"] for coleta in historico if coleta["preco"] is not None]

    if len(precos) < 2:
        return None

    return calcular_variacao(precos[1], precos[0]) * 100


def separar_erros(erros, ultima_execucao):
    # Separa os erros em (recentes, antigos): recentes sao os gravados a partir do inicio
    # da ultima coleta. Como as datas estao no formato "AAAA-MM-DD HH:MM:SS", comparar o
    # texto ja compara as datas.
    # Sem nenhuma coleta registrada, todos os erros contam como antigos.
    if ultima_execucao is None:
        return [], erros

    inicio = ultima_execucao["inicio"]
    recentes = [erro for erro in erros if erro["data_erro"] >= inicio]
    antigos = [erro for erro in erros if erro["data_erro"] < inicio]
    return recentes, antigos


def ler_grupos(cadastro):
    # Dicionario produto_id -> grupo, a partir da coluna opcional "grupo" do produtos.csv.
    # O grupo e um codigo que NOS damos para produtos equivalentes em lojas diferentes
    # (ex.: "FERRO-CA50-10"). Cadastro sem essa coluna simplesmente nao tem grupos.
    grupos = {}

    for linha in cadastro:
        grupo = (linha.get("grupo") or "").strip()

        if grupo:
            grupos[linha["produto_id"]] = grupo

    return grupos


def chave_comparacao(produto_id, historico, grupos):
    # Define com quem o produto vai ser comparado:
    #   1o: o grupo do cadastro (equivalencia definida por nos, vale ate entre marcas diferentes);
    #   2o: o EAN (codigo de barras igual = mesmo produto, casamento automatico).
    # Usamos o EAN mais recente do historico (coletas antigas podem nao ter EAN).
    # Sem grupo e sem EAN, devolve "" e o produto fica fora do comparativo.
    if produto_id in grupos:
        return grupos[produto_id]

    ean = next((coleta["ean"] for coleta in historico if coleta.get("ean")), "")

    if ean:
        return f"EAN {ean}"

    return ""


def montar_comparativos(coletas_por_produto, grupos):
    # Junta os produtos com a mesma chave de comparacao (grupo ou EAN).
    # Resultado: {chave: [ultima coleta de cada produto da chave]}.
    comparativos = defaultdict(list)

    for produto_id, historico in coletas_por_produto.items():
        chave = chave_comparacao(produto_id, historico, grupos)

        if chave:
            comparativos[chave].append(historico[0])

    # So faz sentido comparar quando a chave junta pelo menos 2 lojas diferentes.
    # Usamos um set dos concorrentes para contar lojas sem repeticao.
    return {
        chave: ultimas_coletas
        for chave, ultimas_coletas in sorted(comparativos.items())
        if len({coleta["concorrente"] for coleta in ultimas_coletas}) >= 2
    }


def criar_card_comparativo(chave, ultimas_coletas):
    # Ordena do mais barato para o mais caro; sem preco (indisponivel) vai para o fim.
    # A chave de ordenacao e uma tupla: (True/False, preco). False vem antes de True.
    ordenadas = sorted(
        ultimas_coletas,
        key=lambda coleta: (coleta["preco"] is None, coleta["preco"] or 0),
    )
    precos = [coleta["preco"] for coleta in ordenadas if coleta["preco"] is not None]

    # Diferenca entre o maior e o menor preco, em % sobre o menor.
    resumo = "Menos de 2 precos disponiveis para comparar."

    if len(precos) >= 2:
        diferenca = calcular_variacao(precos[0], precos[-1]) * 100
        diferenca_texto = f"{diferenca:.1f}".replace(".", ",")
        resumo = f"O mais caro custa {diferenca_texto}% a mais que o mais barato."

    linhas = []

    for coleta in ordenadas:
        # Selo "mais barato" so no primeiro da lista, e so se ele tiver preco.
        selo = ""

        if precos and coleta is ordenadas[0]:
            selo = ' <span class="status status-disponivel">mais barato</span>'

        linhas.append(f"""
            <tr>
                <td>{escape(coleta["concorrente"])}</td>
                <td><strong>{escape(coleta["produto_id"])}</strong> {escape(coleta["produto_nome"])}</td>
                <td>{escape(coleta["preco_texto"] or "Sem preco")}{selo}</td>
                <td>{escape(coleta["status_produto"])}</td>
                <td><a href="{escape(coleta["url"])}" target="_blank" rel="noopener noreferrer">Ver no site</a></td>
            </tr>
        """)

    return f"""
        <div class="comparativo">
            <h3>{escape(chave)}</h3>
            <p class="subtitulo">{escape(resumo)}</p>
            <table>
                <thead>
                    <tr>
                        <th>Loja</th>
                        <th>Produto</th>
                        <th>Preco</th>
                        <th>Status</th>
                        <th>Link</th>
                    </tr>
                </thead>
                <tbody>
                    {"".join(linhas)}
                </tbody>
            </table>
        </div>
    """


def criar_resumo_execucao(ultima_execucao):
    if ultima_execucao is None:
        return "Nenhuma coleta registrada ainda."

    if ultima_execucao["fim"] is None:
        return f"Ultima coleta iniciada em {ultima_execucao['inicio']} e interrompida antes do fim."

    return (
        f"Ultima coleta: {ultima_execucao['inicio']} | "
        f"{ultima_execucao['coletados']} coletados, "
        f"{ultima_execucao['erros']} erros, "
        f"{ultima_execucao['alertas']} alertas"
    )


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


def criar_card_produto(produto_id, historico, teve_erro_na_ultima_coleta=False):
    ultima_coleta = historico[0]

    # Variacao em relacao a coleta anterior: so aparece quando o preco mudou.
    variacao = variacao_desde_coleta_anterior(historico)
    selo_variacao = ""

    if variacao:
        classe_variacao = "variacao-alta" if variacao > 0 else "variacao-queda"
        selo_variacao = f'<span class="{classe_variacao}">{escape(formatar_variacao(variacao))}</span>'

    # Se o produto deu erro na coleta mais recente, o preco mostrado pode estar desatualizado.
    selo_erro = ""

    if teve_erro_na_ultima_coleta:
        selo_erro = '<span class="status status-erro">erro na ultima coleta</span>'

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
                    <span class="data-coleta">{escape(ultima_coleta["concorrente"])}</span>
                    <span class="data-coleta">coletado em {escape(ultima_coleta["data_coleta"])}</span>
                </div>
                <div class="produto-meta">
                    <span class="preco">{escape(ultima_coleta["preco_texto"] or "Sem preco")}</span>
                    {selo_variacao}
                    <span class="status {classe_status}">{escape(status)}</span>
                    {selo_erro}
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

    # Nome do produto a partir das coletas; se o produto nunca foi coletado, fica so o ID.
    nome_produto = nomes_produtos.get(alerta["produto_id"], "")

    return f"""
        <tr>
            <td>{escape(alerta["data_alerta"])}</td>
            <td><strong>{escape(alerta["produto_id"])}</strong> {escape(nome_produto)}</td>
            <td>{escape(formatar_preco(alerta["preco_anterior"]))}</td>
            <td>{escape(formatar_preco(alerta["preco_novo"]))}</td>
            <td class="{classe_variacao}">{escape(formatar_variacao(variacao))}</td>
            <td><a href="{escape(alerta["url"])}" target="_blank" rel="noopener noreferrer">Ver no site</a></td>
        </tr>
    """


def criar_tabela_erros(erros, mensagem_vazia):
    linhas = "\n".join(criar_linha_erro(erro) for erro in erros)

    if linhas == "":
        linhas = f"""
            <tr>
                <td colspan="5">{escape(mensagem_vazia)}</td>
            </tr>
        """

    return f"""
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
                {linhas}
            </tbody>
        </table>
    """


def gerar_html(coletas, erros, alertas, ultima_execucao=None, grupos=None):
    coletas_por_produto = agrupar_coletas_por_produto(coletas)

    # Comparativo entre lojas: produtos casados pelo grupo do cadastro ou pelo EAN.
    comparativos = montar_comparativos(coletas_por_produto, grupos or {})
    cards_comparativos = "\n".join(
        criar_card_comparativo(chave, ultimas_coletas)
        for chave, ultimas_coletas in comparativos.items()
    )

    if cards_comparativos == "":
        cards_comparativos = """
            <p class="subtitulo">Nenhum produto casado entre lojas ainda (mesmo EAN ou mesmo grupo).</p>
        """

    # Separamos os erros da ultima coleta (o que precisa de atencao agora)
    # dos erros antigos (so para consulta; mostramos os 20 mais recentes).
    erros_recentes, erros_antigos = separar_erros(erros, ultima_execucao)
    erros_antigos = erros_antigos[-20:]
    produtos_com_erro = {erro["produto_id"] for erro in erros_recentes}

    produtos_ordenados = sorted(
        coletas_por_produto.items(),
        key=lambda item: item[1][0]["produto_nome"].lower(),
    )
    cards_produtos = "\n".join(
        criar_card_produto(produto_id, historico, produto_id in produtos_com_erro)
        for produto_id, historico in produtos_ordenados
    )
    tabela_erros_recentes = criar_tabela_erros(erros_recentes, "Nenhum erro na ultima coleta.")
    tabela_erros_antigos = criar_tabela_erros(list(reversed(erros_antigos)), "Nenhum erro anterior.")
    resumo_execucao = criar_resumo_execucao(ultima_execucao)
    data_geracao = agora()
    estilo = ler_arquivo_modelo(ARQUIVO_ESTILO)
    script = ler_arquivo_modelo(ARQUIVO_SCRIPT)

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
{estilo}
    </style>
</head>
<body>
    <main>
        <header>
            <div>
                <h1>Monitor de Precos</h1>
                <p class="subtitulo">Relatorio gerado em {escape(data_geracao)}</p>
                <p class="subtitulo">{escape(resumo_execucao)}</p>
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

        <section class="secao-comparativo">
            <h2>Comparativo entre Lojas</h2>
            <p class="subtitulo">
                Ultimo preco de cada loja para o mesmo produto (mesmo EAN) ou para produtos
                equivalentes (mesmo grupo no produtos.csv).
            </p>
            {cards_comparativos}
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
            <h2>Erros da Ultima Coleta</h2>
            <p class="subtitulo">
                Produtos com erro na coleta mais recente mostram o ultimo preco que deu certo,
                marcado com "erro na ultima coleta".
            </p>
            {tabela_erros_recentes}

            <details class="erros-antigos">
                <summary>Erros anteriores ({len(erros_antigos)} mais recentes)</summary>
                {tabela_erros_antigos}
            </details>
        </section>
    </main>
    <script>
{script}
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
        ultima_execucao = banco.buscar_ultima_execucao(conexao)
    finally:
        conexao.close()

    # Os grupos de equivalencia vem do cadastro. Sem produtos.csv, o comparativo usa so o EAN.
    cadastro = ler_cadastro() if ARQUIVO_PRODUTOS.exists() else []
    grupos = ler_grupos(cadastro)

    html = gerar_html(coletas, erros, alertas, ultima_execucao, grupos)

    ARQUIVO_RELATORIO.parent.mkdir(exist_ok=True)

    with open(ARQUIVO_RELATORIO, "w", encoding="utf-8") as arquivo_html:
        arquivo_html.write(html)

    print("Relatorio gerado:", ARQUIVO_RELATORIO)


# So gera o relatorio quando rodamos "python src/gerar_relatorio.py" diretamente.
# Se este arquivo for importado (por exemplo, em um teste), nada e executado sozinho.
if __name__ == "__main__":
    main()
