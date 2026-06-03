// tablet_access.js — Tablet de acceso biométrico (Perfect Line II)

const WS_URL = window.TABLET_WS_URL;
const RECONNECT_DELAY_MS = 3000;

const cameraFeed = document.getElementById('camera-feed');
const overlayCanvas = document.getElementById('overlay-canvas');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const accessFlash = document.getElementById('access-flash');
const accessIcon = document.getElementById('access-icon');
const accessTitle = document.getElementById('access-title');
const accessSubtitle = document.getElementById('access-subtitle');

let isProcessingAccess = false;
let isCooldown = false;
let accessFlashTimeout = null;
let serverTimeoutTimer = null;
let socket = null;
let reconnectTimer = null;
let canvasCtx = overlayCanvas.getContext('2d');
let isModelsLoaded = false;
let lastCaptureTime = 0;
const CAPTURE_COOLDOWN_MS = 2500;

async function loadModels() {
    const MODEL_URL = '/static/models';
    await faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL);
    isModelsLoaded = true;
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
    const canCapture = (now - lastCaptureTime) > CAPTURE_COOLDOWN_MS;

    try {
        const detection = await faceapi.detectSingleFace(cameraFeed, new faceapi.TinyFaceDetectorOptions());
        canvasCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);

        if (detection) {
            const resizedDetection = faceapi.resizeResults(detection, displaySize);
            faceapi.draw.drawDetections(overlayCanvas, resizedDetection);

            if (canCapture && detection.score > 0.8 && !isProcessingAccess && !isCooldown) {
                const faceWidth = resizedDetection.box.width;
                if (faceWidth > 120) {
                    showAccessProcessing();
                    sendAccessFrame();
                    lastCaptureTime = now;
                }
            }
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
                hideAccessFlash();
            }
        }, 8000);
    } else if (isProcessingAccess) {
        showAccessResult('DENIED', 'Servidor Offline', 'Sin conexión con el backend', 5000);
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
        if (isProcessingAccess) {
            hideAccessFlash();
        }
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

    if (data.status === 'GRANTED') {
        showAccessResult('GRANTED', '¡Bienvenido!', data.name);
    } else if (data.status === 'DENIED') {
        let reason = data.reason || 'Rostro no reconocido';
        if (data.name) {
            reason = data.name + ' - ' + reason;
        }
        showAccessResult('DENIED', 'Acceso Denegado', reason);
    }
}

function showAccessProcessing() {
    isProcessingAccess = true;
    accessFlash.className = 'access-flash processing';
    accessIcon.innerHTML = '<div class="spinner"></div>';
    accessTitle.textContent = 'Procesando...';
    accessSubtitle.textContent = 'Verificando identidad';
}

function showAccessResult(status, mainText, subText, customWait) {
    const waitTime = customWait || (status === 'GRANTED' ? 5000 : 3000);
    isCooldown = true;

    if (status === 'GRANTED') {
        accessFlash.className = 'access-flash granted';
        accessIcon.textContent = '✅';
    } else {
        accessFlash.className = 'access-flash denied';
        accessIcon.textContent = '❌';
    }
    accessTitle.textContent = mainText;
    accessSubtitle.textContent = subText || '';

    clearTimeout(accessFlashTimeout);
    accessFlashTimeout = setTimeout(function () {
        hideAccessFlash();
        setTimeout(function () {
            isCooldown = false;
        }, waitTime);
    }, waitTime);
}

function hideAccessFlash() {
    accessFlash.className = 'access-flash hidden';
    isProcessingAccess = false;
}

function setStatus(state, text) {
    statusDot.className = state;
    statusText.textContent = text;
}

document.addEventListener('DOMContentLoaded', function () {
    loadModels().then(startCamera).catch(function (err) {
        console.error('[Tablet Acceso] Error cargando IA:', err);
        setStatus('disconnected', 'Error IA');
    });
    connectWebSocket();
});
