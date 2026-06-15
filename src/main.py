# Este programa sera usado para monitorar precos de concorrentes.

# requests faz a requisicao HTTP para acessar o HTML da pagina.
import requests

# BeautifulSoup ajuda a procurar informacoes dentro do HTML.
from bs4 import BeautifulSoup


def extrair_preco(html):
    # Transformamos o texto HTML em um objeto que o Python consegue pesquisar melhor.
    soup = BeautifulSoup(html, "html.parser")

    # Este seletor veio do Inspecionar do navegador.
    # Ele procura o span que contem o preco de venda do produto.
    seletor_preco = ".vtex-product-price-1-x-sellingPrice"

    # select_one procura o primeiro elemento que combina com o seletor CSS.
    elemento_preco = soup.select_one(seletor_preco)

    if elemento_preco is None:
        print("Preco nao encontrado no HTML recebido pelo requests.")
        return None

    print("Elemento encontrado:")
    print(elemento_preco)

    print("Texto do preco:")
    print(elemento_preco.get_text(strip=True))

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

    return preco_numero


url = "https://www.loja-exemplo.com.br/cimento-comum-cp-iv-32-Marca-todas-as-obras/p"

# Aqui fazemos a requisicao para o site.
# O retorno fica salvo na variavel resposta.
resposta = requests.get(url)

# O status_code mostra se a requisicao deu certo.
# Status 200 significa que o site respondeu com sucesso.
print("Status:", resposta.status_code)

preco_numero = extrair_preco(resposta.text)

if preco_numero is not None:
    print("Preco como numero:")
    print(preco_numero)
