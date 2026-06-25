// tablet_access.js — Tablet de acceso biométrico (Perfect Line II)

const WS_URL = window.TABLET_WS_URL;
const RECONNECT_DELAY_MS = 3000;
const CAPTURE_COOLDOWN_MS = 2000;
const RESULT_DISPLAY_MS = 4000;
const RESULT_DISPLAY_DENIED_MS = 3200;
const RESULT_DISPLAY_DENIED_UNKNOWN_MS = 1600;
const COOLDOWN_RELEASE_MS = 300;
const QUICK_RETRY_IDLE_MS = 4000;

const cameraFeed = document.getElementById('camera-feed');
const overlayCanvas = document.getElementById('overlay-canvas');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const faceGuide = document.getElementById('face-guide');
const faceGuideOval = document.querySelector('.access-guide-oval');
const accessBottomBanner = document.getElementById('access-bottom-banner');
const accessBannerTitle = document.getElementById('access-banner-title');
const accessBannerSubtitle = document.getElementById('access-banner-subtitle');
const hudInstruction = document.getElementById('hud-instruction');
const hudText = document.getElementById('hud-text');
const accessProcessingOverlay = document.getElementById('access-processing-overlay');
const accessProcessingLabel = document.getElementById('access-processing-label');

let isProcessingAccess = false;
let isCooldown = false;
let isQuickRetryMode = false;
let resultTimeout = null;
let quickRetryTimeout = null;
let quickRetryNoValidFaceSince = null;
let serverTimeoutTimer = null;
let socket = null;
let reconnectTimer = null;
let canvasCtx = overlayCanvas.getContext('2d');
let isModelsLoaded = false;
let lastCaptureTime = 0;

async function loadModels() {
    const MODEL_URL = '/static/models';
    await faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL);
    isModelsLoaded = true;
}

function setHud(text) {
    hudText.textContent = text;
}

function setFaceGuideVariant(variant) {
    faceGuide.className = 'face-guide face-guide-access active' + (variant ? ' ' + variant : '');
}

function isGrantedVariant(variant) {
    return variant === 'granted' || variant === 'granted_staff' || variant === 'granted_guest';
}

function hideBottomBanner() {
    accessBottomBanner.className = 'access-bottom-banner hidden';
    accessBottomBanner.classList.remove(
        'granted', 'granted_staff', 'granted_guest', 'denied_unknown', 'denied_suspended', 'denied_schedule', 'denied_other', 'processing'
    );
}

function showBottomBanner(variant, title, subtitle) {
    hideBottomBanner();
    accessBottomBanner.classList.remove('hidden');
    accessBottomBanner.classList.add(variant);
    accessBannerTitle.textContent = title;
    accessBannerSubtitle.textContent = subtitle || '';
}

function updateBottomBannerSubtitle(subtitle) {
    accessBannerSubtitle.textContent = subtitle || '';
}

function showProcessingOverlay(label) {
    accessProcessingLabel.textContent = label;
    accessProcessingOverlay.classList.remove('hidden');
}

function hideProcessingOverlay() {
    accessProcessingOverlay.classList.add('hidden');
}

function cancelQuickRetryIdleReset() {
    quickRetryNoValidFaceSince = null;
}

function updateQuickRetryIdleTracking(meetsCriteria) {
    if (!isQuickRetryMode || isProcessingAccess || isCooldown) {
        quickRetryNoValidFaceSince = null;
        return;
    }

    if (meetsCriteria) {
        quickRetryNoValidFaceSince = null;
        return;
    }

    const now = Date.now();
    if (quickRetryNoValidFaceSince === null) {
        quickRetryNoValidFaceSince = now;
        return;
    }

    if (now - quickRetryNoValidFaceSince >= QUICK_RETRY_IDLE_MS) {
        quickRetryNoValidFaceSince = null;
        resetQuickRetryToIdle();
    }
}

function resetQuickRetryToIdle() {
    clearAccessResult();
    setHud('Coloque su rostro en el óvalo');
    isCooldown = false;
}

function exitQuickRetryMode() {
    isQuickRetryMode = false;
    clearTimeout(quickRetryTimeout);
    quickRetryTimeout = null;
    cancelQuickRetryIdleReset();
}

function enterQuickRetryMode() {
    isQuickRetryMode = true;
    isCooldown = false;
    quickRetryNoValidFaceSince = null;
}

function clearAccessResult() {
    exitQuickRetryMode();
    hideProcessingOverlay();
    clearTimeout(resultTimeout);
    clearTimeout(quickRetryTimeout);
    setFaceGuideVariant('');
    hideBottomBanner();
    hudInstruction.classList.remove('hidden');
    isProcessingAccess = false;
}

function formatCutLine(data) {
    if (data.covered_until_display) {
        return 'Vigente hasta ' + data.covered_until_display;
    }
    if (data.next_cut_display) {
        return 'Próximo corte: ' + data.next_cut_display;
    }
    if (data.cut_day) {
        return 'Fecha de corte: día ' + data.cut_day + ' de cada mes';
    }
    if (data.days_until_cut != null) {
        const days = data.days_until_cut;
        const dayWord = days === 1 ? 'día' : 'días';
        return 'Faltan ' + days + ' ' + dayWord + ' para el corte';
    }
    if (data.days_membership_left != null) {
        const days = data.days_membership_left;
        const dayWord = days === 1 ? 'día' : 'días';
        return 'Membresía activa: ' + days + ' ' + dayWord;
    }
    return '';
}

function buildResultCopy(data, variant) {
    let title = '';
    let subtitle = '';

    if (isGrantedVariant(variant)) {
        title = '¡Aprobado!';
        const name = data.name ? data.name + ' — ' : '';
        if (variant === 'granted_staff') {
            subtitle = name + (data.detail || 'Acceso personal');
        } else if (variant === 'granted_guest') {
            const guestLine = data.pass_until_display
                ? 'Pase vigente hasta ' + data.pass_until_display
                : (data.detail || 'Acceso de invitado');
            const sponsor = data.sponsor_name ? ' · Responsable: ' + data.sponsor_name : '';
            subtitle = name + guestLine + sponsor;
        } else {
            const cutLine = formatCutLine(data);
            subtitle = name + (cutLine || 'Acceso concedido');
        }
    } else if (variant === 'denied_unknown') {
        title = 'No reconocido';
        subtitle = data.detail || 'Rostro no registrado en el sistema';
    } else if (variant === 'denied_schedule') {
        title = 'Fuera de horario';
        subtitle = (data.name ? data.name + ' — ' : '') + (data.detail || 'Horario no permitido');
    } else if (variant === 'denied_suspended') {
        title = 'Acceso suspendido';
        const since = data.suspended_since_display
            ? 'Suspendido desde ' + data.suspended_since_display
            : (data.detail || 'Suscripción sin pagar');
        subtitle = (data.name ? data.name + ' — ' : '') + since;
    } else {
        title = 'Acceso denegado';
        subtitle = (data.name ? data.name + ' — ' : '') + (data.detail || data.reason || '');
    }

    return { title: title, subtitle: subtitle };
}

function showAccessProcessing() {
    cancelQuickRetryIdleReset();
    isProcessingAccess = true;
    hudInstruction.classList.add('hidden');

    if (isQuickRetryMode) {
        updateBottomBannerSubtitle('Re-verificando…');
        showProcessingOverlay('Re-verificando…');
    } else {
        setFaceGuideVariant('processing');
        showBottomBanner('processing', 'Verificando…', 'Un momento por favor');
        showProcessingOverlay('Verificando…');
    }
}

function scheduleDeniedUnknownQuickRetry(title, subtitle) {
    clearTimeout(quickRetryTimeout);
    quickRetryTimeout = setTimeout(function () {
        quickRetryTimeout = null;
        enterQuickRetryMode();
        updateBottomBannerSubtitle(subtitle);
    }, RESULT_DISPLAY_DENIED_UNKNOWN_MS);
}

function scheduleFullResultClear() {
    clearTimeout(resultTimeout);
    resultTimeout = setTimeout(function () {
        clearAccessResult();
        setHud('Coloque su rostro en el óvalo');
        setTimeout(function () {
            isCooldown = false;
        }, COOLDOWN_RELEASE_MS);
    }, RESULT_DISPLAY_DENIED_MS);
}

function showAccessResult(data) {
    const variant = data.variant || (data.status === 'GRANTED' ? 'granted' : 'denied_unknown');
    hideProcessingOverlay();
    isProcessingAccess = false;
    setFaceGuideVariant(variant);
    hudInstruction.classList.add('hidden');

    const copy = buildResultCopy(data, variant);
    showBottomBanner(variant, copy.title, copy.subtitle);

    clearTimeout(resultTimeout);
    clearTimeout(quickRetryTimeout);

    if (isGrantedVariant(variant)) {
        exitQuickRetryMode();
        isCooldown = true;
        resultTimeout = setTimeout(function () {
            clearAccessResult();
            setHud('Coloque su rostro en el óvalo');
            setTimeout(function () {
                isCooldown = false;
            }, COOLDOWN_RELEASE_MS);
        }, RESULT_DISPLAY_MS);
        return;
    }

    if (variant === 'denied_unknown') {
        isCooldown = true;
        scheduleDeniedUnknownQuickRetry(copy.title, copy.subtitle);
        return;
    }

    exitQuickRetryMode();
    isCooldown = true;
    scheduleFullResultClear();
}

async function detectFaceLoop() {
    if (!isModelsLoaded || cameraFeed.paused || cameraFeed.ended) {
        requestAnimationFrame(detectFaceLoop);
        return;
    }

    const displaySize = { width: cameraFeed.videoWidth, height: cameraFeed.videoHeight };
    if (overlayCanvas.width !== displaySize.width) {
        faceapi.matchDimensions(overlayCanvas, displaySize);
    }

    const now = Date.now();
    const cooldownOk = isQuickRetryMode || (now - lastCaptureTime) > CAPTURE_COOLDOWN_MS;

    try {
        const detection = await faceapi.detectSingleFace(
            cameraFeed,
            TabletFaceUtils.accessDetectorOptions()
        );
        canvasCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

        let meetsCriteria = false;
        let resizedDetection = null;

        if (detection) {
            resizedDetection = faceapi.resizeResults(detection, displaySize);
            meetsCriteria = TabletFaceUtils.meetsAccessCaptureCriteria(
                detection, resizedDetection, cameraFeed, faceGuideOval
            );
        }

        if (detection && cooldownOk && !isProcessingAccess && !isCooldown && meetsCriteria) {
            showAccessProcessing();
            sendAccessFrame();
            lastCaptureTime = now;
        } else if (detection && !isProcessingAccess && !isQuickRetryMode) {
            setHud('Coloque su rostro en el óvalo');
        } else if (detection && !isProcessingAccess && isQuickRetryMode) {
            updateBottomBannerSubtitle('Coloque su rostro en el óvalo');
        } else if (!detection && !isProcessingAccess) {
            if (isQuickRetryMode) {
                updateBottomBannerSubtitle('Coloque su rostro en el óvalo');
            } else {
                setHud('Coloque su rostro en el óvalo');
            }
        }

        if (isQuickRetryMode && !isProcessingAccess && !isCooldown) {
            updateQuickRetryIdleTracking(meetsCriteria);
        }
    } catch (e) {
        console.error('Error en bucle de detección de acceso:', e);
    }

    requestAnimationFrame(detectFaceLoop);
}

function sendAccessFrame() {
    const canvas = document.createElement('canvas');
    canvas.width = cameraFeed.videoWidth;
    canvas.height = cameraFeed.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(cameraFeed, 0, 0, canvas.width, canvas.height);
    const dataURL = canvas.toDataURL('image/jpeg', 0.85);

    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'FRAME', image: dataURL }));
        clearTimeout(serverTimeoutTimer);
        serverTimeoutTimer = setTimeout(function () {
            if (isProcessingAccess) {
                showAccessResult({
                    status: 'DENIED',
                    variant: 'denied_unknown',
                    detail: 'Sin respuesta del servidor',
                });
            }
        }, 8000);
    } else {
        showAccessResult({
            status: 'DENIED',
            variant: 'denied_unknown',
            detail: 'Sin conexión con el servidor',
        });
    }
}

async function startCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
        });
        cameraFeed.srcObject = stream;
        cameraFeed.addEventListener('loadedmetadata', function () {
            requestAnimationFrame(detectFaceLoop);
        }, { once: true });
    } catch (err) {
        console.error('[Tablet Acceso] Error al iniciar cámara:', err);
        setStatus('disconnected', 'Sin cámara');
    }
}

function connectWebSocket() {
    clearTimeout(reconnectTimer);
    socket = new WebSocket(WS_URL);

    socket.onopen = function () {
        setStatus('connected', 'Conectado');
    };

    socket.onclose = function () {
        setStatus('disconnected', 'Sin conexión...');
        clearAccessResult();
        reconnectTimer = setTimeout(connectWebSocket, RECONNECT_DELAY_MS);
    };

    socket.onmessage = function (event) {
        try {
            handleServerMessage(JSON.parse(event.data));
        } catch (err) {
            console.error('[Tablet Acceso] Mensaje inválido:', event.data);
        }
    };
}

function handleServerMessage(data) {
    clearTimeout(serverTimeoutTimer);

    if (data.status === 'ERROR') {
        showAccessResult({
            status: 'DENIED',
            variant: 'denied_unknown',
            detail: data.reason || 'Error',
        });
        return;
    }

    if (data.status === 'GRANTED' || data.status === 'DENIED') {
        if (!data.variant) {
            data.variant = data.status === 'GRANTED' ? 'granted' : 'denied_unknown';
        }
        showAccessResult(data);
    }
}

function setStatus(state, text) {
    statusDot.className = state;
    statusText.textContent = text;
}

document.addEventListener('DOMContentLoaded', function () {
    setHud('Coloque su rostro en el óvalo');
    loadModels().then(startCamera).catch(function (err) {
        console.error('[Tablet Acceso] Error cargando IA:', err);
        setStatus('disconnected', 'Error IA');
    });
    connectWebSocket();
});
