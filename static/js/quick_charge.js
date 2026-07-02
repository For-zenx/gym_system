(function () {
    const quickChargeBtn = document.getElementById('quickChargeBtn');
    const quickChargeModal = document.getElementById('quickChargeModal');
    const searchInput = document.getElementById('quick-charge-search');
    const resultsContainer = document.getElementById('quick-charge-results');
    const emptyState = document.getElementById('quick-charge-empty');
    const loadingState = document.getElementById('quick-charge-loading');

    if (!quickChargeBtn || !quickChargeModal) return;

    const searchUrl = quickChargeBtn.getAttribute('data-search-url');
    let searchTimer = null;

    // Abrir modal
    quickChargeBtn.addEventListener('click', () => {
        quickChargeModal.classList.add('show');
        setTimeout(() => searchInput.focus(), 100);
    });

    // Cerrar modal
    function closeModal() {
        quickChargeModal.classList.remove('show');
        searchInput.value = '';
        resultsContainer.innerHTML = '';
        resultsContainer.hidden = true;
        emptyState.hidden = true;
        loadingState.hidden = true;
    }

    // Cerrar al hacer clic fuera del contenido o en el botón de cerrar
    quickChargeModal.addEventListener('click', (e) => {
        if (e.target === quickChargeModal) closeModal();
    });

    const closeBtn = quickChargeModal.querySelector('[data-modal-close]');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeModal);
    }

    // Búsqueda dinámica
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
                console.error('Error en búsqueda rápida:', error);
                loadingState.hidden = true;
            });
        }, 300);
    });

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
                <div class="info">
                    <strong>${person.nombre}</strong>
                    <span class="meta">${person.cedula} · ${person.codigo_afiliado}</span>
                </div>
                <span class="category-badge">${person.categoria}</span>
            `;

            item.addEventListener('click', () => {
                // Redirigir al checkout
                window.location.href = `/billing/cobro/${person.codigo_afiliado}/?origin=list`;
            });

            resultsContainer.appendChild(item);
        });

        resultsContainer.hidden = false;
        emptyState.hidden = true;
    }

    // Evitar submit del formulario si el input está en un form
    searchInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') {
            e.preventDefault();
            const firstResult = resultsContainer.querySelector('.quick-search-item');
            if (firstResult) firstResult.click();
        }
    });
})();
