# Este programa sera usado para monitorar precos de concorrentes.
import csv
import re
from datetime import datetime
from pathlib import Path
from time import sleep

import requests
from bs4 import BeautifulSoup


PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_PRODUTOS = PASTA_PROJETO / "dados" / "produtos.csv"
ARQUIVO_COLETAS = PASTA_PROJETO / "dados" / "coletas.csv"


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


def extrair_dados_produto(html, produto):
    url = produto["url"]

    # Transformamos o texto HTML em um objeto que o Python consegue pesquisar melhor.
    soup = BeautifulSoup(html, "html.parser")

    # Estes seletores vieram do Inspecionar do navegador.
    seletor_preco = ".vtex-product-price-1-x-sellingPrice"
    seletor_titulo = ".vtex-store-components-3-x-productNameContainer"
    seletor_indisponivel = ".vtex-availability-notify-1-x-title"

    # select_one procura o primeiro elemento que combina com o seletor CSS.
    elemento_preco = soup.select_one(seletor_preco)
    elemento_titulo = soup.select_one(seletor_titulo)
    elemento_indisponivel = soup.select_one(seletor_indisponivel)

    if elemento_titulo is None:
        print("Titulo nao encontrado no HTML recebido pelo requests.")
        return None

    # get_text(strip=True) pega somente o texto visivel e remove espacos/quebras das pontas.
    titulo = elemento_titulo.get_text(strip=True)

    # Registramos a data e hora em que o nosso programa viu este produto.
    data_coleta = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if elemento_preco is None:
        if elemento_indisponivel is not None:
            mensagem = elemento_indisponivel.get_text(strip=True)

            return {
                "produto_id": produto["produto_id"],
                "concorrente": produto["concorrente"],
                "produto_nome": titulo,
                "preco_texto": "",
                "preco_numero": "",
                "status_produto": "indisponivel",
                "mensagem": mensagem,
                "url": url,
                "data_coleta": data_coleta,
            }

        print("Preco nao encontrado no HTML recebido pelo requests.")
        return None

    # Aqui pegamos apenas o texto do elemento HTML.
    # Exemplos: "R$61,90/un" ou "R$56,90/m2".
    preco_texto = elemento_preco.get_text(strip=True)

    # Para comparar precos, precisamos transformar o texto em numero.
    # Mantemos apenas digitos, virgula e ponto, depois ajustamos para o float.
    preco_limpo = re.sub(r"[^0-9,.]", "", preco_texto)
    preco_limpo = preco_limpo.replace(".", "").replace(",", ".")

    # Convertemos o texto limpo para float.
    # Exemplo: "61.90" vira 61.9.
    preco_numero = float(preco_limpo)

    # Um dicionario guarda os dados em pares de chave e valor.
    dados_produto = {
        "produto_id": produto["produto_id"],
        "concorrente": produto["concorrente"],
        "produto_nome": titulo,
        "preco_texto": preco_texto,
        "preco_numero": preco_numero,
        "status_produto": "disponivel",
        "mensagem": "",
        "url": url,
        "data_coleta": data_coleta,
    }

    return dados_produto


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

    arquivo_vazio = not ARQUIVO_COLETAS.exists() or ARQUIVO_COLETAS.stat().st_size == 0

    # Usamos "a" para acrescentar novas coletas no historico, sem apagar as anteriores.
    with open(ARQUIVO_COLETAS, "a", newline="", encoding="utf-8") as arquivo_csv:
        escritor_csv = csv.DictWriter(arquivo_csv, fieldnames=campos, delimiter=";")

        if arquivo_vazio:
            escritor_csv.writeheader()

        escritor_csv.writerows(dados_coletados)


produtos = ler_produtos()
dados_coletados = []

# Durante o desenvolvimento, usamos apenas os 5 primeiros produtos ativos.
for produto in produtos[:5]:
    print("Coletando:", produto["produto_id"], produto["url"])

    resposta = requests.get(produto["url"])

    print("Status:", resposta.status_code)

    dados_produto = extrair_dados_produto(resposta.text, produto)

    if dados_produto is not None:
        dados_coletados.append(dados_produto)
        print("Dados coletados:")
        print(dados_produto)

    # Fazemos uma pausa para nao enviar muitas requisicoes seguidas ao site.
    sleep(1)

print("Total de produtos coletados:")
print(len(dados_coletados))

salvar_coletas(dados_coletados)
