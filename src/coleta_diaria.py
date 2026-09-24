# Roda a coleta de precos e, em seguida, gera o relatorio HTML.
# E este arquivo que o Agendador de Tarefas do Windows executa todo dia.
#
# Como o agendador roda em segundo plano (sem janela de terminal), tudo o que o programa
# imprimiria na tela e gravado em logs/coleta_diaria.log. Assim da para conferir depois
# se a coleta rodou e se deu algum erro.
#
# Tambem pode ser rodado na mao:  python src/coleta_diaria.py
import contextlib
import traceback
from datetime import datetime
from pathlib import Path

import gerar_relatorio
# O arquivo main.py tem uma funcao chamada main(). Para nao confundir o modulo
# com a funcao, importamos o modulo com outro nome: coleta.
import main as coleta


PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_LOG = PASTA_PROJETO / "logs" / "coleta_diaria.log"


def agora():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def main():
    ARQUIVO_LOG.parent.mkdir(exist_ok=True)

    # "a" acrescenta no fim do arquivo: o log guarda todas as execucoes, uma embaixo da outra.
    with open(ARQUIVO_LOG, "a", encoding="utf-8") as arquivo_log:
        # redirect_stdout/redirect_stderr desviam para o arquivo de log tudo o que seria
        # impresso no terminal (os print() e as mensagens de erro).
        with contextlib.redirect_stdout(arquivo_log), contextlib.redirect_stderr(arquivo_log):
            print(f"===== Inicio da coleta diaria: {agora()}")

            try:
                coleta.main()
                gerar_relatorio.main()
            except Exception:
                # Qualquer erro inesperado fica registrado no log, com o detalhe de onde ocorreu.
                print("ERRO durante a coleta diaria:")
                traceback.print_exc()

            print(f"===== Fim: {agora()}\n")


if __name__ == "__main__":
    main()
