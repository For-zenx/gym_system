// tablet.js — Lógica de la interfaz de la tablet (Gym System - PerfectLine II)

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

let socket = null;
let reconnectTimer = null;
let canvasCtx = overlayCanvas.getContext('2d');

// --- Estados del Sistema ---
let currentMode = 'NORMAL'; // 'NORMAL' o 'ENROLLMENT'
let enrollmentStep = 'FRONT'; // 'FRONT', 'LEFT', 'RIGHT', 'DONE'
let isModelsLoaded = false;
let lastCaptureTime = 0;
const CAPTURE_COOLDOWN_MS = 2500; // Tiempo de espera entre fotos para darle feedback al usuario

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
        console.log('[Tablet] Modelos de IA cargados correctamente.');
        
        hudText.textContent = 'Cámara lista.';
        setTimeout(() => {
            if (currentMode === 'NORMAL') exitEnrollmentMode();
        }, 1000);
    } catch (error) {
        console.error('[Tablet] Error cargando modelos de IA:', error);
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
            // Modo Control de Acceso: Detección rápida y liviana
            const detection = await faceapi.detectSingleFace(cameraFeed, new faceapi.TinyFaceDetectorOptions());
            canvasCtx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
            
            if (detection) {
                const resizedDetection = faceapi.resizeResults(detection, displaySize);
                faceapi.draw.drawDetections(overlayCanvas, resizedDetection);
                
                if (canCapture && detection.score > 0.8) {
                    console.log("[NORMAL] Rostro detectado con alta confianza. Tomando foto...");
                    capturarFoto('NORMAL');
                    lastCaptureTime = now;
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
                const leftCheek = jawOutline[0]; // Extremo izquierdo de la imagen cruda
                const rightCheek = jawOutline[16]; // Extremo derecho de la imagen cruda
                
                const distLeft = Math.abs(nose.x - leftCheek.x);
                const distRight = Math.abs(rightCheek.x - nose.x);
                const ratio = distLeft / distRight; 
                
                // NOTA: Como la imagen raw NO está en modo espejo:
                // Usuario gira a SU izquierda -> Nariz apunta al lado derecho de la imagen raw -> distRight pequeño -> ratio ALTO (> 1.6)
                // Usuario gira a SU derecha -> Nariz apunta al lado izquierdo de la imagen raw -> distLeft pequeño -> ratio BAJO (< 0.6)
                
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
                            // TODO: TASK-012 Enviar todas las fotos al servidor
                        }, 1000);
                    }
                }
            }
        }
    } catch (e) {
        console.error("Error en bucle de detección:", e);
    }

    // Continuar el bucle a la máxima velocidad posible del navegador
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
    console.log(`[Tablet] 📸 Captura en memoria exitosa (${tipoFoto}). Peso aprox: ${Math.round(dataURL.length/1024)} KB`);
    
    // En el futuro (TASK-012), aquí acumularemos las fotos y las enviaremos
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
        console.log('[Tablet] WebSocket conectado.');
    };

    socket.onclose = (event) => {
        setStatus('disconnected', 'Sin conexión...');
        console.warn('[Tablet] WebSocket cerrado. Reintentando en', RECONNECT_DELAY_MS / 1000, 's...');
        reconnectTimer = setTimeout(connectWebSocket, RECONNECT_DELAY_MS);
    };

    socket.onerror = (error) => {
        console.error('[Tablet] Error en WebSocket:', error);
    };

    socket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            handleServerMessage(data);
        } catch (err) {
            console.error('[Tablet] Mensaje inválido del servidor:', event.data);
        }
    };
}

// ─────────────────────────────────────────────
// Manejo de mensajes del servidor
// ─────────────────────────────────────────────
function handleServerMessage(data) {
    const msgType = data.type;

    if (msgType === 'ENROLLMENT_START') {
        enterEnrollmentMode();
    } else if (msgType === 'ENROLLMENT_END') {
        exitEnrollmentMode();
    }
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
