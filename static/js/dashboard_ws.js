
const WS_URL = window.DASHBOARD_WS_URL;
let dashboardSocket = null;
let reconnectTimer = null;

const statusPill = document.getElementById('pc-tablet-status');
const statusText = statusPill.querySelector('.status-text');

function connectDashboardWebSocket() {
    clearTimeout(reconnectTimer);
    dashboardSocket = new WebSocket(WS_URL);

    dashboardSocket.onopen = () => {
        console.log('[Dashboard] WebSocket conectado al servidor.');
    };

    dashboardSocket.onclose = (event) => {
        console.warn('[Dashboard] WebSocket cerrado. Reintentando en 3s...');
        setTabletOffline();
        reconnectTimer = setTimeout(connectDashboardWebSocket, 3000);
    };

    dashboardSocket.onerror = (error) => {
        console.error('[Dashboard] Error en WebSocket:', error);
    };

    dashboardSocket.onmessage = (event) => {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'tablet_status') {
                if (data.online) {
                    setTabletOnline();
                } else {
                    setTabletOffline();
                }
            }
        } catch (err) {
            console.error('[Dashboard] Error parseando mensaje:', event.data);
        }
    };
}

function setTabletOnline() {
    if (statusPill) {
        statusPill.classList.add('online');
        statusText.textContent = 'Tablet Online';
    }
}

function setTabletOffline() {
    if (statusPill) {
        statusPill.classList.remove('online');
        statusText.textContent = 'Tablet Offline';
    }
}

document.addEventListener('DOMContentLoaded', () => {
    if (WS_URL) {
        connectDashboardWebSocket();
    }
});

// Exponer función global para enviar comandos (usada por la página de enrolamiento)
window.sendDashboardCommand = function(commandData) {
    if (dashboardSocket && dashboardSocket.readyState === WebSocket.OPEN) {
        dashboardSocket.send(JSON.stringify(commandData));
    } else {
        console.warn("[Dashboard] Imposible enviar comando. WebSocket no está abierto.");
    }
};
