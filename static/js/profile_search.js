(function () {
    const searchBtn = document.getElementById('profileSearchBtn');
    const profileModal = document.getElementById('profileSearchModal');
    const searchInput = document.getElementById('profile-search-input');
    const resultsContainer = document.getElementById('profile-search-results');
    const emptyState = document.getElementById('profile-search-empty');
    const loadingState = document.getElementById('profile-search-loading');

    if (!searchBtn || !profileModal) return;

    const searchUrl = searchBtn.getAttribute('data-search-url');
    let searchTimer = null;

    function openModal() {
        profileModal.classList.add('show');
        setTimeout(() => searchInput.focus(), 100);
    }

    function closeModal() {
        profileModal.classList.remove('show');
        searchInput.value = '';
        resultsContainer.innerHTML = '';
        resultsContainer.hidden = true;
        emptyState.hidden = true;
        loadingState.hidden = true;
    }

    searchBtn.addEventListener('click', openModal);

    document.addEventListener('keydown', (e) => {
        if (e.ctrlKey && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            openModal();
        }
    });

    profileModal.addEventListener('click', (e) => {
        if (e.target === profileModal) closeModal();
    });

    const closeBtn = profileModal.querySelector('[data-modal-close]');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeModal);
    }

    searchInput.addEventListener('input', () => {
        clearTimeout(searchTimer);
        const query = searchInput.value.trim();

        if (query.length < 2) {
            resultsContainer.innerHTML = '';
            resultsContainer.hidden = true;
            emptyState.hidden = true;
            loadingState.hidden = true;
            return;
        }

        loadingState.hidden = false;
        emptyState.hidden = true;
        resultsContainer.hidden = true;

        searchTimer = setTimeout(() => {
            fetch(`${searchUrl}?q=${encodeURIComponent(query)}`, {
                headers: {
                    'X-Requested-With': 'XMLHttpRequest'
                }
            })
            .then(response => response.json())
            .then(data => {
                loadingState.hidden = true;
                renderResults(data.results || []);
            })
            .catch(error => {
                console.error('Error en búsqueda de perfil:', error);
                loadingState.hidden = true;
            });
        }, 300);
    });

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

    function renderResults(results) {
        resultsContainer.innerHTML = '';

        if (results.length === 0) {
            resultsContainer.hidden = true;
            emptyState.hidden = false;
            return;
        }

        results.forEach(person => {
            const item = document.createElement('button');
            item.type = 'button';
            item.className = 'quick-search-item';

            item.innerHTML = `
                <div class="search-result-main">
                    ${person.photo_url
                        ? `<img class="search-result-avatar" src="${person.photo_url}" alt="">`
                        : '<span class="search-result-avatar search-result-avatar-placeholder" aria-hidden="true">?</span>'}
                    <div class="info">
                        <strong>${person.nombre}</strong>
                        <span class="meta">${formatPersonMeta(person)}</span>
                    </div>
                </div>
                <span class="category-badge">${person.categoria}</span>
            `;

            item.addEventListener('click', () => {
                window.location.href = person.profile_url;
            });

            resultsContainer.appendChild(item);
        });

        resultsContainer.hidden = false;
        emptyState.hidden = true;
    }

    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const firstResult = resultsContainer.querySelector('.quick-search-item');
            if (firstResult) firstResult.click();
        }
    });
})();
