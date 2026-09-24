# Testes do relatorio HTML (gerar_relatorio.py).
# Montamos os dados na mao, no mesmo formato que o banco devolve,
# e conferimos se o HTML gerado contem o que esperamos.
from gerar_relatorio import gerar_html, preparar_coleta


def criar_coleta(produto_id, preco, data_coleta, nome="Telha teste"):
    # Mesmo formato de uma linha da tabela coletas lida do banco.
    return preparar_coleta({
        "id": 1,
        "produto_id": produto_id,
        "concorrente": "Loja A",
        "produto_nome": nome,
        "preco": preco,
        "status_produto": "disponivel" if preco is not None else "indisponivel",
        "mensagem": None if preco is not None else "OutOfStock (preco anunciado: R$229,90)",
        "url": "https://exemplo.com/p",
        "data_coleta": data_coleta,
    })


def criar_alerta(produto_id, preco_anterior, preco_novo, variacao):
    return {
        "id": 1,
        "produto_id": produto_id,
        "concorrente": "Loja A",
        "url": "https://exemplo.com/p",
        "preco_anterior": preco_anterior,
        "preco_novo": preco_novo,
        "variacao_percentual": variacao,
        "data_alerta": "2026-09-24 11:00:00",
    }


def test_preparar_coleta_formata_preco_e_trata_vazios():
    disponivel = criar_coleta("PRD-001", 87.9, "2026-09-24 10:00:00")
    indisponivel = criar_coleta("PRD-010", None, "2026-09-24 10:00:00")

    assert disponivel["preco_texto"] == "R$87,90"
    assert disponivel["mensagem"] == ""
    assert indisponivel["preco_texto"] == ""
    assert indisponivel["preco_numero"] == ""


def test_relatorio_mostra_ultimo_preco_e_historico():
    coletas = [
        criar_coleta("PRD-001", 61.9, "2026-09-23 10:00:00"),
        criar_coleta("PRD-001", 64.9, "2026-09-24 10:00:00"),
    ]

    html = gerar_html(coletas, [], [])

    assert "R$64,90" in html   # preco mais recente
    assert "R$61,90" in html   # historico
    assert "Nenhum alerta de variacao de preco." in html


def test_relatorio_mostra_alertas_com_nome_do_produto():
    coletas = [criar_coleta("PRD-008", 36.9, "2026-09-24 10:00:00", nome="Telha Marca 3,66m")]
    alertas = [
        criar_alerta("PRD-008", 36.9, 114.9, 211.4),
        criar_alerta("PRD-001", 61.9, 6.19, -90.0),
    ]

    html = gerar_html(coletas, [], alertas)

    assert "Telha Marca 3,66m" in html
    assert "R$36,90" in html
    assert "R$114,90" in html
    assert "▲ +211.4%" in html
    assert "▼ -90.0%" in html
    assert "Nenhum alerta" not in html


def test_relatorio_escapa_html_dos_dados():
    # escape() impede que um texto vindo do site vire codigo HTML na pagina.
    coletas = [criar_coleta("PRD-001", 10.0, "2026-09-24 10:00:00", nome="<script>alert(1)</script>")]

    html = gerar_html(coletas, [], [])

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html
