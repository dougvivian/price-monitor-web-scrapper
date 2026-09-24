# Este programa sera usado para monitorar precos de concorrentes.
import csv
import json
from datetime import datetime
from pathlib import Path
from time import sleep
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup


PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_PRODUTOS = PASTA_PROJETO / "dados" / "produtos.csv"
ARQUIVO_COLETAS = PASTA_PROJETO / "dados" / "coletas.csv"
ARQUIVO_ERROS = PASTA_PROJETO / "dados" / "erros.csv"

# Valor de disponibilidade padronizado pelo schema.org que indica produto em estoque.
# Qualquer outro valor (OutOfStock, Discontinued, PreOrder...) tratamos como indisponivel.
DISPONIVEL_SCHEMA = "InStock"


def ler_produtos():
    produtos = []

    # Lemos o cadastro de produtos que queremos monitorar.
    with open(ARQUIVO_PRODUTOS, "r", newline="", encoding="utf-8") as arquivo_csv:
        leitor_csv = csv.DictReader(arquivo_csv, delimiter=";")

        for produto in leitor_csv:
            # Por enquanto, coletamos apenas produtos marcados como ativos.
            if produto["ativo"].lower() == "sim":
                produtos.append(produto)

    return produtos


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
    # Lojas feitas na plataforma VTEX (caso da Loja A) guardam na pagina um objeto
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
    #     (e o caso da Loja A: uma oferta para cada variacao/SKU do produto).
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
    # (ex.: "Telha Fibrocimento Ondulada 6mm Cinza Marca").
    # Se a pagina tiver os dados VTEX, usamos o nome completo da variacao escolhida
    # (ex.: "Telha Fibrocimento Ondulada 6mm Cinza Marca 2,13 x 1,10m").
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
    data_coleta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Um dicionario guarda os dados em pares de chave e valor.
    dados_produto = {
        "produto_id": produto["produto_id"],
        "concorrente": produto["concorrente"],
        "produto_nome": titulo,
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


def salvar_linhas_csv(caminho_arquivo, campos, linhas):
    if len(linhas) == 0:
        return

    arquivo_vazio = not caminho_arquivo.exists() or caminho_arquivo.stat().st_size == 0

    # Usamos "a" para acrescentar novas linhas no historico, sem apagar as anteriores.
    with open(caminho_arquivo, "a", newline="", encoding="utf-8") as arquivo_csv:
        escritor_csv = csv.DictWriter(arquivo_csv, fieldnames=campos, delimiter=";")

        if arquivo_vazio:
            escritor_csv.writeheader()

        escritor_csv.writerows(linhas)


def salvar_coletas(dados_coletados):
    campos = [
        "produto_id",
        "concorrente",
        "produto_nome",
        "preco_texto",
        "preco_numero",
        "status_produto",
        "mensagem",
        "url",
        "data_coleta",
    ]

    salvar_linhas_csv(ARQUIVO_COLETAS, campos, dados_coletados)


def salvar_erros(erros_coleta):
    campos = [
        "produto_id",
        "concorrente",
        "url",
        "tipo_erro",
        "mensagem",
        "data_erro",
    ]

    salvar_linhas_csv(ARQUIVO_ERROS, campos, erros_coleta)


def criar_erro(produto, tipo_erro, mensagem):
    return {
        "produto_id": produto["produto_id"],
        "concorrente": produto["concorrente"],
        "url": produto["url"],
        "tipo_erro": tipo_erro,
        "mensagem": mensagem,
        "data_erro": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


# A funcao main junta o passo a passo da coleta.
# Antes esse codigo ficava solto no arquivo e rodava sempre que o arquivo era aberto,
# inclusive quando outro arquivo (como um teste) so queria importar uma funcao daqui.
def main():
    produtos = ler_produtos()
    dados_coletados = []
    erros_coleta = []

    for produto in produtos:
        try:
            resposta = requests.get(produto["url"], timeout=8)

            if resposta.status_code != 200:
                erro_coleta = criar_erro(
                    produto,
                    "status_http",
                    f"Status HTTP inesperado: {resposta.status_code}",
                )
                erros_coleta.append(erro_coleta)
                salvar_erros([erro_coleta])
                sleep(1)
                continue

            dados_produto = extrair_dados_produto(resposta.text, produto)
            dados_coletados.append(dados_produto)
            salvar_coletas([dados_produto])

        except requests.RequestException as erro:
            erro_coleta = criar_erro(produto, "requisicao", str(erro))
            erros_coleta.append(erro_coleta)
            salvar_erros([erro_coleta])

        except ValueError as erro:
            erro_coleta = criar_erro(produto, "extracao", str(erro))
            erros_coleta.append(erro_coleta)
            salvar_erros([erro_coleta])

        except Exception as erro:
            erro_coleta = criar_erro(produto, "erro_inesperado", str(erro))
            erros_coleta.append(erro_coleta)
            salvar_erros([erro_coleta])

        # Fazemos uma pausa para nao enviar muitas requisicoes seguidas ao site.
        sleep(1)

    print("Resumo da coleta")
    print("Produtos ativos:", len(produtos))
    print("Produtos atualizados:", len(dados_coletados))
    print("Produtos com erro:", len(erros_coleta))


# Quando rodamos "python src/main.py", o Python coloca o valor "__main__" em __name__,
# entao a coleta comeca.
# Quando outro arquivo faz "import main", __name__ vale "main" e a coleta NAO roda.
# Assim conseguimos testar as funcoes sem acessar o site.
if __name__ == "__main__":
    main()
