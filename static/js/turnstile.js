(function () {
    var page = document.getElementById("turnstile-page");
    if (!page) {
        return;
    }

    var searchUrl = page.getAttribute("data-search-url");
    var reasonOther = page.getAttribute("data-reason-other");
    var form = document.getElementById("turnstile-form");
    var clientInput = document.getElementById("id_client_id");
    var personInput = form.querySelector('input[name="person_name"]');
    var reasonSelect = form.querySelector('select[name="reason"]');
    var customReasonInput = form.querySelector('input[name="custom_reason"]');

    var searchBlock = document.getElementById("turnstile-search-block");
    var searchField = document.getElementById("turnstile-client-search");
    var searchResults = document.getElementById("turnstile-search-results");
    var clientActions = document.getElementById("turnstile-client-actions");
    var noClientBtn = document.getElementById("turnstile-no-client-btn");
    var noClientFromSelectedBtn = document.getElementById("turnstile-no-client-from-selected-btn");
    var selectedBlock = document.getElementById("turnstile-selected-client");
    var selectedAvatar = document.getElementById("turnstile-selected-avatar");
    var selectedName = document.getElementById("turnstile-selected-name");
    var selectedMeta = document.getElementById("turnstile-selected-meta");
    var changeClientBtn = document.getElementById("turnstile-change-client-btn");
    var backToSearchBtn = document.getElementById("turnstile-back-to-search-btn");
    var accessWarning = document.getElementById("turnstile-access-warning");
    var personBlock = document.getElementById("turnstile-person-block");
    var customReasonBlock = document.getElementById("turnstile-custom-reason-block");

    var searchTimer = null;

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

    function fillAvatar(slot, photoUrl) {
        if (!slot) {
            return;
        }
        if (photoUrl) {
            slot.innerHTML = '<img class="search-result-avatar" src="' + photoUrl + '" alt="">';
        } else {
            slot.innerHTML =
                '<span class="search-result-avatar search-result-avatar-placeholder" aria-hidden="true">?</span>';
        }
    }

    function avatarHtml(photoUrl) {
        if (photoUrl) {
            return '<img class="search-result-avatar" src="' + photoUrl + '" alt="">';
        }
        return '<span class="search-result-avatar search-result-avatar-placeholder" aria-hidden="true">?</span>';
    }

    function selectClient(client) {
        clientInput.value = String(client.id);
        personInput.value = "";
        fillAvatar(selectedAvatar, client.photo_url);
        selectedName.textContent = client.nombre;
        selectedMeta.textContent = (client.cedula || "—") + " · " + client.codigo_afiliado;
        setAccessWarning(client.access_warning || "");
        hide(searchBlock);
        hide(clientActions);
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
        hide(clientActions);
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
        show(clientActions);
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
            searchResults.innerHTML = '<div class="turnstile-search-empty">No se encontraron afiliados.</div>';
            searchResults.hidden = false;
            return;
        }

        results.forEach(function (client) {
            var button = document.createElement("button");
            button.type = "button";
            button.className = "turnstile-search-item";
            button.innerHTML =
                avatarHtml(client.photo_url) +
                '<span class="turnstile-search-item-text"><strong>' +
                client.nombre +
                "</strong>" +
                '<span class="turnstile-subtext">' +
                (client.cedula || "—") +
                " · " +
                client.codigo_afiliado +
                "</span></span>";
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
                    '<div class="turnstile-search-empty">No se pudo buscar afiliados. Intente de nuevo.</div>';
                searchResults.hidden = false;
            });
    }

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

    noClientBtn.addEventListener("click", function () {
        showGuestMode(false);
    });
    noClientFromSelectedBtn.addEventListener("click", function () {
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

    form.addEventListener("submit", function (event) {
        var hasClient = Boolean(clientInput.value);
        var hasPerson = Boolean((personInput.value || "").trim());
        if (!hasClient && !hasPerson) {
            event.preventDefault();
            if (form.querySelector(".turnstile-client-required-msg")) {
                return;
            }
            var notice = document.createElement("p");
            notice.className = "turnstile-error-text turnstile-client-required-msg";
            notice.textContent = "Seleccione un afiliado o indique el nombre de la persona.";
            personBlock.parentNode.insertBefore(notice, personBlock);
        }
    });

    if (window.turnstileInitialClient) {
        selectClient(window.turnstileInitialClient);
    } else if (window.turnstileInitialGuest) {
        showGuestMode(true);
    } else {
        showSearchMode();
    }

    toggleCustomReason();
})();
