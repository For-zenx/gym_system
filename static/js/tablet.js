// DEPRECATED: TASK-045 — reemplazado por tablet_access.js y tablet_enrollment.js
// tablet.js — Lógica de la interfaz de la tablet (Gym System - Perfect Line II)

const WS_URL = window.TABLET_WS_URL; // Inyectado desde el template Django
const RECONNECT_DELAY_MS = 3000;

// --- Referencias al DOM ---
const cameraFeed = document.getElementById('camera-feed');
const overlayCanvas = document.getElementById('overlay-canvas');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');

// Nuevas referencias UI Enrolamiento
const focusFrame = document.getElementById('focus-frame');
const hudInstruction = document.getElementById('hud-instruction');
const hudText = document.getElementById('hud-text');
const arrowLeft = document.getElementById('arrow-left');
const arrowRight = document.getElementById('arrow-right');

// Referencias UI Acceso
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

// --- DEBUG LOGGING ---
function addDebugLog(msg) {
    // Desactivado para producción
    /*
    console.log(msg);
    const logContent = document.getElementById('debug-log-content');
    if (!logContent) return;
    const now = new Date();
    const timeStr = `${now.getHours().toString().padStart(2, '0')}:${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}.${now.getMilliseconds().toString().padStart(3, '0')}`;
    const div = document.createElement('div');
    div.textContent = `[${timeStr}] ${msg}`;
    logContent.appendChild(div);
    logContent.parentElement.scrollTop = logContent.parentElement.scrollHeight;
    */
}

// --- Estados del Sistema ---
let currentMode = 'NORMAL';
let enrollmentStep = 'FRONT';
let isModelsLoaded = false;
let lastCaptureTime = 0;
const CAPTURE_COOLDOWN_MS = 2500;

// ─────────────────────────────────────────────
// Inteligencia Artificial (face-api.js)
// ─────────────────────────────────────────────
async function loadModels() {
    hudText.textContent = 'Cargando motor de IA...';
    hudInstruction.classList.remove('hidden');
    
    const MODEL_URL = '/static/models';
    try {
        await Promise.all([
            faceapi.nets.tinyFaceDetector.loadFromUri(MODEL_URL),
            faceapi.nets.faceLandmark68Net.loadFromUri(MODEL_URL)
        ]);
        isModelsLoaded = true;
        addDebugLog('Modelos de IA cargados correctamente.');
        
        hudText.textContent = 'Cámara lista.';
        setTimeout(() => {
            if (currentMode === 'NORMAL') exitEnrollmentMode();
        }, 1000);
    } catch (error) {
        addDebugLog(`Error cargando IA: ${error}`);
        hudText.textContent = 'Error iniciando sistema facial.';
    }
}

async function detectFaceLoop() {
    if (!isModelsLoaded || cameraFeed.paused || cameraFeed.ended) {
        requestAnimationFrame(detectFaceLoop);
        return;
    }

    // Ajustar tamaño del canvas interno al tamaño real del video
    const displaySize = { width: cameraFeed.videoWidth, height: cameraFeed.videoHeight };
    if (overlayCanvas.width !== displaySize.width) {
        faceapi.matchDimensions(overlayCanvas, displaySize);
    }

    const now = Date.now();
    const canCapture = (now - lastCaptureTime) > CAPTURE_COOLDOWN_MS;

    try {
        if (currentMode === 'NORMAL') {
            // ===== LÓGICA DE ACCESO (VALIDACIÓN) =====
            const detection = await faceapi.detectSingleFace(cameraFeed, new faceapi.TinyFaceDetectorOptions());
            canvasCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
            
            if (detection) {
                const resizedDetection = faceapi.resizeResults(detection, displaySize);
                faceapi.draw.drawDetections(overlayCanvas, resizedDetection);
                
                if (canCapture && detection.score > 0.8) {
                    if (!isProcessingAccess && !isCooldown) {
                        const faceWidth = resizedDetection.box.width;
                        if (faceWidth > 120) { // Asegurar que está lo suficientemente cerca
                            addDebugLog(`Rostro detectado (Score: ${detection.score.toFixed(2)}, Ancho: ${faceWidth.toFixed(0)}px). Iniciando validación...`);
                            showAccessProcessing();
                            capturarFoto('NORMAL');
                            lastCaptureTime = now;
                        }
                    }
                }
            }
        } else if (currentMode === 'ENROLLMENT') {
            // Modo Enrolamiento: Detección pesada con Landmarks para pose
            if (enrollmentStep === 'DONE') {
                canvasCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
                requestAnimationFrame(detectFaceLoop);
                return; // Esperando salir del modo
            }

            const detection = await faceapi.detectSingleFace(cameraFeed, new faceapi.TinyFaceDetectorOptions()).withFaceLandmarks();
            canvasCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
            
            if (detection) {
                const resizedDetection = faceapi.resizeResults(detection, displaySize);
                faceapi.draw.drawFaceLandmarks(overlayCanvas, resizedDetection);
                
                // --- Cálculo de Pose (Yaw) ---
                const landmarks = detection.landmarks;
                const nose = landmarks.getNose()[3]; // Punta de la nariz (relativo al centro)
                const jawOutline = landmarks.getJawOutline();
                const leftCheek = jawOutline[0];
                const rightCheek = jawOutline[16];
                
                const distLeft = Math.abs(nose.x - leftCheek.x);
                const distRight = Math.abs(rightCheek.x - nose.x);
                const ratio = distLeft / distRight; 
                
                if (canCapture) {
                    if (enrollmentStep === 'FRONT' && ratio > 0.75 && ratio < 1.35) {
                        hudText.textContent = "¡Perfecto! Capturando...";
                        capturarFoto('FRONT');
                        lastCaptureTime = now;
                        enrollmentStep = 'LEFT';
                        setTimeout(() => {
                            hudText.textContent = "Mire hacia la FLECHA";
                            arrowLeft.classList.remove('hidden');
                        }, 1000);
                        
                    } else if (enrollmentStep === 'LEFT' && ratio > 1.6) {
                        hudText.textContent = "¡Perfecto! Capturando...";
                        arrowLeft.classList.add('hidden');
                        capturarFoto('LEFT');
                        lastCaptureTime = now;
                        enrollmentStep = 'RIGHT';
                        setTimeout(() => {
                            hudText.textContent = "Mire hacia la FLECHA";
                            arrowRight.classList.remove('hidden');
                        }, 1000);
                        
                    } else if (enrollmentStep === 'RIGHT' && ratio < 0.6) {
                        hudText.textContent = "¡Perfecto! Capturando...";
                        arrowRight.classList.add('hidden');
                        capturarFoto('RIGHT');
                        lastCaptureTime = now;
                        enrollmentStep = 'DONE';
                        setTimeout(() => {
                            hudText.textContent = "¡Enrolamiento Exitoso!";
                        }, 1000);
                    }
                }
            }
        }
    } catch (e) {
        console.error("Error en bucle de detección:", e);
    }

    requestAnimationFrame(detectFaceLoop);
}

function capturarFoto(tipoFoto) {
    const canvas = document.createElement('canvas');
    canvas.width = cameraFeed.videoWidth;
    canvas.height = cameraFeed.videoHeight;
    const ctx = canvas.getContext('2d');
    
    // TRUCO MATEMÁTICO: Voltear horizontalmente el canvas de memoria
    // Así la foto final se guarda "al derecho", neutralizando el espejo visual.
    ctx.translate(canvas.width, 0);
    ctx.scale(-1, 1);
    
    // Dibujar el fotograma actual del video en el canvas
    ctx.drawImage(cameraFeed, 0, 0, canvas.width, canvas.height);
    
    // Extraer en formato base64 JPEG
    const dataURL = canvas.toDataURL('image/jpeg', 0.85);
    addDebugLog(`Captura ${tipoFoto} en memoria. Peso aprox: ${Math.round(dataURL.length/1024)} KB`);
    
    if (socket && socket.readyState === WebSocket.OPEN) {
        if (tipoFoto === 'NORMAL') {
            addDebugLog(`Enviando FRAME al servidor por WebSocket...`);
            socket.send(JSON.stringify({
                type: 'FRAME',
                image: dataURL
            }));
            
            clearTimeout(serverTimeoutTimer);
            serverTimeoutTimer = setTimeout(() => { 
                if (isProcessingAccess) {
                    addDebugLog(`TIMEOUT: El servidor no respondió después de 8s.`);
                    hideAccessFlash(); 
                }
            }, 8000);
        } else {
            addDebugLog(`Enviando ENROLLMENT_PHOTO al servidor...`);
            socket.send(JSON.stringify({
                type: 'ENROLLMENT_PHOTO',
                photoType: tipoFoto,
                image: dataURL
            }));
        }
    } else {
        addDebugLog(`ERROR: No se pudo enviar foto, WebSocket desconectado.`);
        if (isProcessingAccess) {
            showAccessResult('DENIED', 'Servidor Offline', 'Sin conexión con el backend', 5000);
        }
    }
}

// ─────────────────────────────────────────────
// Cámara
// ─────────────────────────────────────────────
async function startCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } }
        });
        cameraFeed.srcObject = stream;
        
        // Iniciar el bucle de IA una vez que el video tenga dimensiones reales
        cameraFeed.addEventListener('loadedmetadata', () => {
            requestAnimationFrame(detectFaceLoop);
        });
    } catch (err) {
        hudText.textContent = 'No se pudo acceder a la cámara.';
        hudInstruction.classList.remove('hidden');
        console.error('[Tablet] Error al iniciar cámara:', err);
    }
}

// ─────────────────────────────────────────────
// WebSocket
// ─────────────────────────────────────────────
function connectWebSocket() {
    clearTimeout(reconnectTimer);
    socket = new WebSocket(WS_URL);

    socket.onopen = () => {
        setStatus('connected', 'Conectado');
    };

    socket.onclose = (event) => {
        setStatus('disconnected', 'Sin conexión...');
        addDebugLog(`WebSocket cerrado. Reintentando reconexión...`);
        
        if (isProcessingAccess) {
            hideAccessFlash();
        }
        
        reconnectTimer = setTimeout(connectWebSocket, RECONNECT_DELAY_MS);
    };

    socket.onerror = (error) => {
        // console.error('[Tablet] Error en WebSocket:', error);
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleServerMessage(data);
        } catch (err) {
            // console.error('[Tablet] Mensaje inválido del servidor:', event.data);
        }
    };
}

// ─────────────────────────────────────────────
// Manejo de mensajes del servidor
// ─────────────────────────────────────────────
function handleServerMessage(data) {
    const msgType = data.type;
    
    clearTimeout(serverTimeoutTimer);

    if (msgType === 'ENROLLMENT_START') {
        addDebugLog(`Mensaje WS: ENROLLMENT_START`);
        enterEnrollmentMode();
    } else if (msgType === 'ENROLLMENT_END') {
        addDebugLog(`Mensaje WS: ENROLLMENT_END`);
        exitEnrollmentMode();
    } else if (data.status === 'GRANTED') {
        addDebugLog(`Mensaje WS: GRANTED para ${data.name}`);
        showAccessResult('GRANTED', '¡Bienvenido!', data.name);
    } else if (data.status === 'DENIED') {
        let reason = data.reason || 'Rostro no reconocido';
        if (data.name) {
            reason = `${data.name} - ${reason}`;
        }
        addDebugLog(`Mensaje WS: DENIED. Motivo: ${reason}`);
        showAccessResult('DENIED', 'Acceso Denegado', reason);
    } else {
        addDebugLog(`Mensaje WS Desconocido: ${JSON.stringify(data)}`);
    }
}

// ─────────────────────────────────────────────
// UI Acceso (Flash)
// ─────────────────────────────────────────────
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
    accessFlashTimeout = setTimeout(() => {
        addDebugLog(`Ocultando Flash. Iniciando cámara...`);
        hideAccessFlash();
        
        addDebugLog(`Manteniendo Cooldown invisible por ${waitTime/1000}s más...`);
        setTimeout(() => {
            isCooldown = false;
            addDebugLog(`Cooldown finalizado. Listo.`);
        }, waitTime);
    }, waitTime);
}

function hideAccessFlash() {
    accessFlash.className = 'access-flash hidden';
    isProcessingAccess = false;
}

function enterEnrollmentMode() {
    currentMode = 'ENROLLMENT';
    enrollmentStep = 'FRONT';
    
    // Activar UI Inmersiva
    focusFrame.classList.add('active');
    hudInstruction.classList.remove('hidden');
    hudText.textContent = 'Mire al centro del cuadro';
    arrowLeft.classList.add('hidden');
    arrowRight.classList.add('hidden');
    
    console.log('[Tablet] Modo Enrolamiento activado.');
}

function exitEnrollmentMode() {
    currentMode = 'NORMAL';
    
    // Desactivar UI Inmersiva
    focusFrame.classList.remove('active');
    hudInstruction.classList.add('hidden');
    arrowLeft.classList.add('hidden');
    arrowRight.classList.add('hidden');
    
    console.log('[Tablet] Modo Enrolamiento finalizado. Volviendo a reposo.');
}

// ─────────────────────────────────────────────
// Utilidades
// ─────────────────────────────────────────────
function setStatus(state, text) {
    statusDot.className = state; 
    statusText.textContent = text;
}

// ─────────────────────────────────────────────
// Inicialización
// ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    // Primero cargamos los modelos, la cámara se lanza en paralelo
    loadModels();
    startCamera();
    connectWebSocket();
});
