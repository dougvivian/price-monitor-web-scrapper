# Testes da checagem do cadastro de produtos (validar_cadastro e filtrar_ativos).
from main import filtrar_ativos, validar_cadastro


def linha(produto_id="PRD-001", url="https://www.loja-exemplo.com.br/produto/p", ativo="sim"):
    # Uma linha do produtos.csv, como o csv.DictReader devolve.
    return {"produto_id": produto_id, "concorrente": "Loja A", "url": url,
            "sku": "", "ativo": ativo, "categoria": "telha", "observacao": ""}


def test_cadastro_correto_nao_gera_avisos():
    assert validar_cadastro([linha("PRD-001"), linha("PRD-002", ativo="nao")]) == []


def test_cadastro_vazio():
    assert validar_cadastro([]) == ["O cadastro de produtos esta vazio."]


def test_coluna_obrigatoria_faltando():
    sem_url = linha()
    del sem_url["url"]

    avisos = validar_cadastro([sem_url])

    assert avisos == ["Colunas obrigatorias faltando no cadastro: url"]


def test_id_repetido_informa_a_linha_do_arquivo():
    avisos = validar_cadastro([linha("PRD-001"), linha("PRD-002"), linha("PRD-001")])

    # 3o produto = linha 4 do arquivo (a linha 1 e o cabecalho).
    assert avisos == ["Linha 4: produto_id repetido (PRD-001)."]


def test_produto_sem_id():
    assert validar_cadastro([linha(produto_id="")]) == ["Linha 2: produto sem produto_id."]


def test_ativo_com_valor_estranho():
    avisos = validar_cadastro([linha(ativo="talvez")])

    assert avisos == ["Linha 2: ativo deve ser 'sim' ou 'nao' (veio 'talvez')."]


def test_url_invalida():
    avisos = validar_cadastro([linha(url="www.loja-exemplo.com.br/produto/p"), linha("PRD-002", url="")])

    assert avisos == [
        "Linha 2: url invalida (www.loja-exemplo.com.br/produto/p).",
        "Linha 3: url invalida (vazia).",
    ]


def test_filtrar_ativos_aceita_maiusculas_e_espacos():
    linhas = [linha("PRD-001", ativo="Sim "), linha("PRD-002", ativo="nao"), linha("PRD-003", ativo="SIM")]

    ativos = filtrar_ativos(linhas)

    assert [produto["produto_id"] for produto in ativos] == ["PRD-001", "PRD-003"]
