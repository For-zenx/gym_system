(function () {
    var config = window.classMemberSearchConfig;
    var modal = document.getElementById("classAddMemberModal");
    var openBtn = document.getElementById("class-open-add-member-btn");
    if (!config || !modal || !openBtn) {
        return;
    }

    var form = document.getElementById("class-add-member-form");
    var clientInput = document.getElementById("class-add-member-client-id");
    var searchBlock = document.getElementById("class-member-search-block");
    var searchField = document.getElementById("class-member-search");
    var searchResults = document.getElementById("class-member-search-results");
    var selectedBlock = document.getElementById("class-member-selected");
    var selectedName = document.getElementById("class-member-selected-name");
    var selectedMeta = document.getElementById("class-member-selected-meta");
    var changeBtn = document.getElementById("class-member-change-btn");
    var submitBtn = document.getElementById("class-add-member-submit");
    var errorEl = document.getElementById("class-member-search-error");
    var searchTimer = null;

    function clearError() {
        if (!errorEl) {
            return;
        }
        errorEl.textContent = "";
        errorEl.hidden = true;
    }

    function showError(message) {
        if (!errorEl) {
            return;
        }
        errorEl.textContent = message;
        errorEl.hidden = false;
    }

    function clearSearchResults() {
        searchResults.innerHTML = "";
        searchResults.hidden = true;
    }

    function resetSelection() {
        clientInput.value = "";
        submitBtn.disabled = true;
        selectedBlock.hidden = true;
        searchBlock.hidden = false;
        searchField.value = "";
        clearSearchResults();
        clearError();
    }

    function openModal() {
        resetSelection();
        modal.classList.add("show");
        searchField.focus();
    }

    function closeModal() {
        modal.classList.remove("show");
        resetSelection();
    }

    function selectClient(client) {
        clientInput.value = String(client.id);
        selectedName.textContent = client.nombre;
        selectedMeta.textContent = client.cedula + " · " + client.codigo_afiliado;
        searchBlock.hidden = true;
        selectedBlock.hidden = false;
        submitBtn.disabled = false;
        clearSearchResults();
        clearError();
    }

    function renderResults(results) {
        searchResults.innerHTML = "";
        if (!results.length) {
            searchResults.innerHTML =
                '<div class="classes-member-search-empty">Sin resultados.</div>';
            searchResults.hidden = false;
            return;
        }

        results.forEach(function (client) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "classes-member-search-item";
            button.innerHTML =
                "<strong>" + client.nombre + "</strong>" +
                '<span class="classes-muted">' + client.cedula + " · " + client.codigo_afiliado + "</span>";
            button.addEventListener("click", function () {
                selectClient(client);
            });
            searchResults.appendChild(button);
        });
        searchResults.hidden = false;
    }

    function runSearch(query) {
        if (query.length < 2) {
            clearSearchResults();
            return;
        }

        fetch(config.searchUrl + "?q=" + encodeURIComponent(query), {
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" },
        })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("search_failed");
                }
                return response.json();
            })
            .then(function (data) {
                renderResults(data.results || []);
            })
            .catch(function () {
                searchResults.innerHTML =
                    '<div class="classes-member-search-empty">Error al buscar. Intente de nuevo.</div>';
                searchResults.hidden = false;
            });
    }

    openBtn.addEventListener("click", openModal);

    if (typeof bindDismissibleModal === "function") {
        bindDismissibleModal(modal, { onClose: closeModal });
    }

    changeBtn.addEventListener("click", function () {
        resetSelection();
        searchField.focus();
    });

    searchField.addEventListener("input", function () {
        clearTimeout(searchTimer);
        var query = searchField.value.trim();
        searchTimer = setTimeout(function () {
            runSearch(query);
        }, 300);
    });

    searchField.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
            event.preventDefault();
        }
    });

    document.addEventListener("click", function (event) {
        if (!searchBlock.contains(event.target)) {
            clearSearchResults();
        }
    });

    form.addEventListener("submit", function (event) {
        if (!clientInput.value) {
            event.preventDefault();
            showError("Seleccione un afiliado de la lista.");
        }
    });
})();
