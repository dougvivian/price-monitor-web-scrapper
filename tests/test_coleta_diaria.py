# Testes do script da coleta diaria (coleta_diaria.py).
# Trocamos a coleta e o relatorio por funcoes falsas: aqui so interessa conferir
# a ordem das etapas e o que vai para o arquivo de log.
import coleta_diaria


def preparar(tmp_path, monkeypatch, coleta_falsa):
    etapas = []
    monkeypatch.setattr(coleta_diaria, "ARQUIVO_LOG", tmp_path / "logs" / "coleta_diaria.log")
    monkeypatch.setattr(coleta_diaria.coleta, "main", lambda: coleta_falsa(etapas))
    monkeypatch.setattr(coleta_diaria.gerar_relatorio, "main", lambda: etapas.append("relatorio"))
    return etapas, tmp_path / "logs" / "coleta_diaria.log"


def test_roda_coleta_e_depois_relatorio_e_grava_log(tmp_path, monkeypatch):
    def coleta_ok(etapas):
        etapas.append("coleta")
        print("Produtos atualizados: 3")

    etapas, arquivo_log = preparar(tmp_path, monkeypatch, coleta_ok)

    coleta_diaria.main()

    assert etapas == ["coleta", "relatorio"]
    log = arquivo_log.read_text(encoding="utf-8")
    assert "Inicio da coleta diaria" in log
    assert "Produtos atualizados: 3" in log
    assert "Fim:" in log


def test_erro_na_coleta_fica_registrado_no_log(tmp_path, monkeypatch):
    def coleta_quebrada(etapas):
        raise RuntimeError("sem internet")

    etapas, arquivo_log = preparar(tmp_path, monkeypatch, coleta_quebrada)

    coleta_diaria.main()

    log = arquivo_log.read_text(encoding="utf-8")
    assert "ERRO durante a coleta diaria" in log
    assert "RuntimeError: sem internet" in log
    # Com a coleta quebrada, o relatorio nao chega a ser gerado.
    assert etapas == []


def test_execucoes_se_acumulam_no_mesmo_log(tmp_path, monkeypatch):
    etapas, arquivo_log = preparar(tmp_path, monkeypatch, lambda etapas: None)

    coleta_diaria.main()
    coleta_diaria.main()

    assert arquivo_log.read_text(encoding="utf-8").count("Inicio da coleta diaria") == 2
