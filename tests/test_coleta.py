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
    def __init__(self, texto, status_code=200):
        self.status_code = status_code
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


class SiteFalso:
    # Imita um site que devolve uma sequencia de respostas, uma por chamada,
    # e conta quantas vezes as paginas de produto foram acessadas.
    # O robots.txt e respondido a parte (e contado a parte).
    def __init__(self, textos, robots="", status_robots=200):
        self.textos = list(textos)
        self.acessos = 0
        self.robots = robots
        self.status_robots = status_robots
        self.acessos_robots = 0

    def get(self, url, timeout):
        if url.endswith("/robots.txt"):
            self.acessos_robots += 1
            return RespostaFalsa(self.robots, self.status_robots)

        texto = self.textos[min(self.acessos, len(self.textos) - 1)]
        self.acessos += 1
        return RespostaFalsa(texto)


def ler_erros(arquivo_banco):
    conexao = banco.conectar(arquivo_banco)
    erros = banco.listar_erros(conexao)
    conexao.close()
    return erros


def test_robots_bloqueando_a_pagina_impede_o_acesso(tmp_path, monkeypatch):
    arquivo_banco = preparar_ambiente(tmp_path, monkeypatch, preco_anterior=80.0)
    # Regra: nenhum robo pode acessar paginas que comecam com /telha.
    site = SiteFalso([PAGINA_VARIACAO.read_text(encoding="utf-8")],
                     robots="User-agent: *\nDisallow: /telha")
    monkeypatch.setattr(main.requests, "get", site.get)

    main.main()

    erros = ler_erros(arquivo_banco)
    assert site.acessos == 0          # a pagina do produto nem foi acessada
    assert erros[0]["tipo_erro"] == "robots"


def test_robots_permitindo_a_pagina(tmp_path, monkeypatch):
    arquivo_banco = preparar_ambiente(tmp_path, monkeypatch, preco_anterior=80.0)
    # Regra que bloqueia outra area do site (carrinho), mas nao a pagina de produto.
    site = SiteFalso([PAGINA_VARIACAO.read_text(encoding="utf-8")],
                     robots="User-agent: *\nDisallow: /checkout")
    monkeypatch.setattr(main.requests, "get", site.get)

    main.main()

    coletas, _ = ler_banco(arquivo_banco)
    assert site.acessos == 1
    assert coletas[-1]["preco"] == 87.9


def test_site_sem_robots_permite_tudo(tmp_path, monkeypatch):
    arquivo_banco = preparar_ambiente(tmp_path, monkeypatch, preco_anterior=80.0)
    site = SiteFalso([PAGINA_VARIACAO.read_text(encoding="utf-8")], status_robots=404)
    monkeypatch.setattr(main.requests, "get", site.get)

    main.main()

    assert site.acessos == 1
    assert ler_erros(arquivo_banco) == []


def test_robots_com_erro_no_servidor_bloqueia_por_seguranca(tmp_path, monkeypatch):
    arquivo_banco = preparar_ambiente(tmp_path, monkeypatch, preco_anterior=80.0)
    site = SiteFalso([PAGINA_VARIACAO.read_text(encoding="utf-8")], status_robots=503)
    monkeypatch.setattr(main.requests, "get", site.get)

    main.main()

    assert site.acessos == 0
    assert ler_erros(arquivo_banco)[0]["tipo_erro"] == "robots"


def test_robots_e_baixado_uma_vez_por_site(tmp_path, monkeypatch):
    preparar_ambiente(tmp_path, monkeypatch, preco_anterior=80.0)
    # Cadastro com 3 produtos do mesmo site.
    arquivo_produtos = tmp_path / "produtos.csv"
    with open(arquivo_produtos, "w", newline="", encoding="utf-8") as arquivo_csv:
        escritor = csv.writer(arquivo_csv, delimiter=";")
        escritor.writerow(["produto_id", "concorrente", "url", "sku", "ativo", "categoria", "observacao"])
        for numero in range(1, 4):
            escritor.writerow([f"PRD-00{numero}", "Loja A", URL_VARIACAO, "", "sim", "telha", ""])
    site = SiteFalso([PAGINA_VARIACAO.read_text(encoding="utf-8")])
    monkeypatch.setattr(main.requests, "get", site.get)

    main.main()

    assert site.acessos == 3
    assert site.acessos_robots == 1


def test_pagina_incompleta_e_baixada_de_novo(tmp_path, monkeypatch):
    arquivo_banco = preparar_ambiente(tmp_path, monkeypatch, preco_anterior=80.0)
    pagina_boa = PAGINA_VARIACAO.read_text(encoding="utf-8")
    # 1o acesso: pagina pela metade (sem JSON-LD). 2o acesso: pagina completa.
    site = SiteFalso(["<html><body>carregando...</body></html>", pagina_boa])
    monkeypatch.setattr(main.requests, "get", site.get)

    main.main()

    coletas, _ = ler_banco(arquivo_banco)
    assert site.acessos == 2
    assert coletas[-1]["preco"] == 87.9


def test_pagina_incompleta_duas_vezes_vira_erro(tmp_path, monkeypatch):
    arquivo_banco = preparar_ambiente(tmp_path, monkeypatch, preco_anterior=80.0)
    site = SiteFalso(["<html><body>carregando...</body></html>"])
    monkeypatch.setattr(main.requests, "get", site.get)

    main.main()

    conexao = banco.conectar(arquivo_banco)
    erros = banco.listar_erros(conexao)
    conexao.close()

    # Tenta so uma vez a mais (2 acessos no total), sem insistir.
    assert site.acessos == 2
    assert len(erros) == 1
    assert "JSON-LD" in erros[0]["mensagem"]


def test_pagina_completa_nao_e_baixada_de_novo(tmp_path, monkeypatch):
    preparar_ambiente(tmp_path, monkeypatch, preco_anterior=80.0)
    site = SiteFalso([PAGINA_VARIACAO.read_text(encoding="utf-8")])
    monkeypatch.setattr(main.requests, "get", site.get)

    main.main()

    assert site.acessos == 1


def test_coleta_registra_a_execucao_no_banco(tmp_path, monkeypatch):
    arquivo_banco = preparar_ambiente(tmp_path, monkeypatch, preco_anterior=80.0)

    main.main()

    conexao = banco.conectar(arquivo_banco)
    execucao = banco.buscar_ultima_execucao(conexao)
    conexao.close()

    assert execucao["fim"] is not None
    assert (execucao["produtos"], execucao["coletados"], execucao["erros"], execucao["alertas"]) == (1, 1, 0, 0)


def test_cadastro_sem_coluna_obrigatoria_cancela_a_coleta(tmp_path, monkeypatch, capsys):
    arquivo_produtos = tmp_path / "produtos.csv"
    # Cadastro sem a coluna "url" (como se tivesse sido apagada no Excel).
    arquivo_produtos.write_text("produto_id;concorrente;ativo\nPRD-001;Loja A;sim\n", encoding="utf-8")
    monkeypatch.setattr(main, "ARQUIVO_PRODUTOS", arquivo_produtos)
    monkeypatch.setattr(main, "ARQUIVO_BANCO", tmp_path / "teste.db")

    main.main()   # antes desta correcao, quebrava com KeyError

    saida = capsys.readouterr().out
    assert "Colunas obrigatorias faltando no cadastro: url" in saida
    assert "Coleta cancelada" in saida
    assert not (tmp_path / "teste.db").exists()
