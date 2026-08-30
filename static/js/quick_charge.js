(function () {
    const quickChargeTriggers = document.querySelectorAll('.js-quick-charge-trigger, #quickChargeBtn');
    const quickChargeModal = document.getElementById('quickChargeModal');

    if (quickChargeTriggers.length === 0 || !quickChargeModal || typeof window.initPersonSearchBar !== 'function') return;

    const searchUrl = quickChargeTriggers[0].getAttribute('data-search-url');
    const searchRoot = quickChargeModal.querySelector('[data-person-search-root]');

    const searchBar = initPersonSearchBar({
        root: searchRoot,
        searchUrl: searchUrl,
        resultsContainer: quickChargeModal.querySelector('[data-person-search-results]'),
        emptyState: quickChargeModal.querySelector('[data-person-search-empty]'),
        loadingState: quickChargeModal.querySelector('[data-person-search-loading]'),
        onResultClick: function (person) {
            window.location.href = '/billing/cobro/' + person.codigo_afiliado + '/?origin=list';
        }
    });

    if (!searchBar) return;

    quickChargeTriggers.forEach(function (trigger) {
        trigger.addEventListener('click', function () {
            quickChargeModal.classList.add('show');
            setTimeout(function () { searchBar.focus(); }, 100);
        });
    });

    function closeModal() {
        quickChargeModal.classList.remove('show');
        searchBar.reset();
    }

    quickChargeModal.addEventListener('click', function (e) {
        if (e.target === quickChargeModal) closeModal();
    });

    const closeBtn = quickChargeModal.querySelector('[data-modal-close]');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeModal);
    }
})();
