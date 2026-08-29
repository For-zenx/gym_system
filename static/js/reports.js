(function () {
    var banner = document.getElementById("report-offline-banner");
    var sendBtn = document.getElementById("report-send-btn");
    var sendForm = document.getElementById("report-send-form");
    var sendCountEl = document.getElementById("report-send-count");
    var dailyLimit = null;

    var modal = document.getElementById("report-send-modal");
    var modalTitle = document.getElementById("report-send-modal-title");
    var modalCloseX = document.getElementById("report-send-modal-close");
    var loadingState = document.getElementById("report-send-loading");
    var resultState = document.getElementById("report-send-result");
    var resultIcon = document.getElementById("report-send-result-icon");
    var resultTitle = document.getElementById("report-send-result-title");
    var checklistEl = document.getElementById("report-send-checklist");
    var closeBtn = document.getElementById("report-send-close-btn");

    function updateOnlineState() {
        var online = navigator.onLine;
        if (banner) {
            banner.hidden = online;
        }
        if (sendBtn && !sendBtn.hasAttribute("data-server-blocked")) {
            sendBtn.disabled = !online;
            if (!online) {
                sendBtn.title = "Sin conexión a internet.";
            }
        }
    }

    if (sendBtn && sendBtn.disabled && sendBtn.title) {
        sendBtn.setAttribute("data-server-blocked", "1");
    }

    if (sendCountEl) {
        var match = sendCountEl.textContent.match(/\/\s*(\d+)/);
        if (match) {
            dailyLimit = match[1];
        }
    }

    function getCsrfToken() {
        var input = sendForm && sendForm.querySelector('input[name="csrfmiddlewaretoken"]');
        return input ? input.value : "";
    }

    function showModal() {
        if (!modal) {
            return;
        }
        modal.classList.add("show");
        modal.setAttribute("aria-hidden", "false");
    }

    function hideModal() {
        if (!modal) {
            return;
        }
        modal.classList.remove("show");
        modal.setAttribute("aria-hidden", "true");
    }

    function showLoading() {
        if (!modal) {
            return;
        }
        if (modalTitle) {
            modalTitle.textContent = "Enviando reporte";
        }
        if (loadingState) {
            loadingState.classList.remove("hidden");
        }
        if (resultState) {
            resultState.classList.add("hidden");
        }
        if (modalCloseX) {
            modalCloseX.hidden = true;
        }
        showModal();
    }

    function renderChecklist(items) {
        if (!checklistEl) {
            return;
        }
        checklistEl.innerHTML = "";
        items.forEach(function (item) {
            var li = document.createElement("li");
            li.className = item.ok ? "report-send-check-ok" : "report-send-check-fail";
            var icon = document.createElement("span");
            icon.className = "report-send-check-icon";
            icon.textContent = item.ok ? "✓" : "✕";
            var text = document.createElement("span");
            text.textContent = item.text;
            li.appendChild(icon);
            li.appendChild(text);
            checklistEl.appendChild(li);
        });
    }

    function showResult(data) {
        if (!modal || !resultState || !loadingState) {
            return;
        }
        loadingState.classList.add("hidden");
        resultState.classList.remove("hidden");
        if (modalCloseX) {
            modalCloseX.hidden = false;
        }

        var success = !!data.success;
        if (modalTitle) {
            modalTitle.textContent = success ? "Reporte enviado" : "No se pudo enviar";
        }
        if (resultIcon) {
            resultIcon.className = "report-send-result-icon " + (success ? "is-success" : "is-error");
            resultIcon.textContent = success ? "✓" : "✕";
        }
        if (resultTitle) {
            resultTitle.textContent = success
                ? "El resumen fue enviado correctamente."
                : "Revisa los siguientes puntos:";
        }
        renderChecklist(data.items || []);

        if (success && sendCountEl && typeof data.daily_send_count === "number" && dailyLimit) {
            sendCountEl.textContent = "Envíos hoy: " + data.daily_send_count + " / " + dailyLimit;
        }

        if (success && sendBtn && typeof data.daily_send_count === "number" && dailyLimit
            && data.daily_send_count >= parseInt(dailyLimit, 10)) {
            sendBtn.disabled = true;
            sendBtn.title = "Límite diario alcanzado.";
            sendBtn.setAttribute("data-server-blocked", "1");
        }
    }

    window.addEventListener("online", updateOnlineState);
    window.addEventListener("offline", updateOnlineState);
    updateOnlineState();

    if (sendForm && modal) {
        sendForm.addEventListener("submit", function (event) {
            event.preventDefault();
            if (sendBtn && sendBtn.disabled) {
                return;
            }

            showLoading();
            if (sendBtn) {
                sendBtn.disabled = true;
                sendBtn.textContent = "Enviando…";
            }

            var formData = new FormData(sendForm);
            fetch(sendForm.action, {
                method: "POST",
                headers: {
                    "X-Requested-With": "XMLHttpRequest",
                    "X-CSRFToken": getCsrfToken(),
                },
                body: formData,
            })
                .then(function (response) {
                    return response.json();
                })
                .then(function (data) {
                    showResult(data);
                    if (sendBtn) {
                        sendBtn.textContent = "Enviar por correo";
                        if (!sendBtn.hasAttribute("data-server-blocked")) {
                            sendBtn.disabled = false;
                            updateOnlineState();
                        }
                    }
                })
                .catch(function () {
                    showResult({
                        success: false,
                        items: [{ ok: false, text: "Error de conexión con el servidor" }],
                    });
                    if (sendBtn) {
                        sendBtn.textContent = "Enviar por correo";
                        if (!sendBtn.hasAttribute("data-server-blocked")) {
                            sendBtn.disabled = false;
                            updateOnlineState();
                        }
                    }
                });
        });
    }

    if (closeBtn) {
        closeBtn.addEventListener("click", hideModal);
    }
    if (typeof bindDismissibleModalById === "function") {
        bindDismissibleModalById("report-send-modal", {
            onClose: hideModal,
            allowBackdrop: true,
        });
    }

    // --- Reportes fiscales X / Z ---
    var page = document.getElementById("report-page");
    var fiscalUrl = page && page.getAttribute("data-fiscal-url");
    var printXBtn = document.getElementById("report-print-x-btn");
    var printZBtn = document.getElementById("report-print-z-btn");
    var confirmModal = document.getElementById("report-fiscal-confirm-modal");
    var confirmTitle = document.getElementById("report-fiscal-confirm-title");
    var confirmMessage = document.getElementById("report-fiscal-confirm-message");
    var confirmCancel = document.getElementById("report-fiscal-confirm-cancel");
    var confirmOk = document.getElementById("report-fiscal-confirm-ok");
    var fiscalResultModal = document.getElementById("report-fiscal-result-modal");
    var fiscalResultMsg = document.getElementById("report-fiscal-result-message");
    var fiscalResultClose = document.getElementById("report-fiscal-result-close");
    var fiscalBusy = false;
    var pendingReportType = null;

    function getPageCsrf() {
        var tokenInput =
            (page && page.querySelector('input[name="csrfmiddlewaretoken"]')) ||
            (sendForm && sendForm.querySelector('input[name="csrfmiddlewaretoken"]'));
        return tokenInput ? tokenInput.value : "";
    }

    function setFiscalButtonsLoading(loading) {
        [printXBtn, printZBtn].forEach(function (btn) {
            if (!btn) {
                return;
            }
            btn.disabled = loading;
            btn.classList.toggle("is-loading", loading);
        });
        if (confirmOk) {
            confirmOk.disabled = loading;
        }
    }

    function openFiscalConfirm(reportType) {
        if (!confirmModal) {
            return;
        }
        pendingReportType = reportType;
        if (confirmTitle) {
            confirmTitle.textContent =
                reportType === "Z" ? "Confirmar reporte Z" : "Confirmar reporte X";
        }
        if (confirmMessage) {
            if (reportType === "Z") {
                confirmMessage.innerHTML =
                    "Va a imprimir el <strong>reporte Z</strong>. Esto cierra la jornada fiscal en la impresora y reinicia sus acumuladores.";
            } else {
                confirmMessage.innerHTML =
                    "Va a imprimir el <strong>reporte X</strong> en la impresora fiscal.";
            }
        }
        if (confirmOk) {
            confirmOk.textContent =
                reportType === "Z" ? "Imprimir reporte Z" : "Imprimir reporte X";
            confirmOk.className =
                reportType === "Z" ? "btn btn-primary" : "btn btn-secondary";
        }
        confirmModal.classList.add("show");
        confirmModal.setAttribute("aria-hidden", "false");
    }

    function closeFiscalConfirm() {
        if (!confirmModal) {
            return;
        }
        pendingReportType = null;
        confirmModal.classList.remove("show");
        confirmModal.setAttribute("aria-hidden", "true");
    }

    function openFiscalResult(data) {
        if (!fiscalResultModal || !fiscalResultMsg) {
            return;
        }
        fiscalResultMsg.textContent = data.message || "";
        if (data.simulated) {
            fiscalResultMsg.style.color = "#f59e0b";
        } else {
            fiscalResultMsg.style.color = data.success ? "var(--success)" : "var(--danger)";
        }
        fiscalResultModal.classList.add("show");
        fiscalResultModal.setAttribute("aria-hidden", "false");
    }

    function closeFiscalResult() {
        if (!fiscalResultModal) {
            return;
        }
        fiscalResultModal.classList.remove("show");
        fiscalResultModal.setAttribute("aria-hidden", "true");
    }

    function printFiscalReport(reportType) {
        if (!fiscalUrl || fiscalBusy) {
            return;
        }
        fiscalBusy = true;
        setFiscalButtonsLoading(true);
        closeFiscalConfirm();

        var body = new FormData();
        body.append("report_type", reportType);
        body.append("csrfmiddlewaretoken", getPageCsrf());

        fetch(fiscalUrl, {
            method: "POST",
            headers: {
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": getPageCsrf(),
            },
            body: body,
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return data;
                });
            })
            .then(function (data) {
                openFiscalResult(data);
            })
            .catch(function () {
                openFiscalResult({
                    success: false,
                    message: "No se pudo contactar al servidor. Intente de nuevo.",
                });
            })
            .finally(function () {
                fiscalBusy = false;
                setFiscalButtonsLoading(false);
            });
    }

    if (printXBtn) {
        printXBtn.addEventListener("click", function () {
            openFiscalConfirm("X");
        });
    }

    if (printZBtn) {
        printZBtn.addEventListener("click", function () {
            openFiscalConfirm("Z");
        });
    }

    if (confirmCancel) {
        confirmCancel.addEventListener("click", closeFiscalConfirm);
    }

    if (confirmOk) {
        confirmOk.addEventListener("click", function () {
            if (pendingReportType) {
                printFiscalReport(pendingReportType);
            }
        });
    }

    if (fiscalResultClose) {
        fiscalResultClose.addEventListener("click", closeFiscalResult);
    }

    if (typeof bindDismissibleModalById === "function") {
        bindDismissibleModalById("report-fiscal-confirm-modal", {
            onClose: closeFiscalConfirm,
        });
        bindDismissibleModalById("report-fiscal-result-modal", {
            onClose: closeFiscalResult,
        });
    }

    document.addEventListener("click", function (event) {
        var target = event.target;
        var row = target && target.closest ? target.closest("tr[data-href]") : null;
        if (!row) return;
        if (target.closest("a, button, input, select, textarea")) return;
        window.location.href = row.getAttribute("data-href");
    });

    var rangeForm = document.getElementById("report-range-form");
    var fechaDesdeInput = document.getElementById("fecha_desde");
    var fechaHastaInput = document.getElementById("fecha_hasta");

    function syncReportDateRange(changedField) {
        if (!fechaDesdeInput || !fechaHastaInput) {
            return;
        }
        var desde = fechaDesdeInput.value;
        var hasta = fechaHastaInput.value;
        if (!desde || !hasta) {
            return;
        }
        if (desde > hasta) {
            if (changedField === "desde") {
                fechaHastaInput.value = desde;
            } else {
                fechaDesdeInput.value = hasta;
            }
        }
    }

    if (fechaDesdeInput) {
        fechaDesdeInput.addEventListener("change", function () {
            syncReportDateRange("desde");
        });
    }
    if (fechaHastaInput) {
        fechaHastaInput.addEventListener("change", function () {
            syncReportDateRange("hasta");
        });
    }
    if (rangeForm) {
        rangeForm.addEventListener("submit", function () {
            syncReportDateRange("desde");
            if (fechaDesdeInput && fechaHastaInput) {
                if (fechaDesdeInput.value && !fechaHastaInput.value) {
                    fechaHastaInput.value = fechaDesdeInput.value;
                } else if (!fechaDesdeInput.value && fechaHastaInput.value) {
                    fechaDesdeInput.value = fechaHastaInput.value;
                }
            }
        });
    }
})();
