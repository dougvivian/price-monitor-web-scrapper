const buscaProduto = document.querySelector("#buscaProduto");
const contadorFiltro = document.querySelector("#contadorFiltro");
const botoesFiltro = document.querySelectorAll(".filtro-status");
const cardsProdutos = document.querySelectorAll(".produto-card");
let statusSelecionado = "todos";

function aplicarFiltros() {
    const termoBusca = buscaProduto.value.trim().toLowerCase();
    let totalVisivel = 0;

    cardsProdutos.forEach((card) => {
        const textoBusca = card.dataset.busca;
        const status = card.dataset.status;
        const combinaBusca = textoBusca.includes(termoBusca);
        const combinaStatus = statusSelecionado === "todos" || status === statusSelecionado;
        const visivel = combinaBusca && combinaStatus;

        card.style.display = visivel ? "" : "none";

        if (visivel) {
            totalVisivel += 1;
        }
    });

    contadorFiltro.textContent = `${totalVisivel} produto(s) encontrado(s)`;
}

buscaProduto.addEventListener("input", aplicarFiltros);

botoesFiltro.forEach((botao) => {
    botao.addEventListener("click", () => {
        statusSelecionado = botao.dataset.status;

        botoesFiltro.forEach((item) => item.classList.remove("ativo"));
        botao.classList.add("ativo");

        aplicarFiltros();
    });
});

aplicarFiltros();
