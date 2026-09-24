# Teste do fluxo completo da funcao main(), sem acessar o site e sem mexer nos CSVs reais.
#
# Usamos duas ferramentas do pytest:
#   - tmp_path: uma pasta temporaria, criada do zero para cada teste.
#   - monkeypatch: troca temporariamente algo do codigo durante o teste
#     (aqui: os caminhos dos CSVs, o requests.get e o sleep). Ao final do teste,
#     tudo volta ao normal sozinho.
import csv
from pathlib import Path

import main


PAGINA_VARIACAO = Path(__file__).parent / "paginas" / "produto_variacao_sku.html"
URL_VARIACAO = "https://www.loja-exemplo.com.br/telha-fibrocimento-ondulada-6mm-cinza-Marca/p?skuId=10000103"


class RespostaFalsa:
    # Imita o objeto que o requests.get devolve, com so o que o main() usa.
    def __init__(self, texto):
        self.status_code = 200
        self.text = texto


def escrever_csv(caminho, campos, linhas):
    with open(caminho, "w", newline="", encoding="utf-8") as arquivo_csv:
        escritor = csv.DictWriter(arquivo_csv, fieldnames=campos, delimiter=";")
        escritor.writeheader()
        escritor.writerows(linhas)


def ler_csv(caminho):
    if not caminho.exists():
        return []

    with open(caminho, newline="", encoding="utf-8") as arquivo_csv:
        return list(csv.DictReader(arquivo_csv, delimiter=";"))


def preparar_ambiente(tmp_path, monkeypatch, preco_anterior):
    # Cadastro com um produto so: a telha de 2,13m (SKU 10000103), que na pagina salva custa R$87,90.
    arquivo_produtos = tmp_path / "produtos.csv"
    escrever_csv(
        arquivo_produtos,
        ["produto_id", "concorrente", "url", "sku", "ativo", "categoria", "observacao"],
        [{"produto_id": "PRD-003", "concorrente": "Loja A", "url": URL_VARIACAO,
          "sku": "", "ativo": "sim", "categoria": "telha", "observacao": ""}],
    )

    # Historico com uma coleta anterior desse produto.
    arquivo_coletas = tmp_path / "coletas.csv"
    main.salvar_linhas_csv(
        arquivo_coletas,
        ["produto_id", "concorrente", "produto_nome", "preco_texto", "preco_numero",
         "status_produto", "mensagem", "url", "data_coleta"],
        [{"produto_id": "PRD-003", "concorrente": "Loja A", "produto_nome": "Telha",
          "preco_texto": "", "preco_numero": preco_anterior, "status_produto": "disponivel",
          "mensagem": "", "url": URL_VARIACAO, "data_coleta": "2026-09-01 10:00:00"}],
    )

    # Apontamos o main() para os arquivos temporarios.
    monkeypatch.setattr(main, "ARQUIVO_PRODUTOS", arquivo_produtos)
    monkeypatch.setattr(main, "ARQUIVO_COLETAS", arquivo_coletas)
    monkeypatch.setattr(main, "ARQUIVO_ERROS", tmp_path / "erros.csv")
    monkeypatch.setattr(main, "ARQUIVO_ALERTAS", tmp_path / "alertas.csv")

    # Em vez de acessar o site, requests.get devolve a pagina salva.
    html = PAGINA_VARIACAO.read_text(encoding="utf-8")
    monkeypatch.setattr(main.requests, "get", lambda url, timeout: RespostaFalsa(html))

    # Sem pausas durante o teste.
    monkeypatch.setattr(main, "sleep", lambda segundos: None)

    return arquivo_coletas, tmp_path / "alertas.csv"


def test_preco_com_variacao_normal_e_salvo(tmp_path, monkeypatch):
    # Anterior R$80,00 -> novo R$87,90: variacao de ~10%, normal.
    arquivo_coletas, arquivo_alertas = preparar_ambiente(tmp_path, monkeypatch, preco_anterior=80.0)

    main.main()

    coletas = ler_csv(arquivo_coletas)
    assert len(coletas) == 2
    assert coletas[-1]["preco_numero"] == "87.9"
    assert ler_csv(arquivo_alertas) == []


def test_variacao_absurda_gera_alerta_e_depois_e_confirmada(tmp_path, monkeypatch):
    # Anterior R$40,00 -> novo R$87,90: subiu ~120%.
    arquivo_coletas, arquivo_alertas = preparar_ambiente(tmp_path, monkeypatch, preco_anterior=40.0)

    # 1a coleta: vira alerta e NAO entra no historico.
    main.main()

    assert len(ler_csv(arquivo_coletas)) == 1
    alertas = ler_csv(arquivo_alertas)
    assert len(alertas) == 1
    assert alertas[0]["preco_anterior"] == "40.0"
    assert alertas[0]["preco_novo"] == "87.9"
    assert alertas[0]["variacao_percentual"] == "119.8"

    # 2a coleta: o site mostrou o mesmo preco de novo, entao ele e confirmado e salvo.
    main.main()

    coletas = ler_csv(arquivo_coletas)
    assert len(coletas) == 2
    assert coletas[-1]["preco_numero"] == "87.9"
    assert len(ler_csv(arquivo_alertas)) == 1
