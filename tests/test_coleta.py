# Teste do fluxo completo da funcao main(), sem acessar o site e sem mexer no banco real.
#
# Usamos duas ferramentas do pytest:
#   - tmp_path: uma pasta temporaria, criada do zero para cada teste.
#   - monkeypatch: troca temporariamente algo do codigo durante o teste
#     (aqui: os caminhos dos arquivos, o requests.get e o sleep). Ao final do teste,
#     tudo volta ao normal sozinho.
import csv
from pathlib import Path

import banco
import main


PAGINA_VARIACAO = Path(__file__).parent / "paginas" / "produto_variacao_sku.html"
URL_VARIACAO = "https://www.loja-exemplo.com.br/telha-fibrocimento-ondulada-6mm/p?skuId=10000103"


class RespostaFalsa:
    # Imita o objeto que o requests.get devolve, com so o que o main() usa.
    def __init__(self, texto):
        self.status_code = 200
        self.text = texto


def preparar_ambiente(tmp_path, monkeypatch, preco_anterior):
    # Cadastro com um produto so: a telha de 2,13m (SKU 10000103), que na pagina salva custa R$87,90.
    arquivo_produtos = tmp_path / "produtos.csv"

    with open(arquivo_produtos, "w", newline="", encoding="utf-8") as arquivo_csv:
        escritor = csv.writer(arquivo_csv, delimiter=";")
        escritor.writerow(["produto_id", "concorrente", "url", "sku", "ativo", "categoria", "observacao"])
        escritor.writerow(["PRD-003", "Loja A", URL_VARIACAO, "", "sim", "telha", ""])

    # Banco temporario com uma coleta anterior desse produto.
    arquivo_banco = tmp_path / "teste.db"
    conexao = banco.conectar(arquivo_banco)
    banco.salvar_coleta(conexao, {
        "produto_id": "PRD-003", "concorrente": "Loja A", "produto_nome": "Telha",
        "preco_numero": preco_anterior, "status_produto": "disponivel", "mensagem": "",
        "url": URL_VARIACAO, "data_coleta": "2026-09-01 10:00:00",
    })
    conexao.close()

    # Apontamos o main() para os arquivos temporarios.
    monkeypatch.setattr(main, "ARQUIVO_PRODUTOS", arquivo_produtos)
    monkeypatch.setattr(main, "ARQUIVO_BANCO", arquivo_banco)

    # Em vez de acessar o site, requests.get devolve a pagina salva.
    html = PAGINA_VARIACAO.read_text(encoding="utf-8")
    monkeypatch.setattr(main.requests, "get", lambda url, timeout: RespostaFalsa(html))

    # Sem pausas durante o teste.
    monkeypatch.setattr(main, "sleep", lambda segundos: None)

    return arquivo_banco


def ler_banco(arquivo_banco):
    # Abre o banco temporario e devolve (coletas, alertas) para conferir no teste.
    conexao = banco.conectar(arquivo_banco)
    coletas = banco.listar_coletas(conexao)
    alertas = banco.listar_alertas(conexao)
    conexao.close()
    return coletas, alertas


def test_preco_com_variacao_normal_e_salvo(tmp_path, monkeypatch):
    # Anterior R$80,00 -> novo R$87,90: variacao de ~10%, normal.
    arquivo_banco = preparar_ambiente(tmp_path, monkeypatch, preco_anterior=80.0)

    main.main()

    coletas, alertas = ler_banco(arquivo_banco)
    assert len(coletas) == 2
    assert coletas[-1]["preco"] == 87.9
    assert coletas[-1]["produto_nome"] == "Telha Fibrocimento Ondulada 6mm 2,13 x 1,10m"
    assert alertas == []


def test_variacao_absurda_gera_alerta_e_depois_e_confirmada(tmp_path, monkeypatch):
    # Anterior R$40,00 -> novo R$87,90: subiu ~120%.
    arquivo_banco = preparar_ambiente(tmp_path, monkeypatch, preco_anterior=40.0)

    # 1a coleta: vira alerta e NAO entra no historico.
    main.main()

    coletas, alertas = ler_banco(arquivo_banco)
    assert len(coletas) == 1
    assert len(alertas) == 1
    assert alertas[0]["preco_anterior"] == 40.0
    assert alertas[0]["preco_novo"] == 87.9
    assert alertas[0]["variacao_percentual"] == 119.8

    # 2a coleta: o site mostrou o mesmo preco de novo, entao ele e confirmado e salvo.
    main.main()

    coletas, alertas = ler_banco(arquivo_banco)
    assert len(coletas) == 2
    assert coletas[-1]["preco"] == 87.9
    assert len(alertas) == 1


def test_erro_de_extracao_vai_para_tabela_de_erros(tmp_path, monkeypatch):
    arquivo_banco = preparar_ambiente(tmp_path, monkeypatch, preco_anterior=80.0)
    # Desta vez o "site" devolve uma pagina sem JSON-LD.
    monkeypatch.setattr(main.requests, "get", lambda url, timeout: RespostaFalsa("<html></html>"))

    main.main()

    conexao = banco.conectar(arquivo_banco)
    erros = banco.listar_erros(conexao)
    conexao.close()

    assert len(erros) == 1
    assert erros[0]["tipo_erro"] == "extracao"
    assert "JSON-LD" in erros[0]["mensagem"]


def test_sem_cadastro_de_produtos_avisa_e_nao_coleta(tmp_path, monkeypatch, capsys):
    # capsys captura o que o programa imprime no terminal, para conferirmos a mensagem.
    monkeypatch.setattr(main, "ARQUIVO_PRODUTOS", tmp_path / "nao_existe.csv")
    monkeypatch.setattr(main, "ARQUIVO_BANCO", tmp_path / "teste.db")

    main.main()

    saida = capsys.readouterr().out
    assert "Cadastro de produtos nao encontrado" in saida
    assert "produtos.exemplo.csv" in saida
    # Nem chegou a abrir o banco.
    assert not (tmp_path / "teste.db").exists()
