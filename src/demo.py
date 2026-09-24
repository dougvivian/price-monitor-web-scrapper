# Modo demonstracao: gera um banco de dados FICTICIO e o relatorio a partir dele.
#
# Serve para ver o projeto funcionando sem acessar site nenhum e sem precisar de um
# cadastro real de produtos (ex.: um recrutador que clonou o repositorio).
#   - 3 lojas ficticias (Loja A, Loja B, Loja C) e produtos com nomes genericos;
#   - 30 dias de coletas simuladas: precos que sobem e descem, promocao, produto
#     indisponivel, um alerta de variacao e alguns erros de coleta;
#   - tudo vai para dados/demo.db e relatorios/demo.html. O banco real (monitor.db)
#     nao e tocado.
#
# Para rodar:  python src/demo.py
import random
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import banco
from gerar_relatorio import gerar_relatorio
from main import calcular_variacao


PASTA_PROJETO = Path(__file__).resolve().parent.parent
ARQUIVO_BANCO_DEMO = PASTA_PROJETO / "dados" / "demo.db"
ARQUIVO_RELATORIO_DEMO = PASTA_PROJETO / "relatorios" / "demo.html"

DIAS_DE_HISTORICO = 30

# Semente fixa: os numeros "aleatorios" saem sempre iguais, entao a demonstracao
# (e os testes dela) dao o mesmo resultado toda vez.
SEMENTE = 42

LOJAS = {
    "Loja A": ("PRD-0", "https://www.loja-a.exemplo.com.br"),
    "Loja B": ("PRD-1", "https://www.loja-b.exemplo.com.br"),
    "Loja C": ("PRD-2", "https://www.loja-c.exemplo.com.br"),
}

# Catalogo ficticio: (grupo, categoria, nome, {loja: (preco_inicial, marca)}).
# Mesma marca em lojas diferentes = mesmo produto = mesmo EAN.
# Grupo vazio: o produto so e comparado se o EAN for igual (casamento automatico).
CATALOGO = [
    ("", "telha", "Telha Fibrocimento Ondulada 6mm 2,44 x 1,10m",
     {"Loja A": (64.90, "Marca X"), "Loja B": (69.90, "Marca X"), "Loja C": (62.90, "Marca X")}),
    ("TELHA-6MM-1.83", "telha", "Telha Fibrocimento Ondulada 6mm 1,83 x 1,10m",
     {"Loja A": (54.90, "Marca X"), "Loja B": (52.90, "Marca Y")}),
    ("TELHA-5MM-2.44", "telha", "Telha Fibrocimento Ondulada 5mm 2,44 x 1,10m",
     {"Loja A": (49.90, "Marca Y"), "Loja C": (54.90, "Marca X")}),
    ("CIMENTO-CPII-50", "cimento", "Cimento CP II-F 32 50kg",
     {"Loja A": (39.90, "Marca Z"), "Loja B": (36.90, "Marca Z"), "Loja C": (41.50, "Marca Z")}),
    ("CIMENTO-CPIV-50", "cimento", "Cimento CP IV 32 50kg",
     {"Loja A": (44.90, "Marca Z"), "Loja B": (47.90, "Marca W")}),
    ("VERGALHAO-CA50-10", "aco", "Vergalhao CA50 10mm 12m",
     {"Loja A": (53.90, "Usina 1"), "Loja B": (58.90, "Usina 2"), "Loja C": (49.90, "Usina 1")}),
    ("VERGALHAO-CA50-8", "aco", "Vergalhao CA50 8mm 12m",
     {"Loja A": (36.90, "Usina 1"), "Loja C": (34.90, "Usina 2")}),
    ("VERGALHAO-CA60-5", "aco", "Vergalhao CA60 5mm 12m",
     {"Loja A": (21.90, "Usina 2"), "Loja B": (22.50, "Usina 2")}),
    ("MALHA-15X15-4.2", "aco", "Malha Pop 15x15 4,2mm 2 x 3m",
     {"Loja A": (89.90, "Usina 1"), "Loja B": (96.90, "Usina 1")}),
    ("ARGAMASSA-ACII-20", "argamassa", "Argamassa AC-II 20kg",
     {"Loja A": (18.90, "Marca Q"), "Loja B": (16.90, "Marca Q"), "Loja C": (19.90, "Marca R")}),
    ("AREIA-MEDIA-20", "agregado", "Areia Media Saco 20kg",
     {"Loja A": (6.90, "Marca S"), "Loja C": (7.50, "Marca S")}),
    ("TINTA-FOSCA-18", "tinta", "Tinta Acrilica Fosca Branca 18L",
     {"Loja A": (389.90, "Marca T"), "Loja B": (419.90, "Marca T"), "Loja C": (399.90, "Marca T")}),
    ("TINTA-FOSCA-3.6", "tinta", "Tinta Acrilica Fosca Branca 3,6L",
     {"Loja A": (119.90, "Marca T"), "Loja B": (109.90, "Marca T")}),
    ("PORCELANATO-60X60", "porcelanato", "Porcelanato Acetinado Cinza 60x60 (m2)",
     {"Loja A": (69.90, "Marca P"), "Loja C": (64.90, "Marca P")}),
    ("BLOCO-9-FUROS", "bloco", "Bloco Ceramico 9 Furos 14x19x29",
     {"Loja A": (1.89, "Olaria 1"), "Loja B": (1.99, "Olaria 1"), "Loja C": (1.79, "Olaria 2")}),
    ("CAIXA-AGUA-1000", "hidraulica", "Caixa d'Agua Polietileno 1000L",
     {"Loja A": (449.90, "Marca H"), "Loja B": (469.90, "Marca H")}),
    # Produtos sem equivalente em outra loja: aparecem em Produtos, mas nao no Comparador.
    ("", "placa cimenticia", "Placa Cimenticia 8mm 1,20 x 2,40m", {"Loja A": (189.90, "Marca X")}),
    ("", "telha", "Cumeeira Fibrocimento 6mm", {"Loja B": (39.90, "Marca Y")}),
]


def calcular_digito_verificador(corpo):
    # Mesma regra do GTIN usada em main.ean_valido: pesos 3, 1, 3, 1... da direita para
    # a esquerda; o digito completa a soma ate o proximo multiplo de 10.
    soma = sum(
        int(digito) * (3 if posicao % 2 == 0 else 1)
        for posicao, digito in enumerate(reversed(corpo))
    )
    return str((10 - soma % 10) % 10)


def gerar_ean(numero):
    # EAN-13 ficticio e valido. "789" e o prefixo do Brasil; o resto e um contador.
    corpo = f"789{numero:09d}"
    return corpo + calcular_digito_verificador(corpo)


def criar_slug(texto):
    # "Cimento CP II-F 32 50kg" -> "cimento-cp-ii-f-32-50kg" (para montar URLs ficticias).
    permitido = "".join(letra if letra.isalnum() else "-" for letra in texto.lower())
    return "-".join(parte for parte in permitido.split("-") if parte)


def montar_produtos_demo():
    # Transforma o CATALOGO numa lista de produtos (um por loja), no formato do cadastro,
    # com os campos extras que a simulacao usa (preco inicial e EAN).
    produtos = []
    eans = {}                       # (nome, marca) -> EAN: mesma marca, mesmo EAN
    contador_por_loja = {loja: 0 for loja in LOJAS}

    for grupo, categoria, nome, ofertas in CATALOGO:
        for loja, (preco_inicial, marca) in ofertas.items():
            contador_por_loja[loja] += 1
            prefixo_id, site = LOJAS[loja]
            chave_ean = (nome, marca)

            if chave_ean not in eans:
                eans[chave_ean] = gerar_ean(len(eans) + 1)

            produtos.append({
                "produto_id": f"{prefixo_id}{contador_por_loja[loja]:02d}",
                "concorrente": loja,
                "produto_nome": f"{nome} {marca}",
                "url": f"{site}/{criar_slug(nome + ' ' + marca)}/p",
                "categoria": categoria,
                "grupo": grupo,
                "ean": eans[chave_ean],
                "preco_inicial": preco_inicial,
            })

    return produtos


def arredondar_preco(preco):
    # Precos de loja costumam terminar em ,90. Itens baratos (ex.: bloco) terminam em ,x9.
    if preco < 10:
        return round(round(preco, 1) - 0.01, 2)

    return int(preco) + 0.90


def simular_dia(sorteio, produto, preco_atual, dia):
    # Decide o que acontece com um produto num dia da simulacao.
    # Devolve (evento, preco): evento e "coleta", "indisponivel", "alerta" ou "erro".
    nome, loja = produto["produto_nome"], produto["concorrente"]

    # Roteiro fixo, para a demonstracao sempre mostrar todos os casos:
    if loja == "Loja B" and nome.startswith("Cimento CP IV") and 20 <= dia <= 24:
        return "indisponivel", preco_atual
    if loja == "Loja C" and nome.startswith("Vergalhao CA50 10mm") and dia == 15:
        # O site mostrou um preco absurdo (erro de cadastro da loja): vira alerta.
        return "alerta", 4.99
    if loja == "Loja B" and nome.startswith("Tinta Acrilica Fosca Branca 18L") and dia == DIAS_DE_HISTORICO - 3:
        return "coleta", arredondar_preco(preco_atual * 0.88)       # promocao
    if loja == "Loja C" and nome.startswith("Areia") and dia == DIAS_DE_HISTORICO - 1:
        return "erro", preco_atual

    # Fora do roteiro: pequenas mudancas de preco e erros de coleta raros, por sorteio.
    if sorteio.random() < 0.015:
        return "erro", preco_atual
    if sorteio.random() < 0.08 or (dia == DIAS_DE_HISTORICO - 1 and sorteio.random() < 0.25):
        # O preco tende a voltar para perto do inicial: se ja subiu mais de 8%, so desce;
        # se ja caiu mais de 8%, so sobe. Assim a simulacao nao "passeia" para valores irreais.
        proporcao = preco_atual / produto["preco_inicial"]
        mudancas = [-0.06, -0.04, -0.03, 0.03, 0.04, 0.05]

        if proporcao > 1.08:
            mudancas = [-0.06, -0.04, -0.03]
        elif proporcao < 0.92:
            mudancas = [0.03, 0.04, 0.05]

        return "coleta", arredondar_preco(preco_atual * (1 + sorteio.choice(mudancas)))

    return "coleta", preco_atual


def criar_dados_demo(arquivo_banco, hoje=None):
    # Cria o banco ficticio com DIAS_DE_HISTORICO dias de coletas, um por dia as 9h.
    # Devolve o cadastro (lista de produtos), usado pelo relatorio para grupos e categorias.
    sorteio = random.Random(SEMENTE)
    hoje = hoje or datetime.now()
    produtos = montar_produtos_demo()
    precos = {produto["produto_id"]: produto["preco_inicial"] for produto in produtos}

    # Montamos o banco na MEMORIA e so no fim copiamos para o arquivo.
    # Motivo: cada funcao do banco.py faz commit, e cada commit num arquivo espera o disco
    # gravar. Com ~1.000 coletas simuladas isso levava minutos; em memoria leva segundos.
    conexao = banco.conectar(":memory:")

    try:
        for dia in range(DIAS_DE_HISTORICO):
            data = (hoje - timedelta(days=DIAS_DE_HISTORICO - 1 - dia)).replace(
                hour=9, minute=0, second=0, microsecond=0
            )
            inicio = data.strftime("%Y-%m-%d %H:%M:%S")
            execucao_id = banco.iniciar_execucao(conexao, inicio)
            resultados = {"coletado": 0, "erro": 0, "alerta": 0}

            for posicao, produto in enumerate(produtos):
                # Cada produto e "coletado" alguns segundos depois do anterior.
                momento = (data + timedelta(seconds=2 * posicao + 1)).strftime("%Y-%m-%d %H:%M:%S")
                evento, preco = simular_dia(sorteio, produto, precos[produto["produto_id"]], dia)
                base = {chave: produto[chave] for chave in ("produto_id", "concorrente", "url")}

                if evento == "erro":
                    banco.salvar_erro(conexao, {
                        **base,
                        "tipo_erro": "extracao",
                        "mensagem": "JSON-LD do produto nao encontrado na pagina.",
                        "data_erro": momento,
                    })
                    resultados["erro"] += 1
                    continue

                if evento == "alerta":
                    preco_anterior = precos[produto["produto_id"]]
                    banco.salvar_alerta(conexao, {
                        **base,
                        "preco_anterior": preco_anterior,
                        "preco_novo": preco,
                        "variacao_percentual": round(calcular_variacao(preco_anterior, preco) * 100, 1),
                        "data_alerta": momento,
                    })
                    resultados["alerta"] += 1
                    continue

                disponivel = evento == "coleta"
                banco.salvar_coleta(conexao, {
                    **base,
                    "produto_nome": produto["produto_nome"],
                    "ean": produto["ean"],
                    "preco_numero": preco if disponivel else "",
                    "status_produto": "disponivel" if disponivel else "indisponivel",
                    "mensagem": "" if disponivel else f"OutOfStock (preco anunciado: R${preco:.2f})".replace(".", ","),
                    "data_coleta": momento,
                })
                precos[produto["produto_id"]] = preco
                resultados["coletado"] += 1

            fim = (data + timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")
            banco.finalizar_execucao(conexao, execucao_id, fim, len(produtos), resultados)

        # Comecamos sempre de um arquivo vazio (a demonstracao e recriada a cada execucao)
        # e copiamos o banco da memoria para ele de uma vez so, com backup().
        arquivo_banco.unlink(missing_ok=True)
        destino = sqlite3.connect(arquivo_banco)

        try:
            conexao.backup(destino)
        finally:
            destino.close()
    finally:
        conexao.close()

    return produtos


def main():
    cadastro = criar_dados_demo(ARQUIVO_BANCO_DEMO)
    print(f"Banco de demonstracao criado: {ARQUIVO_BANCO_DEMO} "
          f"({len(cadastro)} produtos, {DIAS_DE_HISTORICO} dias de historico)")
    gerar_relatorio(ARQUIVO_BANCO_DEMO, ARQUIVO_RELATORIO_DEMO, cadastro)
    print("Abra o arquivo no navegador para ver a demonstracao.")


if __name__ == "__main__":
    main()
