# Este programa sera usado para monitorar precos de concorrentes.

# datetime permite registrar a data e hora em que coletamos o preco.
from datetime import datetime

# requests faz a requisicao HTTP para acessar o HTML da pagina.
import requests

# BeautifulSoup ajuda a procurar informacoes dentro do HTML.
from bs4 import BeautifulSoup


def extrair_dados_produto(html, url):
    # Transformamos o texto HTML em um objeto que o Python consegue pesquisar melhor.
    soup = BeautifulSoup(html, "html.parser")

    # Este seletor veio do Inspecionar do navegador.
    # Ele procura o span que contem o preco de venda do produto.
    seletor_preco = ".vtex-product-price-1-x-sellingPrice"
    seletor_titulo = ".vtex-store-components-3-x-productNameContainer"

    # select_one procura o primeiro elemento que combina com o seletor CSS.
    elemento_preco = soup.select_one(seletor_preco)
    elemento_titulo = soup.select_one(seletor_titulo)

    if elemento_preco is None:
        print("Preco nao encontrado no HTML recebido pelo requests.")
        return None

    if elemento_titulo is None:
        print("Titulo nao encontrado no HTML recebido pelo requests.")
        return None

    # get_text(strip=True) pega somente o texto visivel e remove espacos/quebras das pontas.
    titulo = elemento_titulo.get_text(strip=True)

    # Aqui pegamos apenas o texto do elemento HTML.
    # No site testado, o texto vem assim: "R$61,90/un".
    preco_texto = elemento_preco.get_text(strip=True)

    # Para comparar precos, precisamos transformar o texto em numero.
    # Por isso removemos "R$", removemos a unidade "/un",
    # trocamos a virgula decimal brasileira por ponto
    # e tiramos espacos extras com strip().
    preco_limpo = (
        preco_texto
        .replace("R$", "")
        .replace("/un", "")
        .replace(".", "")
        .replace(",", ".")
        .strip()
    )

    # Convertemos o texto limpo para float.
    # Exemplo: "61.90" vira 61.9.
    preco_numero = float(preco_limpo)

    # Registramos a data e hora em que o nosso programa viu este preco.
    data_coleta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Um dicionario guarda os dados em pares de chave e valor.
    dados_produto = {
        "produto_nome": titulo,
        "preco_texto": preco_texto,
        "preco_numero": preco_numero,
        "url": url,
        "data_coleta": data_coleta,
    }

    return dados_produto


urls = [
    "https://www.loja-exemplo.com.br/telha-fibrocimento-ondulada-6mm-cinza-Marca/p?skuId=10000101",
    "https://www.loja-exemplo.com.br/telha-fibrocimento-ondulada-6mm-cinza-Marca/p?skuId=00000000",
    "https://www.loja-exemplo.com.br/telha-fibrocimento-ondulada-6mm-cinza-Marca/p?skuId=10000103",
    "https://www.loja-exemplo.com.br/telha-fibrocimento-ondulada-6mm-cinza-Marca/p?skuId=00000000",
    "https://www.loja-exemplo.com.br/telha-fibrocimento-ondulada-6mm-cinza-Marca/p?skuId=00000000",
    "https://www.loja-exemplo.com.br/telha-fibrocimento-ondulada-6mm-cinza-Marca/p?skuId=00000000",
    "https://www.loja-exemplo.com.br/telha-de-fibrocimento-ondulada-Marca-5mm/p?skuId=00000000",
    "https://www.loja-exemplo.com.br/telha-ondulada-fibrocimento-6mm-Marca/p",
    "https://www.loja-exemplo.com.br/telha-ondulada-de-fibrocimento-244x50-6cm-4mm-Marca-cinza-Marca-20000202/p",
    "https://www.loja-exemplo.com.br/placa-cimenticia-Marca-cinza-6mm-1-20-x-3m/p",
    "https://www.loja-exemplo.com.br/telha-estrutural-Canalete-90-820m-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/telha-ondulada-de-fibrocimento-244x110cm-8mm-cinza-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/telha-cumeeira-normal-110-6mm-fibrocimento-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/telha-fibrocimento-canalete-8mm-Marca/p?skuId=00000000",
    "https://www.loja-exemplo.com.br/telha-fibrocimento-canalete-8mm-Marca/p?skuId=00000000",
    "https://www.loja-exemplo.com.br/telha-de-fibrocimento-Marca-6mm-300x106m-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/telha-fibrocimento-Canalete-460x90cm-8mm-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/telha-ondulada-br-crfs-8mm-3-66-x-1-10m-Marca-00000000-unitario-00000000-1/p",
    "https://www.loja-exemplo.com.br/telha-estrutural-Canalete-90-Marca/p",
    "https://www.loja-exemplo.com.br/placa-Marca-rb-plus-10mmx120x300m-Marca-00000000/p",
    "https://www.loja-exemplo.com.br/placa-cimenticia-6mmx120x240m-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/telha-fibrocimento-Canalete-600x90cm-8mm-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/telha-estrutural-Canalete-90-920m-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/telha-Canalete-90-crfs-8mm-7-40m-Marca-00000000-unitario-00000000-1/p",
    "https://www.loja-exemplo.com.br/telha-ondulada-de-fibrocimento-330x106-4cm-6mm-Marca-cinza-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/telha-Canalete-90-crfs-8mm-3-00m-Marca-00000000-unitario-00000000-1/p",
    "https://www.loja-exemplo.com.br/telha-de-fibrocimento-Marca-8mm-370x106m-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/telha-claraboia-Marca-1-10x1-83m-6mm-Marca--00000000-1/p",
    "https://www.loja-exemplo.com.br/telha-ondulada-de-fibrocimento-370x60cm-8mm-onda-50-cinza-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/telha-fibrocimento-onda50-410x60cm-8mm-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/barra-de-ferro-dobrado-ca50-12-00mm-12-metros-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/barra-de-ferro-dobrado-ca50-10-00mm-12-metros-Marca-00000000/p",
    "https://www.loja-exemplo.com.br/barra-de-ferro-dobrado-ca60-4-20mm-12-metros-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/barra-ferro-dobr-ca60-5-0-12m-Marca-00000000/p",
    "https://www.loja-exemplo.com.br/barra-ferro-dobr-ca50-6-3-0-12m-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/barra-ferro-dobr-ca50-16-0-12m-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/malha-pop-leve-Marca-20x20-3-4mm-x-2m-x-3m/p",
    "https://www.loja-exemplo.com.br/malha-pop-reforcada-Marca-15x15-4-2mm-x-2m-x-3m/p",
    "https://www.loja-exemplo.com.br/malha-pop-pesada-Marca-10x10-4-2mm-x-3m/p",
    "https://www.loja-exemplo.com.br/cimento-comum-cpiv-50kg-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/cimento-cp-iv-32-saco-50kg-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/tinta-acrilica-toque-fosco-completo-3-6l-algodao-eg-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/tinta-Marca-semibrilho-branco-Marca/p",
    "https://www.loja-exemplo.com.br/tinta-Marca-semibrilho-branco-Marca/p?skuId=00000000",
    "https://www.loja-exemplo.com.br/tinta-acrilica-toque-fosco-completo-3-6l-branco-neve-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/tinta-acrilica-premium-toque-seda-18l-branco-neve-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/tinta-acrilica-premium-fosco-sempre-limpo-18-l-branco-neve-Marca-00000000-1/p",
    "https://www.loja-exemplo.com.br/tinta-acrilica-premium-toque-fosco-lata-18l-branco-neve-Marca--00000000-1/p",
    "https://www.loja-exemplo.com.br/porcelanato-acetinado-retificado-imigrantes-Marca/p",
    "https://www.loja-exemplo.com.br/porcelanato-polido-retificado-nero-reale-Marca/p",
    "https://www.loja-exemplo.com.br/porcelanato-acetinado-retificado-urban-cinza-Marca/p",
    "https://www.loja-exemplo.com.br/porcelanato-acetinado-retificado-york-sgr-cinza-Marca/p",
    "https://www.loja-exemplo.com.br/porcelanato-acetinado-bold-munari-grafiti-Marca/p",
]

dados_coletados = []

for url in urls:
    print("Coletando:", url)

    # Aqui fazemos a requisicao para o site.
    # O retorno fica salvo na variavel resposta.
    resposta = requests.get(url)

    # O status_code mostra se a requisicao deu certo.
    # Status 200 significa que o site respondeu com sucesso.
    print("Status:", resposta.status_code)

    dados_produto = extrair_dados_produto(resposta.text, url)

    if dados_produto is not None:
        dados_coletados.append(dados_produto)
        print("Dados coletados:")
        print(dados_produto)

print("Total de produtos coletados:")
print(len(dados_coletados))
