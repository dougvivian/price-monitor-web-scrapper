# Este arquivo concentra tudo o que conversa com o banco de dados SQLite.
# O resto do projeto nao precisa saber SQL: so chama as funcoes daqui.
#
# SQLite e um banco de dados guardado em um unico arquivo (dados/monitor.db).
# O modulo sqlite3 ja vem com o Python, nao precisa instalar nada.
import sqlite3


# Comandos SQL que criam as tabelas.
# "IF NOT EXISTS" faz o comando nao dar erro quando a tabela ja existe,
# entao podemos rodar isso toda vez que o programa abre o banco.
#
# Tipos usados:
#   INTEGER = numero inteiro
#   REAL    = numero com casas decimais (preco)
#   TEXT    = texto. O SQLite nao tem tipo proprio de data; guardamos a data como
#             texto no formato "AAAA-MM-DD HH:MM:SS", que ordena corretamente.
#
# "id INTEGER PRIMARY KEY AUTOINCREMENT" cria um numero unico para cada linha,
# preenchido automaticamente pelo banco (1, 2, 3...).
# "NOT NULL" obriga a coluna a ter valor.
CRIAR_TABELAS = """
CREATE TABLE IF NOT EXISTS coletas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id TEXT NOT NULL,
    concorrente TEXT NOT NULL,
    produto_nome TEXT NOT NULL,
    ean TEXT,
    preco REAL,
    status_produto TEXT NOT NULL,
    mensagem TEXT,
    url TEXT NOT NULL,
    data_coleta TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS erros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id TEXT NOT NULL,
    concorrente TEXT NOT NULL,
    url TEXT NOT NULL,
    tipo_erro TEXT NOT NULL,
    mensagem TEXT,
    data_erro TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alertas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    produto_id TEXT NOT NULL,
    concorrente TEXT NOT NULL,
    url TEXT NOT NULL,
    preco_anterior REAL NOT NULL,
    preco_novo REAL NOT NULL,
    variacao_percentual REAL NOT NULL,
    data_alerta TEXT NOT NULL
);

-- Um indice funciona como o indice de um livro: deixa rapida a busca por produto,
-- mesmo quando a tabela tiver milhares de coletas.
CREATE INDEX IF NOT EXISTS idx_coletas_produto ON coletas (produto_id);
"""


def conectar(caminho_banco):
    # Abre o arquivo do banco (se nao existir, o SQLite cria um vazio).
    conexao = sqlite3.connect(caminho_banco)

    # Row faz cada linha lida se comportar como um dicionario: linha["preco"].
    # Sem isso, cada linha seria uma tupla e teriamos que usar linha[4].
    conexao.row_factory = sqlite3.Row

    # executescript roda varios comandos SQL de uma vez.
    conexao.executescript(CRIAR_TABELAS)
    atualizar_tabelas(conexao)

    return conexao


def atualizar_tabelas(conexao):
    # "CREATE TABLE IF NOT EXISTS" nao mexe numa tabela que ja existe. Entao, quando uma
    # versao nova do programa precisa de uma coluna nova, um banco criado antes nao a tem.
    # Aqui conferimos as colunas e acrescentamos as que faltam, SEM apagar os dados.
    # (Isso se chama "migracao" do banco de dados.)

    # PRAGMA table_info lista as colunas de uma tabela; a chave "name" e o nome da coluna.
    colunas_coletas = [coluna["name"] for coluna in conexao.execute("PRAGMA table_info(coletas)")]

    if "ean" not in colunas_coletas:
        # ALTER TABLE ... ADD COLUMN acrescenta a coluna; as linhas antigas ficam com NULL nela.
        conexao.execute("ALTER TABLE coletas ADD COLUMN ean TEXT")
        conexao.commit()


# ---------------------------------------------------------------------------
# Gravacao
# ---------------------------------------------------------------------------
# Os "?" sao lugares reservados para os valores. O sqlite3 encaixa cada valor
# com seguranca, em vez de montarmos o texto do SQL na mao. Isso evita o
# "SQL injection" (quando um texto malicioso vira parte do comando SQL).
#
# conexao.commit() confirma a gravacao no arquivo. Fazemos commit a cada linha
# para nao perder o que ja foi coletado se o programa parar no meio.

def salvar_coleta(conexao, dados_produto):
    # No banco, produto sem preco fica NULL (vazio de verdade), e nao texto vazio "".
    preco = dados_produto["preco_numero"]

    if preco == "":
        preco = None

    # Mesmo cuidado com o EAN. Usamos get() porque nem todo dicionario de coleta
    # precisa trazer o EAN (ex.: coletas montadas nos testes).
    ean = dados_produto.get("ean") or None

    conexao.execute(
        """
        INSERT INTO coletas
            (produto_id, concorrente, produto_nome, ean, preco, status_produto, mensagem, url, data_coleta)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            dados_produto["produto_id"],
            dados_produto["concorrente"],
            dados_produto["produto_nome"],
            ean,
            preco,
            dados_produto["status_produto"],
            dados_produto["mensagem"],
            dados_produto["url"],
            dados_produto["data_coleta"],
        ),
    )
    conexao.commit()


def salvar_erro(conexao, erro):
    conexao.execute(
        """
        INSERT INTO erros (produto_id, concorrente, url, tipo_erro, mensagem, data_erro)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (
            erro["produto_id"],
            erro["concorrente"],
            erro["url"],
            erro["tipo_erro"],
            erro["mensagem"],
            erro["data_erro"],
        ),
    )
    conexao.commit()


def salvar_alerta(conexao, alerta):
    conexao.execute(
        """
        INSERT INTO alertas
            (produto_id, concorrente, url, preco_anterior, preco_novo, variacao_percentual, data_alerta)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            alerta["produto_id"],
            alerta["concorrente"],
            alerta["url"],
            alerta["preco_anterior"],
            alerta["preco_novo"],
            alerta["variacao_percentual"],
            alerta["data_alerta"],
        ),
    )
    conexao.commit()


# ---------------------------------------------------------------------------
# Consultas
# ---------------------------------------------------------------------------

def buscar_ultimos_precos(conexao):
    # Ultimo preco salvo de cada produto, ignorando coletas sem preco (indisponivel).
    #
    # Como o id cresce a cada linha gravada, a coleta mais recente de cada produto
    # e a de MAIOR id. A subconsulta acha esse id por produto:
    #   GROUP BY produto_id  -> junta as linhas de cada produto
    #   MAX(id)              -> pega o maior id de cada grupo
    # A consulta de fora busca o preco dessas linhas.
    linhas = conexao.execute(
        """
        SELECT produto_id, preco
        FROM coletas
        WHERE id IN (
            SELECT MAX(id)
            FROM coletas
            WHERE preco IS NOT NULL
            GROUP BY produto_id
        )
        """
    ).fetchall()

    # Transformamos o resultado em um dicionario produto_id -> preco.
    return {linha["produto_id"]: linha["preco"] for linha in linhas}


def buscar_ultimos_alertas(conexao):
    # Preco que gerou o ultimo alerta de cada produto (mesma logica da funcao acima).
    linhas = conexao.execute(
        """
        SELECT produto_id, preco_novo
        FROM alertas
        WHERE id IN (SELECT MAX(id) FROM alertas GROUP BY produto_id)
        """
    ).fetchall()

    return {linha["produto_id"]: linha["preco_novo"] for linha in linhas}


def listar_coletas(conexao):
    # Todas as coletas, da mais antiga para a mais recente.
    # dict(linha) transforma cada linha do banco em um dicionario comum do Python.
    linhas = conexao.execute("SELECT * FROM coletas ORDER BY id").fetchall()
    return [dict(linha) for linha in linhas]


def listar_erros(conexao):
    linhas = conexao.execute("SELECT * FROM erros ORDER BY id").fetchall()
    return [dict(linha) for linha in linhas]


def listar_alertas(conexao):
    linhas = conexao.execute("SELECT * FROM alertas ORDER BY id").fetchall()
    return [dict(linha) for linha in linhas]
