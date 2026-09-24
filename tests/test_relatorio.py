# Testes do relatorio HTML (gerar_relatorio.py).
# Montamos os dados na mao, no mesmo formato que o banco devolve,
# e conferimos se o HTML gerado contem o que esperamos.
from gerar_relatorio import (
    agrupar_coletas_por_produto, criar_grafico_svg, criar_seletor_historico, diferenca_entre_lojas,
    gerar_html, ler_categorias, ler_grupos, montar_comparativos, preparar_coleta,
)


def criar_coleta(produto_id, preco, data_coleta, nome="Telha teste", concorrente="Loja A", ean=None):
    # Mesmo formato de uma linha da tabela coletas lida do banco.
    return preparar_coleta({
        "id": 1,
        "produto_id": produto_id,
        "concorrente": concorrente,
        "produto_nome": nome,
        "ean": ean,
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


# ---------- Comparativo entre lojas ----------

def test_ler_grupos_ignora_produtos_sem_grupo_e_cadastro_sem_a_coluna():
    cadastro = [
        {"produto_id": "PRD-001", "grupo": " TELHA-6MM "},
        {"produto_id": "PRD-002", "grupo": ""},
        {"produto_id": "PRD-003"},   # cadastro antigo, sem a coluna grupo
    ]

    assert ler_grupos(cadastro) == {"PRD-001": "TELHA-6MM"}


def test_comparativo_casa_produtos_de_lojas_diferentes_pelo_ean():
    coletas = [
        criar_coleta("PRD-001", 64.9, "2026-09-24 09:00:00", concorrente="Loja A", ean="7890000000352"),
        criar_coleta("PRD-101", 59.9, "2026-09-24 09:00:00", concorrente="Loja B", ean="7890000000352"),
        criar_coleta("PRD-002", 25.9, "2026-09-24 09:00:00", concorrente="Loja A", ean="7890000002028"),
    ]

    comparativos = montar_comparativos(agrupar_coletas_por_produto(coletas), {})

    # So o EAN que aparece nas duas lojas vira comparativo.
    assert list(comparativos) == ["EAN 7890000000352"]
    assert {coleta["produto_id"] for coleta in comparativos["EAN 7890000000352"]} == {"PRD-001", "PRD-101"}


def test_grupo_do_cadastro_casa_marcas_diferentes_e_tem_prioridade_sobre_o_ean():
    coletas = [
        criar_coleta("PRD-001", 53.9, "2026-09-24 09:00:00", concorrente="Loja A", ean="7890000000116"),
        criar_coleta("PRD-101", 49.9, "2026-09-24 09:00:00", concorrente="Loja B", ean="7890000000994"),
    ]
    grupos = {"PRD-001": "FERRO-CA50-10", "PRD-101": "FERRO-CA50-10"}

    comparativos = montar_comparativos(agrupar_coletas_por_produto(coletas), grupos)

    assert list(comparativos) == ["FERRO-CA50-10"]


def test_mesma_loja_nao_vira_comparativo():
    coletas = [
        criar_coleta("PRD-001", 64.9, "2026-09-24 09:00:00", ean="7890000000352"),
        criar_coleta("PRD-002", 61.9, "2026-09-24 09:00:00", ean="7890000000352"),
    ]

    assert montar_comparativos(agrupar_coletas_por_produto(coletas), {}) == {}


def test_relatorio_mostra_comparativo_com_mais_barato_e_diferenca():
    coletas = [
        criar_coleta("PRD-001", 60.0, "2026-09-24 09:00:00", concorrente="Loja A"),
        criar_coleta("PRD-101", 50.0, "2026-09-24 09:00:00", concorrente="Loja B"),
        criar_coleta("PRD-201", None, "2026-09-24 09:00:00", concorrente="Loja C"),   # indisponivel
    ]
    grupos = {"PRD-001": "TELHA-6MM", "PRD-101": "TELHA-6MM", "PRD-201": "TELHA-6MM"}

    html = gerar_html(coletas, [], [], grupos=grupos)

    assert "Comparativo entre Lojas" in html
    assert "TELHA-6MM" in html
    assert "mais barato" in html
    assert "A loja mais cara cobra 20,0% a mais que a mais barata." in html
    # Ordem: mais barato primeiro, indisponivel por ultimo.
    assert html.index("PRD-101</strong>") < html.index("PRD-001</strong>") < html.index("PRD-201</strong>")


def test_relatorio_sem_comparativos_mostra_aviso():
    html = gerar_html([criar_coleta("PRD-001", 10.0, "2026-09-24 09:00:00")], [], [])

    assert "Nenhum produto casado entre lojas ainda" in html


def test_css_e_js_vao_para_dentro_do_html():
    # O relatorio precisa ser um arquivo so: o CSS e o JS sao copiados para dentro dele,
    # e nao ligados por <link> ou <script src>, que quebrariam ao enviar so o HTML.
    html = gerar_html([], [], [])

    assert "<link" not in html and "<script src" not in html
    assert "font-family" in html               # veio do estilo.css
    assert "addEventListener" in html          # veio do interacao.js


# ---------- Layout com abas ----------

def test_diferenca_compara_lojas_e_nao_produtos_da_mesma_loja():
    # A Loja A tem duas marcas no grupo (50 e 70). Comparando lojas, vale a opcao mais
    # barata de cada uma: Loja A 50 x Loja B 55 = 10%, e nao 70 x 50 = 40%.
    ultimas = [
        criar_coleta("PRD-001", 70.0, "2026-09-24 09:00:00", concorrente="Loja A"),
        criar_coleta("PRD-002", 50.0, "2026-09-24 09:00:00", concorrente="Loja A"),
        criar_coleta("PRD-101", 55.0, "2026-09-24 09:00:00", concorrente="Loja B"),
    ]

    assert round(diferenca_entre_lojas(ultimas), 1) == 10.0


def test_diferenca_precisa_de_duas_lojas_com_preco():
    ultimas = [
        criar_coleta("PRD-001", 50.0, "2026-09-24 09:00:00", concorrente="Loja A"),
        criar_coleta("PRD-101", None, "2026-09-24 09:00:00", concorrente="Loja B"),
    ]

    assert diferenca_entre_lojas(ultimas) is None


def test_grafico_ignora_coletas_sem_preco():
    historico = [   # do mais recente para o mais antigo, como no relatorio
        criar_coleta("PRD-001", 66.9, "2026-09-24 09:00:00"),
        criar_coleta("PRD-001", None, "2026-09-23 09:00:00"),
        criar_coleta("PRD-001", 61.9, "2026-09-22 09:00:00"),
        criar_coleta("PRD-001", 64.9, "2026-09-21 09:00:00"),
    ]

    svg = criar_grafico_svg(historico)

    assert svg.count("<circle") == 3          # um ponto por coleta com preco
    assert "maior: R$66,90" in svg and "menor: R$61,90" in svg


def test_grafico_com_preco_estavel_e_com_poucos_dados():
    estavel = [criar_coleta("PRD-001", 10.0, f"2026-09-2{dia} 09:00:00") for dia in (4, 3)]
    uma_coleta = [criar_coleta("PRD-001", 10.0, "2026-09-24 09:00:00")]

    assert "preco estavel: R$10,00" in criar_grafico_svg(estavel)
    assert "<svg" not in criar_grafico_svg(uma_coleta)


def test_historico_abre_no_produto_com_mais_coletas_com_preco():
    produtos = [
        ("PRD-001", [criar_coleta("PRD-001", None, f"2026-09-2{dia} 09:00:00") for dia in (4, 3, 2)]),
        ("PRD-002", [criar_coleta("PRD-002", 10.0, f"2026-09-2{dia} 09:00:00") for dia in (4, 3)]),
    ]

    seletor = criar_seletor_historico(produtos)

    assert '<option value="PRD-002" selected>' in seletor
    assert '<option value="PRD-001">' in seletor


def test_menu_tem_as_abas_e_contador_de_erros_em_destaque():
    coletas = [criar_coleta("PRD-022", 50.0, "2026-09-24 11:48:00")]
    erros = [criar_erro("PRD-022", "2026-09-24 11:49:02")]

    html = gerar_html(coletas, erros, [], EXECUCAO)

    for aba in ["visao-geral", "comparador", "produtos", "historico", "alertas", "erros"]:
        assert f'href="#{aba}"' in html
        # id diferente do endereco, para o navegador nao rolar a pagina sozinho
        assert f'id="aba-{aba}"' in html
    assert '<span class="contador contador-destaque">1</span>' in html


def test_filtros_de_loja_e_categoria_usam_os_valores_coletados():
    coletas = [
        criar_coleta("PRD-001", 10.0, "2026-09-24 09:00:00", concorrente="Loja A"),
        criar_coleta("PRD-101", 12.0, "2026-09-24 09:00:00", concorrente="Loja B"),
    ]
    categorias = ler_categorias([
        {"produto_id": "PRD-001", "categoria": "telha"},
        {"produto_id": "PRD-101", "categoria": " cimento "},
        {"produto_id": "PRD-999", "categoria": ""},
    ])

    html = gerar_html(coletas, [], [], categorias=categorias)

    assert categorias == {"PRD-001": "telha", "PRD-101": "cimento"}
    assert '<option value="Loja B">Loja B</option>' in html
    assert '<option value="cimento">cimento</option>' in html
    assert 'data-categoria="telha"' in html
