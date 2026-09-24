# Testes da funcao extrair_dados_produto.
# Nenhum teste acessa o site: usamos paginas HTML salvas na pasta tests/paginas
# (paginas sinteticas que imitam uma loja na plataforma VTEX) ou pequenos trechos de HTML escritos aqui mesmo.
# Assim os testes sao rapidos, funcionam sem internet e sempre dao o mesmo resultado.
#
# Para rodar:  python -m pytest
import json
from pathlib import Path

import pytest

from main import extrair_dados_produto


PASTA_PAGINAS = Path(__file__).parent / "paginas"


def ler_pagina(nome_arquivo):
    # Le uma pagina HTML salva e devolve o texto dela.
    caminho = PASTA_PAGINAS / nome_arquivo
    return caminho.read_text(encoding="utf-8")


def criar_produto(url="https://exemplo.com/produto/p", sku=""):
    # Monta um produto no mesmo formato de uma linha do dados/produtos.csv.
    return {
        "produto_id": "TESTE-001",
        "concorrente": "Loja A",
        "url": url,
        "sku": sku,
    }


# ---------------------------------------------------------------------------
# Testes com paginas reais salvas
# ---------------------------------------------------------------------------

def test_variacao_usa_preco_do_sku_da_url():
    # Pagina acessada com ?skuId=10000103. O JSON-LD tem 6 ofertas (uma por tamanho);
    # a do SKU 10000103 custa R$87,90. O metodo antigo (seletor CSS) devolvia R$61,90,
    # que era o preco de outra variacao.
    html = ler_pagina("produto_variacao_sku.html")
    url = "https://www.loja-exemplo.com.br/telha-fibrocimento-ondulada-6mm/p?skuId=10000103"

    dados = extrair_dados_produto(html, criar_produto(url=url))

    assert dados["status_produto"] == "disponivel"
    assert dados["preco_numero"] == 87.9
    assert dados["preco_texto"] == "R$87,90"
    # O nome vem da variacao (dados VTEX), com a medida no final.
    assert dados["produto_nome"] == "Telha Fibrocimento Ondulada 6mm 2,13 x 1,10m"


def test_sku_da_coluna_tem_prioridade_sobre_o_link():
    # Se a coluna sku estiver preenchida, ela vale mais que o ?skuId= do link.
    html = ler_pagina("produto_variacao_sku.html")
    url = "https://www.loja-exemplo.com.br/telha-fibrocimento-ondulada-6mm/p?skuId=10000103"

    dados = extrair_dados_produto(html, criar_produto(url=url, sku="10000101"))

    assert dados["preco_numero"] == 61.9


def test_varias_ofertas_sem_sku_gera_erro_de_sku_ambiguo():
    # Esta pagina tem 2 ofertas (R$26,90 e R$25,90) e o link nao tem ?skuId=.
    # Em vez de adivinhar, a funcao deve avisar que falta informar o SKU.
    html = ler_pagina("produto_disponivel.html")

    with pytest.raises(ValueError, match="SKU ambiguo"):
        extrair_dados_produto(html, criar_produto())


def test_varias_ofertas_com_sku_na_coluna():
    html = ler_pagina("produto_disponivel.html")

    dados = extrair_dados_produto(html, criar_produto(sku="20000202"))

    assert dados["status_produto"] == "disponivel"
    assert dados["preco_numero"] == 25.9
    assert dados["produto_nome"] == "Telha Ondulada Fibrocimento 4mm 2,44m x 50cm"


def test_sku_inexistente_gera_erro():
    html = ler_pagina("produto_disponivel.html")

    with pytest.raises(ValueError, match="SKU 123 nao encontrado"):
        extrair_dados_produto(html, criar_produto(sku="123"))


def test_produto_fora_de_estoque_fica_indisponivel_sem_preco():
    # O JSON-LD informa preco (R$229,90), mas com availability OutOfStock.
    # O produto deve ficar indisponivel, sem preco nas colunas de preco,
    # e o preco anunciado deve aparecer so na mensagem.
    html = ler_pagina("produto_indisponivel.html")

    dados = extrair_dados_produto(html, criar_produto())

    assert dados["status_produto"] == "indisponivel"
    assert dados["preco_texto"] == ""
    assert dados["preco_numero"] == ""
    assert dados["mensagem"] == "OutOfStock (preco anunciado: R$229,90)"
    assert dados["produto_nome"] == "Placa Cimentícia 6mm 1,20 x 3m Peça"


def test_sku_com_zero_a_esquerda():
    # No JSON-LD o SKU aparece como "03000301"; quem cadastra pode digitar "3000301".
    html = ler_pagina("produto_indisponivel.html")

    dados = extrair_dados_produto(html, criar_produto(sku="3000301"))

    assert dados["status_produto"] == "indisponivel"


def test_dados_de_identificacao_vem_do_cadastro():
    # produto_id, concorrente e url devem vir do cadastro (produtos.csv), nao da pagina.
    html = ler_pagina("produto_indisponivel.html")
    produto = criar_produto(url="https://www.loja-exemplo.com.br/qualquer/p")

    dados = extrair_dados_produto(html, produto)

    assert dados["produto_id"] == "TESTE-001"
    assert dados["concorrente"] == "Loja A"
    assert dados["url"] == "https://www.loja-exemplo.com.br/qualquer/p"


# ---------------------------------------------------------------------------
# Testes com pequenos trechos de HTML
# Montamos so o minimo necessario: um bloco JSON-LD dentro de uma pagina vazia.
# ---------------------------------------------------------------------------

def montar_html(json_ld):
    # json.dumps faz o caminho inverso do json.loads: transforma o dicionario em texto JSON.
    texto_json = json.dumps(json_ld)
    return f'<html><head><script type="application/ld+json">{texto_json}</script></head></html>'


def montar_produto_json(ofertas, nome="Produto teste"):
    return {"@type": "Product", "name": nome, "offers": ofertas}


def test_oferta_unica_sem_aggregate_offer():
    # Nem todo site usa AggregateOffer; aqui "offers" e uma oferta so.
    html = montar_html(montar_produto_json(
        {"@type": "Offer", "price": 10.5, "availability": "https://schema.org/InStock"}
    ))

    dados = extrair_dados_produto(html, criar_produto())

    assert dados["preco_numero"] == 10.5
    assert dados["preco_texto"] == "R$10,50"
    # Sem os dados VTEX na pagina, o nome vem do JSON-LD.
    assert dados["produto_nome"] == "Produto teste"


def test_preco_como_texto():
    # Alguns sites mandam o preco como texto ("1234.56") em vez de numero.
    html = montar_html(montar_produto_json(
        {"@type": "Offer", "price": "1234.56", "availability": "http://schema.org/InStock"}
    ))

    dados = extrair_dados_produto(html, criar_produto())

    assert dados["preco_numero"] == 1234.56


def test_nome_da_variacao_vem_dos_dados_vtex():
    # Pagina com JSON-LD (2 ofertas) e o __STATE__ da VTEX com o nome de cada variacao.
    json_ld = montar_produto_json(
        {
            "@type": "AggregateOffer",
            "offers": [
                {"@type": "Offer", "sku": "111", "price": 10, "availability": "http://schema.org/InStock"},
                {"@type": "Offer", "sku": "222", "price": 20, "availability": "http://schema.org/InStock"},
            ],
        },
        nome="Telha",
    )
    estado_vtex = {
        "Product:telha.items.0": {"itemId": "111", "nameComplete": "Telha 1,22m"},
        "Product:telha.items.1": {"itemId": "222", "nameComplete": "Telha 2,44m"},
    }
    script_vtex = f"<script>window.x = 1; __STATE__ = {json.dumps(estado_vtex)}; outraCoisa()</script>"
    html = montar_html(json_ld).replace("</head>", script_vtex + "</head>")

    dados = extrair_dados_produto(html, criar_produto(sku="222"))

    assert dados["produto_nome"] == "Telha 2,44m"
    assert dados["preco_numero"] == 20


def test_pagina_sem_json_ld_gera_erro():
    html = "<html><body><h1>Produto</h1></body></html>"

    # pytest.raises confere que a funcao realmente levanta o erro esperado.
    with pytest.raises(ValueError, match="JSON-LD do produto nao encontrado"):
        extrair_dados_produto(html, criar_produto())


def test_json_ld_mal_formatado_e_ignorado():
    # Um bloco quebrado nao deve impedir de ler o proximo bloco, que esta correto.
    bloco_quebrado = '<script type="application/ld+json">{ isto nao e json </script>'
    html_valido = montar_html(montar_produto_json(
        {"@type": "Offer", "price": 5, "availability": "http://schema.org/InStock"}
    ))
    html = html_valido.replace("<head>", "<head>" + bloco_quebrado)

    dados = extrair_dados_produto(html, criar_produto())

    assert dados["preco_numero"] == 5


def test_em_estoque_sem_preco_gera_erro():
    html = montar_html(montar_produto_json(
        {"@type": "Offer", "availability": "http://schema.org/InStock"}
    ))

    with pytest.raises(ValueError, match="Preco nao encontrado"):
        extrair_dados_produto(html, criar_produto())


def test_preco_zero_gera_erro():
    html = montar_html(montar_produto_json(
        {"@type": "Offer", "price": 0, "availability": "http://schema.org/InStock"}
    ))

    with pytest.raises(ValueError, match="Preco invalido"):
        extrair_dados_produto(html, criar_produto())


# O parametrize roda o mesmo teste varias vezes, uma para cada valor da lista.
@pytest.mark.parametrize("disponibilidade", ["OutOfStock", "Discontinued", "PreOrder"])
def test_qualquer_disponibilidade_diferente_de_instock_fica_indisponivel(disponibilidade):
    html = montar_html(montar_produto_json(
        {"@type": "Offer", "price": 10, "availability": f"http://schema.org/{disponibilidade}"}
    ))

    dados = extrair_dados_produto(html, criar_produto())

    assert dados["status_produto"] == "indisponivel"
    assert dados["mensagem"].startswith(disponibilidade)
