
const WS_URL = window.DASHBOARD_WS_URL;
let dashboardSocket = null;
let reconnectTimer = null;

const TABLET_STATUS = {
    access: false,
    enrollment: false,
};

function getStatusPill(role) {
    return document.getElementById('pc-tablet-' + role + '-status');
}

function updateStatusPill(role, online) {
    const pill = getStatusPill(role);
    if (!pill) {
        return;
    }
    const statusText = pill.querySelector('.status-text');
    TABLET_STATUS[role] = online;
    if (online) {
        pill.classList.add('online');
        statusText.textContent = role === 'access' ? 'Acceso Online' : 'Enrol. Online';
    } else {
        pill.classList.remove('online');
        statusText.textContent = role === 'access' ? 'Acceso Offline' : 'Enrol. Offline';
    }
    window.dispatchEvent(new CustomEvent('tabletStatusChanged', {
        detail: { online: online, role: role },
    }));
}

function connectDashboardWebSocket() {
    clearTimeout(reconnectTimer);
    dashboardSocket = new WebSocket(WS_URL);

    dashboardSocket.onopen = function () {
        console.log('[Dashboard] WebSocket conectado al servidor.');
    };

    dashboardSocket.onclose = function () {
        console.warn('[Dashboard] WebSocket cerrado. Reintentando en 3s...');
        updateStatusPill('access', false);
        updateStatusPill('enrollment', false);
        reconnectTimer = setTimeout(connectDashboardWebSocket, 3000);
    };

    dashboardSocket.onerror = function (error) {
        console.error('[Dashboard] Error en WebSocket:', error);
    };

    dashboardSocket.onmessage = function (event) {
        try {
            const data = JSON.parse(event.data);
            if (data.type === 'tablet_status' && data.role) {
                updateStatusPill(data.role, !!data.online);
            } else if (data.type === 'ENROLLMENT_PHOTO') {
                window.dispatchEvent(new CustomEvent('enrollmentPhotoReceived', {
                    detail: { photoType: data.photoType, image: data.image },
                }));
            } else if (data.type === 'NEW_ACCESS_LOG') {
                window.dispatchEvent(new CustomEvent('newAccessLog', { detail: data }));
            }
        } catch (err) {
            console.error('[Dashboard] Error parseando mensaje:', event.data);
        }
    };
}

document.addEventListener('DOMContentLoaded', function () {
    if (WS_URL) {
        connectDashboardWebSocket();
    }
});

window.sendDashboardCommand = function (commandData) {
    if (dashboardSocket && dashboardSocket.readyState === WebSocket.OPEN) {
        dashboardSocket.send(JSON.stringify(commandData));
    } else {
        console.warn('[Dashboard] Imposible enviar comando. WebSocket no está abierto.');
    }
};
