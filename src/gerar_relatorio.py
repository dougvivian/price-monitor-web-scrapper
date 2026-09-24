# Este programa gera um relatorio HTML com as ultimas coletas de precos.
#
# O relatorio e uma pagina com menu lateral e abas:
#   Visao geral | Comparador | Produtos | Historico | Alertas | Erros
# O HTML de cada aba e montado aqui no Python (facil de testar com pytest).
# O visual fica em src/relatorio/estilo.css e a interacao (abas, filtros, ordenacao)
# em src/relatorio/interacao.js.
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

# Quantos itens mostrar nas listas resumidas.
LIMITE_MAIORES_DIFERENCAS = 5
LIMITE_VARIACOES_RECENTES = 8
LIMITE_ALERTAS = 50
LIMITE_ERROS_ANTIGOS = 20


def ler_arquivo_modelo(caminho):
    return caminho.read_text(encoding="utf-8")


# ---------- Preparacao dos dados ----------

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


def formatar_percentual(percentual):
    # 20.0 -> "20,0%"   (sem seta: usado nas diferencas entre lojas)
    return f"{percentual:.1f}%".replace(".", ",")


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


def ler_categorias(cadastro):
    # Dicionario produto_id -> categoria (coluna "categoria" do produtos.csv), usado nos filtros.
    return {
        linha["produto_id"]: (linha.get("categoria") or "").strip()
        for linha in cadastro
        if (linha.get("categoria") or "").strip()
    }


# ---------- Comparativo entre lojas ----------

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


def ordenar_por_preco(ultimas_coletas):
    # Do mais barato para o mais caro; sem preco (indisponivel) vai para o fim.
    # A chave de ordenacao e uma tupla: (True/False, preco). False vem antes de True.
    return sorted(
        ultimas_coletas,
        key=lambda coleta: (coleta["preco"] is None, coleta["preco"] or 0),
    )


def menor_preco_por_loja(ultimas_coletas):
    # Um grupo pode ter mais de um produto da mesma loja (ex.: duas marcas de telha na
    # mesma medida). Para comparar LOJAS, ficamos com a opcao mais barata de cada uma.
    # Resultado: lista com a coleta mais barata de cada loja, do menor para o maior preco.
    melhores = {}

    for coleta in ultimas_coletas:
        if coleta["preco"] is None:
            continue

        loja = coleta["concorrente"]

        if loja not in melhores or coleta["preco"] < melhores[loja]["preco"]:
            melhores[loja] = coleta

    return sorted(melhores.values(), key=lambda coleta: coleta["preco"])


def diferenca_entre_lojas(ultimas_coletas):
    # Quanto a loja mais cara cobra a mais que a mais barata, em %,
    # comparando a opcao mais barata de cada loja.
    # None quando menos de 2 lojas tem preco (ex.: produto indisponivel numa delas).
    melhores = menor_preco_por_loja(ultimas_coletas)

    if len(melhores) < 2:
        return None

    return calcular_variacao(melhores[0]["preco"], melhores[-1]["preco"]) * 100


# ---------- Pedacos de HTML reaproveitados ----------

def criar_selo_status(status):
    classe = "selo-alerta" if status == "indisponivel" else "selo-ok"
    return f'<span class="selo {classe}">{escape(status)}</span>'


def criar_selo_variacao(variacao):
    # Seta e cor mostram se o preco subiu ou caiu. Sem variacao, nao mostra nada.
    if not variacao:
        return ""

    classe = "variacao-alta" if variacao > 0 else "variacao-queda"
    return f'<span class="{classe}">{escape(formatar_variacao(variacao))}</span>'


def criar_link_site(url):
    # rel="noopener noreferrer": a pagina aberta nao consegue mexer na aba do relatorio.
    return f'<a class="sem-quebra" href="{escape(url)}" target="_blank" rel="noopener noreferrer">Ver no site</a>'


def criar_tabela(cabecalhos, linhas, mensagem_vazia, id_tabela=""):
    # Monta uma tabela padrao do relatorio.
    # cabecalhos: lista de (texto, classe). A classe "num" alinha numeros a direita.
    # Sem linhas, mostra a mensagem_vazia ocupando a tabela toda (estado vazio).
    celulas_cabecalho = "".join(
        f'<th class="{classe}">{escape(texto)}</th>' for texto, classe in cabecalhos
    )
    corpo = "".join(linhas)

    if corpo == "":
        corpo = f'<tr><td class="vazio" colspan="{len(cabecalhos)}">{escape(mensagem_vazia)}</td></tr>'

    atributo_id = f' id="{id_tabela}"' if id_tabela else ""

    return f"""
        <div class="tabela-rolagem">
            <table{atributo_id}>
                <thead><tr>{celulas_cabecalho}</tr></thead>
                <tbody>{corpo}</tbody>
            </table>
        </div>
    """


# ---------- Aba: Visao geral ----------

def criar_indicador(valor, texto, destaque=""):
    # Cartao com um numero grande. destaque="alerta" pinta o numero de vermelho.
    classe = f"indicador indicador-{destaque}" if destaque else "indicador"
    return f"""
        <div class="{classe}">
            <strong>{valor}</strong>
            <span>{escape(texto)}</span>
        </div>
    """


def criar_maiores_diferencas(comparativos):
    # As comparacoes com maior diferenca de preco entre lojas: onde vale mais a pena olhar.
    com_diferenca = []

    for chave, ultimas_coletas in comparativos.items():
        diferenca = diferenca_entre_lojas(ultimas_coletas)

        if diferenca is not None:
            com_diferenca.append((diferenca, chave, menor_preco_por_loja(ultimas_coletas)))

    # sort com key: ordena so pela diferenca (a maior primeiro).
    com_diferenca.sort(key=lambda item: item[0], reverse=True)
    linhas = []

    for diferenca, chave, melhores in com_diferenca[:LIMITE_MAIORES_DIFERENCAS]:
        # melhores: opcao mais barata de cada loja, do menor para o maior preco.
        mais_barato = melhores[0]
        mais_caro = melhores[-1]
        linhas.append(f"""
            <tr>
                <td>{escape(chave)}</td>
                <td>{escape(mais_barato["concorrente"])}</td>
                <td class="num">{escape(mais_barato["preco_texto"])}</td>
                <td>{escape(mais_caro["concorrente"])}</td>
                <td class="num">{escape(mais_caro["preco_texto"])}</td>
                <td class="num"><strong>{escape(formatar_percentual(diferenca))}</strong></td>
            </tr>
        """)

    return criar_tabela(
        [("Grupo", ""), ("Loja mais barata", ""), ("Preco", "num"),
         ("Loja mais cara", ""), ("Preco", "num"), ("Diferenca", "num")],
        linhas,
        "Nenhuma comparacao com 2 lojas com preco ainda.",
    )


def criar_variacoes_recentes(coletas_por_produto):
    # Produtos cujo preco mudou desde a coleta anterior, das maiores mudancas para as menores.
    variacoes = []

    for produto_id, historico in coletas_por_produto.items():
        variacao = variacao_desde_coleta_anterior(historico)

        if variacao:
            variacoes.append((abs(variacao), variacao, produto_id, historico))

    variacoes.sort(reverse=True)
    linhas = []

    for _, variacao, produto_id, historico in variacoes[:LIMITE_VARIACOES_RECENTES]:
        ultima = historico[0]
        linhas.append(f"""
            <tr>
                <td><a href="#historico/{escape(produto_id)}">{escape(ultima["produto_nome"])}</a></td>
                <td>{escape(ultima["concorrente"])}</td>
                <td class="num">{escape(ultima["preco_texto"])}</td>
                <td class="num">{criar_selo_variacao(variacao)}</td>
            </tr>
        """)

    return criar_tabela(
        [("Produto", ""), ("Loja", ""), ("Preco atual", "num"), ("Variacao", "num")],
        linhas,
        "Nenhum preco mudou desde a coleta anterior.",
    )


# ---------- Aba: Comparador ----------

def criar_card_comparativo(chave, ultimas_coletas, categoria=""):
    ordenadas = ordenar_por_preco(ultimas_coletas)
    tem_preco = ordenadas[0]["preco"] is not None
    diferenca = diferenca_entre_lojas(ultimas_coletas)

    resumo = "Menos de 2 lojas com preco disponivel para comparar."

    if diferenca is not None:
        resumo = f"A loja mais cara cobra {formatar_percentual(diferenca)} a mais que a mais barata."

    linhas = []

    for coleta in ordenadas:
        # Selo "mais barato" so no primeiro da lista, e so se ele tiver preco.
        selo = ""

        if tem_preco and coleta is ordenadas[0]:
            selo = ' <span class="selo selo-ok">mais barato</span>'

        linhas.append(f"""
            <tr>
                <td>{escape(coleta["concorrente"])}</td>
                <td><strong>{escape(coleta["produto_id"])}</strong> {escape(coleta["produto_nome"])}</td>
                <td class="num">{escape(coleta["preco_texto"] or "Sem preco")}{selo}</td>
                <td>{criar_selo_status(coleta["status_produto"])}</td>
                <td>{criar_link_site(coleta["url"])}</td>
            </tr>
        """)

    tabela = criar_tabela(
        [("Loja", ""), ("Produto", ""), ("Preco", "num"), ("Status", ""), ("Link", "")],
        linhas,
        "",
    )
    selo_categoria = f'<span class="selo selo-neutro">{escape(categoria)}</span>' if categoria else ""

    # data-* guardam os valores que o JavaScript usa para filtrar e ordenar os cards.
    return f"""
        <article class="cartao comparativo" data-categoria="{escape(categoria)}"
                 data-diferenca="{diferenca if diferenca is not None else -1}" data-nome="{escape(chave.lower())}">
            <header class="cartao-cabecalho">
                <h3>{escape(chave)}</h3>
                {selo_categoria}
            </header>
            <p class="texto-suave">{escape(resumo)}</p>
            {tabela}
        </article>
    """


# ---------- Aba: Produtos ----------

def criar_linha_produto(produto_id, historico, categoria, teve_erro_na_ultima_coleta):
    ultima = historico[0]
    variacao = variacao_desde_coleta_anterior(historico)

    # Se o produto deu erro na coleta mais recente, o preco mostrado pode estar desatualizado.
    selo_erro = ""

    if teve_erro_na_ultima_coleta:
        selo_erro = ' <span class="selo selo-erro">erro na ultima coleta</span>'

    texto_busca = f"{produto_id} {ultima['produto_nome']} {ultima['concorrente']} {categoria}".lower()
    preco = ultima["preco"] if ultima["preco"] is not None else ""

    # data-valor em cada celula e o valor "cru" usado para ordenar a coluna no JavaScript
    # (ordenar "R$9,90" como texto colocaria depois de "R$10,00").
    return f"""
        <tr data-busca="{escape(texto_busca)}" data-status="{escape(ultima["status_produto"])}"
            data-loja="{escape(ultima["concorrente"])}" data-categoria="{escape(categoria)}">
            <td class="texto-suave sem-quebra" data-valor="{escape(produto_id)}">{escape(produto_id)}</td>
            <td data-valor="{escape(ultima["produto_nome"].lower())}">
                <a href="#historico/{escape(produto_id)}">{escape(ultima["produto_nome"])}</a>
            </td>
            <td data-valor="{escape(ultima["concorrente"])}">{escape(ultima["concorrente"])}</td>
            <td data-valor="{escape(categoria)}">{escape(categoria)}</td>
            <td class="num" data-valor="{preco}">{escape(ultima["preco_texto"] or "Sem preco")}</td>
            <td class="num" data-valor="{variacao or 0}">{criar_selo_variacao(variacao)}</td>
            <td data-valor="{escape(ultima["status_produto"])}">{criar_selo_status(ultima["status_produto"])}{selo_erro}</td>
            <td class="texto-suave sem-quebra" data-valor="{escape(ultima["data_coleta"])}">{escape(ultima["data_coleta"])}</td>
            <td>{criar_link_site(ultima["url"])}</td>
        </tr>
    """


def criar_opcoes(valores, texto_todos):
    # Opcoes de um <select> de filtro: "Todas" + cada valor, em ordem alfabetica.
    opcoes = [f'<option value="">{escape(texto_todos)}</option>']
    opcoes += [f'<option value="{escape(valor)}">{escape(valor)}</option>' for valor in sorted(valores)]
    return "".join(opcoes)


# ---------- Aba: Historico ----------

def criar_grafico_svg(historico):
    # Grafico de linha do preco, desenhado em SVG (formato de imagem feito de texto que o
    # navegador entende). Sem biblioteca: calculamos a posicao de cada ponto na mao.
    # historico esta do mais recente para o mais antigo; o grafico vai do antigo (esquerda)
    # para o recente (direita). Coletas sem preco (indisponivel) ficam de fora.
    pontos = [coleta for coleta in reversed(historico) if coleta["preco"] is not None]

    if len(pontos) < 2:
        return '<p class="texto-suave">O grafico aparece a partir de 2 coletas com preco.</p>'

    # Tamanho do desenho. O SVG estica para a largura da tela mantendo a proporcao
    # (5 x 1): numa tela de ~1000px, as medidas ficam perto do tamanho real em pixels.
    largura, altura, margem = 1000, 200, 28
    precos = [coleta["preco"] for coleta in pontos]
    menor, maior = min(precos), max(precos)

    def posicao_x(indice):
        # Pontos espalhados por igual na largura (um por coleta).
        return margem + indice * (largura - 2 * margem) / (len(pontos) - 1)

    def posicao_y(preco):
        # No SVG o y cresce para BAIXO, por isso subtraimos da altura.
        # Preco que nunca mudou: linha reta no meio (evita divisao por zero).
        if maior == menor:
            return altura / 2
        return altura - margem - (preco - menor) * (altura - 2 * margem) / (maior - menor)

    coordenadas = [(posicao_x(i), posicao_y(coleta["preco"])) for i, coleta in enumerate(pontos)]
    linha = " ".join(f"{x:.1f},{y:.1f}" for x, y in coordenadas)

    # Cada ponto tem um <title>: o navegador mostra data e preco ao passar o mouse.
    circulos = "".join(
        f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4"><title>{escape(coleta["data_coleta"])}: '
        f'{escape(coleta["preco_texto"])}</title></circle>'
        for (x, y), coleta in zip(coordenadas, pontos)
    )
    descricao = (
        f"Preco de {pontos[0]['preco_texto']} em {pontos[0]['data_coleta']} "
        f"a {pontos[-1]['preco_texto']} em {pontos[-1]['data_coleta']}"
    )

    # Rotulos de maior e menor preco; se o preco nunca mudou, um rotulo so.
    if maior == menor:
        rotulos = f'<text x="4" y="{altura / 2 - 12}" class="grafico-rotulo">preco estavel: {escape(formatar_preco(maior))}</text>'
    else:
        rotulos = (
            f'<text x="4" y="{margem - 12}" class="grafico-rotulo">maior: {escape(formatar_preco(maior))}</text>'
            f'<text x="4" y="{altura - 4}" class="grafico-rotulo">menor: {escape(formatar_preco(menor))}</text>'
        )

    return f"""
        <figure class="grafico">
            <svg viewBox="0 0 {largura} {altura}" role="img" aria-label="{escape(descricao)}">
                {rotulos}
                <polyline points="{linha}" />
                {circulos}
            </svg>
            <figcaption>
                <span>{escape(pontos[0]["data_coleta"][:10])}</span>
                <span>{escape(pontos[-1]["data_coleta"][:10])}</span>
            </figcaption>
        </figure>
    """


def criar_linha_historico(coleta):
    return f"""
        <tr>
            <td>{escape(coleta["data_coleta"])}</td>
            <td class="num">{escape(coleta["preco_texto"] or "Sem preco")}</td>
            <td>{criar_selo_status(coleta["status_produto"])}</td>
            <td class="texto-suave">{escape(coleta["mensagem"])}</td>
        </tr>
    """


def criar_painel_historico(produto_id, historico):
    ultima = historico[0]
    tabela = criar_tabela(
        [("Data", ""), ("Preco", "num"), ("Status", ""), ("Mensagem", "")],
        [criar_linha_historico(coleta) for coleta in historico],
        "",
    )

    return f"""
        <article class="cartao painel-historico" id="historico-{escape(produto_id)}" data-produto="{escape(produto_id)}">
            <header class="cartao-cabecalho">
                <h3>{escape(ultima["produto_nome"])}</h3>
                {criar_link_site(ultima["url"])}
            </header>
            <p class="texto-suave">
                {escape(produto_id)} &middot; {escape(ultima["concorrente"])} &middot;
                coletado em {escape(ultima["data_coleta"])}
            </p>
            {criar_grafico_svg(historico)}
            {tabela}
        </article>
    """


def criar_seletor_historico(produtos_ordenados):
    # <select> com os produtos separados por loja (<optgroup>).
    # Ja vem escolhido o produto com o grafico mais interessante:
    #   1o: mais coletas COM PRECO (um produto sempre indisponivel nao tem grafico);
    #   2o: no empate, mais precos diferentes (um grafico reto nao mostra nada).
    # A chave de ordenacao e uma tupla: compara o 1o item e, se empatar, o 2o.
    def interesse(item):
        precos = [coleta["preco"] for coleta in item[1] if coleta["preco"] is not None]
        return (len(precos), len(set(precos)))

    mais_coletado = max(produtos_ordenados, key=interesse, default=("", []))[0]
    por_loja = defaultdict(list)

    for produto_id, historico in produtos_ordenados:
        por_loja[historico[0]["concorrente"]].append((produto_id, historico[0]["produto_nome"]))

    grupos = []

    for loja in sorted(por_loja):
        opcoes = "".join(
            f'<option value="{escape(produto_id)}"{" selected" if produto_id == mais_coletado else ""}>'
            f'{escape(produto_id)} &middot; {escape(nome)}</option>'
            for produto_id, nome in por_loja[loja]
        )
        grupos.append(f'<optgroup label="{escape(loja)}">{opcoes}</optgroup>')

    return "".join(grupos)


# ---------- Abas: Alertas e Erros ----------

def criar_linha_alerta(alerta, nomes_produtos):
    # Nome do produto a partir das coletas; se o produto nunca foi coletado, fica so o ID.
    nome_produto = nomes_produtos.get(alerta["produto_id"], "")

    return f"""
        <tr>
            <td>{escape(alerta["data_alerta"])}</td>
            <td><strong>{escape(alerta["produto_id"])}</strong> {escape(nome_produto)}</td>
            <td class="num">{escape(formatar_preco(alerta["preco_anterior"]))}</td>
            <td class="num">{escape(formatar_preco(alerta["preco_novo"]))}</td>
            <td class="num">{criar_selo_variacao(alerta["variacao_percentual"])}</td>
            <td>{criar_link_site(alerta["url"])}</td>
        </tr>
    """


def criar_linha_erro(erro):
    return f"""
        <tr>
            <td>{escape(erro["data_erro"])}</td>
            <td>{escape(erro["produto_id"])}</td>
            <td><span class="selo selo-erro">{escape(erro["tipo_erro"])}</span></td>
            <td>{escape(erro["mensagem"] or "")}</td>
            <td>{criar_link_site(erro["url"])}</td>
        </tr>
    """


def criar_tabela_erros(erros, mensagem_vazia):
    return criar_tabela(
        [("Data", ""), ("Produto", ""), ("Tipo", ""), ("Mensagem", ""), ("Link", "")],
        [criar_linha_erro(erro) for erro in erros],
        mensagem_vazia,
    )


def criar_contador(quantidade, destaque=False):
    # Numero ao lado do nome da aba no menu. destaque=True pinta de vermelho (algo a resolver).
    if not quantidade:
        return ""

    classe = "contador contador-destaque" if destaque else "contador"
    return f'<span class="{classe}">{quantidade}</span>'


# ---------- Pagina completa ----------

def gerar_html(coletas, erros, alertas, ultima_execucao=None, grupos=None, categorias=None):
    categorias = categorias or {}
    coletas_por_produto = agrupar_coletas_por_produto(coletas)
    produtos_ordenados = sorted(
        coletas_por_produto.items(),
        key=lambda item: item[1][0]["produto_nome"].lower(),
    )

    # Comparativo entre lojas: produtos casados pelo grupo do cadastro ou pelo EAN.
    comparativos = montar_comparativos(coletas_por_produto, grupos or {})

    # Separamos os erros da ultima coleta (o que precisa de atencao agora)
    # dos erros antigos (so para consulta; mostramos os mais recentes).
    erros_recentes, erros_antigos = separar_erros(erros, ultima_execucao)
    erros_antigos = erros_antigos[-LIMITE_ERROS_ANTIGOS:]
    produtos_com_erro = {erro["produto_id"] for erro in erros_recentes}

    # --- Comparador ---
    cards_comparativos = "\n".join(
        criar_card_comparativo(
            chave,
            ultimas_coletas,
            # Categoria do comparativo: a do primeiro produto do grupo que tiver categoria.
            next((categorias[c["produto_id"]] for c in ultimas_coletas if c["produto_id"] in categorias), ""),
        )
        for chave, ultimas_coletas in comparativos.items()
    )

    if cards_comparativos == "":
        cards_comparativos = """
            <p class="vazio">Nenhum produto casado entre lojas ainda (mesmo EAN ou mesmo grupo).</p>
        """

    # --- Produtos ---
    linhas_produtos = [
        criar_linha_produto(
            produto_id, historico, categorias.get(produto_id, ""), produto_id in produtos_com_erro
        )
        for produto_id, historico in produtos_ordenados
    ]
    tabela_produtos = criar_tabela(
        [("ID", ""), ("Produto", ""), ("Loja", ""), ("Categoria", ""), ("Preco", "num"),
         ("Variacao", "num"), ("Status", ""), ("Coletado em", ""), ("Link", "")],
        linhas_produtos,
        "Nenhum produto coletado ainda.",
        id_tabela="tabelaProdutos",
    )
    lojas = {historico[0]["concorrente"] for historico in coletas_por_produto.values()}
    categorias_usadas = {categorias[p] for p in coletas_por_produto if p in categorias}

    # --- Historico ---
    paineis_historico = "\n".join(
        criar_painel_historico(produto_id, historico) for produto_id, historico in produtos_ordenados
    )

    if paineis_historico == "":
        paineis_historico = '<p class="vazio">Nenhum produto coletado ainda.</p>'

    # --- Alertas ---
    # Dicionario produto_id -> nome da ultima coleta, usado na tabela de alertas.
    nomes_produtos = {
        produto_id: historico[0]["produto_nome"]
        for produto_id, historico in coletas_por_produto.items()
    }
    # Ultimos alertas, do mais recente para o mais antigo.
    # alertas[-N:] pega os N ultimos; reversed() inverte a ordem.
    tabela_alertas = criar_tabela(
        [("Data", ""), ("Produto", ""), ("Preco anterior", "num"), ("Preco novo", "num"),
         ("Variacao", "num"), ("Link", "")],
        [criar_linha_alerta(alerta, nomes_produtos) for alerta in reversed(alertas[-LIMITE_ALERTAS:])],
        "Nenhum alerta de variacao de preco.",
    )

    # --- Erros ---
    tabela_erros_recentes = criar_tabela_erros(erros_recentes, "Nenhum erro na ultima coleta.")
    tabela_erros_antigos = criar_tabela_erros(list(reversed(erros_antigos)), "Nenhum erro anterior.")

    resumo_execucao = criar_resumo_execucao(ultima_execucao)
    data_geracao = agora()
    estilo = ler_arquivo_modelo(ARQUIVO_ESTILO)
    script = ler_arquivo_modelo(ARQUIVO_SCRIPT)

    return f"""<!DOCTYPE html>
<html lang="pt-BR">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>Monitor de Precos</title>
    <!-- Marca que o JavaScript esta ligado. Sem JS, todas as abas aparecem uma embaixo da outra. -->
    <script>document.documentElement.classList.add("js");</script>
    <style>
{estilo}
    </style>
</head>
<body>
    <div class="layout">
        <nav class="menu" aria-label="Secoes do relatorio">
            <p class="menu-titulo">Monitor de Precos</p>
            <a href="#visao-geral" data-aba="visao-geral">Visao geral</a>
            <a href="#comparador" data-aba="comparador">Comparador {criar_contador(len(comparativos))}</a>
            <a href="#produtos" data-aba="produtos">Produtos {criar_contador(len(coletas_por_produto))}</a>
            <a href="#historico" data-aba="historico">Historico</a>
            <a href="#alertas" data-aba="alertas">Alertas {criar_contador(len(alertas))}</a>
            <a href="#erros" data-aba="erros">Erros {criar_contador(len(erros_recentes), destaque=True)}</a>
        </nav>

        <main class="conteudo">
            <header class="topo">
                <p class="topo-coleta">{escape(resumo_execucao)}</p>
                <p class="texto-suave">Relatorio gerado em {escape(data_geracao)}</p>
            </header>

            <section class="aba" id="aba-visao-geral" aria-labelledby="titulo-visao-geral">
                <h1 id="titulo-visao-geral">Visao geral</h1>
                <div class="indicadores">
                    {criar_indicador(len(coletas_por_produto), "produtos com coleta")}
                    {criar_indicador(len(comparativos), "comparacoes entre lojas")}
                    {criar_indicador(len(alertas), "alertas de preco")}
                    {criar_indicador(len(erros_recentes), "erros na ultima coleta", "alerta" if erros_recentes else "")}
                </div>

                <h2>Maiores diferencas entre lojas</h2>
                <p class="texto-suave">
                    Onde o mesmo produto (ou um equivalente) tem a maior diferenca de preco entre as
                    lojas, comparando a opcao mais barata de cada loja.
                </p>
                {criar_maiores_diferencas(comparativos)}

                <h2>Precos que mudaram</h2>
                <p class="texto-suave">Variacao desde a coleta anterior de cada produto.</p>
                {criar_variacoes_recentes(coletas_por_produto)}
            </section>

            <section class="aba" id="aba-comparador" aria-labelledby="titulo-comparador">
                <h1 id="titulo-comparador">Comparativo entre Lojas</h1>
                <p class="texto-suave">
                    Ultimo preco de cada loja para o mesmo produto (mesmo EAN) ou para produtos
                    equivalentes (mesmo grupo no produtos.csv), do mais barato para o mais caro.
                </p>
                <div class="controles">
                    <label>Categoria
                        <select id="filtroCategoriaComparador">{criar_opcoes(categorias_usadas, "Todas")}</select>
                    </label>
                    <label>Ordenar por
                        <select id="ordemComparador">
                            <option value="diferenca">Maior diferenca</option>
                            <option value="nome">Nome do grupo</option>
                        </select>
                    </label>
                </div>
                <div id="listaComparativos">
                    {cards_comparativos}
                </div>
            </section>

            <section class="aba" id="aba-produtos" aria-labelledby="titulo-produtos">
                <h1 id="titulo-produtos">Produtos pesquisados</h1>
                <p class="texto-suave">Clique no nome para ver o historico. Clique no titulo de uma coluna para ordenar.</p>
                <div class="controles">
                    <label class="controle-busca">Buscar
                        <input id="buscaProduto" type="search" placeholder="Produto, ID, loja ou categoria">
                    </label>
                    <label>Loja
                        <select id="filtroLoja">{criar_opcoes(lojas, "Todas")}</select>
                    </label>
                    <label>Categoria
                        <select id="filtroCategoria">{criar_opcoes(categorias_usadas, "Todas")}</select>
                    </label>
                    <label>Status
                        <select id="filtroStatus">
                            <option value="">Todos</option>
                            <option value="disponivel">Disponiveis</option>
                            <option value="indisponivel">Indisponiveis</option>
                        </select>
                    </label>
                </div>
                <p class="texto-suave" id="contadorProdutos" aria-live="polite"></p>
                {tabela_produtos}
            </section>

            <section class="aba" id="aba-historico" aria-labelledby="titulo-historico">
                <h1 id="titulo-historico">Historico de precos</h1>
                <div class="controles">
                    <label class="controle-busca">Produto
                        <select id="seletorHistorico">{criar_seletor_historico(produtos_ordenados)}</select>
                    </label>
                </div>
                {paineis_historico}
            </section>

            <section class="aba" id="aba-alertas" aria-labelledby="titulo-alertas">
                <h1 id="titulo-alertas">Alertas de Variacao de Preco</h1>
                <p class="texto-suave">
                    Precos que variaram mais de 50% em relacao a ultima coleta. Eles nao entram no
                    historico; se o mesmo preco aparecer na coleta seguinte, e confirmado e salvo.
                </p>
                {tabela_alertas}
            </section>

            <section class="aba" id="aba-erros" aria-labelledby="titulo-erros">
                <h1 id="titulo-erros">Erros da Ultima Coleta</h1>
                <p class="texto-suave">
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
    </div>
    <script>
{script}
    </script>
</body>
</html>
"""


def gerar_relatorio(arquivo_banco, arquivo_relatorio, cadastro):
    # Gera o relatorio a partir de um banco e de um cadastro quaisquer.
    # Fica separado do main() para o modo demonstracao (demo.py) usar o mesmo codigo
    # com um banco de dados ficticio, sem tocar no banco real.

    # Lemos tudo do banco de dados e fechamos a conexao logo em seguida.
    conexao = banco.conectar(arquivo_banco)

    try:
        coletas = [preparar_coleta(coleta) for coleta in banco.listar_coletas(conexao)]
        erros = banco.listar_erros(conexao)
        alertas = banco.listar_alertas(conexao)
        ultima_execucao = banco.buscar_ultima_execucao(conexao)
    finally:
        conexao.close()

    # Grupos de equivalencia e categorias vem do cadastro.
    html = gerar_html(
        coletas, erros, alertas, ultima_execucao,
        grupos=ler_grupos(cadastro),
        categorias=ler_categorias(cadastro),
    )

    arquivo_relatorio.parent.mkdir(exist_ok=True)

    with open(arquivo_relatorio, "w", encoding="utf-8") as arquivo_html:
        arquivo_html.write(html)

    print("Relatorio gerado:", arquivo_relatorio)


def main():
    # Sem produtos.csv, o comparativo usa so o EAN e os filtros de categoria ficam vazios.
    cadastro = ler_cadastro() if ARQUIVO_PRODUTOS.exists() else []
    gerar_relatorio(ARQUIVO_BANCO, ARQUIVO_RELATORIO, cadastro)


# So gera o relatorio quando rodamos "python src/gerar_relatorio.py" diretamente.
# Se este arquivo for importado (por exemplo, em um teste), nada e executado sozinho.
if __name__ == "__main__":
    main()
