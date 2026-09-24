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
    coletas = [criar_coleta("PRD-008", 36.9, "2026-09-24 10:00:00", nome="Telha 3,66m")]
    alertas = [
        criar_alerta("PRD-008", 36.9, 114.9, 211.4),
        criar_alerta("PRD-001", 61.9, 6.19, -90.0),
    ]

    html = gerar_html(coletas, [], alertas)

    assert "Telha 3,66m" in html
    assert "R$36,90" in html
    assert "R$114,90" in html
    assert "▲ +211,4%" in html
    assert "▼ -90,0%" in html
    assert "Nenhum alerta" not in html


def test_relatorio_escapa_html_dos_dados():
    # escape() impede que um texto vindo do site vire codigo HTML na pagina.
    coletas = [criar_coleta("PRD-001", 10.0, "2026-09-24 10:00:00", nome="<script>alert(1)</script>")]

    html = gerar_html(coletas, [], [])

    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def criar_erro(produto_id, data_erro):
    return {"id": 1, "produto_id": produto_id, "concorrente": "Loja A", "url": "https://exemplo.com/p",
            "tipo_erro": "extracao", "mensagem": "JSON-LD do produto nao encontrado na pagina.",
            "data_erro": data_erro}


EXECUCAO = {"id": 2, "inicio": "2026-09-24 11:47:38", "fim": "2026-09-24 11:51:14",
            "produtos": 59, "coletados": 54, "erros": 5, "alertas": 0}


def test_card_mostra_variacao_desde_a_coleta_anterior():
    coletas = [
        criar_coleta("PRD-001", 100.0, "2026-09-23 09:00:00"),
        criar_coleta("PRD-001", None, "2026-09-24 09:00:00"),   # indisponivel: ignorada na comparacao
        criar_coleta("PRD-001", 105.0, "2026-09-25 09:00:00"),
    ]

    html = gerar_html(coletas, [], [])

    assert "▲ +5,0%" in html


def test_card_sem_mudanca_de_preco_nao_mostra_variacao():
    coletas = [
        criar_coleta("PRD-001", 100.0, "2026-09-23 09:00:00"),
        criar_coleta("PRD-001", 100.0, "2026-09-24 09:00:00"),
    ]

    html = gerar_html(coletas, [], [])

    assert "▲" not in html and "▼" not in html


def test_card_mostra_data_da_ultima_coleta():
    html = gerar_html([criar_coleta("PRD-001", 10.0, "2026-09-24 09:00:01")], [], [])

    assert "coletado em 2026-09-24 09:00:01" in html


def test_resumo_da_ultima_coleta_no_topo():
    html = gerar_html([], [], [], EXECUCAO)

    assert "Ultima coleta: 2026-09-24 11:47:38 | 54 coletados, 5 erros, 0 alertas" in html


def test_coleta_interrompida_aparece_no_resumo():
    interrompida = dict(EXECUCAO, fim=None)

    html = gerar_html([], [], [], interrompida)

    assert "interrompida antes do fim" in html


def test_erros_da_ultima_coleta_separados_dos_antigos():
    coletas = [criar_coleta("PRD-022", 50.0, "2026-09-24 10:42:00")]
    erros = [
        criar_erro("PRD-010", "2026-09-24 11:14:42"),   # antes do inicio da ultima coleta
        criar_erro("PRD-022", "2026-09-24 11:49:02"),   # durante a ultima coleta
    ]

    html = gerar_html(coletas, erros, [], EXECUCAO)

    secao_recentes = html.split("Erros da Ultima Coleta")[1].split("Erros anteriores")[0]
    secao_antigos = html.split("Erros anteriores")[1]
    assert "PRD-022" in secao_recentes and "PRD-010" not in secao_recentes
    assert "PRD-010" in secao_antigos
    # O produto que falhou na ultima coleta ganha o aviso no card.
    assert "erro na ultima coleta</span>" in html
