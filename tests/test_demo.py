# Testes do modo demonstracao (demo.py).
# Conferimos que o banco ficticio tem todos os casos que a demonstracao promete mostrar,
# e que nada acessa a internet.
import sqlite3

import pytest

import demo
from main import ean_valido


@pytest.fixture
def banco_demo(tmp_path, monkeypatch):
    # Se algo tentar acessar a internet durante o teste, o teste falha na hora.
    def sem_internet(*args, **kwargs):
        raise AssertionError("a demonstracao nao pode acessar a internet")

    monkeypatch.setattr("requests.get", sem_internet)

    arquivo = tmp_path / "demo.db"
    cadastro = demo.criar_dados_demo(arquivo)
    conexao = sqlite3.connect(arquivo)
    yield conexao, cadastro
    conexao.close()


def contar(conexao, sql):
    return conexao.execute(sql).fetchone()[0]


def test_demo_cria_30_dias_de_coletas(banco_demo):
    conexao, cadastro = banco_demo

    assert contar(conexao, "SELECT COUNT(*) FROM execucoes") == demo.DIAS_DE_HISTORICO
    assert contar(conexao, "SELECT COUNT(DISTINCT produto_id) FROM coletas") == len(cadastro)


def test_demo_tem_todos_os_casos_do_relatorio(banco_demo):
    conexao, _ = banco_demo

    assert contar(conexao, "SELECT COUNT(*) FROM alertas") >= 1
    assert contar(conexao, "SELECT COUNT(*) FROM erros") >= 1
    assert contar(conexao, "SELECT COUNT(*) FROM coletas WHERE status_produto = 'indisponivel'") >= 1
    # Algum produto mudou de preco ao longo do historico.
    assert contar(conexao, """
        SELECT COUNT(*) FROM (
            SELECT produto_id FROM coletas WHERE preco IS NOT NULL
            GROUP BY produto_id HAVING COUNT(DISTINCT preco) > 1
        )
    """) >= 1


def test_demo_tem_so_dados_ficticios(banco_demo):
    _, cadastro = banco_demo

    for produto in cadastro:
        assert produto["concorrente"] in demo.LOJAS
        assert ".exemplo.com.br/" in produto["url"]
        assert ean_valido(produto["ean"])


def test_demo_sai_igual_toda_vez(tmp_path):
    # Semente fixa: duas execucoes geram exatamente os mesmos precos.
    def precos(arquivo):
        demo.criar_dados_demo(arquivo)
        conexao = sqlite3.connect(arquivo)
        try:
            return conexao.execute("SELECT produto_id, preco FROM coletas ORDER BY id").fetchall()
        finally:
            conexao.close()

    assert precos(tmp_path / "a.db") == precos(tmp_path / "b.db")


def test_demo_gera_o_relatorio(tmp_path, monkeypatch):
    monkeypatch.setattr(demo, "ARQUIVO_BANCO_DEMO", tmp_path / "demo.db")
    monkeypatch.setattr(demo, "ARQUIVO_RELATORIO_DEMO", tmp_path / "relatorios" / "demo.html")

    demo.main()

    html = (tmp_path / "relatorios" / "demo.html").read_text(encoding="utf-8")
    assert "Comparativo entre Lojas" in html
    assert "Loja B" in html
    assert "<svg" in html          # pelo menos um grafico de historico
