
const WS_URL = window.DASHBOARD_WS_URL;
let dashboardSocket = null;
let reconnectTimer = null;

const TABLET_STATUS = {
    access: false,
    enrollment: false,
};

function getTabletStatusElements(role) {
    var widget = document.getElementById('tabletStatusWidget');
    if (!widget) {
        return null;
    }
    return {
        dot: widget.querySelector('.tablet-status-dot-indicator[data-role="' + role + '"]'),
        row: widget.querySelector('.tablet-status-popover-row[data-role="' + role + '"]'),
    };
}

function updateStatusPill(role, online) {
    var elements = getTabletStatusElements(role);
    if (!elements || !elements.dot || !elements.row) {
        return;
    }

    var statusText = elements.row.querySelector('.status-text');
    TABLET_STATUS[role] = online;

    elements.dot.classList.toggle('online', online);
    elements.row.classList.toggle('online', online);

    if (statusText) {
        statusText.textContent = online ? 'Online' : 'Offline';
    }

    window.dispatchEvent(new CustomEvent('tabletStatusChanged', {
        detail: { online: online, role: role },
    }));
}

function setTabletPopoverOpen(isOpen) {
    var trigger = document.getElementById('tabletStatusTrigger');
    var popover = document.getElementById('tabletStatusPopover');
    if (!trigger || !popover) {
        return;
    }
    trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
    popover.hidden = !isOpen;
}

function initTabletStatusPopover() {
    var widget = document.getElementById('tabletStatusWidget');
    var trigger = document.getElementById('tabletStatusTrigger');
    var popover = document.getElementById('tabletStatusPopover');
    if (!widget || !trigger || !popover) {
        return;
    }

    trigger.addEventListener('click', function (event) {
        event.stopPropagation();
        var isOpen = trigger.getAttribute('aria-expanded') === 'true';
        setTabletPopoverOpen(!isOpen);
    });

    document.addEventListener('click', function (event) {
        if (!widget.contains(event.target)) {
            setTabletPopoverOpen(false);
        }
    });

    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape') {
            setTabletPopoverOpen(false);
        }
    });
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
            } else if (data.type === 'TABLET_MODE_CHANGED') {
                window.dispatchEvent(new CustomEvent('tabletModeChanged', { detail: { mode: data.mode } }));
            }
        } catch (err) {
            console.error('[Dashboard] Error parseando mensaje:', event.data);
        }
    };
}

window.addEventListener('tabletModeChanged', function (e) {
    var banner = document.getElementById('global-enrollment-banner');
    if (!banner) return;
    var path = window.location.pathname;
    if (path.startsWith('/tablet/')) {
        banner.style.display = 'none';
        return;
    }
    banner.style.display = e.detail.mode === 'enrollment' ? 'block' : 'none';
});

document.addEventListener('DOMContentLoaded', function () {
    initTabletStatusPopover();
    updateStatusPill('access', false);
    updateStatusPill('enrollment', false);
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

window.reloadTablet = function () {
    window.sendDashboardCommand({ type: 'TABLET_RELOAD' });
    // En /enrolamiento/ la recarga sola no reabre la captura; la página reenvía ENROLLMENT_START.
    if (typeof window.onEnrollmentPageTabletReload === 'function') {
        window.onEnrollmentPageTabletReload();
    }
};
