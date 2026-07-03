(function () {
    const modal = document.getElementById("quickTurnstileModal");
    if (!modal) return;

    const searchUrl = modal.getAttribute("data-search-url");
    const reasonOther = modal.getAttribute("data-reason-other");
    const quickTurnstileBtn = document.getElementById("quickTurnstileBtn");
    const form = document.getElementById("quickTurnstileForm");
    const clientInput = document.getElementById("quick_client_id");
    const personInput = document.getElementById("quick_person_name");
    const reasonSelect = document.getElementById("quick_reason");
    const customReasonBlock = document.getElementById("quick_custom_reason_block");
    const customReasonInput = document.getElementById("quick_custom_reason");
    const unspecifiedBtn = document.getElementById("quickTurnstileUnspecifiedBtn");

    const searchBlock = document.getElementById("quick-search-block");
    const searchField = document.getElementById("quick-client-search");
    const searchResults = document.getElementById("quick-search-results");
    const noClientBtn = document.getElementById("quick-no-client-btn");
    const selectedBlock = document.getElementById("quick-selected-client");
    const selectedName = document.getElementById("quick-selected-name");
    const selectedMeta = document.getElementById("quick-selected-meta");
    const changeClientBtn = document.getElementById("quick-change-client-btn");
    const backToSearchBtn = document.getElementById("quick-back-to-search-btn");
    const accessWarning = document.getElementById("quick-access-warning");
    const personBlock = document.getElementById("quick-person-block");

    let searchTimer = null;

    function show(el) {
        el.classList.remove("is-hidden");
    }

    function hide(el) {
        el.classList.add("is-hidden");
    }

    function clearSearchResults() {
        searchResults.innerHTML = "";
        searchResults.hidden = true;
    }

    function setAccessWarning(message) {
        if (message) {
            accessWarning.textContent = message;
            show(accessWarning);
        } else {
            accessWarning.textContent = "";
            hide(accessWarning);
        }
    }

    function selectClient(client) {
        clientInput.value = String(client.id);
        personInput.value = "";
        selectedName.textContent = client.nombre;
        selectedMeta.textContent =
            (client.cedula || "—") + " · " + client.codigo_afiliado;
        setAccessWarning(client.access_warning || "");
        hide(searchBlock);
        show(selectedBlock);
        hide(personBlock);
        clearSearchResults();
        searchField.value = "";
    }

    function showGuestMode(keepPersonName) {
        clientInput.value = "";
        if (!keepPersonName) {
            personInput.value = "";
        }
        setAccessWarning("");
        hide(selectedBlock);
        hide(searchBlock);
        show(personBlock);
        clearSearchResults();
        searchField.value = "";
        personInput.focus();
    }

    function showSearchMode() {
        clientInput.value = "";
        personInput.value = "";
        setAccessWarning("");
        hide(selectedBlock);
        hide(personBlock);
        show(searchBlock);
        clearSearchResults();
        searchField.value = "";
        searchField.focus();
    }

    function toggleCustomReason() {
        if (reasonSelect.value === reasonOther) {
            show(customReasonBlock);
        } else {
            hide(customReasonBlock);
            customReasonInput.value = "";
        }
    }

    function renderResults(results) {
        searchResults.innerHTML = "";
        if (!results.length) {
            searchResults.innerHTML =
                '<div class="quick-turnstile-search-empty">No se encontraron personas.</div>';
            searchResults.hidden = false;
            return;
        }

        results.forEach(function (client) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = "quick-turnstile-search-item";
            button.innerHTML =
                "<strong>" +
                client.nombre +
                "</strong>" +
                '<span class="quick-turnstile-subtext">' +
                (client.cedula || "—") +
                " · " +
                client.codigo_afiliado +
                "</span>";
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

        fetch(searchUrl + "?q=" + encodeURIComponent(query), {
            credentials: "same-origin",
            headers: { "X-Requested-With": "XMLHttpRequest" },
        })
            .then(function (response) {
                if (!response.ok) throw new Error("search_failed");
                return response.json();
            })
            .then(function (data) {
                renderResults(data.results || []);
            })
            .catch(function () {
                searchResults.innerHTML =
                    '<div class="quick-turnstile-search-empty">No se pudo buscar. Intente de nuevo.</div>';
                searchResults.hidden = false;
            });
    }

    function resetModal() {
        form.reset();
        clientInput.value = "";
        hide(customReasonBlock);
        hide(accessWarning);
        showSearchMode();
        toggleCustomReason();
    }

    function openModal() {
        resetModal();
        modal.classList.add("show");
        setTimeout(function () {
            searchField.focus();
        }, 100);
    }

    function closeModal() {
        modal.classList.remove("show");
        resetModal();
    }

    function getPersonPayload() {
        const clientId = clientInput.value;
        const manualName = (personInput.value || "").trim();
        return { clientId: clientId, manualName: manualName };
    }

    function submitQuickOpen(reason, options) {
        options = options || {};
        const allowUnidentified = Boolean(options.allowUnidentified);
        const { clientId, manualName } = getPersonPayload();

        if (!allowUnidentified && !clientId && !manualName) {
            alert("Seleccione una persona o indique el nombre.");
            return;
        }

        if (
            reason === reasonOther &&
            !(customReasonInput.value || "").trim()
        ) {
            alert("Debe especificar el motivo.");
            return;
        }

        const formData = new FormData();
        formData.append("reason", reason);
        formData.append(
            "custom_reason",
            reason === reasonOther ? customReasonInput.value.trim() : ""
        );
        if (clientId) {
            formData.append("client_id", clientId);
        } else if (manualName) {
            formData.append("person_name", manualName);
        }
        formData.append(
            "csrfmiddlewaretoken",
            form.querySelector("[name=csrfmiddlewaretoken]").value
        );

        const submitBtn = document.getElementById("quickTurnstileSubmitBtn");
        const originalText = submitBtn.innerText;
        submitBtn.disabled = true;
        unspecifiedBtn.disabled = true;
        submitBtn.innerText = "Abriendo...";

        fetch(form.action, {
            method: "POST",
            body: formData,
            headers: { "X-Requested-With": "XMLHttpRequest" },
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                if (result.data.success) {
                    closeModal();
                    if (window.location.pathname.includes("historial-manual")) {
                        window.location.reload();
                    }
                } else {
                    alert("Error: " + (result.data.error || "No se pudo abrir."));
                }
            })
            .catch(function () {
                alert("Error al conectar con el servidor.");
            })
            .finally(function () {
                submitBtn.disabled = false;
                unspecifiedBtn.disabled = false;
                submitBtn.innerText = originalText;
            });
    }

    document.addEventListener("keydown", function (e) {
        if (e.key === "F2") {
            e.preventDefault();
            openModal();
        }
        if (e.key === "Escape" && modal.classList.contains("show")) {
            closeModal();
        }
    });

    if (quickTurnstileBtn) {
        quickTurnstileBtn.addEventListener("click", openModal);
    }

    modal.addEventListener("click", function (e) {
        if (e.target === modal) closeModal();
    });

    const closeBtn = modal.querySelector("[data-modal-close]");
    if (closeBtn) {
        closeBtn.addEventListener("click", closeModal);
    }

    searchField.addEventListener("input", function () {
        clearTimeout(searchTimer);
        const query = searchField.value.trim();
        searchTimer = setTimeout(function () {
            runSearch(query);
        }, 300);
    });

    searchField.addEventListener("keydown", function (event) {
        if (event.key === "Enter") {
            event.preventDefault();
        }
    });

    noClientBtn.addEventListener("click", function () {
        showGuestMode(false);
    });
    changeClientBtn.addEventListener("click", showSearchMode);
    backToSearchBtn.addEventListener("click", showSearchMode);
    reasonSelect.addEventListener("change", toggleCustomReason);

    document.addEventListener("click", function (event) {
        if (!searchBlock.contains(event.target)) {
            clearSearchResults();
        }
    });

    form.addEventListener("submit", function (e) {
        e.preventDefault();
        submitQuickOpen(reasonSelect.value);
    });

    unspecifiedBtn.addEventListener("click", function () {
        submitQuickOpen("unspecified", { allowUnidentified: true });
    });
})();
