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
})();
