(function (window) {
    'use strict';

    const AUTO_PLACEHOLDER = 'Buscar por nombre, cédula o código...';
    const CODE_PLACEHOLDER = 'Ej. 32';

    function parseModeValue(value) {
        if (!value || value === 'auto') {
            return { mode: 'auto', prefix: null };
        }
        if (value.startsWith('code:')) {
            return { mode: 'code', prefix: value.slice(5).toUpperCase() };
        }
        return { mode: 'auto', prefix: null };
    }

    function formatPersonMeta(person) {
        const parts = [];
        if (person.cedula) {
            parts.push('Cédula ' + person.cedula);
        }
        if (person.codigo_afiliado) {
            parts.push('Código ' + person.codigo_afiliado);
        }
        return parts.join(' · ') || '—';
    }

    function buildSearchUrl(searchUrl, query, modeValue) {
        const parsed = parseModeValue(modeValue);
        const params = new URLSearchParams({ q: query, mode: parsed.mode });
        if (parsed.mode === 'code' && parsed.prefix) {
            params.set('prefix', parsed.prefix);
        }
        return searchUrl + '?' + params.toString();
    }

    function minQueryLength(modeValue) {
        return parseModeValue(modeValue).mode === 'code' ? 1 : 2;
    }

    function initPersonSearchBar(options) {
        const root = options.root;
        if (!root) return null;

        const modeSelect = root.querySelector('[data-person-search-mode]');
        const searchInput = root.querySelector('[data-person-search-input]');
        const prefixEl = root.querySelector('[data-person-search-prefix]');
        const resultsContainer = options.resultsContainer;
        const emptyState = options.emptyState;
        const loadingState = options.loadingState;
        const searchUrl = options.searchUrl;
        const onResultClick = options.onResultClick;

        if (!modeSelect || !searchInput || !resultsContainer || !searchUrl) {
            return null;
        }

        let searchTimer = null;

        function clearResults() {
            resultsContainer.innerHTML = '';
            resultsContainer.hidden = true;
            if (emptyState) emptyState.hidden = true;
            if (loadingState) loadingState.hidden = true;
        }

        function applyModeUi() {
            const parsed = parseModeValue(modeSelect.value);
            const isCodeMode = parsed.mode === 'code';

            if (prefixEl) {
                if (isCodeMode && parsed.prefix) {
                    prefixEl.textContent = parsed.prefix + '-';
                    prefixEl.hidden = false;
                    prefixEl.removeAttribute('aria-hidden');
                    searchInput.classList.add('has-code-prefix');
                } else {
                    prefixEl.hidden = true;
                    prefixEl.setAttribute('aria-hidden', 'true');
                    searchInput.classList.remove('has-code-prefix');
                }
            }

            searchInput.placeholder = isCodeMode ? CODE_PLACEHOLDER : AUTO_PLACEHOLDER;
            searchInput.inputMode = isCodeMode ? 'numeric' : 'text';
            searchInput.pattern = isCodeMode ? '[0-9]*' : null;
        }

        function sanitizeInputValue() {
            const parsed = parseModeValue(modeSelect.value);
            if (parsed.mode === 'code') {
                const digits = searchInput.value.replace(/\D/g, '');
                if (searchInput.value !== digits) {
                    searchInput.value = digits;
                }
            }
        }

        function renderResults(results) {
            resultsContainer.innerHTML = '';

            if (!results.length) {
                resultsContainer.hidden = true;
                if (emptyState) emptyState.hidden = false;
                return;
            }

            results.forEach(function (person) {
                const item = document.createElement('button');
                item.type = 'button';
                item.className = 'quick-search-item';

                item.innerHTML =
                    '<div class="search-result-main">' +
                        (person.photo_url
                            ? '<img class="search-result-avatar" src="' + person.photo_url + '" alt="">'
                            : '<span class="search-result-avatar search-result-avatar-placeholder" aria-hidden="true">?</span>') +
                        '<div class="info">' +
                            '<strong>' + person.nombre + '</strong>' +
                            '<span class="meta">' + formatPersonMeta(person) + '</span>' +
                        '</div>' +
                    '</div>' +
                    '<span class="category-badge">' + person.categoria + '</span>';

                item.addEventListener('click', function () {
                    onResultClick(person);
                });

                resultsContainer.appendChild(item);
            });

            resultsContainer.hidden = false;
            if (emptyState) emptyState.hidden = true;
        }

        function runSearch() {
            sanitizeInputValue();
            const query = searchInput.value.trim();
            const minLen = minQueryLength(modeSelect.value);

            if (query.length < minLen) {
                clearResults();
                return;
            }

            if (loadingState) loadingState.hidden = false;
            if (emptyState) emptyState.hidden = true;
            resultsContainer.hidden = true;

            fetch(buildSearchUrl(searchUrl, query, modeSelect.value), {
                headers: { 'X-Requested-With': 'XMLHttpRequest' }
            })
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    if (loadingState) loadingState.hidden = true;
                    renderResults(data.results || []);
                })
                .catch(function (error) {
                    console.error('Error en búsqueda de persona:', error);
                    if (loadingState) loadingState.hidden = true;
                });
        }

        modeSelect.addEventListener('change', function () {
            applyModeUi();
            searchInput.value = '';
            clearResults();
            searchInput.focus();
        });

        searchInput.addEventListener('input', function () {
            clearTimeout(searchTimer);
            searchTimer = setTimeout(runSearch, 300);
        });

        searchInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') {
                e.preventDefault();
                const firstResult = resultsContainer.querySelector('.quick-search-item');
                if (firstResult) firstResult.click();
            }
        });

        applyModeUi();

        return {
            focus: function () {
                searchInput.focus();
            },
            reset: function () {
                modeSelect.value = 'auto';
                applyModeUi();
                searchInput.value = '';
                clearResults();
            }
        };
    }

    window.initPersonSearchBar = initPersonSearchBar;
})(window);
