// =====================================================================
// Interacao do relatorio (copiado para dentro do relatorio.html ao gerar).
// JavaScript puro, sem biblioteca. Cada parte abaixo e independente:
//   1. Abas (menu lateral)   2. Filtros e ordenacao da tabela de produtos
//   3. Comparador            4. Historico
// =====================================================================

// ---------- 1. Abas ----------
// A aba aberta fica no endereco da pagina, depois do "#": relatorio.html#comparador.
// Assim, recarregar a pagina mantem a aba, e da para mandar o link direto de uma aba.
// O Historico aceita tambem o produto: #historico/PRD-001.

const ABA_PADRAO = "visao-geral";
const abas = document.querySelectorAll(".aba");
const linksMenu = document.querySelectorAll(".menu a");

function lerEndereco() {
    // "#historico/PRD-001" -> { aba: "historico", produto: "PRD-001" }
    const [aba, produto] = decodeURIComponent(location.hash.slice(1)).split("/");
    // As secoes tem id "aba-<nome>" (e nao so "<nome>") de proposito: se o id fosse igual
    // ao do endereco, o navegador rolaria a pagina sozinho ate a secao ao abrir o link.
    const existe = document.getElementById(`aba-${aba}`) !== null;
    return { aba: existe ? aba : ABA_PADRAO, produto: produto || "" };
}

function abrirAba() {
    const { aba, produto } = lerEndereco();

    abas.forEach((secao) => secao.classList.toggle("ativa", secao.id === `aba-${aba}`));
    linksMenu.forEach((link) => {
        if (link.dataset.aba === aba) {
            link.setAttribute("aria-current", "page");
        } else {
            link.removeAttribute("aria-current");
        }
    });

    if (aba === "historico") {
        mostrarHistorico(produto);
    }

    window.scrollTo(0, 0);
}

window.addEventListener("hashchange", abrirAba);

// ---------- 2. Produtos: busca, filtros e ordenacao ----------

const buscaProduto = document.querySelector("#buscaProduto");
const filtroLoja = document.querySelector("#filtroLoja");
const filtroCategoria = document.querySelector("#filtroCategoria");
const filtroStatus = document.querySelector("#filtroStatus");
const contadorProdutos = document.querySelector("#contadorProdutos");
const tabelaProdutos = document.querySelector("#tabelaProdutos");
const linhasProdutos = tabelaProdutos ? [...tabelaProdutos.querySelectorAll("tbody tr[data-busca]")] : [];

function filtrarProdutos() {
    const termo = buscaProduto.value.trim().toLowerCase();
    let visiveis = 0;

    linhasProdutos.forEach((linha) => {
        // Cada filtro vazio ("Todas") aceita qualquer valor.
        const visivel =
            linha.dataset.busca.includes(termo) &&
            (!filtroLoja.value || linha.dataset.loja === filtroLoja.value) &&
            (!filtroCategoria.value || linha.dataset.categoria === filtroCategoria.value) &&
            (!filtroStatus.value || linha.dataset.status === filtroStatus.value);

        linha.hidden = !visivel;
        visiveis += visivel ? 1 : 0;
    });

    contadorProdutos.textContent = `${visiveis} de ${linhasProdutos.length} produto(s)`;
}

[buscaProduto, filtroLoja, filtroCategoria, filtroStatus].forEach((campo) => {
    campo.addEventListener("input", filtrarProdutos);
});

function compararValores(a, b) {
    // Numeros comparados como numero ("9.9" < "10"); o resto como texto em portugues.
    // Celula vazia (ex.: produto sem preco) vai sempre para o fim.
    if (a === "" || b === "") {
        return (a === "") - (b === "");
    }
    const numeroA = Number(a);
    const numeroB = Number(b);
    if (!Number.isNaN(numeroA) && !Number.isNaN(numeroB)) {
        return numeroA - numeroB;
    }
    return a.localeCompare(b, "pt-BR");
}

function ativarOrdenacao(tabela) {
    const cabecalhos = tabela.querySelectorAll("thead th");

    cabecalhos.forEach((th, coluna) => {
        if (th.textContent.trim() === "Link") {
            return;
        }

        // Transformamos o titulo em botao: assim ele funciona tambem pelo teclado.
        const botao = document.createElement("button");
        botao.type = "button";
        botao.className = "ordenar";
        botao.textContent = th.textContent;
        th.textContent = "";
        th.appendChild(botao);

        botao.addEventListener("click", () => {
            // Clicar de novo na mesma coluna inverte a ordem.
            const crescente = th.getAttribute("aria-sort") !== "ascending";
            cabecalhos.forEach((outro) => outro.removeAttribute("aria-sort"));
            th.setAttribute("aria-sort", crescente ? "ascending" : "descending");

            const corpo = tabela.querySelector("tbody");
            const linhas = [...corpo.querySelectorAll("tr[data-busca]")];
            linhas.sort((linhaA, linhaB) => {
                const a = linhaA.cells[coluna].dataset.valor ?? "";
                const b = linhaB.cells[coluna].dataset.valor ?? "";
                return crescente ? compararValores(a, b) : compararValores(b, a);
            });
            // appendChild de uma linha que ja existe apenas a move para o fim: reordena a tabela.
            linhas.forEach((linha) => corpo.appendChild(linha));
        });
    });
}

if (tabelaProdutos) {
    ativarOrdenacao(tabelaProdutos);
}

// ---------- 3. Comparador: filtro de categoria e ordenacao ----------

const listaComparativos = document.querySelector("#listaComparativos");
const filtroCategoriaComparador = document.querySelector("#filtroCategoriaComparador");
const ordemComparador = document.querySelector("#ordemComparador");
const cardsComparativos = [...document.querySelectorAll(".comparativo")];

function atualizarComparador() {
    const categoria = filtroCategoriaComparador.value;

    cardsComparativos.forEach((card) => {
        card.hidden = Boolean(categoria) && card.dataset.categoria !== categoria;
    });

    const porNome = ordemComparador.value === "nome";
    cardsComparativos.sort((a, b) =>
        porNome
            ? a.dataset.nome.localeCompare(b.dataset.nome, "pt-BR")
            : Number(b.dataset.diferenca) - Number(a.dataset.diferenca)
    );
    cardsComparativos.forEach((card) => listaComparativos.appendChild(card));
}

filtroCategoriaComparador.addEventListener("input", atualizarComparador);
ordemComparador.addEventListener("input", atualizarComparador);

// ---------- 4. Historico: um produto por vez ----------

const seletorHistorico = document.querySelector("#seletorHistorico");
const paineisHistorico = document.querySelectorAll(".painel-historico");

function mostrarHistorico(produto) {
    // Sem produto no endereco, mostra o que estiver escolhido no seletor (o primeiro).
    const escolhido = produto || seletorHistorico.value;
    seletorHistorico.value = escolhido;
    paineisHistorico.forEach((painel) => {
        painel.classList.toggle("ativo", painel.dataset.produto === escolhido);
    });
}

seletorHistorico.addEventListener("input", () => {
    // Trocar o produto muda o endereco; o evento "hashchange" mostra o painel certo.
    location.hash = `historico/${seletorHistorico.value}`;
});

// ---------- Inicio ----------
atualizarComparador();
filtrarProdutos();
abrirAba();
