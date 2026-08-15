// tablet_enrolamiento_acceso.js — Una tablet: acceso (default) + enrolamiento (comando PC)
// Basado en Perfect Line tablet_access.js + tablet_enrollment.js (modo NCN).

const WS_URL = window.TABLET_WS_URL;
const RECONNECT_DELAY_MS = 3000;
const ACCESS_CAPTURE_COOLDOWN_MS = 2000;
const ENROLLMENT_CAPTURE_COOLDOWN_MS = 2500;
const RESULT_DISPLAY_MS = 4000;
const RESULT_DISPLAY_DENIED_MS = 3200;
const RESULT_DISPLAY_DENIED_UNKNOWN_MS = 1600;
const COOLDOWN_RELEASE_MS = 300;
const QUICK_RETRY_IDLE_MS = 4000;
const JPEG_QUALITY = 0.9;

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
const accessProcessingOverlay = document.getElementById("access-processing-overlay");
const accessProcessingLabel = document.getElementById("access-processing-label");
const termsOverlay = document.getElementById("terms-overlay");
const termsAcceptBtn = document.getElementById("terms-accept-btn");
const waitingOverlay = document.getElementById("enrollment-waiting-overlay");

let currentMode = MODE_ACCESS;
let socket = null;
let reconnectTimer = null;
let cameraStream = null;
let canvasCtx = overlayCanvas.getContext("2d");
let isModelsLoaded = false;
let accessLoopActive = false;

let isProcessingAccess = false;
let isCooldown = false;
let isQuickRetryMode = false;
let resultTimeout = null;
let quickRetryTimeout = null;
let quickRetryNoValidFaceSince = null;
let serverTimeoutTimer = null;
let lastAccessCaptureTime = 0;

let isEnrollmentCaptureActive = false;
let enrollmentCaptureCompleted = false;
let termsAcceptedThisSession = false;
let skipTermsAfterCapture = false;
let lastEnrollmentCaptureTime = 0;
let enrollmentDetectionRunning = false;
let stableSince = null;

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
    hudText.textContent = text;
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
    setHud("Coloque su rostro en el óvalo");
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
    exitQuickRetryMode();
    hideProcessingOverlay();
    clearTimeout(resultTimeout);
    clearTimeout(quickRetryTimeout);
    setFaceGuideVariant("");
    hideBottomBanner();
    hudInstruction.classList.remove("hidden");
    isProcessingAccess = false;
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
    hudInstruction.classList.add("hidden");

    if (isQuickRetryMode) {
        updateBottomBannerSubtitle("Re-verificando…");
        showProcessingOverlay("Re-verificando…");
    } else {
        setFaceGuideVariant("processing");
        showBottomBanner("processing", "Verificando…", "Un momento por favor");
        showProcessingOverlay("Verificando…");
    }
}

function scheduleDeniedUnknownQuickRetry(title, subtitle) {
    clearTimeout(quickRetryTimeout);
    quickRetryTimeout = setTimeout(function () {
        quickRetryTimeout = null;
        if (currentMode !== MODE_ACCESS) {
            return;
        }
        enterQuickRetryMode();
        updateBottomBannerSubtitle(subtitle);
    }, RESULT_DISPLAY_DENIED_UNKNOWN_MS);
}

function scheduleFullResultClear() {
    clearTimeout(resultTimeout);
    resultTimeout = setTimeout(function () {
        if (currentMode !== MODE_ACCESS) {
            return;
        }
        clearAccessResult();
        setHud("Coloque su rostro en el óvalo");
        setTimeout(function () {
            if (currentMode === MODE_ACCESS) {
                isCooldown = false;
            }
        }, COOLDOWN_RELEASE_MS);
    }, RESULT_DISPLAY_DENIED_MS);
}

function showAccessResult(data) {
    if (currentMode !== MODE_ACCESS) {
        return;
    }

    const variant = data.variant || (data.status === "GRANTED" ? "granted" : "denied_unknown");
    hideProcessingOverlay();
    isProcessingAccess = false;
    setFaceGuideVariant(variant);
    hudInstruction.classList.add("hidden");

    const copy = buildResultCopy(data, variant);
    showBottomBanner(variant, copy.title, copy.subtitle);

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
            setHud("Coloque su rostro en el óvalo");
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

async function accessDetectLoop() {
    if (!accessLoopActive || currentMode !== MODE_ACCESS) {
        return;
    }

    if (!isModelsLoaded || cameraFeed.paused || cameraFeed.ended) {
        requestAnimationFrame(accessDetectLoop);
        return;
    }

    const displaySize = { width: cameraFeed.videoWidth, height: cameraFeed.videoHeight };
    if (overlayCanvas.width !== displaySize.width) {
        faceapi.matchDimensions(overlayCanvas, displaySize);
    }

    const now = Date.now();
    const cooldownOk = isQuickRetryMode || now - lastAccessCaptureTime > ACCESS_CAPTURE_COOLDOWN_MS;

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
            showAccessProcessing();
            sendAccessFrame();
            lastAccessCaptureTime = now;
        } else if (detection && !isProcessingAccess && !isQuickRetryMode) {
            setHud("Coloque su rostro en el óvalo");
        } else if (detection && !isProcessingAccess && isQuickRetryMode) {
            updateBottomBannerSubtitle("Coloque su rostro en el óvalo");
        } else if (!detection && !isProcessingAccess) {
            if (isQuickRetryMode) {
                updateBottomBannerSubtitle("Coloque su rostro en el óvalo");
            } else {
                setHud("Coloque su rostro en el óvalo");
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

function sendAccessFrame() {
    const canvas = document.createElement("canvas");
    canvas.width = cameraFeed.videoWidth;
    canvas.height = cameraFeed.videoHeight;
    const ctx = canvas.getContext("2d");
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(cameraFeed, 0, 0, canvas.width, canvas.height);
    const dataURL = canvas.toDataURL("image/jpeg", 0.85);

    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: "FRAME", image: dataURL }));
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

async function enrollmentDetectLoop() {
    if (
        !isEnrollmentCaptureActive ||
        !isModelsLoaded ||
        enrollmentCaptureCompleted ||
        currentMode !== MODE_ENROLLMENT
    ) {
        enrollmentDetectionRunning = false;
        return;
    }

    if (cameraFeed.paused || cameraFeed.ended) {
        requestAnimationFrame(enrollmentDetectLoop);
        return;
    }

    const displaySize = { width: cameraFeed.videoWidth, height: cameraFeed.videoHeight };
    if (overlayCanvas.width !== displaySize.width) {
        faceapi.matchDimensions(overlayCanvas, displaySize);
    }

    const now = Date.now();
    const canCapture = now - lastEnrollmentCaptureTime > ENROLLMENT_CAPTURE_COOLDOWN_MS;

    try {
        const detection = await faceapi
            .detectSingleFace(cameraFeed, TabletFaceUtils.detectorOptions())
            .withFaceLandmarks();
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
                    hudText.textContent = "Capturando...";
                    sendEnrollmentPhoto();
                    lastEnrollmentCaptureTime = now;
                    enrollmentCaptureCompleted = true;
                    resetStability();
                    setTimeout(function () {
                        stopCameraTracks();
                        faceGuide.classList.remove("active");
                        faceGuide.classList.remove("face-guide-access");
                        hudInstruction.classList.add("hidden");
                        isEnrollmentCaptureActive = false;
                        if (skipTermsAfterCapture) {
                            showWaitingScreen();
                        } else {
                            showTermsScreen();
                        }
                    }, 1200);
                } else {
                    hudText.textContent = "Coloque su rostro en el óvalo";
                }
            } else {
                resetStability();
                hudText.textContent = "Coloque su rostro en el óvalo";
            }
        } else if (!detection) {
            resetStability();
        }
    } catch (e) {
        console.error("[Tablet EA] Error en bucle de enrolamiento:", e);
        resetStability();
    }

    requestAnimationFrame(enrollmentDetectLoop);
}

function startEnrollmentDetectionLoop() {
    if (!enrollmentDetectionRunning && isEnrollmentCaptureActive && !enrollmentCaptureCompleted) {
        enrollmentDetectionRunning = true;
        requestAnimationFrame(enrollmentDetectLoop);
    }
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
    if (cameraStream) {
        return;
    }
    const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } },
    });
    cameraStream = stream;
    cameraFeed.srcObject = stream;
    return new Promise(function (resolve) {
        cameraFeed.addEventListener("loadedmetadata", resolve, { once: true });
    });
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
    isEnrollmentCaptureActive = false;
    enrollmentCaptureCompleted = false;
    termsAcceptedThisSession = false;
    skipTermsAfterCapture = false;
    enrollmentDetectionRunning = false;
    resetStability();
    hideTermsScreen();
    hideWaitingScreen();
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
    hudInstruction.classList.remove("hidden");
    setHud("Coloque su rostro en el óvalo");

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
    hudText.textContent = "Coloque su rostro en el óvalo";
    enrollmentCaptureCompleted = false;
    termsAcceptedThisSession = false;
    skipTermsAfterCapture = false;
    isEnrollmentCaptureActive = true;
    resetStability();
    setStatus("connected", "Capturando");

    try {
        stopCameraTracks();
        await ensureCamera();
        startEnrollmentDetectionLoop();
    } catch (err) {
        console.error("[Tablet EA] Error iniciando enrolamiento:", err);
        hudText.textContent = "No se pudo acceder a la cámara.";
        setStatus("disconnected", "Sin cámara");
    }
}

function finishEnrollmentWaiting() {
    hideTermsScreen();
    hideWaitingScreen();
    faceGuide.classList.remove("active");
    hudInstruction.classList.add("hidden");
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

    if (data.status === "GRANTED" || data.status === "DENIED") {
        if (!data.variant) {
            data.variant = data.status === "GRANTED" ? "granted" : "denied_unknown";
        }
        showAccessResult(data);
    }
}

function handleServerMessage(data) {
    if (data.type && String(data.type).indexOf("ENROLLMENT_") === 0) {
        handleEnrollmentCommand(data);
        return;
    }
    handleAccessResponse(data);
}

function connectWebSocket() {
    clearTimeout(reconnectTimer);
    socket = new WebSocket(WS_URL);

    socket.onopen = function () {
        if (currentMode === MODE_ENROLLMENT && !isEnrollmentCaptureActive && !enrollmentCaptureCompleted) {
            enterAccessMode();
        } else if (currentMode === MODE_ACCESS) {
            setStatus("connected", "Conectado");
        }
    };

    socket.onclose = function () {
        setStatus("disconnected", "Sin conexión...");
        stopAccessLoop();
        reconnectTimer = setTimeout(connectWebSocket, RECONNECT_DELAY_MS);
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
