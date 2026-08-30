(function () {
    const searchBtn = document.getElementById('profileSearchBtn');
    const profileModal = document.getElementById('profileSearchModal');

    if (!searchBtn || !profileModal || typeof window.initPersonSearchBar !== 'function') return;

    const searchUrl = searchBtn.getAttribute('data-search-url');
    const searchRoot = profileModal.querySelector('[data-person-search-root]');

    const searchBar = initPersonSearchBar({
        root: searchRoot,
        searchUrl: searchUrl,
        resultsContainer: profileModal.querySelector('[data-person-search-results]'),
        emptyState: profileModal.querySelector('[data-person-search-empty]'),
        loadingState: profileModal.querySelector('[data-person-search-loading]'),
        onResultClick: function (person) {
            window.location.href = person.profile_url;
        }
    });

    if (!searchBar) return;

    function openModal() {
        profileModal.classList.add('show');
        setTimeout(function () { searchBar.focus(); }, 100);
    }

    function closeModal() {
        profileModal.classList.remove('show');
        searchBar.reset();
    }

    searchBtn.addEventListener('click', openModal);

    document.addEventListener('keydown', function (e) {
        if (e.ctrlKey && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            openModal();
        }
    });

    profileModal.addEventListener('click', function (e) {
        if (e.target === profileModal) closeModal();
    });

    const closeBtn = profileModal.querySelector('[data-modal-close]');
    if (closeBtn) {
        closeBtn.addEventListener('click', closeModal);
    }
})();
