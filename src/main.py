# Coleta os precos dos produtos cadastrados em dados/produtos.csv, valida cada preco
# e grava o resultado no banco de dados (dados/monitor.db).
#
# Para rodar:  python src/main.py
import csv
import json
from datetime import datetime
from pathlib import Path
from time import sleep
from urllib.parse import parse_qs, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

import banco


PASTA_PROJETO = Path(__file__).resolve().parent.parent
# O cadastro de produtos continua em CSV, porque e editado a mao no Excel.
ARQUIVO_PRODUTOS = PASTA_PROJETO / "dados" / "produtos.csv"
# Coletas, erros e alertas sao gravados no banco de dados SQLite (ver banco.py).
ARQUIVO_BANCO = PASTA_PROJETO / "dados" / "monitor.db"

# Variacao maxima aceita entre o preco novo e o ultimo preco salvo do mesmo produto.
# 0.5 = 50%. Acima disso o preco vira alerta e nao e salvo no historico.
LIMITE_VARIACAO = 0.5

# Segundos de espera antes de baixar de novo uma pagina que veio incompleta.
ESPERA_NOVA_TENTATIVA = 5

# Nome do "robo" usado para consultar as regras do robots.txt.
# Como nao enviamos um nome proprio nas requisicoes, seguimos as regras gerais ("*"),
# que valem para qualquer robo.
AGENTE_ROBOTS = "*"

# Colunas que o produtos.csv precisa ter. Sem elas a coleta nao consegue rodar.
COLUNAS_OBRIGATORIAS = ["produto_id", "concorrente", "url", "ativo"]

# Valor de disponibilidade padronizado pelo schema.org que indica produto em estoque.
# Qualquer outro valor (OutOfStock, Discontinued, PreOrder...) tratamos como indisponivel.
DISPONIVEL_SCHEMA = "InStock"


def agora():
    # Data e hora atuais no formato usado em todo o projeto: "2026-09-24 11:47:38".
    # Esse formato (ano-mes-dia) tem uma vantagem: ordenar o texto ja ordena as datas.
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def ler_cadastro():
    # Le todas as linhas do cadastro de produtos (ativas ou nao).
    with open(ARQUIVO_PRODUTOS, "r", newline="", encoding="utf-8") as arquivo_csv:
        return list(csv.DictReader(arquivo_csv, delimiter=";"))


def colunas_faltando(linhas):
    # Lista as colunas obrigatorias que nao existem no cadastro.
    # linhas[0] e a primeira linha de dados; as chaves dela sao os nomes das colunas.
    if not linhas:
        return []

    return [coluna for coluna in COLUNAS_OBRIGATORIAS if coluna not in linhas[0]]


def validar_cadastro(linhas):
    # Confere o cadastro ANTES de coletar e devolve uma lista de avisos (texto).
    # Um erro de digitacao no Excel (ID repetido, coluna apagada, "Sim " com espaco...)
    # apareceria so no meio da coleta, ou nem apareceria. Assim ele aparece logo no inicio.
    avisos = []

    if not linhas:
        return ["O cadastro de produtos esta vazio."]

    # Colunas obrigatorias: se faltar alguma, nem da para conferir o resto.
    faltando = colunas_faltando(linhas)

    if faltando:
        return [f"Colunas obrigatorias faltando no cadastro: {', '.join(faltando)}"]

    # Um set guarda valores sem repeticao; usamos para achar IDs repetidos.
    ids_vistos = set()

    # enumerate(..., start=2): a linha 1 do arquivo e o cabecalho, entao os dados comecam na 2.
    for numero_linha, linha in enumerate(linhas, start=2):
        produto_id = (linha["produto_id"] or "").strip()
        ativo = (linha["ativo"] or "").strip().lower()
        url = (linha["url"] or "").strip()

        if produto_id == "":
            avisos.append(f"Linha {numero_linha}: produto sem produto_id.")
        elif produto_id in ids_vistos:
            avisos.append(f"Linha {numero_linha}: produto_id repetido ({produto_id}).")
        else:
            ids_vistos.add(produto_id)

        if ativo not in ("sim", "nao"):
            avisos.append(f"Linha {numero_linha}: ativo deve ser 'sim' ou 'nao' (veio '{linha['ativo']}').")

        if not url.startswith(("http://", "https://")):
            avisos.append(f"Linha {numero_linha}: url invalida ({url or 'vazia'}).")

    return avisos


def filtrar_ativos(linhas):
    # So coletamos os produtos marcados como ativos.
    # strip() e lower() aceitam variacoes como "Sim" ou "sim " digitadas no Excel.
    return [linha for linha in linhas if (linha["ativo"] or "").strip().lower() == "sim"]


def ler_json_ld_produto(soup):
    # O JSON-LD fica dentro de tags <script type="application/ld+json">.
    # Uma pagina pode ter varios desses blocos (produto, empresa, caminho de navegacao...),
    # entao procuramos o que tem "@type": "Product".
    for tag_script in soup.select('script[type="application/ld+json"]'):
        texto_json = tag_script.string

        if not texto_json:
            continue

        try:
            # json.loads transforma o texto JSON em dicionario (ou lista) do Python.
            dados_json = json.loads(texto_json)
        except json.JSONDecodeError:
            # Se algum bloco estiver mal formatado, ignoramos e tentamos o proximo.
            continue

        # Alguns sites colocam varios objetos dentro de uma lista.
        # Transformamos o caso de objeto unico em lista para tratar os dois do mesmo jeito.
        if isinstance(dados_json, dict):
            dados_json = [dados_json]

        for item in dados_json:
            if isinstance(item, dict) and item.get("@type") == "Product":
                return item

    raise ValueError("JSON-LD do produto nao encontrado na pagina.")


def ler_variacoes_vtex(soup):
    # Lojas feitas na plataforma VTEX guardam na pagina um objeto
    # chamado __STATE__, com os dados de cada variacao (SKU): nome completo, medida, EAN...
    # Ele NAO e padrao schema.org (so existe em lojas VTEX), entao usamos apenas como
    # complemento do JSON-LD: se nao existir, seguimos sem ele.
    marcador = "__STATE__ ="

    for tag_script in soup.find_all("script"):
        texto_script = tag_script.string or ""

        if marcador not in texto_script:
            continue

        # O script tem o formato:  __STATE__ = {...json...}
        # Pegamos o texto logo depois do "=".
        inicio_json = texto_script.index(marcador) + len(marcador)

        try:
            # raw_decode le um objeto JSON do comeco do texto e ignora o que vier depois.
            estado, _ = json.JSONDecoder().raw_decode(texto_script[inicio_json:].lstrip())
        except json.JSONDecodeError:
            return {}

        # Cada variacao aparece como um dicionario com a chave "itemId" (o SKU).
        # Montamos um dicionario SKU -> dados da variacao.
        # Tiramos os zeros a esquerda da chave, pelo mesmo motivo da funcao mesmo_sku.
        variacoes = {}

        for valor in estado.values():
            if isinstance(valor, dict) and "itemId" in valor:
                variacoes[str(valor["itemId"]).lstrip("0")] = valor

        return variacoes

    return {}


def listar_ofertas(json_produto):
    # Em "offers" a loja informa preco e disponibilidade. Pode vir de tres jeitos:
    #   - uma oferta so:        {"@type": "Offer", "price": 26.9, ...}
    #   - uma lista de ofertas: [{...}, {...}]
    #   - um "AggregateOffer", que agrupa varias ofertas dentro de outro "offers"
    #     (comum em lojas VTEX: uma oferta para cada variacao/SKU do produto).
    ofertas = json_produto.get("offers")

    if isinstance(ofertas, dict) and ofertas.get("@type") == "AggregateOffer":
        ofertas = ofertas.get("offers", [])

    if isinstance(ofertas, dict):
        ofertas = [ofertas]

    if not ofertas:
        raise ValueError("Nenhuma oferta encontrada no JSON-LD do produto.")

    return ofertas


def descobrir_sku(produto):
    # 1o: usamos o SKU preenchido na coluna "sku" do produtos.csv (se existir).
    sku = (produto.get("sku") or "").strip()

    if sku:
        return sku

    # 2o: se o link tiver "?skuId=...", pegamos o SKU do proprio link.
    # urlparse separa as partes da URL e parse_qs transforma "skuId=123" em {"skuId": ["123"]}.
    parametros_url = parse_qs(urlparse(produto["url"]).query)

    if "skuId" in parametros_url:
        return parametros_url["skuId"][0]

    # Nenhum SKU informado.
    return ""


def mesmo_sku(sku_a, sku_b):
    # Comparamos ignorando zeros a esquerda: "03000301" e "3000301" sao o mesmo SKU.
    return str(sku_a).lstrip("0") == str(sku_b).lstrip("0")


def escolher_oferta(ofertas, sku):
    # Com SKU informado, procuramos exatamente a oferta desse SKU.
    if sku:
        for oferta in ofertas:
            if mesmo_sku(oferta.get("sku", ""), sku):
                return oferta

        raise ValueError(f"SKU {sku} nao encontrado entre as ofertas da pagina.")

    # Sem SKU e com uma oferta so, nao ha duvida.
    if len(ofertas) == 1:
        return ofertas[0]

    # Varias ofertas e nenhum SKU informado: preferimos registrar erro a adivinhar o preco.
    skus = ", ".join(str(oferta.get("sku", "?")) for oferta in ofertas)
    raise ValueError(
        f"SKU ambiguo: a pagina tem {len(ofertas)} ofertas (SKUs {skus}). "
        "Preencha a coluna sku no produtos.csv."
    )


def ler_gtin(dados):
    # O schema.org guarda o codigo de barras (EAN) em campos "gtin". Existem variacoes
    # conforme o tamanho do codigo: gtin13 (EAN-13, o mais comum no Brasil), gtin14,
    # gtin12, gtin8 ou so "gtin". Devolvemos o primeiro que estiver preenchido.
    for campo in ("gtin13", "gtin", "gtin14", "gtin12", "gtin8"):
        valor = str(dados.get(campo) or "").strip()

        if valor:
            return valor

    return ""


def ean_valido(codigo):
    # Todo codigo de barras (GTIN/EAN) tem 8, 12, 13 ou 14 digitos, e o ultimo e um
    # "digito verificador", calculado a partir dos outros. Conferir esse digito separa um
    # EAN de verdade de outros numeros que as lojas as vezes colocam no campo (ex.: o
    # codigo interno do SKU).
    if not codigo.isdigit() or len(codigo) not in (8, 12, 13, 14):
        return False

    digitos = [int(digito) for digito in codigo]
    corpo = digitos[:-1]

    # Regra do GTIN: da direita para a esquerda, multiplica os digitos por 3, 1, 3, 1...
    # e soma. O verificador e o que falta para a soma chegar no proximo multiplo de 10.
    soma = sum(
        digito * (3 if posicao % 2 == 0 else 1)
        for posicao, digito in enumerate(reversed(corpo))
    )
    return (10 - soma % 10) % 10 == digitos[-1]


def descobrir_ean(oferta, json_produto, variacao):
    # EAN = codigo de barras do produto. Serve para casar o mesmo produto entre lojas.
    # Procuramos nesta ordem, do mais especifico (a variacao escolhida) para o mais geral:
    #   1o: gtin da oferta escolhida no JSON-LD (cada variacao pode ter o seu);
    #   2o: EAN dos dados VTEX da variacao escolhida;
    #   3o: gtin do produto "pai" no JSON-LD.
    # O gtin do produto fica por ultimo porque vale para a pagina toda, e nao para a
    # variacao: numa loja VTEX ele vinha preenchido com o codigo do SKU padrao, e todas
    # as medidas da telha ficavam com o mesmo "EAN" errado.
    # So aceitamos codigos com digito verificador correto. Se nenhum servir, fica vazio.
    candidatos = [ler_gtin(oferta), str(variacao.get("ean") or "").strip(), ler_gtin(json_produto)]

    for codigo in candidatos:
        if ean_valido(codigo):
            return codigo

    return ""


def formatar_preco(preco_numero):
    # Exemplo: 87.9 vira "R$87,90" (formato brasileiro, para exibir no relatorio).
    return f"R${preco_numero:.2f}".replace(".", ",")


def extrair_dados_produto(html, produto):
    url = produto["url"]

    # Transformamos o texto HTML em um objeto que o Python consegue pesquisar melhor.
    soup = BeautifulSoup(html, "html.parser")

    # Lemos os dados estruturados (JSON-LD) e escolhemos a oferta do SKU certo.
    json_produto = ler_json_ld_produto(soup)
    ofertas = listar_ofertas(json_produto)
    oferta = escolher_oferta(ofertas, descobrir_sku(produto))

    # O "name" do JSON-LD e o nome do produto "pai", sem a medida da variacao
    # (ex.: "Telha Fibrocimento Ondulada 6mm").
    # Se a pagina tiver os dados VTEX, usamos o nome completo da variacao escolhida
    # (ex.: "Telha Fibrocimento Ondulada 6mm 2,13 x 1,10m").
    variacoes = ler_variacoes_vtex(soup)
    variacao = variacoes.get(str(oferta.get("sku", "")).lstrip("0"), {})

    titulo = (variacao.get("nameComplete") or json_produto.get("name") or "").strip()

    if titulo == "":
        raise ValueError("Nome do produto nao encontrado no JSON-LD.")

    # A disponibilidade vem como link do schema.org, por exemplo "http://schema.org/InStock".
    # rsplit("/", 1) corta no ultimo "/" e [-1] pega o final: "InStock".
    disponibilidade = str(oferta.get("availability") or "").rsplit("/", 1)[-1]

    # O preco pode vir como numero (26.9) ou como texto ("26.90"); float() aceita os dois.
    preco = oferta.get("price")
    preco_numero = float(preco) if preco not in (None, "") else None

    # Registramos a data e hora em que o nosso programa viu este produto.
    data_coleta = agora()

    # Um dicionario guarda os dados em pares de chave e valor.
    dados_produto = {
        "produto_id": produto["produto_id"],
        "concorrente": produto["concorrente"],
        "produto_nome": titulo,
        "ean": descobrir_ean(oferta, json_produto, variacao),
        "preco_texto": "",
        "preco_numero": "",
        "status_produto": "",
        "mensagem": "",
        "url": url,
        "data_coleta": data_coleta,
    }

    if disponibilidade != DISPONIVEL_SCHEMA:
        # Produto sem estoque. A loja pode ate informar um preco, mas ninguem consegue
        # comprar por ele. Por isso NAO salvamos esse preco nas colunas de preco
        # (para nao misturar com precos reais nas comparacoes); ele fica so na mensagem.
        dados_produto["status_produto"] = "indisponivel"
        dados_produto["mensagem"] = disponibilidade or "Disponibilidade nao informada"

        if preco_numero is not None:
            dados_produto["mensagem"] += f" (preco anunciado: {formatar_preco(preco_numero)})"

        return dados_produto

    # Produto em estoque precisa ter um preco valido.
    if preco_numero is None:
        raise ValueError("Preco nao encontrado na oferta do JSON-LD.")

    if preco_numero <= 0:
        raise ValueError(f"Preco invalido na oferta do JSON-LD: {preco}")

    dados_produto["status_produto"] = "disponivel"
    dados_produto["preco_texto"] = formatar_preco(preco_numero)
    dados_produto["preco_numero"] = preco_numero

    return dados_produto


def calcular_variacao(preco_anterior, preco_novo):
    # Variacao percentual em forma decimal. Exemplos:
    #   de 100 para 150 -> 0.5  (subiu 50%)
    #   de 100 para 40  -> -0.6 (caiu 60%)
    return (preco_novo - preco_anterior) / preco_anterior


def validar_preco(preco_anterior, preco_novo, preco_ultimo_alerta):
    # Decide se um preco novo pode ser salvo no historico.
    # Devolve True (pode salvar) ou False (vira alerta).

    # Primeira coleta do produto: nao ha com o que comparar.
    if preco_anterior is None:
        return True

    # abs() tira o sinal: tanto subir quanto cair demais contam como variacao absurda.
    if abs(calcular_variacao(preco_anterior, preco_novo)) <= LIMITE_VARIACAO:
        return True

    # Variacao grande, mas o ultimo alerta deste produto foi exatamente este preco:
    # o site mostrou o mesmo valor de novo, entao consideramos que o preco e real.
    # Sem essa regra, um aumento real acima do limite ficaria bloqueado para sempre.
    # (Na coleta diaria, o "ultimo alerta" normalmente e o da coleta anterior.)
    if preco_ultimo_alerta == preco_novo:
        return True

    return False


def criar_alerta(produto, preco_anterior, preco_novo):
    return {
        "produto_id": produto["produto_id"],
        "concorrente": produto["concorrente"],
        "url": produto["url"],
        "preco_anterior": preco_anterior,
        "preco_novo": preco_novo,
        # round(..., 1) arredonda para 1 casa decimal. Ex.: 0.61234 -> 61.2 (%).
        "variacao_percentual": round(calcular_variacao(preco_anterior, preco_novo) * 100, 1),
        "data_alerta": agora(),
    }


def criar_erro(produto, tipo_erro, mensagem):
    return {
        "produto_id": produto["produto_id"],
        "concorrente": produto["concorrente"],
        "url": produto["url"],
        "tipo_erro": tipo_erro,
        "mensagem": mensagem,
        "data_erro": agora(),
    }


def carregar_robots(url_produto):
    # O robots.txt fica sempre na raiz do site: https://site.com.br/robots.txt
    # Montamos esse endereco a partir da URL do produto.
    partes_url = urlparse(url_produto)
    url_robots = f"{partes_url.scheme}://{partes_url.netloc}/robots.txt"

    # RobotFileParser (biblioteca padrao do Python) entende as regras do robots.txt.
    regras = RobotFileParser(url_robots)

    # Seguimos o padrao oficial do robots.txt (RFC 9309):
    #   - site sem robots.txt (erro 4xx): nao ha regras, tudo permitido;
    #   - servidor com problema (erro 5xx) ou sem conexao: nao sabemos as regras,
    #     entao por seguranca consideramos tudo bloqueado.
    # Com uma excecao nossa, mais cuidadosa que a RFC: 401 (nao autorizado) e
    # 403 (proibido) indicam que o site esta barrando robos (ex.: tela de CAPTCHA).
    # Nesses casos tambem consideramos tudo bloqueado.
    try:
        resposta = requests.get(url_robots, timeout=8)
    except requests.RequestException:
        regras.disallow_all = True
        return regras

    if resposta.status_code in (401, 403):
        regras.disallow_all = True
    elif 400 <= resposta.status_code < 500:
        regras.allow_all = True
    elif resposta.status_code >= 500:
        regras.disallow_all = True
    else:
        # splitlines() quebra o texto em uma lista de linhas, que e o que o parse() espera.
        regras.parse(resposta.text.splitlines())

    return regras


def permitido_pelo_robots(url_produto, cache_robots):
    # cache_robots guarda as regras ja baixadas de cada site (dominio -> regras),
    # para baixar o robots.txt uma vez so por coleta, e nao uma vez por produto.
    dominio = urlparse(url_produto).netloc

    if dominio not in cache_robots:
        cache_robots[dominio] = carregar_robots(url_produto)

    return cache_robots[dominio].can_fetch(AGENTE_ROBOTS, url_produto)


def pagina_completa(html):
    # As vezes o site responde com status 200, mas manda a pagina pela metade:
    # sem o bloco JSON-LD, que e de onde tiramos o preco.
    return "application/ld+json" in html


def baixar_pagina(url):
    resposta = requests.get(url, timeout=8)

    # Pagina incompleta costuma ser uma falha passageira do site.
    # Esperamos alguns segundos e tentamos UMA vez mais (sem insistir, para nao
    # sobrecarregar o site). Se vier incompleta de novo, a extracao registra o erro.
    if resposta.status_code == 200 and not pagina_completa(resposta.text):
        sleep(ESPERA_NOVA_TENTATIVA)
        resposta = requests.get(url, timeout=8)

    return resposta


def coletar_produto(conexao, produto, ultimos_precos, ultimos_alertas, cache_robots):
    # Coleta um produto e grava o resultado no banco.
    # Devolve "coletado", "alerta" ou "erro", para o resumo final.

    # Antes de acessar a pagina, conferimos se o robots.txt do site permite.
    # Se nao permitir, a pagina NAO e acessada: so registramos o motivo.
    if not permitido_pelo_robots(produto["url"], cache_robots):
        banco.salvar_erro(conexao, criar_erro(
            produto,
            "robots",
            "Pagina bloqueada pelo robots.txt do site (nao foi acessada).",
        ))
        return "erro"

    try:
        resposta = baixar_pagina(produto["url"])

        if resposta.status_code != 200:
            banco.salvar_erro(conexao, criar_erro(
                produto,
                "status_http",
                f"Status HTTP inesperado: {resposta.status_code}",
            ))
            return "erro"

        dados_produto = extrair_dados_produto(resposta.text, produto)

    except requests.RequestException as erro:
        banco.salvar_erro(conexao, criar_erro(produto, "requisicao", str(erro)))
        return "erro"

    except ValueError as erro:
        banco.salvar_erro(conexao, criar_erro(produto, "extracao", str(erro)))
        return "erro"

    except Exception as erro:
        banco.salvar_erro(conexao, criar_erro(produto, "erro_inesperado", str(erro)))
        return "erro"

    produto_id = produto["produto_id"]
    preco_novo = dados_produto["preco_numero"]

    # So validamos quando ha preco (produto indisponivel nao tem preco para comparar).
    preco_valido = preco_novo == "" or validar_preco(
        ultimos_precos.get(produto_id),
        preco_novo,
        ultimos_alertas.get(produto_id),
    )

    if not preco_valido:
        # Variacao absurda: registramos o alerta e NAO salvamos no historico.
        banco.salvar_alerta(conexao, criar_alerta(produto, ultimos_precos[produto_id], preco_novo))
        return "alerta"

    banco.salvar_coleta(conexao, dados_produto)

    if preco_novo != "":
        ultimos_precos[produto_id] = preco_novo

    return "coletado"


# A funcao main junta o passo a passo da coleta.
# Ela so roda quando o arquivo e executado diretamente (ver o "if" no final do arquivo).
def main():
    # O cadastro real (produtos.csv) nao vai para o GitHub, porque mostra quais produtos
    # sao monitorados. No repositorio fica so o produtos.exemplo.csv, como modelo.
    if not ARQUIVO_PRODUTOS.exists():
        print(f"Cadastro de produtos nao encontrado: {ARQUIVO_PRODUTOS}")
        print("Copie dados/produtos.exemplo.csv para dados/produtos.csv e preencha com os seus produtos.")
        return

    cadastro = ler_cadastro()

    # Os avisos nao interrompem a coleta: so ficam visiveis no terminal/log para corrigir.
    for aviso in validar_cadastro(cadastro):
        print("AVISO no cadastro:", aviso)

    # A excecao: sem as colunas obrigatorias nao da para coletar nada (o programa quebraria
    # ao procurar a url ou o produto_id). Nesse caso paramos antes de comecar.
    if colunas_faltando(cadastro):
        print("Coleta cancelada: corrija as colunas do cadastro e rode de novo.")
        return

    produtos = filtrar_ativos(cadastro)
    conexao = banco.conectar(ARQUIVO_BANCO)

    # Contador de resultados para o resumo final: {"coletado": 50, "erro": 3, ...}
    resultados = {"coletado": 0, "erro": 0, "alerta": 0}

    # try/finally garante que o banco sera fechado mesmo se der erro no meio.
    try:
        # Registramos o inicio desta coleta (o relatorio usa isso para saber
        # quais erros aconteceram na coleta mais recente).
        execucao_id = banco.iniciar_execucao(conexao, agora())

        # Lemos do banco uma vez so, no comeco, os dados usados na validacao.
        ultimos_precos = banco.buscar_ultimos_precos(conexao)
        ultimos_alertas = banco.buscar_ultimos_alertas(conexao)
        cache_robots = {}

        for produto in produtos:
            resultado = coletar_produto(conexao, produto, ultimos_precos, ultimos_alertas, cache_robots)
            resultados[resultado] += 1

            # Fazemos uma pausa para nao enviar muitas requisicoes seguidas ao site.
            sleep(1)

        # So chega aqui se a coleta terminou; se quebrar no meio, o "fim" fica vazio no banco.
        banco.finalizar_execucao(conexao, execucao_id, agora(), len(produtos), resultados)
    finally:
        conexao.close()

    print("Resumo da coleta")
    print("Produtos ativos:", len(produtos))
    print("Produtos atualizados:", resultados["coletado"])
    print("Produtos com erro:", resultados["erro"])
    print("Alertas de variacao de preco:", resultados["alerta"])


# Quando rodamos "python src/main.py", o Python coloca o valor "__main__" em __name__,
# entao a coleta comeca.
# Quando outro arquivo faz "import main", __name__ vale "main" e a coleta NAO roda.
# Assim conseguimos testar as funcoes sem acessar o site.
if __name__ == "__main__":
    main()
