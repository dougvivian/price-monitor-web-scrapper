# Testes da funcao extrair_dados_produto.
# Nenhum teste acessa o site: usamos paginas HTML salvas na pasta tests/paginas
# (baixadas da Loja A em 2026-09-24) ou pequenos trechos de HTML escritos aqui mesmo.
# Assim os testes sao rapidos, funcionam sem internet e sempre dao o mesmo resultado.
#
# Para rodar:  python -m pytest
from pathlib import Path

import pytest

from main import extrair_dados_produto


PASTA_PAGINAS = Path(__file__).parent / "paginas"


def ler_pagina(nome_arquivo):
    # Le uma pagina HTML salva e devolve o texto dela.
    caminho = PASTA_PAGINAS / nome_arquivo
    return caminho.read_text(encoding="utf-8")


def criar_produto(url="https://exemplo.com/produto/p"):
    # Monta um produto no mesmo formato de uma linha do dados/produtos.csv.
    return {
        "produto_id": "TESTE-001",
        "concorrente": "Loja A",
        "url": url,
    }


# ---------------------------------------------------------------------------
# Testes com paginas reais salvas
# ---------------------------------------------------------------------------

def test_produto_disponivel_retorna_preco_e_status():
    html = ler_pagina("produto_disponivel.html")

    dados = extrair_dados_produto(html, criar_produto())

    assert dados["status_produto"] == "disponivel"
    assert dados["preco_texto"] == "R$26,90/un"
    assert dados["preco_numero"] == 26.9
    assert dados["produto_nome"].startswith("Telha de Fibrocimento Ondulada Marca Marca")


def test_produto_indisponivel_retorna_status_e_mensagem_sem_preco():
    html = ler_pagina("produto_indisponivel.html")

    dados = extrair_dados_produto(html, criar_produto())

    assert dados["status_produto"] == "indisponivel"
    assert dados["preco_texto"] == ""
    assert dados["preco_numero"] == ""
    assert "não está disponível" in dados["mensagem"]


def test_dados_de_identificacao_vem_do_cadastro():
    # produto_id, concorrente e url devem vir do cadastro (produtos.csv), nao da pagina.
    html = ler_pagina("produto_disponivel.html")
    produto = criar_produto(url="https://www.loja-exemplo.com.br/qualquer/p")

    dados = extrair_dados_produto(html, produto)

    assert dados["produto_id"] == "TESTE-001"
    assert dados["concorrente"] == "Loja A"
    assert dados["url"] == "https://www.loja-exemplo.com.br/qualquer/p"


# BUG CONHECIDO: esta pagina foi baixada com ?skuId=10000103 (telha de 1,83m).
# O JSON-LD da propria pagina diz que esse SKU custa R$87,90, mas o seletor CSS
# pega o preco da variacao padrao da pagina (SKU 10000101, R$61,90).
# O "xfail" avisa o pytest que ESPERAMOS que este teste falhe por enquanto.
# O "strict=True" faz o pytest reclamar quando o bug for corrigido,
# lembrando de tirar esta marcacao.
@pytest.mark.xfail(strict=True, reason="seletor CSS ignora o skuId da URL; corrigir com JSON-LD")
def test_variacao_usa_preco_do_sku_da_url():
    html = ler_pagina("produto_variacao_sku.html")
    url = "https://www.loja-exemplo.com.br/telha-fibrocimento-ondulada-6mm-cinza-Marca/p?skuId=10000103"

    dados = extrair_dados_produto(html, criar_produto(url=url))

    assert dados["preco_numero"] == 87.9


# ---------------------------------------------------------------------------
# Testes com pequenos trechos de HTML
# Usamos as mesmas classes CSS da Loja A, mas so com o minimo necessario.
# ---------------------------------------------------------------------------

def montar_html(titulo=None, preco=None, aviso_indisponivel=None):
    # Monta um HTML minimo com os elementos que a funcao procura.
    partes = ["<html><body>"]

    if titulo is not None:
        partes.append(f'<h1 class="vtex-store-components-3-x-productNameContainer">{titulo}</h1>')

    if preco is not None:
        partes.append(f'<span class="vtex-product-price-1-x-sellingPrice">{preco}</span>')

    if aviso_indisponivel is not None:
        partes.append(f'<p class="vtex-availability-notify-1-x-title">{aviso_indisponivel}</p>')

    partes.append("</body></html>")
    return "".join(partes)


# O parametrize roda o mesmo teste varias vezes, uma para cada par (texto, numero esperado).
@pytest.mark.parametrize(
    "preco_texto, preco_esperado",
    [
        ("R$61,90/un", 61.9),
        ("R$56,90/m²", 56.9),
        ("R$ 1.234,56", 1234.56),
        ("R$869,90", 869.9),
    ],
)
def test_limpeza_do_preco(preco_texto, preco_esperado):
    html = montar_html(titulo="Produto teste", preco=preco_texto)

    dados = extrair_dados_produto(html, criar_produto())

    assert dados["preco_numero"] == preco_esperado


def test_sem_titulo_gera_erro():
    html = montar_html(preco="R$10,00")

    # pytest.raises confere que a funcao realmente levanta o erro esperado.
    with pytest.raises(ValueError, match="Titulo nao encontrado"):
        extrair_dados_produto(html, criar_produto())


def test_sem_preco_e_sem_aviso_de_indisponivel_gera_erro():
    html = montar_html(titulo="Produto teste")

    with pytest.raises(ValueError, match="Preco nao encontrado"):
        extrair_dados_produto(html, criar_produto())


def test_preco_sem_numeros_gera_erro():
    html = montar_html(titulo="Produto teste", preco="Consulte")

    with pytest.raises(ValueError, match="Preco vazio"):
        extrair_dados_produto(html, criar_produto())
