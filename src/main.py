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
ARQUIVO_ERROS = PASTA_PROJETO / "dados" / "erros.csv"

SELETORES_POR_CONCORRENTE = {
    "Loja A": {
        "preco": ".vtex-product-price-1-x-sellingPrice",
        "titulo": ".vtex-store-components-3-x-productNameContainer",
        "indisponivel": ".vtex-availability-notify-1-x-title",
    }
}


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


def buscar_seletores(concorrente):
    if concorrente not in SELETORES_POR_CONCORRENTE:
        raise ValueError(f"Concorrente sem seletores cadastrados: {concorrente}")

    return SELETORES_POR_CONCORRENTE[concorrente]


def extrair_dados_produto(html, produto):
    url = produto["url"]
    seletores = buscar_seletores(produto["concorrente"])

    # Transformamos o texto HTML em um objeto que o Python consegue pesquisar melhor.
    soup = BeautifulSoup(html, "html.parser")

    # select_one procura o primeiro elemento que combina com o seletor CSS.
    elemento_preco = soup.select_one(seletores["preco"])
    elemento_titulo = soup.select_one(seletores["titulo"])
    elemento_indisponivel = soup.select_one(seletores["indisponivel"])

    if elemento_titulo is None:
        raise ValueError("Titulo nao encontrado no HTML recebido pelo requests.")

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

        raise ValueError("Preco nao encontrado no HTML recebido pelo requests.")

    # Aqui pegamos apenas o texto do elemento HTML.
    # Exemplos: "R$61,90/un" ou "R$56,90/m2".
    preco_texto = elemento_preco.get_text(strip=True)

    # Para comparar precos, precisamos transformar o texto em numero.
    # Mantemos apenas digitos, virgula e ponto, depois ajustamos para o float.
    preco_limpo = re.sub(r"[^0-9,.]", "", preco_texto)
    preco_limpo = preco_limpo.replace(".", "").replace(",", ".")

    # Convertemos o texto limpo para float.
    # Exemplo: "61.90" vira 61.9.
    if preco_limpo == "":
        raise ValueError(f"Preco vazio apos limpeza: {preco_texto}")

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
