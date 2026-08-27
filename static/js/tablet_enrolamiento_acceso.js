// tablet_enrolamiento_acceso.js — Una tablet: acceso (default) + enrolamiento (comando PC)
// Basado en Perfect Line tablet_access.js + tablet_enrollment.js (modo NCN).

const WS_URL = window.TABLET_WS_URL;
const RECONNECT_DELAY_MS = 3000;
const ACCESS_CAPTURE_COOLDOWN_MS = 2000;
const CONFIRM_CAPTURE_COOLDOWN_MS = 400;
const ACCESS_FIRST_STABILITY_MS = 400;
const ENROLLMENT_CAPTURE_COOLDOWN_MS = 2500;
const RESULT_DISPLAY_MS = 4000;
const RESULT_DISPLAY_DENIED_MS = 3200;
const RESULT_DISPLAY_DENIED_UNKNOWN_MS = 1600;
const COOLDOWN_RELEASE_MS = 300;
const QUICK_RETRY_IDLE_MS = 4000;
const JPEG_QUALITY = 0.9;
const WS_PING_MS = 20000;
const WS_PONG_TIMEOUT_MS = 45000;
const LONG_DISCONNECT_RELOAD_MS = 5 * 60 * 1000;
const CONFIRMING_MAX_MS = 4000;
const CONFIRM_ABANDON_MS = 1200;
const DETECT_WATCHDOG_MS = 15000;
const ACCESS_BURST_INTERVAL_MS = 150;
const ACCESS_BURST_SAMPLE_COUNT = 4;
const ACCESS_BURST_MIN_SEPARATION_MS = 250;
const ACCESS_FRAME_MAX_WIDTH = 1152;
const ACCESS_FRAME_MAX_HEIGHT = 648;
const ACCESS_FRAME_JPEG_QUALITY = 0.85;
const ACCESS_HUD_STICKY_MS = 400;
const ACCESS_HUD_IDLE = "Coloque su rostro en el óvalo";
const ACCESS_HUD_HOLD = "Mantenga la cara quieta…";
const ACCESS_UI_IDLE = "idle";
const ACCESS_UI_HOLD_STILL = "hold_still";
const ACCESS_UI_CAPTURING = "capturing";
const ACCESS_UI_VERIFYING = "verifying";
const ACCESS_UI_RESULT = "result";
const ACCESS_QUICK_RETRY_SUBTITLE = "Intente de nuevo";

const MODE_ACCESS = "access";
const MODE_ENROLLMENT = "enrollment";

const cameraFeed = document.getElementById("camera-feed");
const overlayCanvas = document.getElementById("overlay-canvas");
const statusDot = document.getElementById("status-dot");
const statusText = document.getElementById("status-text");
const faceGuide = document.getElementById("face-guide");
const faceGuideOval = document.querySelector(".access-guide-oval") || document.querySelector(".face-guide-oval");
const accessBottomBanner = document.getElementById("access-bottom-banner");
const accessBannerTitle = document.getElementById("access-banner-title");
const accessBannerSubtitle = document.getElementById("access-banner-subtitle");
const hudInstruction = document.getElementById("hud-instruction");
const hudText = document.getElementById("hud-text");
const enrollmentCoach = document.getElementById("enrollment-coach");
const enrollmentCoachText = document.getElementById("enrollment-coach-text");
const accessProcessingOverlay = document.getElementById("access-processing-overlay");
const accessProcessingLabel = document.getElementById("access-processing-label");
const termsOverlay = document.getElementById("terms-overlay");
const termsAcceptBtn = document.getElementById("terms-accept-btn");
const waitingOverlay = document.getElementById("enrollment-waiting-overlay");
const accessBurstCanvas = document.createElement("canvas");

let currentMode = MODE_ACCESS;
let socket = null;
let reconnectTimer = null;
let cameraStream = null;
let canvasCtx = overlayCanvas.getContext("2d");
let isModelsLoaded = false;
let accessLoopActive = false;

let isProcessingAccess = false;
let isCooldown = false;
let isConfirmingIdentity = false;
let isQuickRetryMode = false;
let resultTimeout = null;
let quickRetryTimeout = null;
let quickRetryNoValidFaceSince = null;
let serverTimeoutTimer = null;
let lastAccessCaptureTime = 0;
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
let pendingSoftReloadReason = "—";
let isCollectingAccessBurst = false;
let accessBurstGeneration = 0;
let accessUiState = ACCESS_UI_IDLE;
let accessHudPending = null;
let accessHudPendingSince = 0;
let accessHudShown = null;

// OPS_AUDIT
function sendOpsEvent(event, reason, detail) {
    try {
        if (!socket || socket.readyState !== WebSocket.OPEN) {
            return;
        }
        socket.send(JSON.stringify({
            type: "OPS",
            event: event || "—",
            reason: reason || "—",
            detail: detail || "—",
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
        currentMode === MODE_ACCESS &&
        !isProcessingAccess &&
        !isConfirmingIdentity &&
        !isEnrollmentCaptureActive &&
        accessBottomBanner.classList.contains("hidden")
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
        if (isConfirmingIdentity && currentMode === MODE_ACCESS) {
            abortConfirmingToIdle();
        }
    }, CONFIRMING_MAX_MS);
}

function sendConfirmAbort() {
    if (socket && socket.readyState === WebSocket.OPEN) {
        try {
            socket.send(JSON.stringify({ type: "CONFIRM_ABORT" }));
        } catch (err) { /* ignore */ }
    }
}

function abortConfirmingToIdle() {
    sendConfirmAbort();
    confirmAbandonSince = null;
    clearAccessResult();
    setAccessUiState(ACCESS_UI_IDLE, { immediate: true });
    isCooldown = false;
}

function noteConfirmingFacePresence(meetsCriteria, now) {
    if (!isConfirmingIdentity || currentMode !== MODE_ACCESS) {
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
            socket.send(JSON.stringify({ type: "PING" }));
        } catch (err) {
            return;
        }
        clearTimeout(pongTimer);
        pongTimer = setTimeout(function () {
            // OPS_AUDIT
            sendOpsEvent("pong_timeout", "pong_timeout", "—");
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
    sendOpsEvent("soft_reload", pendingSoftReloadReason || "—", "—");
    pendingSoftReloadReason = "—";
    window.location.reload();
}

function tryPendingSoftReload() {
    if (
        pendingSoftReload &&
        isAccessUiIdle() &&
        socket &&
        socket.readyState === WebSocket.OPEN
    ) {
        pendingSoftReload = false;
        // OPS_AUDIT
        sendOpsEvent("soft_reload", pendingSoftReloadReason || "—", "—");
        pendingSoftReloadReason = "—";
        window.location.reload();
    }
}

function onWsOpened() {
    const downMs = disconnectedSince ? Date.now() - disconnectedSince : 0;
    disconnectedSince = null;
    startHeartbeat();
    // OPS_AUDIT
    sendOpsEvent(
        "ws_open",
        downMs > 0 ? "reconnect" : "initial",
        "down_ms=" + downMs
    );
    if (currentMode === MODE_ENROLLMENT && !isEnrollmentCaptureActive && !enrollmentCaptureCompleted) {
        enterAccessMode();
    } else if (currentMode === MODE_ACCESS) {
        enterAccessMode();
    }
    if (downMs >= LONG_DISCONNECT_RELOAD_MS && !softReloadDoneForThisDown) {
        softReloadDoneForThisDown = true;
        requestSafeReload("offline_ge_5min");
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
    setStatus("disconnected", "Sin conexión...");
    stopAccessLoop();
    if (currentMode === MODE_ACCESS) {
        clearAccessResult();
    }
    reconnectTimer = setTimeout(connectWebSocket, RECONNECT_DELAY_MS);
}

function startDetectWatchdog() {
    clearInterval(detectWatchdogTimer);
    detectWatchdogTimer = setInterval(function () {
        if (document.visibilityState !== "visible" || currentMode !== MODE_ACCESS) {
            return;
        }
        if (!accessLoopActive) {
            return;
        }
        if (Date.now() - lastDetectTick > DETECT_WATCHDOG_MS) {
            detectRestartCount += 1;
            lastDetectTick = Date.now();
            // OPS_AUDIT
            sendOpsEvent("detect_stall", "detect_watchdog", "stalls=" + detectRestartCount);
            stopAccessLoop();
            startAccessLoop();
            if (detectRestartCount >= 2) {
                detectRestartCount = 0;
                requestSafeReload("detect_watchdog");
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
    tracks[0].addEventListener("ended", function () {
        if (cameraRetrying) {
            return;
        }
        const recoverAccess = currentMode === MODE_ACCESS;
        const recoverEnrollment =
            currentMode === MODE_ENROLLMENT
            && isEnrollmentCaptureActive
            && !enrollmentCaptureCompleted;
        if (!recoverAccess && !recoverEnrollment) {
            return;
        }
        cameraRetrying = true;
        // OPS_AUDIT
        sendOpsEvent("camera_ended", "camera_ended", currentMode);
        stopCameraTracks();
        ensureCamera()
            .then(function () {
                if (recoverAccess && currentMode === MODE_ACCESS) {
                    stopAccessLoop();
                    startAccessLoop();
                    return;
                }
                if (
                    recoverEnrollment
                    && currentMode === MODE_ENROLLMENT
                    && isEnrollmentCaptureActive
                    && !enrollmentCaptureCompleted
                ) {
                    startEnrollmentDetectionLoop();
                }
            })
            .catch(function (err) {
                console.error("[Tablet EA] Error reintentando cámara:", err);
                setStatus("disconnected", "Sin cámara");
            })
            .finally(function () {
                cameraRetrying = false;
            });
    });
}

let isEnrollmentCaptureActive = false;
let enrollmentCaptureCompleted = false;
let termsAcceptedThisSession = false;
let skipTermsAfterCapture = false;
let lastEnrollmentCaptureTime = 0;
let enrollmentDetectionRunning = false;
let stableSince = null;
let enrollmentSessionId = 0;
let postCaptureUiTimer = null;
let enrollmentCameraResumeAt = 0;
const enrollmentHud = TabletFaceUtils.createEnrollmentHudController(hudText, {
    coachEl: enrollmentCoach,
    coachTextEl: enrollmentCoachText,
    hudBubbleEl: hudInstruction,
});

function clearPostCaptureUiTimer() {
    if (postCaptureUiTimer !== null) {
        clearTimeout(postCaptureUiTimer);
        postCaptureUiTimer = null;
    }
}

function playCameraFeed() {
    try {
        const playResult = cameraFeed.play();
        if (playResult && typeof playResult.then === "function") {
            return playResult.catch(function () {
                return null;
            });
        }
    } catch (err) {
        /* autoplay bloqueado: el bucle reintenta */
    }
    return Promise.resolve();
}

function cameraStreamIsLive() {
    if (!cameraStream) {
        return false;
    }
    const tracks = cameraStream.getVideoTracks();
    let i;
    for (i = 0; i < tracks.length; i += 1) {
        if (tracks[i].readyState === "live") {
            return true;
        }
    }
    return false;
}

function tryResumeEnrollmentCamera(sessionId) {
    if (sessionId !== enrollmentSessionId || cameraRetrying) {
        return;
    }
    const now = Date.now();
    if (now - enrollmentCameraResumeAt < 1000) {
        return;
    }
    enrollmentCameraResumeAt = now;

    if (cameraStreamIsLive() && cameraFeed.paused) {
        playCameraFeed();
        return;
    }

    cameraRetrying = true;
    stopCameraTracks();
    ensureCamera()
        .then(function () {
            if (sessionId !== enrollmentSessionId) {
                return null;
            }
            return playCameraFeed();
        })
        .catch(function (err) {
            console.error("[Tablet EA] Error recuperando cámara en enrolamiento:", err);
            if (sessionId === enrollmentSessionId) {
                setStatus("disconnected", "Sin cámara");
                enrollmentHud.show("No se pudo acceder a la cámara.", Date.now(), {
                    immediate: true,
                });
            }
        })
        .finally(function () {
            cameraRetrying = false;
        });
}

async function loadModels() {
    const MODEL_URL = "/static/models";
    await Promise.all([
        faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
        faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
    ]);
    isModelsLoaded = true;
}

function setStatus(state, text) {
    statusDot.className = state;
    statusText.textContent = text;
}

function setHud(text) {
    if (!text) {
        return;
    }
    accessHudShown = text;
    accessHudPending = null;
    hudText.textContent = text;
}

function commitAccessHud(text, immediate) {
    const now = Date.now();
    if (!text) {
        return;
    }
    if (immediate || text === ACCESS_HUD_HOLD) {
        setHud(text);
        return;
    }
    if (text === accessHudShown) {
        accessHudPending = null;
        return;
    }
    if (text !== accessHudPending) {
        accessHudPending = text;
        accessHudPendingSince = now;
        return;
    }
    if (now - accessHudPendingSince >= ACCESS_HUD_STICKY_MS) {
        setHud(text);
    }
}

function resetAccessHudSticky(initialText) {
    accessHudPending = null;
    accessHudPendingSince = 0;
    accessHudShown = null;
    if (initialText) {
        setHud(initialText);
    }
}

function setAccessUiState(state, options) {
    if (currentMode !== MODE_ACCESS) {
        return;
    }
    options = options || {};
    accessUiState = state;

    if (state === ACCESS_UI_IDLE || state === ACCESS_UI_HOLD_STILL || state === ACCESS_UI_CAPTURING) {
        hideProcessingOverlay();
        if (isQuickRetryMode) {
            hudInstruction.classList.add("hidden");
            if (accessBottomBanner.classList.contains("hidden")) {
                showBottomBanner("denied_unknown", "No reconocido", ACCESS_QUICK_RETRY_SUBTITLE);
            } else if (state === ACCESS_UI_IDLE) {
                updateBottomBannerSubtitle(ACCESS_QUICK_RETRY_SUBTITLE);
            } else {
                updateBottomBannerSubtitle(ACCESS_HUD_HOLD);
            }
            return;
        }
        hideBottomBanner();
        setFaceGuideVariant("");
        hudInstruction.classList.remove("hidden");
        if (state === ACCESS_UI_IDLE) {
            commitAccessHud(ACCESS_HUD_IDLE, options.immediate);
        } else {
            commitAccessHud(ACCESS_HUD_HOLD, true);
        }
        return;
    }

    if (state === ACCESS_UI_VERIFYING) {
        hideProcessingOverlay();
        hudInstruction.classList.add("hidden");
        cancelQuickRetryIdleReset();
        setFaceGuideVariant("processing");
        const title = options.title || "Verificando…";
        const subtitle = options.subtitle || "Un momento por favor";
        if (isQuickRetryMode && !accessBottomBanner.classList.contains("hidden")) {
            accessBannerTitle.textContent = title;
            updateBottomBannerSubtitle(subtitle);
            accessBottomBanner.classList.remove(
                "granted",
                "granted_staff",
                "granted_guest",
                "granted_grace",
                "denied_unknown",
                "denied_suspended",
                "denied_schedule",
                "denied_cooldown",
                "denied_other"
            );
            accessBottomBanner.classList.add("processing");
        } else {
            showBottomBanner("processing", title, subtitle);
        }
        return;
    }

    if (state === ACCESS_UI_RESULT) {
        hideProcessingOverlay();
        hudInstruction.classList.add("hidden");
        setFaceGuideVariant(options.variant || "");
        showBottomBanner(options.variant || "denied_other", options.title || "", options.subtitle || "");
    }
}

function resetStability() {
    stableSince = null;
}

function hideTermsScreen() {
    if (termsOverlay) {
        termsOverlay.classList.add("hidden");
    }
}

function hideWaitingScreen() {
    if (waitingOverlay) {
        waitingOverlay.classList.add("hidden");
    }
}

function showWaitingScreen() {
    hideTermsScreen();
    enrollmentHud.hideCoach();
    if (waitingOverlay) {
        waitingOverlay.classList.remove("hidden");
    }
    setStatus("connected", "Espere");
}

function showTermsScreen() {
    showWaitingScreen();
}

function isGrantedVariant(variant) {
    return (
        variant === "granted" ||
        variant === "granted_staff" ||
        variant === "granted_guest" ||
        variant === "granted_grace"
    );
}

function setFaceGuideVariant(variant) {
    faceGuide.className =
        "face-guide face-guide-access active" + (variant ? " " + variant : "");
}

function hideBottomBanner() {
    accessBottomBanner.className = "access-bottom-banner hidden";
    accessBottomBanner.classList.remove(
        "granted",
        "granted_staff",
        "granted_guest",
        "granted_grace",
        "denied_unknown",
        "denied_suspended",
        "denied_schedule",
        "denied_cooldown",
        "denied_other",
        "processing"
    );
}

function showBottomBanner(variant, title, subtitle) {
    hideBottomBanner();
    accessBottomBanner.classList.remove("hidden");
    accessBottomBanner.classList.add(variant);
    accessBannerTitle.textContent = title;
    accessBannerSubtitle.textContent = subtitle || "";
}

function updateBottomBannerSubtitle(subtitle) {
    accessBannerSubtitle.textContent = subtitle || "";
}

function showProcessingOverlay(label) {
    if (!accessProcessingOverlay) {
        return;
    }
    accessProcessingLabel.textContent = label;
    accessProcessingOverlay.classList.remove("hidden");
}

function hideProcessingOverlay() {
    if (accessProcessingOverlay) {
        accessProcessingOverlay.classList.add("hidden");
    }
}

function cancelQuickRetryIdleReset() {
    quickRetryNoValidFaceSince = null;
}

function updateQuickRetryIdleTracking(meetsCriteria) {
    if (!isQuickRetryMode || isProcessingAccess || isCooldown || currentMode !== MODE_ACCESS) {
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
    setAccessUiState(ACCESS_UI_IDLE, { immediate: true });
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

function clearAccessTimers() {
    clearTimeout(resultTimeout);
    clearTimeout(quickRetryTimeout);
    clearTimeout(serverTimeoutTimer);
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
    setFaceGuideVariant("");
    hideBottomBanner();
    hudInstruction.classList.remove("hidden");
    isProcessingAccess = false;
    accessUiState = ACCESS_UI_IDLE;
    tryPendingSoftReload();
}

function formatCutLine(data) {
    if (data.covered_until_display) {
        return "Vigente hasta " + data.covered_until_display;
    }
    if (data.next_cut_display) {
        return "Próximo corte: " + data.next_cut_display;
    }
    if (data.cut_day) {
        return "Fecha de corte: día " + data.cut_day + " de cada mes";
    }
    if (data.days_until_cut != null) {
        const days = data.days_until_cut;
        const dayWord = days === 1 ? "día" : "días";
        return "Faltan " + days + " " + dayWord + " para el corte";
    }
    if (data.days_membership_left != null) {
        const days = data.days_membership_left;
        const dayWord = days === 1 ? "día" : "días";
        return "Membresía activa: " + days + " " + dayWord;
    }
    return "";
}

function buildResultCopy(data, variant) {
    let title = "";
    let subtitle = "";

    if (isGrantedVariant(variant)) {
        if (variant === "granted_grace") {
            title = "Período de gracia";
            const name = data.name ? data.name + " — " : "";
            const remaining = data.grace_days_remaining;
            let graceLine = "Debe pagar en caja";
            if (remaining !== undefined && remaining !== null) {
                const dayWord = remaining === 1 ? "día" : "días";
                graceLine =
                    remaining +
                    " " +
                    dayWord +
                    " de acceso restante" +
                    (remaining === 1 ? "" : "s");
            }
            if (data.grace_until_display) {
                graceLine += " · Hasta " + data.grace_until_display;
            }
            subtitle = name + graceLine;
        } else {
            title = "¡Aprobado!";
            const name = data.name ? data.name + " — " : "";
            if (variant === "granted_staff") {
                subtitle = name + (data.detail || "Acceso personal");
            } else if (variant === "granted_guest") {
                const guestLine = data.pass_until_display
                    ? "Pase vigente hasta " + data.pass_until_display
                    : data.detail || "Acceso de invitado";
                const sponsor = data.sponsor_name ? " · Responsable: " + data.sponsor_name : "";
                subtitle = name + guestLine + sponsor;
            } else {
                const cutLine = formatCutLine(data);
                subtitle = name + (cutLine || "Acceso concedido");
            }
        }
    } else if (variant === "denied_unknown") {
        title = "No reconocido";
        subtitle = data.detail || "Rostro no registrado en el sistema";
    } else if (variant === "denied_schedule") {
        title = "Fuera de horario";
        subtitle = (data.name ? data.name + " — " : "") + (data.detail || "Horario no permitido");
    } else if (variant === "denied_cooldown") {
        title = "Espere un momento";
        const waitLine = data.cooldown_remaining_display
            ? "Puede volver a intentar en " + data.cooldown_remaining_display
            : data.detail || "Debe esperar antes de volver a entrar";
        subtitle = (data.name ? data.name + " — " : "") + waitLine;
    } else if (variant === "denied_suspended") {
        title = "Acceso suspendido";
        const since = data.suspended_since_display
            ? "Suspendido desde " + data.suspended_since_display
            : data.detail || "Suscripción sin pagar";
        subtitle = (data.name ? data.name + " — " : "") + since;
    } else {
        title = "Acceso denegado";
        subtitle = (data.name ? data.name + " — " : "") + (data.detail || data.reason || "");
    }

    return { title: title, subtitle: subtitle };
}

function showAccessProcessing() {
    cancelQuickRetryIdleReset();
    isProcessingAccess = true;
    setAccessUiState(ACCESS_UI_VERIFYING, {
        title: "Verificando…",
        subtitle: "Un momento por favor",
    });
}

function scheduleDeniedUnknownQuickRetry(title, subtitle) {
    clearTimeout(quickRetryTimeout);
    quickRetryTimeout = setTimeout(function () {
        quickRetryTimeout = null;
        if (currentMode !== MODE_ACCESS) {
            return;
        }
        enterQuickRetryMode();
        showBottomBanner("denied_unknown", title || "No reconocido", ACCESS_QUICK_RETRY_SUBTITLE);
        accessUiState = ACCESS_UI_IDLE;
    }, RESULT_DISPLAY_DENIED_UNKNOWN_MS);
}

function scheduleFullResultClear() {
    clearTimeout(resultTimeout);
    resultTimeout = setTimeout(function () {
        if (currentMode !== MODE_ACCESS) {
            return;
        }
        clearAccessResult();
        resetAccessHudSticky(ACCESS_HUD_IDLE);
        setTimeout(function () {
            if (currentMode === MODE_ACCESS) {
                isCooldown = false;
            }
        }, COOLDOWN_RELEASE_MS);
    }, RESULT_DISPLAY_DENIED_MS);
}

function showConfirmingIdentity(data) {
    if (currentMode !== MODE_ACCESS) {
        return;
    }
    cancelQuickRetryIdleReset();
    isConfirmingIdentity = true;
    isProcessingAccess = false;
    isCooldown = false;
    confirmAbandonSince = null;
    resetAccessStability();
    startConfirmingWatchdog();
    setAccessUiState(ACCESS_UI_VERIFYING, {
        title: "Siga frente a la cámara",
        subtitle: "",
    });
}

function showAccessResult(data) {
    if (currentMode !== MODE_ACCESS) {
        return;
    }

    const variant = data.variant || (data.status === "GRANTED" ? "granted" : "denied_unknown");
    isConfirmingIdentity = false;
    confirmAbandonSince = null;
    clearConfirmingWatchdog();
    isProcessingAccess = false;

    const copy = buildResultCopy(data, variant);
    setAccessUiState(ACCESS_UI_RESULT, {
        variant: variant,
        title: copy.title,
        subtitle: copy.subtitle,
    });

    clearTimeout(resultTimeout);
    clearTimeout(quickRetryTimeout);

    if (isGrantedVariant(variant)) {
        exitQuickRetryMode();
        isCooldown = true;
        resultTimeout = setTimeout(function () {
            if (currentMode !== MODE_ACCESS) {
                return;
            }
            clearAccessResult();
            resetAccessHudSticky(ACCESS_HUD_IDLE);
            setTimeout(function () {
                if (currentMode === MODE_ACCESS) {
                    isCooldown = false;
                }
            }, COOLDOWN_RELEASE_MS);
        }, RESULT_DISPLAY_MS);
        return;
    }

    if (variant === "denied_unknown") {
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
    const sourceWidth = cameraFeed.videoWidth;
    const sourceHeight = cameraFeed.videoHeight;
    const scale = Math.min(
        1,
        ACCESS_FRAME_MAX_WIDTH / Math.max(1, sourceWidth),
        ACCESS_FRAME_MAX_HEIGHT / Math.max(1, sourceHeight)
    );
    const frameWidth = Math.max(1, Math.round(sourceWidth * scale));
    const frameHeight = Math.max(1, Math.round(sourceHeight * scale));
    accessBurstCanvas.width = frameWidth;
    accessBurstCanvas.height = frameHeight;
    const ctx = accessBurstCanvas.getContext("2d");
    ctx.setTransform(-1, 0, 0, 1, frameWidth, 0);
    ctx.drawImage(cameraFeed, 0, 0, frameWidth, frameHeight);

    const det = TabletFaceUtils.getFaceDetection(detection);
    const box = det && det.box;
    let brightnessScore = 0.5;
    let sharpnessScore = 0.5;
    let sizeScore = 0;

    if (box && box.width > 0 && box.height > 0) {
        const sample = document.createElement("canvas");
        sample.width = 64;
        sample.height = 64;
        const sampleCtx = sample.getContext("2d", { willReadFrequently: true });
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
            const luminance =
                (pixels[i] * 0.299) +
                (pixels[i + 1] * 0.587) +
                (pixels[i + 2] * 0.114);
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

    const detectionScore = det && typeof det.score === "number" ? det.score : 0;
    return {
        image: accessBurstCanvas.toDataURL("image/jpeg", ACCESS_FRAME_JPEG_QUALITY),
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
    let bestPair = null;
    let bestPairScore = -Infinity;
    for (let i = 0; i < limited.length; i += 1) {
        for (let j = i + 1; j < limited.length; j += 1) {
            if (limited[j].capturedAt - limited[i].capturedAt >= ACCESS_BURST_MIN_SEPARATION_MS) {
                const pairScore = limited[i].score + limited[j].score;
                if (pairScore > bestPairScore) {
                    bestPair = [limited[i], limited[j]];
                    bestPairScore = pairScore;
                }
            }
        }
    }
    if (!bestPair) {
        return null;
    }
    bestPair.sort(function (a, b) {
        return (b.score - a.score) || (a.capturedAt - b.capturedAt);
    });
    const remaining = limited.filter(function (candidate) {
        return candidate !== bestPair[0] && candidate !== bestPair[1];
    }).sort(function (a, b) {
        return (b.score - a.score) || (a.capturedAt - b.capturedAt);
    });
    return bestPair.concat(remaining);
}

async function collectAndSendAccessBurst(initialDetection) {
    if (isCollectingAccessBurst || isProcessingAccess || currentMode !== MODE_ACCESS) {
        return;
    }
    const burstGeneration = ++accessBurstGeneration;
    isCollectingAccessBurst = true;
    isProcessingAccess = true;
    setAccessUiState(ACCESS_UI_CAPTURING);
    const candidates = [captureBurstCandidate(initialDetection)];

    try {
        for (let i = 1; i < ACCESS_BURST_SAMPLE_COUNT; i += 1) {
            await waitMs(ACCESS_BURST_INTERVAL_MS);
            if (
                currentMode !== MODE_ACCESS ||
                burstGeneration !== accessBurstGeneration
            ) {
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
            setAccessUiState(ACCESS_UI_IDLE, { immediate: true });
            isCooldown = false;
            return;
        }
        showAccessProcessing();
        sendAccessBurst(samples.map(function (candidate) { return candidate.image; }));
    } catch (err) {
        console.error("[Tablet EA] Error capturando ráfaga:", err);
        clearAccessResult();
        setAccessUiState(ACCESS_UI_IDLE, { immediate: true });
        isCooldown = false;
    } finally {
        if (burstGeneration === accessBurstGeneration) {
            isCollectingAccessBurst = false;
        }
    }
}

async function accessDetectLoop() {
    if (!accessLoopActive || currentMode !== MODE_ACCESS) {
        return;
    }

    lastDetectTick = Date.now();

    if (!isModelsLoaded || cameraFeed.paused || cameraFeed.ended) {
        requestAnimationFrame(accessDetectLoop);
        return;
    }

    const displaySize = { width: cameraFeed.videoWidth, height: cameraFeed.videoHeight };
    if (overlayCanvas.width !== displaySize.width) {
        faceapi.matchDimensions(overlayCanvas, displaySize);
    }

    const now = Date.now();
    const cooldownOk =
        isQuickRetryMode ||
        now - lastAccessCaptureTime > ACCESS_CAPTURE_COOLDOWN_MS;

    try {
        const detection = await faceapi.detectSingleFace(
            cameraFeed,
            TabletFaceUtils.accessDetectorOptions()
        );
        canvasCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

        let meetsCriteria = false;

        if (detection) {
            const resizedDetection = faceapi.resizeResults(detection, displaySize);
            meetsCriteria = TabletFaceUtils.meetsAccessCaptureCriteria(
                detection,
                resizedDetection,
                cameraFeed,
                faceGuideOval
            );
        }

        if (detection && cooldownOk && !isProcessingAccess && !isCooldown && meetsCriteria) {
            if (accessStableSince === null) {
                accessStableSince = now;
            }
            if (now - accessStableSince >= ACCESS_FIRST_STABILITY_MS) {
                resetAccessStability();
                await collectAndSendAccessBurst(detection);
                lastAccessCaptureTime = now;
            } else {
                setAccessUiState(ACCESS_UI_HOLD_STILL);
            }
        } else {
            resetAccessStability();
            if (!isProcessingAccess && !isCooldown && accessUiState !== ACCESS_UI_RESULT) {
                setAccessUiState(ACCESS_UI_IDLE);
            }
        }

        if (isQuickRetryMode && !isProcessingAccess && !isCooldown) {
            updateQuickRetryIdleTracking(meetsCriteria);
        }
    } catch (e) {
        console.error("[Tablet EA] Error en bucle de acceso:", e);
    }

    requestAnimationFrame(accessDetectLoop);
}

function startAccessLoop() {
    if (!accessLoopActive) {
        accessLoopActive = true;
        requestAnimationFrame(accessDetectLoop);
    }
}

function stopAccessLoop() {
    accessLoopActive = false;
}

function sendAccessBurst(images) {
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "FRAME_BURST", images: images }));
        clearTimeout(serverTimeoutTimer);
        serverTimeoutTimer = setTimeout(function () {
            if (isProcessingAccess && currentMode === MODE_ACCESS) {
                showAccessResult({
                    status: "DENIED",
                    variant: "denied_unknown",
                    detail: "Sin respuesta del servidor",
                });
            }
        }, 8000);
    } else {
        showAccessResult({
            status: "DENIED",
            variant: "denied_unknown",
            detail: "Sin conexión con el servidor",
        });
    }
}

async function enrollmentDetectLoop(sessionId) {
    if (
        sessionId !== enrollmentSessionId
        || !isEnrollmentCaptureActive
        || !isModelsLoaded
        || enrollmentCaptureCompleted
        || currentMode !== MODE_ENROLLMENT
    ) {
        if (sessionId === enrollmentSessionId) {
            enrollmentDetectionRunning = false;
        }
        return;
    }

    if (cameraFeed.paused || cameraFeed.ended || !cameraStreamIsLive()) {
        tryResumeEnrollmentCamera(sessionId);
        requestAnimationFrame(function () {
            enrollmentDetectLoop(sessionId);
        });
        return;
    }

    const displaySize = { width: cameraFeed.videoWidth, height: cameraFeed.videoHeight };
    if (!displaySize.width || !displaySize.height) {
        requestAnimationFrame(function () {
            enrollmentDetectLoop(sessionId);
        });
        return;
    }
    if (overlayCanvas.width !== displaySize.width) {
        faceapi.matchDimensions(overlayCanvas, displaySize);
    }

    const now = Date.now();
    const canCapture = now - lastEnrollmentCaptureTime > ENROLLMENT_CAPTURE_COOLDOWN_MS;

    try {
        const detection = await faceapi
            .detectSingleFace(cameraFeed, TabletFaceUtils.detectorOptions())
            .withFaceLandmarks();
        if (sessionId !== enrollmentSessionId) {
            return;
        }
        canvasCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

        if (detection && canCapture) {
            const resizedDetection = faceapi.resizeResults(detection, displaySize);

            if (
                TabletFaceUtils.meetsCaptureCriteria(
                    detection,
                    resizedDetection,
                    cameraFeed,
                    faceGuideOval
                )
            ) {
                if (stableSince === null) {
                    stableSince = now;
                }

                if (now - stableSince >= TabletFaceUtils.STABILITY_MS) {
                    enrollmentHud.show(TabletFaceUtils.ENROLLMENT_BUBBLE_CAPTURING, now, { immediate: true });
                    sendEnrollmentPhoto();
                    lastEnrollmentCaptureTime = now;
                    enrollmentCaptureCompleted = true;
                    resetStability();
                    const sessionAtCapture = enrollmentSessionId;
                    clearPostCaptureUiTimer();
                    postCaptureUiTimer = setTimeout(function () {
                        postCaptureUiTimer = null;
                        if (
                            enrollmentSessionId !== sessionAtCapture
                            || currentMode !== MODE_ENROLLMENT
                            || !enrollmentCaptureCompleted
                        ) {
                            return;
                        }
                        stopCameraTracks();
                        faceGuide.classList.remove("active");
                        faceGuide.classList.remove("face-guide-access");
                        hudInstruction.classList.add("hidden");
                        enrollmentHud.hideCoach();
                        isEnrollmentCaptureActive = false;
                        if (skipTermsAfterCapture) {
                            showWaitingScreen();
                        } else {
                            showTermsScreen();
                        }
                    }, 1200);
                } else {
                    enrollmentHud.show(TabletFaceUtils.ENROLLMENT_COACH_HOLD, now, { immediate: true });
                }
            } else {
                resetStability();
                enrollmentHud.show(
                    TabletFaceUtils.getEnrollmentHudMessage(
                        detection,
                        resizedDetection,
                        cameraFeed,
                        faceGuideOval
                    ) || TabletFaceUtils.ENROLLMENT_COACH_CENTER,
                    now
                );
            }
        } else if (!detection) {
            resetStability();
            enrollmentHud.show(
                TabletFaceUtils.getEnrollmentHudMessage(
                    null,
                    null,
                    cameraFeed,
                    faceGuideOval
                ) || TabletFaceUtils.ENROLLMENT_COACH_CENTER,
                now
            );
        }
    } catch (e) {
        console.error("[Tablet EA] Error en bucle de enrolamiento:", e);
        resetStability();
    }

    requestAnimationFrame(function () {
        enrollmentDetectLoop(sessionId);
    });
}

function startEnrollmentDetectionLoop() {
    if (
        !isEnrollmentCaptureActive
        || enrollmentCaptureCompleted
        || currentMode !== MODE_ENROLLMENT
    ) {
        return;
    }
    if (enrollmentDetectionRunning) {
        return;
    }
    const sessionId = enrollmentSessionId;
    enrollmentDetectionRunning = true;
    requestAnimationFrame(function () {
        enrollmentDetectLoop(sessionId);
    });
}

function sendEnrollmentPhoto() {
    const canvas = document.createElement("canvas");
    canvas.width = cameraFeed.videoWidth;
    canvas.height = cameraFeed.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(cameraFeed, 0, 0, canvas.width, canvas.height);
    const dataURL = canvas.toDataURL("image/jpeg", JPEG_QUALITY);

    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(
            JSON.stringify({
                type: "ENROLLMENT_PHOTO",
                photoType: "FRONT",
                image: dataURL,
            })
        );
    }
}

async function ensureCamera() {
    if (cameraStreamIsLive()) {
        await playCameraFeed();
        return;
    }
    if (cameraStream) {
        stopCameraTracks();
    }
    const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
    });
    cameraStream = stream;
    cameraFeed.srcObject = stream;
    attachCameraEndedHandler(stream);
    await new Promise(function (resolve) {
        cameraFeed.addEventListener("loadedmetadata", resolve, { once: true });
    });
    await playCameraFeed();
}

function stopCameraTracks() {
    if (cameraStream) {
        cameraStream.getTracks().forEach(function (track) {
            track.stop();
        });
        cameraStream = null;
    }
    cameraFeed.srcObject = null;
    canvasCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
}

function resetEnrollmentState() {
    clearPostCaptureUiTimer();
    enrollmentSessionId += 1;
    isEnrollmentCaptureActive = false;
    enrollmentCaptureCompleted = false;
    termsAcceptedThisSession = false;
    skipTermsAfterCapture = false;
    enrollmentDetectionRunning = false;
    resetStability();
    hideTermsScreen();
    hideWaitingScreen();
    enrollmentHud.hideCoach();
}

async function enterAccessMode() {
    currentMode = MODE_ACCESS;
    resetEnrollmentState();
    clearAccessTimers();
    clearAccessResult();
    isCooldown = false;
    isProcessingAccess = false;
    lastAccessCaptureTime = 0;

    faceGuide.classList.add("face-guide-access");
    faceGuide.classList.add("active");
    setAccessUiState(ACCESS_UI_IDLE, { immediate: true });

    try {
        await ensureCamera();
        stopAccessLoop();
        startAccessLoop();
        setStatus("connected", "Conectado");
    } catch (err) {
        console.error("[Tablet EA] Error al iniciar cámara:", err);
        setStatus("disconnected", "Sin cámara");
    }
}

async function startEnrollmentSession() {
    clearPostCaptureUiTimer();
    enrollmentSessionId += 1;
    const sessionId = enrollmentSessionId;
    currentMode = MODE_ENROLLMENT;
    clearAccessTimers();
    clearAccessResult();
    stopAccessLoop();
    isCooldown = true;
    isProcessingAccess = false;

    hideTermsScreen();
    hideWaitingScreen();
    faceGuide.classList.add("active");
    faceGuide.classList.remove("face-guide-access");
    hudInstruction.classList.remove("hidden");
    enrollmentHud.reset(TabletFaceUtils.ENROLLMENT_COACH_CENTER);
    enrollmentCaptureCompleted = false;
    termsAcceptedThisSession = false;
    skipTermsAfterCapture = false;
    isEnrollmentCaptureActive = true;
    enrollmentDetectionRunning = false;
    enrollmentCameraResumeAt = 0;
    resetStability();
    setStatus("connected", "Capturando");

    try {
        stopCameraTracks();
        await ensureCamera();
        if (sessionId !== enrollmentSessionId) {
            return;
        }
        startEnrollmentDetectionLoop();
    } catch (err) {
        console.error("[Tablet EA] Error iniciando enrolamiento:", err);
        if (sessionId === enrollmentSessionId) {
            enrollmentHud.show("No se pudo acceder a la cámara.", Date.now(), {
                immediate: true,
            });
            setStatus("disconnected", "Sin cámara");
        }
    }
}

function finishEnrollmentWaiting() {
    hideTermsScreen();
    hideWaitingScreen();
    faceGuide.classList.remove("active");
    hudInstruction.classList.add("hidden");
    enrollmentHud.hideCoach();
    isEnrollmentCaptureActive = false;
    stopCameraTracks();
    setStatus("connected", termsAcceptedThisSession ? "Listo" : "Foto lista");
}

function stopEnrollmentSession() {
    enterAccessMode();
}

function acceptTermsOnTablet() {
    if (termsAcceptedThisSession) {
        return;
    }
    termsAcceptedThisSession = true;
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "ENROLLMENT_TERMS_ACCEPTED" }));
    }
    faceGuide.classList.remove("active");
    hudInstruction.classList.add("hidden");
    enrollmentHud.hideCoach();
    stopCameraTracks();
    isEnrollmentCaptureActive = false;
    showWaitingScreen();
}

function skipTermsOnTablet() {
    termsAcceptedThisSession = true;
    skipTermsAfterCapture = true;
    hideTermsScreen();
    if (enrollmentCaptureCompleted) {
        faceGuide.classList.remove("active");
        hudInstruction.classList.add("hidden");
        enrollmentHud.hideCoach();
        stopCameraTracks();
        isEnrollmentCaptureActive = false;
        showWaitingScreen();
    }
}

function requireTermsOnTablet() {
    termsAcceptedThisSession = false;
    skipTermsAfterCapture = false;
    if (enrollmentCaptureCompleted) {
        showTermsScreen();
        setStatus("connected", "Lea y acepte");
    }
}

function handleEnrollmentCommand(data) {
    if (data.type === "ENROLLMENT_START") {
        startEnrollmentSession();
    } else if (data.type === "ENROLLMENT_END") {
        stopEnrollmentSession();
    } else if (data.type === "ENROLLMENT_SKIP_TERMS") {
        skipTermsOnTablet();
    } else if (data.type === "ENROLLMENT_REQUIRE_TERMS") {
        requireTermsOnTablet();
    }
}

function handleAccessResponse(data) {
    if (currentMode !== MODE_ACCESS) {
        return;
    }

    clearTimeout(serverTimeoutTimer);

    if (data.status === "ERROR") {
        showAccessResult({
            status: "DENIED",
            variant: "denied_unknown",
            detail: data.reason || "Error",
        });
        return;
    }

    if (data.status === "PENDING" || data.variant === "confirming") {
        showConfirmingIdentity(data);
        return;
    }

    if (data.status === "GRANTED" || data.status === "DENIED") {
        if (!data.variant) {
            data.variant = data.status === "GRANTED" ? "granted" : "denied_unknown";
        }
        showAccessResult(data);
    }
}

function handleServerMessage(data) {
    if (data.type === "PONG") {
        notePongReceived();
        return;
    }
    if (data.type === "TABLET_RELOAD") {
        requestSafeReload("dashboard_forced");
        return;
    }
    if (data.type && String(data.type).indexOf("ENROLLMENT_") === 0) {
        handleEnrollmentCommand(data);
        return;
    }
    handleAccessResponse(data);
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
            console.error("[Tablet EA] Mensaje inválido:", event.data);
        }
    };
}

document.addEventListener("DOMContentLoaded", function () {
    if (termsAcceptBtn) {
        termsAcceptBtn.addEventListener("click", acceptTermsOnTablet);
    }
    document.addEventListener("visibilitychange", function () {
        if (
            document.visibilityState === "visible" &&
            (!socket || socket.readyState === WebSocket.CLOSED || socket.readyState === WebSocket.CLOSING)
        ) {
            clearTimeout(reconnectTimer);
            connectWebSocket();
        }
    });
    startDetectWatchdog();
    loadModels()
        .then(function () {
            return enterAccessMode();
        })
        .then(function () {
            connectWebSocket();
        })
        .catch(function (err) {
            console.error("[Tablet EA] Error cargando IA:", err);
            setStatus("disconnected", "Error IA");
        });
});
