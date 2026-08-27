// tablet_enrollment.js — Tablet de enrolamiento (Perfect Line II)

const WS_URL = window.TABLET_WS_URL;
const RECONNECT_DELAY_MS = 3000;
const CAPTURE_COOLDOWN_MS = 2500;
const JPEG_QUALITY = 0.9;

const cameraFeed = document.getElementById('camera-feed');
const overlayCanvas = document.getElementById('overlay-canvas');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const idleOverlay = document.getElementById('idle-overlay');
const faceGuide = document.getElementById('face-guide');
const faceGuideOval = document.querySelector('.face-guide-oval');
const hudInstruction = document.getElementById('hud-instruction');
const hudText = document.getElementById('hud-text');
const enrollmentCoach = document.getElementById('enrollment-coach');
const enrollmentCoachText = document.getElementById('enrollment-coach-text');
const termsOverlay = document.getElementById('terms-overlay');
const termsAcceptBtn = document.getElementById('terms-accept-btn');
const waitingOverlay = document.getElementById('enrollment-waiting-overlay');

let socket = null;
let reconnectTimer = null;
let cameraStream = null;
let canvasCtx = overlayCanvas.getContext('2d');
let isModelsLoaded = false;
let isCaptureActive = false;
let captureCompleted = false;
let termsAcceptedThisSession = false;
let skipTermsAfterCapture = false;
let lastCaptureTime = 0;
let detectionLoopRunning = false;
let stableSince = null;
let enrollmentSessionId = 0;
let postCaptureUiTimer = null;
let enrollmentCameraResumeAt = 0;
let cameraRetrying = false;
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
        if (playResult && typeof playResult.then === 'function') {
            return playResult.catch(function () {
                return null;
            });
        }
    } catch (err) {
        /* ignore */
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
        if (tracks[i].readyState === 'live') {
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
    stopCamera();
    startCamera()
        .then(function () {
            if (sessionId !== enrollmentSessionId) {
                return null;
            }
            return playCameraFeed();
        })
        .catch(function (err) {
            console.error('[Tablet Enrolamiento] Error recuperando cámara:', err);
            if (sessionId === enrollmentSessionId) {
                setStatus('disconnected', 'Sin cámara');
                enrollmentHud.show('No se pudo acceder a la cámara.', Date.now(), {
                    immediate: true,
                });
            }
        })
        .finally(function () {
            cameraRetrying = false;
        });
}

async function loadModels() {
    hudText.textContent = 'Cargando motor de IA...';
    const MODEL_URL = '/static/models';
    await Promise.all([
        faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
        faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL),
    ]);
    isModelsLoaded = true;
}

function resetStability() {
    stableSince = null;
}

function hideTermsScreen() {
    if (termsOverlay) {
        termsOverlay.classList.add('hidden');
    }
}

function hideWaitingScreen() {
    if (waitingOverlay) {
        waitingOverlay.classList.add('hidden');
    }
}

function showWaitingScreen() {
    hideTermsScreen();
    enrollmentHud.hideCoach();
    if (idleOverlay) {
        idleOverlay.classList.add('hidden');
    }
    if (waitingOverlay) {
        waitingOverlay.classList.remove('hidden');
    }
    setStatus('connected', 'Espere');
}

function showTermsScreen() {
    showWaitingScreen();
}

function completeEnrollmentIdle() {
    hideTermsScreen();
    hideWaitingScreen();
    enrollmentHud.hideCoach();
    idleOverlay.classList.remove('hidden');
    const idleSubtitle = idleOverlay.querySelector('.idle-subtitle');
    if (idleSubtitle) {
        idleSubtitle.textContent = termsAcceptedThisSession
            ? 'Foto y términos listos'
            : 'Foto capturada';
    }
    setStatus('connected', termsAcceptedThisSession ? 'Listo' : 'Foto lista');
}

function acceptTermsOnTablet() {
    if (termsAcceptedThisSession) {
        return;
    }
    termsAcceptedThisSession = true;
    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({ type: 'ENROLLMENT_TERMS_ACCEPTED' }));
    }
    showWaitingScreen();
}

function skipTermsOnTablet() {
    termsAcceptedThisSession = true;
    skipTermsAfterCapture = true;
    hideTermsScreen();
    if (captureCompleted) {
        showWaitingScreen();
    }
}

function requireTermsOnTablet() {
    termsAcceptedThisSession = false;
    skipTermsAfterCapture = false;
    if (captureCompleted) {
        showTermsScreen();
        setStatus('connected', 'Lea y acepte');
    }
}

async function detectFaceLoop(sessionId) {
    if (
        sessionId !== enrollmentSessionId
        || !isCaptureActive
        || !isModelsLoaded
        || captureCompleted
    ) {
        if (sessionId === enrollmentSessionId) {
            detectionLoopRunning = false;
        }
        return;
    }

    if (cameraFeed.paused || cameraFeed.ended || !cameraStreamIsLive()) {
        tryResumeEnrollmentCamera(sessionId);
        requestAnimationFrame(function () {
            detectFaceLoop(sessionId);
        });
        return;
    }

    const displaySize = { width: cameraFeed.videoWidth, height: cameraFeed.videoHeight };
    if (!displaySize.width || !displaySize.height) {
        requestAnimationFrame(function () {
            detectFaceLoop(sessionId);
        });
        return;
    }
    if (overlayCanvas.width !== displaySize.width) {
        faceapi.matchDimensions(overlayCanvas, displaySize);
    }

    const now = Date.now();
    const canCapture = (now - lastCaptureTime) > CAPTURE_COOLDOWN_MS;

    try {
        const detection = await faceapi.detectSingleFace(
            cameraFeed,
            TabletFaceUtils.detectorOptions()
        ).withFaceLandmarks();
        if (sessionId !== enrollmentSessionId) {
            return;
        }
        canvasCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

        if (detection && canCapture) {
            const resizedDetection = faceapi.resizeResults(detection, displaySize);

            if (TabletFaceUtils.meetsCaptureCriteria(detection, resizedDetection, cameraFeed, faceGuideOval)) {
                if (stableSince === null) {
                    stableSince = now;
                }

                if (now - stableSince >= TabletFaceUtils.STABILITY_MS) {
                    enrollmentHud.show(TabletFaceUtils.ENROLLMENT_BUBBLE_CAPTURING, now, { immediate: true });
                    sendEnrollmentPhoto();
                    lastCaptureTime = now;
                    captureCompleted = true;
                    resetStability();
                    const sessionAtCapture = enrollmentSessionId;
                    clearPostCaptureUiTimer();
                    postCaptureUiTimer = setTimeout(function () {
                        postCaptureUiTimer = null;
                        if (enrollmentSessionId !== sessionAtCapture || !captureCompleted) {
                            return;
                        }
                        if (idleOverlay && !idleOverlay.classList.contains('hidden')) {
                            return;
                        }
                        stopCamera();
                        faceGuide.classList.remove('active');
                        hudInstruction.classList.add('hidden');
                        enrollmentHud.hideCoach();
                        isCaptureActive = false;
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
        console.error('Error en bucle de enrolamiento:', e);
        resetStability();
    }

    requestAnimationFrame(function () {
        detectFaceLoop(sessionId);
    });
}

function startDetectionLoop() {
    if (!isCaptureActive || captureCompleted) {
        return;
    }
    if (detectionLoopRunning) {
        return;
    }
    const sessionId = enrollmentSessionId;
    detectionLoopRunning = true;
    requestAnimationFrame(function () {
        detectFaceLoop(sessionId);
    });
}

function sendEnrollmentPhoto() {
    const canvas = document.createElement('canvas');
    canvas.width = cameraFeed.videoWidth;
    canvas.height = cameraFeed.videoHeight;
    const ctx = canvas.getContext('2d');
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    ctx.drawImage(cameraFeed, 0, 0, canvas.width, canvas.height);
    const dataURL = canvas.toDataURL('image/jpeg', JPEG_QUALITY);

    if (socket && socket.readyState === WebSocket.OPEN) {
        socket.send(JSON.stringify({
            type: 'ENROLLMENT_PHOTO',
            photoType: 'FRONT',
            image: dataURL,
        }));
    }
}

async function startCamera() {
    if (cameraStreamIsLive()) {
        await playCameraFeed();
        return;
    }
    if (cameraStream) {
        stopCamera();
    }
    const stream = await navigator.mediaDevices.getUserMedia({
        video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } },
    });
    cameraStream = stream;
    cameraFeed.srcObject = stream;
    cameraFeed.classList.remove('hidden');
    overlayCanvas.classList.remove('hidden');
    await new Promise(function (resolve) {
        cameraFeed.addEventListener('loadedmetadata', resolve, { once: true });
    });
    await playCameraFeed();
}

function stopCamera() {
    if (cameraStream) {
        cameraStream.getTracks().forEach(function (track) {
            track.stop();
        });
        cameraStream = null;
    }
    cameraFeed.srcObject = null;
    cameraFeed.classList.add('hidden');
    overlayCanvas.classList.add('hidden');
    canvasCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
}

function showIdleScreen() {
    clearPostCaptureUiTimer();
    enrollmentSessionId += 1;
    hideTermsScreen();
    hideWaitingScreen();
    idleOverlay.classList.remove('hidden');
    const idleSubtitle = idleOverlay.querySelector('.idle-subtitle');
    if (idleSubtitle) {
        idleSubtitle.textContent = 'Conectada — en espera del encargado en caja';
    }
    faceGuide.classList.remove('active');
    hudInstruction.classList.add('hidden');
    enrollmentHud.hideCoach();
    isCaptureActive = false;
    captureCompleted = false;
    termsAcceptedThisSession = false;
    skipTermsAfterCapture = false;
    detectionLoopRunning = false;
    resetStability();
}

function connectWebSocket() {
    clearTimeout(reconnectTimer);
    socket = new WebSocket(WS_URL);

    socket.onopen = function () {
        setStatus('connected', 'En espera');
    };

    socket.onclose = function () {
        setStatus('disconnected', 'Sin conexión...');
        stopEnrollmentSession();
        reconnectTimer = setTimeout(connectWebSocket, RECONNECT_DELAY_MS);
    };

    socket.onmessage = function (event) {
        try {
            handleServerMessage(JSON.parse(event.data));
        } catch (err) {
            console.error('[Tablet Enrolamiento] Mensaje inválido:', event.data);
        }
    };
}

async function startEnrollmentSession() {
    clearPostCaptureUiTimer();
    enrollmentSessionId += 1;
    const sessionId = enrollmentSessionId;
    if (cameraStream) {
        stopCamera();
    }
    hideTermsScreen();
    hideWaitingScreen();
    idleOverlay.classList.add('hidden');
    faceGuide.classList.add('active');
    hudInstruction.classList.remove('hidden');
    enrollmentHud.reset(TabletFaceUtils.ENROLLMENT_COACH_CENTER);
    captureCompleted = false;
    termsAcceptedThisSession = false;
    skipTermsAfterCapture = false;
    isCaptureActive = true;
    detectionLoopRunning = false;
    enrollmentCameraResumeAt = 0;
    resetStability();
    setStatus('connected', 'Capturando');

    try {
        if (!isModelsLoaded) {
            await loadModels();
        }
        if (sessionId !== enrollmentSessionId) {
            return;
        }
        await startCamera();
        if (sessionId !== enrollmentSessionId) {
            return;
        }
        startDetectionLoop();
    } catch (err) {
        console.error('[Tablet Enrolamiento] Error iniciando sesión:', err);
        if (sessionId === enrollmentSessionId) {
            enrollmentHud.show('No se pudo acceder a la cámara.', Date.now(), {
                immediate: true,
            });
            setStatus('disconnected', 'Sin cámara');
        }
    }
}

function stopEnrollmentSession() {
    stopCamera();
    showIdleScreen();
    setStatus(socket && socket.readyState === WebSocket.OPEN ? 'connected' : 'disconnected',
        socket && socket.readyState === WebSocket.OPEN ? 'En espera' : 'Sin conexión...');
}

function handleServerMessage(data) {
    if (data.type === 'ENROLLMENT_START') {
        startEnrollmentSession();
    } else if (data.type === 'ENROLLMENT_END') {
        stopEnrollmentSession();
    } else if (data.type === 'ENROLLMENT_SKIP_TERMS') {
        skipTermsOnTablet();
    } else if (data.type === 'ENROLLMENT_REQUIRE_TERMS') {
        requireTermsOnTablet();
    }
}

function setStatus(state, text) {
    statusDot.className = state;
    statusText.textContent = text;
}

document.addEventListener('DOMContentLoaded', function () {
    showIdleScreen();
    connectWebSocket();
    if (termsAcceptBtn) {
        termsAcceptBtn.addEventListener('click', acceptTermsOnTablet);
    }
});
