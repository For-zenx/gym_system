// tablet_access.js — Tablet de acceso biométrico (Perfect Line II)

const WS_URL = window.TABLET_WS_URL;
const RECONNECT_DELAY_MS = 3000;
const CAPTURE_COOLDOWN_MS = 2000;
const CONFIRM_CAPTURE_COOLDOWN_MS = 400;
const ACCESS_FIRST_STABILITY_MS = 400;
const RESULT_DISPLAY_MS = 4000;
const RESULT_DISPLAY_DENIED_MS = 3200;
const RESULT_DISPLAY_DENIED_UNKNOWN_MS = 1600;
const COOLDOWN_RELEASE_MS = 300;
const QUICK_RETRY_IDLE_MS = 4000;
const WS_PING_MS = 20000;
const WS_PONG_TIMEOUT_MS = 45000;
const LONG_DISCONNECT_RELOAD_MS = 5 * 60 * 1000;
const CONFIRMING_MAX_MS = 4000;
const CONFIRM_ABANDON_MS = 1200;
const DETECT_WATCHDOG_MS = 15000;
const ACCESS_BURST_INTERVAL_MS = 150;
const ACCESS_BURST_SAMPLE_COUNT = 4;
const ACCESS_BURST_MIN_SEPARATION_MS = 250;

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
let isConfirmingIdentity = false;
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
let accessStableSince = null;
let disconnectedSince = null;
let pendingSoftReload = false;
let softReloadDoneForThisDown = false;
let pingTimer = null;
let pongTimer = null;
let confirmingWatchdogTimer = null;
let confirmAbandonSince = null;
let lastDetectTick = Date.now();
let detectWatchdogTimer = null;
let detectRestartCount = 0;
let cameraRetrying = false;
let pendingSoftReloadReason = '—';
let isCollectingAccessBurst = false;
let accessBurstGeneration = 0;

// OPS_AUDIT
function sendOpsEvent(event, reason, detail) {
    try {
        if (!socket || socket.readyState !== WebSocket.OPEN) {
            return;
        }
        socket.send(JSON.stringify({
            type: 'OPS',
            event: event || '—',
            reason: reason || '—',
            detail: detail || '—',
        }));
    } catch (err) {
        /* ignore */
    }
}

function resetAccessStability() {
    accessStableSince = null;
}

function isAccessUiIdle() {
    return (
        !isProcessingAccess &&
        !isConfirmingIdentity &&
        accessBottomBanner.classList.contains('hidden')
    );
}

function clearConfirmingWatchdog() {
    clearTimeout(confirmingWatchdogTimer);
    confirmingWatchdogTimer = null;
}

function startConfirmingWatchdog() {
    clearConfirmingWatchdog();
    confirmingWatchdogTimer = setTimeout(function () {
        confirmingWatchdogTimer = null;
        if (isConfirmingIdentity) {
            abortConfirmingToIdle();
        }
    }, CONFIRMING_MAX_MS);
}

function sendConfirmAbort() {
    if (socket && socket.readyState === WebSocket.OPEN) {
        try {
            socket.send(JSON.stringify({ type: 'CONFIRM_ABORT' }));
        } catch (err) { /* ignore */ }
    }
}

function abortConfirmingToIdle() {
    sendConfirmAbort();
    confirmAbandonSince = null;
    clearAccessResult();
    setHud('Coloque su rostro en el óvalo');
    isCooldown = false;
}

function noteConfirmingFacePresence(meetsCriteria, now) {
    if (!isConfirmingIdentity) {
        confirmAbandonSince = null;
        return;
    }
    if (meetsCriteria) {
        confirmAbandonSince = null;
        return;
    }
    if (confirmAbandonSince === null) {
        confirmAbandonSince = now;
        return;
    }
    if (now - confirmAbandonSince >= CONFIRM_ABANDON_MS) {
        abortConfirmingToIdle();
    }
}

function stopHeartbeat() {
    clearInterval(pingTimer);
    clearTimeout(pongTimer);
    pingTimer = null;
    pongTimer = null;
}

function notePongReceived() {
    clearTimeout(pongTimer);
    pongTimer = null;
}

function startHeartbeat() {
    stopHeartbeat();
    pingTimer = setInterval(function () {
        if (!socket || socket.readyState !== WebSocket.OPEN) {
            return;
        }
        try {
            socket.send(JSON.stringify({ type: 'PING' }));
        } catch (err) {
            return;
        }
        clearTimeout(pongTimer);
        pongTimer = setTimeout(function () {
            // OPS_AUDIT
            sendOpsEvent('pong_timeout', 'pong_timeout', '—');
            if (socket) {
                try {
                    socket.close();
                } catch (e) { /* ignore */ }
            }
        }, WS_PONG_TIMEOUT_MS);
    }, WS_PING_MS);
}

function requestSafeReload(reason) {
    if (reason) {
        pendingSoftReloadReason = reason;
    }
    if (!socket || socket.readyState !== WebSocket.OPEN) {
        pendingSoftReload = true;
        return;
    }
    if (!isAccessUiIdle()) {
        pendingSoftReload = true;
        return;
    }
    pendingSoftReload = false;
    // OPS_AUDIT
    sendOpsEvent('soft_reload', pendingSoftReloadReason || '—', '—');
    pendingSoftReloadReason = '—';
    window.location.reload();
}

function tryPendingSoftReload() {
    if (pendingSoftReload && isAccessUiIdle() && socket && socket.readyState === WebSocket.OPEN) {
        pendingSoftReload = false;
        // OPS_AUDIT
        sendOpsEvent('soft_reload', pendingSoftReloadReason || '—', '—');
        pendingSoftReloadReason = '—';
        window.location.reload();
    }
}

function onWsOpened() {
    const downMs = disconnectedSince ? (Date.now() - disconnectedSince) : 0;
    disconnectedSince = null;
    setStatus('connected', 'Conectado');
    startHeartbeat();
    // OPS_AUDIT
    sendOpsEvent(
        'ws_open',
        downMs > 0 ? 'reconnect' : 'initial',
        'down_ms=' + downMs
    );
    if (downMs >= LONG_DISCONNECT_RELOAD_MS && !softReloadDoneForThisDown) {
        softReloadDoneForThisDown = true;
        requestSafeReload('offline_ge_5min');
        return;
    }
    softReloadDoneForThisDown = false;
    tryPendingSoftReload();
}

function onWsClosed() {
    stopHeartbeat();
    clearConfirmingWatchdog();
    if (disconnectedSince === null) {
        disconnectedSince = Date.now();
    }
    softReloadDoneForThisDown = false;
    setStatus('disconnected', 'Sin conexión...');
    clearAccessResult();
    reconnectTimer = setTimeout(connectWebSocket, RECONNECT_DELAY_MS);
}

function startDetectWatchdog() {
    clearInterval(detectWatchdogTimer);
    detectWatchdogTimer = setInterval(function () {
        if (document.visibilityState !== 'visible') {
            return;
        }
        if (Date.now() - lastDetectTick > DETECT_WATCHDOG_MS) {
            detectRestartCount += 1;
            lastDetectTick = Date.now();
            // OPS_AUDIT
            sendOpsEvent('detect_stall', 'detect_watchdog', 'stalls=' + detectRestartCount);
            requestAnimationFrame(detectFaceLoop);
            if (detectRestartCount >= 2) {
                detectRestartCount = 0;
                requestSafeReload('detect_watchdog');
            }
        } else {
            detectRestartCount = 0;
        }
    }, DETECT_WATCHDOG_MS);
}

function attachCameraEndedHandler(stream) {
    const tracks = stream.getVideoTracks();
    if (!tracks.length) {
        return;
    }
    tracks[0].addEventListener('ended', function () {
        if (cameraRetrying) {
            return;
        }
        cameraRetrying = true;
        // OPS_AUDIT
        sendOpsEvent('camera_ended', 'camera_ended', '—');
        startCamera().finally(function () {
            cameraRetrying = false;
        });
    });
}

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
    return variant === 'granted' || variant === 'granted_staff' || variant === 'granted_guest' || variant === 'granted_grace';
}

function hideBottomBanner() {
    accessBottomBanner.className = 'access-bottom-banner hidden';
    accessBottomBanner.classList.remove(
        'granted', 'granted_staff', 'granted_guest', 'granted_grace', 'denied_unknown', 'denied_suspended', 'denied_schedule', 'denied_cooldown', 'denied_other', 'processing'
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
    accessBurstGeneration += 1;
    isCollectingAccessBurst = false;
    exitQuickRetryMode();
    isConfirmingIdentity = false;
    confirmAbandonSince = null;
    clearConfirmingWatchdog();
    resetAccessStability();
    hideProcessingOverlay();
    clearTimeout(resultTimeout);
    clearTimeout(quickRetryTimeout);
    setFaceGuideVariant('');
    hideBottomBanner();
    hudInstruction.classList.remove('hidden');
    isProcessingAccess = false;
    tryPendingSoftReload();
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
        if (variant === 'granted_grace') {
            title = 'Período de gracia';
            const name = data.name ? data.name + ' — ' : '';
            const remaining = data.grace_days_remaining;
            let graceLine = 'Debe pagar en caja';
            if (remaining !== undefined && remaining !== null) {
                const dayWord = remaining === 1 ? 'día' : 'días';
                graceLine = remaining + ' ' + dayWord + ' de acceso restante' + (remaining === 1 ? '' : 's');
            }
            if (data.grace_until_display) {
                graceLine += ' · Hasta ' + data.grace_until_display;
            }
            subtitle = name + graceLine;
        } else {
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
        }
    } else if (variant === 'denied_unknown') {
        title = 'No reconocido';
        subtitle = data.detail || 'Rostro no registrado en el sistema';
    } else if (variant === 'denied_schedule') {
        title = 'Fuera de horario';
        subtitle = (data.name ? data.name + ' — ' : '') + (data.detail || 'Horario no permitido');
    } else if (variant === 'denied_cooldown') {
        title = 'Espere un momento';
        const waitLine = data.cooldown_remaining_display
            ? 'Puede volver a intentar en ' + data.cooldown_remaining_display
            : (data.detail || 'Debe esperar antes de volver a entrar');
        subtitle = (data.name ? data.name + ' — ' : '') + waitLine;
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

function showConfirmingIdentity(data) {
    cancelQuickRetryIdleReset();
    isConfirmingIdentity = true;
    isProcessingAccess = false;
    isCooldown = false;
    confirmAbandonSince = null;
    resetAccessStability();
    startConfirmingWatchdog();
    hideProcessingOverlay();
    hudInstruction.classList.add('hidden');
    setFaceGuideVariant('processing');
    showBottomBanner(
        'processing',
        'Siga frente a la cámara',
        ''
    );
}

function showAccessResult(data) {
    const variant = data.variant || (data.status === 'GRANTED' ? 'granted' : 'denied_unknown');
    isConfirmingIdentity = false;
    confirmAbandonSince = null;
    clearConfirmingWatchdog();
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

function waitMs(ms) {
    return new Promise(function (resolve) {
        setTimeout(resolve, ms);
    });
}

function captureBurstCandidate(detection) {
    const canvas = document.createElement('canvas');
    canvas.width = cameraFeed.videoWidth;
    canvas.height = cameraFeed.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(cameraFeed, 0, 0, canvas.width, canvas.height);

    const det = TabletFaceUtils.getFaceDetection(detection);
    const box = det && det.box;
    let brightnessScore = 0.5;
    let sharpnessScore = 0.5;
    let sizeScore = 0;

    if (box && box.width > 0 && box.height > 0) {
        const sample = document.createElement('canvas');
        sample.width = 64;
        sample.height = 64;
        const sampleCtx = sample.getContext('2d', { willReadFrequently: true });
        sampleCtx.drawImage(
            cameraFeed,
            box.x, box.y, box.width, box.height,
            0, 0, sample.width, sample.height
        );
        const pixels = sampleCtx.getImageData(0, 0, sample.width, sample.height).data;
        let luminanceTotal = 0;
        let edgeTotal = 0;
        let previous = null;
        for (let i = 0; i < pixels.length; i += 4) {
            const luminance = (pixels[i] * 0.299) + (pixels[i + 1] * 0.587) + (pixels[i + 2] * 0.114);
            luminanceTotal += luminance;
            if (previous !== null) {
                edgeTotal += Math.abs(luminance - previous);
            }
            previous = luminance;
        }
        const pixelCount = pixels.length / 4;
        const meanLuminance = luminanceTotal / pixelCount;
        brightnessScore = Math.max(0, 1 - (Math.abs(meanLuminance - 128) / 128));
        sharpnessScore = Math.min(1, (edgeTotal / pixelCount) / 24);
        sizeScore = Math.min(1, box.width / Math.max(1, cameraFeed.videoWidth * 0.45));
    }

    const detectionScore = det && typeof det.score === 'number' ? det.score : 0;
    return {
        image: canvas.toDataURL('image/jpeg', 0.85),
        score: (detectionScore * 0.55) + (sharpnessScore * 0.25) +
            (brightnessScore * 0.15) + (sizeScore * 0.05),
        capturedAt: Date.now(),
    };
}

function selectBurstSamplesForSend(candidates) {
    if (!candidates || candidates.length < 2) {
        return null;
    }
    const ordered = candidates.slice().sort(function (a, b) {
        return a.capturedAt - b.capturedAt;
    });
    const limited = ordered.slice(0, ACCESS_BURST_SAMPLE_COUNT);
    let hasSeparatedPair = false;
    for (let i = 0; i < limited.length; i += 1) {
        for (let j = i + 1; j < limited.length; j += 1) {
            if (limited[j].capturedAt - limited[i].capturedAt >= ACCESS_BURST_MIN_SEPARATION_MS) {
                hasSeparatedPair = true;
                break;
            }
        }
        if (hasSeparatedPair) {
            break;
        }
    }
    if (!hasSeparatedPair) {
        return null;
    }
    return limited;
}

async function collectAndSendAccessBurst(initialDetection) {
    if (isCollectingAccessBurst || isProcessingAccess) {
        return;
    }
    const burstGeneration = ++accessBurstGeneration;
    isCollectingAccessBurst = true;
    isProcessingAccess = true;
    if (isQuickRetryMode) {
        updateBottomBannerSubtitle('Mantenga el rostro un instante');
    } else {
        setHud('Mantenga el rostro un instante');
    }
    const candidates = [captureBurstCandidate(initialDetection)];

    try {
        for (let i = 1; i < ACCESS_BURST_SAMPLE_COUNT; i += 1) {
            await waitMs(ACCESS_BURST_INTERVAL_MS);
            if (burstGeneration !== accessBurstGeneration) {
                return;
            }
            const detection = await faceapi.detectSingleFace(
                cameraFeed,
                TabletFaceUtils.accessDetectorOptions()
            );
            if (!detection) {
                continue;
            }
            const displaySize = { width: cameraFeed.videoWidth, height: cameraFeed.videoHeight };
            const resized = faceapi.resizeResults(detection, displaySize);
            if (TabletFaceUtils.meetsAccessCaptureCriteria(
                detection, resized, cameraFeed, faceGuideOval
            )) {
                candidates.push(captureBurstCandidate(detection));
            }
        }

        const samples = selectBurstSamplesForSend(candidates);
        if (burstGeneration !== accessBurstGeneration) {
            return;
        }
        if (!samples) {
            clearAccessResult();
            setHud('Coloque su rostro en el óvalo');
            isCooldown = false;
            return;
        }
        showAccessProcessing();
        sendAccessBurst(samples.map(function (candidate) { return candidate.image; }));
    } catch (err) {
        console.error('[Tablet Acceso] Error capturando ráfaga:', err);
        clearAccessResult();
        setHud('Coloque su rostro en el óvalo');
        isCooldown = false;
    } finally {
        if (burstGeneration === accessBurstGeneration) {
            isCollectingAccessBurst = false;
        }
    }
}

async function detectFaceLoop() {
    lastDetectTick = Date.now();

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
            if (accessStableSince === null) {
                accessStableSince = now;
            }
            if ((now - accessStableSince) >= ACCESS_FIRST_STABILITY_MS) {
                resetAccessStability();
                await collectAndSendAccessBurst(detection);
                lastCaptureTime = now;
            } else {
                setHud('Mantenga la cara quieta…');
            }
        } else {
            resetAccessStability();
            if (detection && !isProcessingAccess && !isQuickRetryMode) {
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
        }

        if (isQuickRetryMode && !isProcessingAccess && !isCooldown) {
            updateQuickRetryIdleTracking(meetsCriteria);
        }
    } catch (e) {
        console.error('Error en bucle de detección de acceso:', e);
    }

    requestAnimationFrame(detectFaceLoop);
}

function sendAccessBurst(images) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'FRAME_BURST', images: images }));
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
        attachCameraEndedHandler(stream);
        cameraFeed.addEventListener('loadedmetadata', function () {
            lastDetectTick = Date.now();
            requestAnimationFrame(detectFaceLoop);
        }, { once: true });
    } catch (err) {
        console.error('[Tablet Acceso] Error al iniciar cámara:', err);
        setStatus('disconnected', 'Sin cámara');
    }
}

function connectWebSocket() {
    clearTimeout(reconnectTimer);
    stopHeartbeat();
    socket = new WebSocket(WS_URL);

    socket.onopen = function () {
        onWsOpened();
    };

    socket.onclose = function () {
        onWsClosed();
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

    if (data.type === 'PONG') {
        notePongReceived();
        return;
    }

    if (data.type === 'TABLET_RELOAD') {
        requestSafeReload('dashboard_forced');
        return;
    }

    if (data.status === 'ERROR') {
        showAccessResult({
            status: 'DENIED',
            variant: 'denied_unknown',
            detail: data.reason || 'Error',
        });
        return;
    }

    if (data.status === 'PENDING' || data.variant === 'confirming') {
        showConfirmingIdentity(data);
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
    document.addEventListener('visibilitychange', function () {
        if (
            document.visibilityState === 'visible' &&
            (!socket || socket.readyState === WebSocket.CLOSED || socket.readyState === WebSocket.CLOSING)
        ) {
            clearTimeout(reconnectTimer);
            connectWebSocket();
        }
    });
    startDetectWatchdog();
    loadModels().then(startCamera).catch(function (err) {
        console.error('[Tablet Acceso] Error cargando IA:', err);
        setStatus('disconnected', 'Error IA');
    });
    connectWebSocket();
});
