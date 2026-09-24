# Testes das funcoes do banco de dados (banco.py).
# Cada teste usa um banco novo em ":memory:": o SQLite cria o banco so na memoria,
# sem arquivo, e ele some quando a conexao fecha. Perfeito para testes.
import pytest

import banco


@pytest.fixture
def conexao():
    # Uma "fixture" prepara algo que os testes recebem pronto como parametro.
    # Tudo antes do "yield" roda antes do teste; tudo depois, no final.
    conexao = banco.conectar(":memory:")
    yield conexao
    conexao.close()


def criar_coleta(produto_id, preco, data_coleta="2026-09-24 10:00:00"):
    return {
        "produto_id": produto_id,
        "concorrente": "Loja A",
        "produto_nome": f"Produto {produto_id}",
        "preco_numero": preco,
        "status_produto": "disponivel" if preco != "" else "indisponivel",
        "mensagem": "",
        "url": "https://exemplo.com/p",
        "data_coleta": data_coleta,
    }


def criar_alerta(produto_id, preco_novo):
    return {
        "produto_id": produto_id,
        "concorrente": "Loja A",
        "url": "https://exemplo.com/p",
        "preco_anterior": 10.0,
        "preco_novo": preco_novo,
        "variacao_percentual": 100.0,
        "data_alerta": "2026-09-24 10:00:00",
    }


def test_banco_novo_comeca_vazio(conexao):
    assert banco.listar_coletas(conexao) == []
    assert banco.listar_erros(conexao) == []
    assert banco.listar_alertas(conexao) == []
    assert banco.buscar_ultimos_precos(conexao) == {}


def test_salvar_e_listar_coleta(conexao):
    banco.salvar_coleta(conexao, criar_coleta("PRD-001", 61.9))

    coletas = banco.listar_coletas(conexao)

    assert len(coletas) == 1
    assert coletas[0]["id"] == 1
    assert coletas[0]["preco"] == 61.9


def test_produto_sem_preco_fica_null_no_banco(conexao):
    # "" no Python vira NULL no banco (None quando lemos de volta).
    banco.salvar_coleta(conexao, criar_coleta("PRD-010", ""))

    assert banco.listar_coletas(conexao)[0]["preco"] is None


def test_ultimos_precos_pega_a_coleta_mais_recente_de_cada_produto(conexao):
    banco.salvar_coleta(conexao, criar_coleta("PRD-001", 50.0))
    banco.salvar_coleta(conexao, criar_coleta("PRD-002", 70.0))
    banco.salvar_coleta(conexao, criar_coleta("PRD-001", 55.0))

    assert banco.buscar_ultimos_precos(conexao) == {"PRD-001": 55.0, "PRD-002": 70.0}


def test_ultimos_precos_ignora_coletas_sem_preco(conexao):
    # Se a ultima coleta foi "indisponivel", o ultimo preco continua sendo o anterior.
    banco.salvar_coleta(conexao, criar_coleta("PRD-001", 50.0))
    banco.salvar_coleta(conexao, criar_coleta("PRD-001", ""))

    assert banco.buscar_ultimos_precos(conexao) == {"PRD-001": 50.0}


def test_ultimos_alertas_pega_o_mais_recente_de_cada_produto(conexao):
    banco.salvar_alerta(conexao, criar_alerta("PRD-008", 100.0))
    banco.salvar_alerta(conexao, criar_alerta("PRD-008", 114.9))

    assert banco.buscar_ultimos_alertas(conexao) == {"PRD-008": 114.9}


def test_texto_com_aspas_e_gravado_sem_quebrar_o_sql(conexao):
    # Os "?" do sqlite3 protegem contra SQL injection: aspas e comandos SQL
    # dentro de um texto sao gravados como texto comum, sem virar comando.
    nome_perigoso = "Telha 'especial'; DROP TABLE coletas; --"
    coleta = criar_coleta("PRD-001", 10.0)
    coleta["produto_nome"] = nome_perigoso

    banco.salvar_coleta(conexao, coleta)

    assert banco.listar_coletas(conexao)[0]["produto_nome"] == nome_perigoso
