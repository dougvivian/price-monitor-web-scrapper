# Testes das regras de validacao de preco.
# Sao funcoes "puras": recebem numeros e devolvem numeros/True/False,
# sem ler arquivos nem acessar o site. Por isso sao faceis de testar.
import pytest

from main import calcular_variacao, validar_preco


@pytest.mark.parametrize(
    "preco_anterior, preco_novo, variacao_esperada",
    [
        (100, 150, 0.5),    # subiu 50%
        (100, 40, -0.6),    # caiu 60%
        (61.9, 61.9, 0.0),  # nao mudou
    ],
)
def test_calcular_variacao(preco_anterior, preco_novo, variacao_esperada):
    # pytest.approx compara numeros com casas decimais sem sofrer com
    # pequenos erros de arredondamento do float (ex.: 0.30000000000000004).
    assert calcular_variacao(preco_anterior, preco_novo) == pytest.approx(variacao_esperada)


def test_primeira_coleta_sempre_e_valida():
    # Sem preco anterior nao ha com o que comparar.
    assert validar_preco(None, 999.9, None) is True


def test_variacao_pequena_e_valida():
    assert validar_preco(100, 120, None) is True
    assert validar_preco(100, 80, None) is True


def test_variacao_exatamente_no_limite_e_valida():
    # O limite e 50%: exatamente 50% ainda e aceito.
    assert validar_preco(100, 150, None) is True
    assert validar_preco(100, 50, None) is True


def test_alta_absurda_vira_alerta():
    assert validar_preco(36.9, 114.9, None) is False


def test_queda_absurda_vira_alerta():
    # Ex.: o site mostrar R$6,19 por erro de digitacao em vez de R$61,90.
    assert validar_preco(61.9, 6.19, None) is False


def test_mesmo_preco_do_alerta_anterior_e_confirmado():
    # Na coleta anterior, 114.9 gerou alerta. Agora o site mostrou 114.9 de novo:
    # o preco foi confirmado duas vezes seguidas e passa a ser aceito.
    assert validar_preco(36.9, 114.9, 114.9) is True


def test_preco_diferente_do_alerta_anterior_continua_alerta():
    # O alerta anterior era de 114.9; agora veio 200. Nao e confirmacao.
    assert validar_preco(36.9, 200, 114.9) is False
