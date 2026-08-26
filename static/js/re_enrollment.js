(function () {
    const TABLET_ROLE = 'enrollment';
    const offlineOverlay = document.getElementById('tablet-offline-overlay');
    const statusEl = document.getElementById('reenrollment-photo-status');
    const imgElement = document.getElementById('img-frente');
    const placeholderEl = document.getElementById('new-photo-placeholder');
    const inputElement = document.getElementById('input-foto-frente');
    const form = document.getElementById('re-enrollment-form');
    const saveButton = form ? form.querySelector('.btn-enrollment-save') : null;
    const processModal = document.getElementById('reenrollment-process-modal');
    const processLoading = document.getElementById('reenrollment-process-loading');
    const processSuccess = document.getElementById('reenrollment-process-success');
    const processError = document.getElementById('reenrollment-process-error');
    const processErrorMessage = document.getElementById('reenrollment-process-error-message');
    const processCloseBtn = document.getElementById('reenrollment-process-close-btn');
    const processCloseX = document.getElementById('reenrollment-process-close-x');
    const validateUrl = window.ENROLLMENT_VALIDATE_PHOTO_URL || '';

    let photoReady = false;
    let photoRejected = false;
    let photoRejectMessage = '';
    let photoVerifying = false;
    let photoGate = null;

    function getCsrfToken() {
        const input = form ? form.querySelector('input[name="csrfmiddlewaretoken"]') : null;
        return input ? input.value : '';
    }

    function syncFromPhotoGate(gateState) {
        photoReady = gateState.ready;
        photoRejected = gateState.rejected;
        photoVerifying = gateState.verifying;
        photoRejectMessage = gateState.rejectMessage;
        updateSaveState();
        if (photoReady && window.sendDashboardCommand) {
            window.sendDashboardCommand({ type: 'ENROLLMENT_SKIP_TERMS' });
        }
    }

    function updateSaveState() {
        if (saveButton) {
            const canClick = (photoReady || photoRejected) && !photoVerifying;
            saveButton.disabled = !canClick;
        }
    }

    function clearPhoto() {
        if (inputElement) {
            inputElement.value = '';
        }
        if (imgElement) {
            imgElement.src = '';
            imgElement.style.display = 'none';
            imgElement.classList.add('hidden');
        }
        if (placeholderEl) {
            placeholderEl.classList.remove('hidden');
        }
        if (photoGate) {
            photoGate.resetIdle('Esperando nueva foto en la tablet');
        }
    }

    function showPhotoPreview(image) {
        if (!imgElement || !inputElement) {
            return;
        }
        imgElement.src = image;
        imgElement.style.display = 'block';
        imgElement.classList.remove('hidden');
        if (placeholderEl) {
            placeholderEl.classList.add('hidden');
        }
        inputElement.value = image;
    }

    function validateEnrollmentPhoto(imageDataUrl) {
        if (photoGate) {
            photoGate.validate(imageDataUrl);
        }
    }

    function startTabletSession() {
        if (!window.sendDashboardCommand) {
            return;
        }
        window.sendDashboardCommand({ type: 'ENROLLMENT_START' });
        window.setTimeout(function () {
            window.sendDashboardCommand({ type: 'ENROLLMENT_SKIP_TERMS' });
        }, 150);
    }

    function reconnectTablet() {
        clearPhoto();
        startTabletSession();
    }

    window.retakeEnrollmentPhoto = reconnectTablet;

    window.addEventListener('tabletStatusChanged', function (e) {
        if (e.detail.role !== TABLET_ROLE) {
            return;
        }
        if (!offlineOverlay) {
            return;
        }
        if (e.detail.online) {
            offlineOverlay.classList.add('hidden');
            if (document.visibilityState === 'visible') {
                reconnectTablet();
            }
        } else {
            offlineOverlay.classList.remove('hidden');
        }
    });

    window.addEventListener('enrollmentPhotoReceived', function (e) {
        if (e.detail.photoType !== 'FRONT') {
            return;
        }
        showPhotoPreview(e.detail.image);
        validateEnrollmentPhoto(e.detail.image);
    });

    function showProcessState(state) {
        processLoading.classList.toggle('hidden', state !== 'loading');
        processSuccess.classList.toggle('hidden', state !== 'success');
        processError.classList.toggle('hidden', state !== 'error');
    }

    function processDismissAllowed() {
        return processError && !processError.classList.contains('hidden');
    }

    function openProcessModal(state) {
        showProcessState(state);
        processModal.classList.add('show');
        processModal.setAttribute('aria-hidden', 'false');
        if (processCloseX) {
            processCloseX.hidden = state !== 'error';
        }
    }

    function closeProcessModal() {
        processModal.classList.remove('show');
        processModal.setAttribute('aria-hidden', 'true');
        if (processCloseX) {
            processCloseX.hidden = true;
        }
        updateSaveState();
    }

    if (processCloseBtn) {
        processCloseBtn.addEventListener('click', closeProcessModal);
    }

    if (processModal && window.bindDismissibleModal) {
        bindDismissibleModal(processModal, {
            onClose: closeProcessModal,
            canClose: processDismissAllowed,
        });
    }

    if (form) {
        function proceedReEnrollmentSave() {
            if (saveButton) {
                saveButton.disabled = true;
            }
            openProcessModal('loading');

            fetch(form.action, {
                method: 'POST',
                body: new FormData(form),
                headers: { 'X-Reenroll-Submit': '1' },
                credentials: 'same-origin',
            })
                .then(function (response) {
                    return response.json().then(function (data) {
                        return { ok: response.ok, data: data };
                    });
                })
                .then(function (result) {
                    if (result.ok && result.data.status === 'success') {
                        openProcessModal('success');
                        window.setTimeout(function () {
                            window.location.href = result.data.redirect_url;
                        }, 900);
                        return;
                    }
                    processErrorMessage.textContent = result.data.message || 'Ocurrió un error al guardar la nueva foto.';
                    openProcessModal('error');
                })
                .catch(function () {
                    processErrorMessage.textContent = 'Error de conexión con el servidor. Intente nuevamente.';
                    openProcessModal('error');
                });
        }

        form.addEventListener('submit', function (event) {
            event.preventDefault();
            if (photoRejected) {
                processErrorMessage.textContent = photoRejectMessage
                    || 'La foto no es válida: no se detectó una cara usable. Use Tomar otra foto.';
                openProcessModal('error');
                return;
            }
            if (!photoReady) {
                processErrorMessage.textContent = 'Debe capturar la nueva foto del afiliado en la tablet.';
                openProcessModal('error');
                return;
            }
            if (photoGate && !photoGate.confirmRiskyIfNeeded(proceedReEnrollmentSave)) {
                return;
            }
            proceedReEnrollmentSave();
        });
    }

    document.addEventListener('DOMContentLoaded', function () {
        if (window.EnrollmentPhotoQuality) {
            photoGate = EnrollmentPhotoQuality.createGate({
                statusEl: statusEl,
                barRoot: document.getElementById('enrollment-quality-bar'),
                riskyModalRoot: document.getElementById('enrollment-risky-photo-modal'),
                validateUrl: validateUrl,
                getCsrfToken: getCsrfToken,
                idleMessage: 'Esperando nueva foto en la tablet',
                onStateChange: syncFromPhotoGate,
            });
            photoGate.resetIdle();
        }
        updateSaveState();
        window.setTimeout(startTabletSession, 500);
    });

    document.addEventListener('visibilitychange', function () {
        if (document.visibilityState === 'hidden') {
            if (window.sendDashboardCommand) {
                window.sendDashboardCommand({ type: 'ENROLLMENT_END' });
            }
        } else if (window.sendDashboardCommand) {
            startTabletSession();
        }
    });

    window.addEventListener('beforeunload', function () {
        if (window.sendDashboardCommand) {
            window.sendDashboardCommand({ type: 'ENROLLMENT_END' });
        }
    });
})();
