// tablet.js — Lógica de la interfaz de la tablet (Gym System - PerfectLine II)

const WS_URL = window.TABLET_WS_URL; // Inyectado desde el template Django
const RECONNECT_DELAY_MS = 3000;

// --- Referencias al DOM ---
const cameraFeed = document.getElementById('camera-feed');
const statusDot = document.getElementById('status-dot');
const statusText = document.getElementById('status-text');
const overlayMode = document.getElementById('overlay-mode');
const modeInstruction = document.getElementById('mode-instruction');
const currentModeText = document.getElementById('current-mode-text');

let socket = null;
let reconnectTimer = null;

// ─────────────────────────────────────────────
// Cámara
// ─────────────────────────────────────────────
async function startCamera() {
    try {
        const stream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'user', width: { ideal: 1280 }, height: { ideal: 720 } }
        });
        cameraFeed.srcObject = stream;
    } catch (err) {
        modeInstruction.textContent = 'No se pudo acceder a la cámara.';
        overlayMode.classList.add('visible');
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
    // Otros tipos de mensajes (GRANTED, DENIED) se implementarán en tareas futuras.
}

function enterEnrollmentMode() {
    modeInstruction.textContent = 'Modo Enrolamiento';
    overlayMode.classList.add('visible');
    if (currentModeText) {
        currentModeText.textContent = 'MODO ENROLAMIENTO';
        currentModeText.style.color = '#3b82f6'; // Azul
    }
    console.log('[Tablet] Modo Enrolamiento activado.');
}

function exitEnrollmentMode() {
    overlayMode.classList.remove('visible');
    if (currentModeText) {
        currentModeText.textContent = 'MODO NORMAL';
        currentModeText.style.color = '#6b7280'; // Gris
    }
    console.log('[Tablet] Modo Enrolamiento finalizado. Volviendo a reposo.');
}

// ─────────────────────────────────────────────
// Utilidades
// ─────────────────────────────────────────────
function setStatus(state, text) {
    statusDot.className = state; // 'connected' | 'disconnected'
    statusText.textContent = text;
}

// ─────────────────────────────────────────────
// Inicialización
// ─────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    startCamera();
    connectWebSocket();
});
