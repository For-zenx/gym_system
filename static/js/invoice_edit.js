(function () {
    var form = document.getElementById("invoice-review-form");
    var previewBox = document.getElementById("invoice-ticket-preview");
    var totalEl = document.getElementById("invoice-live-total");
    var previewUrl = form && form.getAttribute("data-preview-url");
    var canEdit = form && form.getAttribute("data-can-edit") === "1";
    var debounceTimer = null;
    var isDirty = false;

    function getCsrfToken() {
        var input = form && form.querySelector('input[name="csrfmiddlewaretoken"]');
        return input ? input.value : "";
    }

    function getAmountInputs() {
        if (!form) {
            return [];
        }
        return Array.prototype.slice.call(
            form.querySelectorAll("[data-invoice-amount]")
        );
    }

    function markDirty() {
        if (!canEdit) {
            return;
        }
        isDirty = false;
        getAmountInputs().forEach(function (input) {
            var original = input.getAttribute("data-original-value") || "";
            if ((input.value || "").trim() !== original.trim()) {
                isDirty = true;
            }
        });
    }

    function buildPreviewFormData() {
        var data = new FormData();
        getAmountInputs().forEach(function (input) {
            data.append(input.name, input.value);
        });
        return data;
    }

    function renderTicket(lines) {
        if (!previewBox) {
            return;
        }
        previewBox.innerHTML = "";
        (lines || []).forEach(function (line) {
            var span = document.createElement("span");
            span.className = "ticket-line";
            span.textContent = line;
            previewBox.appendChild(span);
        });
    }

    function refreshPreview() {
        if (!previewUrl || !form) {
            return;
        }
        markDirty();
        fetch(previewUrl, {
            method: "POST",
            headers: {
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": getCsrfToken(),
            },
            body: buildPreviewFormData(),
        })
            .then(function (response) {
                return response.json();
            })
            .then(function (data) {
                renderTicket(data.ticket_lines);
                if (totalEl && data.monto_total_fmt) {
                    totalEl.textContent = data.monto_total_fmt;
                }
            })
            .catch(function () {});
    }

    function schedulePreview() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(refreshPreview, 180);
    }

    if (form && canEdit) {
        getAmountInputs().forEach(function (input) {
            input.addEventListener("input", schedulePreview);
        });
    }

    var backLinks = document.querySelectorAll("[data-invoice-leave]");
    backLinks.forEach(function (link) {
        link.addEventListener("click", function (event) {
            markDirty();
            if (!isDirty) {
                return;
            }
            event.preventDefault();
            var target = link.getAttribute("href");
            var modal = document.getElementById("invoice-discard-modal");
            if (!modal) {
                window.location.href = target;
                return;
            }
            modal.classList.add("show");
            modal.setAttribute("data-leave-url", target);
        });
    });

    var discardConfirm = document.getElementById("invoice-discard-confirm");
    if (discardConfirm) {
        discardConfirm.addEventListener("click", function () {
            var modal = document.getElementById("invoice-discard-modal");
            var target = modal && modal.getAttribute("data-leave-url");
            if (target) {
                isDirty = false;
                window.location.href = target;
            }
        });
    }

    var discardCancel = document.getElementById("invoice-discard-cancel");
    if (discardCancel) {
        discardCancel.addEventListener("click", function () {
            var modal = document.getElementById("invoice-discard-modal");
            if (modal) {
                modal.classList.remove("show");
            }
        });
    }

    if (typeof bindDismissibleModalById === "function") {
        bindDismissibleModalById("invoice-discard-modal", {
            onClose: function () {
                var modal = document.getElementById("invoice-discard-modal");
                if (modal) {
                    modal.classList.remove("show");
                }
            },
        });
    }

    markDirty();

    var printBtn = document.getElementById("invoice-print-btn");
    var printModal = document.getElementById("invoice-print-result-modal");
    var printMessage = document.getElementById("invoice-print-result-message");
    var printSteps = document.getElementById("invoice-print-result-steps");
    var printClose = document.getElementById("invoice-print-result-close");
    var isPrinting = false;

    function setPrintButtonLoading(loading) {
        if (!printBtn) {
            return;
        }
        printBtn.disabled = loading;
        printBtn.classList.toggle("is-loading", loading);
        var label = printBtn.querySelector(".invoice-print-btn-label");
        if (label) {
            label.textContent = loading ? "Imprimiendo…" : "Imprimir factura";
        }
    }

    function renderPrintSteps(steps) {
        if (!printSteps) {
            return;
        }
        printSteps.innerHTML = "";
        if (!steps || !steps.length) {
            printSteps.hidden = true;
            return;
        }
        var failed = steps.filter(function (step) {
            return !step.ok;
        });
        if (!failed.length) {
            printSteps.hidden = true;
            return;
        }
        failed.forEach(function (step) {
            var item = document.createElement("li");
            item.className = "invoice-print-step invoice-print-step--failed";
            item.textContent = step.detail || step.label || "Paso fallido";
            printSteps.appendChild(item);
        });
        printSteps.hidden = false;
    }

    function openPrintResultModal(data) {
        if (!printModal || !printMessage) {
            return;
        }
        printMessage.textContent = data.message || "";
        if (data.simulated) {
            printMessage.style.color = "#f59e0b";
        } else {
            printMessage.style.color = data.success ? "var(--success)" : "var(--danger)";
        }
        renderPrintSteps(data.steps || []);
        printModal.classList.add("show");
    }

    function closePrintResultModal() {
        if (printModal) {
            printModal.classList.remove("show");
        }
    }

    function buildPrintFormData() {
        var data = new FormData(form);
        getAmountInputs().forEach(function (input) {
            data.set(input.name, input.value);
        });
        return data;
    }

    function handlePrintClick() {
        if (!form || !printBtn || isPrinting) {
            return;
        }
        isPrinting = true;
        setPrintButtonLoading(true);

        fetch(form.action, {
            method: "POST",
            headers: {
                "X-Requested-With": "XMLHttpRequest",
                "X-CSRFToken": getCsrfToken(),
            },
            body: buildPrintFormData(),
        })
            .then(function (response) {
                return response.json().then(function (data) {
                    return { ok: response.ok, data: data };
                });
            })
            .then(function (result) {
                openPrintResultModal(result.data);
                if (result.data.success && result.data.esta_impresa && !result.data.simulated) {
                    isDirty = false;
                    window.setTimeout(function () {
                        window.location.reload();
                    }, 1200);
                }
            })
            .catch(function () {
                openPrintResultModal({
                    success: false,
                    message: "No se pudo contactar al servidor. Verifique la conexión e intente de nuevo.",
                });
            })
            .finally(function () {
                isPrinting = false;
                setPrintButtonLoading(false);
            });
    }

    if (printBtn && form) {
        printBtn.addEventListener("click", handlePrintClick);
    }

    if (printClose) {
        printClose.addEventListener("click", closePrintResultModal);
    }

    if (typeof bindDismissibleModalById === "function") {
        bindDismissibleModalById("invoice-print-result-modal", {
            onClose: closePrintResultModal,
        });
    }
})();
