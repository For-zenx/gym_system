(function () {
    var config = window.INACTIVE_CLIENTS_PURGE || {};
    var modal = document.getElementById("inactiveClientsPurgeModal");
    if (!modal || !config.previewUrl) {
        return;
    }

    var step1 = document.getElementById("inactiveClientsPurgeStep1");
    var step2 = document.getElementById("inactiveClientsPurgeStep2");
    var nextBtn = document.getElementById("inactiveClientsNextBtn");
    var step1Error = document.getElementById("inactiveClientsStep1Error");
    var loadingEl = document.getElementById("inactiveClientsLoading");
    var reviewPanel = document.getElementById("inactiveClientsReviewPanel");
    var reviewSummary = document.getElementById("inactiveClientsReviewSummary");
    var reviewEmpty = document.getElementById("inactiveClientsReviewEmpty");
    var tableWrap = document.getElementById("inactiveClientsTableWrap");
    var tableBody = document.getElementById("inactiveClientsTableBody");
    var reviewTruncated = document.getElementById("inactiveClientsReviewTruncated");
    var confirmPanel = document.getElementById("inactiveClientsConfirmPanel");
    var confirmCountLabel = document.getElementById("inactiveClientsConfirmCountLabel");
    var formYears = document.getElementById("inactiveClientsFormYears");
    var confirmCountInput = document.getElementById("inactiveClientsConfirmCount");
    var confirmAck = document.getElementById("inactiveClientsConfirmAck");
    var backBtn = document.getElementById("inactiveClientsBackBtn");
    var closeBtn = document.getElementById("inactiveClientsCloseBtn");
    var submitBtn = document.getElementById("inactiveClientsSubmitBtn");
    var openBtn = document.getElementById("inactiveClientsPurgeOpenBtn");

    var state = {
        previewCount: 0,
        inactivityYears: 1,
    };

    function getSelectedYears() {
        var selected = modal.querySelector('input[name="inactive_clients_years"]:checked');
        return selected ? parseInt(selected.value, 10) : 1;
    }

    function clearStep1Error() {
        step1Error.hidden = true;
        step1Error.textContent = "";
    }

    function showStep1Error(message) {
        step1Error.textContent = message;
        step1Error.hidden = false;
    }

    function resetStep2View() {
        loadingEl.hidden = false;
        reviewPanel.hidden = true;
        reviewSummary.textContent = "";
        reviewEmpty.hidden = true;
        tableWrap.hidden = true;
        tableBody.innerHTML = "";
        reviewTruncated.hidden = true;
        reviewTruncated.textContent = "";
        confirmPanel.hidden = true;
        closeBtn.hidden = true;
        submitBtn.hidden = true;
        submitBtn.disabled = true;
        submitBtn.textContent = "Eliminar afiliados";
        confirmCountInput.value = "";
        confirmAck.checked = false;
    }

    function resetStep1View() {
        clearStep1Error();
        nextBtn.disabled = false;
        nextBtn.textContent = "Siguiente";
    }

    function showStep1() {
        step1.hidden = false;
        step2.hidden = true;
        resetStep1View();
    }

    function showStep2Loading() {
        step1.hidden = true;
        step2.hidden = false;
        resetStep2View();
    }

    function updateSubmitState() {
        var countValue = parseInt(confirmCountInput.value, 10);
        var countMatches = countValue === state.previewCount;
        submitBtn.disabled = !(confirmAck.checked && countMatches && state.previewCount > 0);
    }

    function renderReview(data) {
        state.previewCount = data.count;
        state.inactivityYears = data.inactivity_years;
        formYears.value = String(state.inactivityYears);

        loadingEl.hidden = true;
        reviewPanel.hidden = false;

        if (data.count === 0) {
            reviewSummary.textContent = "No hay afiliados elegibles para eliminar.";
            reviewEmpty.hidden = false;
            tableWrap.hidden = true;
            confirmPanel.hidden = true;
            closeBtn.hidden = false;
            submitBtn.hidden = true;
            return;
        }

        reviewSummary.innerHTML =
            "Se eliminarán <strong>" + data.count + "</strong> afiliados inactivos.";
        reviewEmpty.hidden = true;
        tableWrap.hidden = false;
        tableBody.innerHTML = "";

        data.sample.forEach(function (row) {
            var tr = document.createElement("tr");
            tr.innerHTML =
                "<td>" + escapeHtml(row.nombre) + "</td>" +
                "<td>" + escapeHtml(row.codigo_afiliado) + "</td>" +
                "<td>" + escapeHtml(row.cedula) + "</td>" +
                "<td>" + escapeHtml(row.inactivity_since) + "</td>";
            tableBody.appendChild(tr);
        });

        if (data.sample_truncated) {
            reviewTruncated.hidden = false;
            reviewTruncated.textContent =
                "Mostrando " + data.sample.length + " de " + data.count +
                ". La eliminación aplicará a todos los elegibles.";
        }

        confirmPanel.hidden = false;
        confirmCountLabel.textContent = String(data.count);
        submitBtn.hidden = false;
        submitBtn.textContent = "Eliminar " + data.count + " afiliados";
        submitBtn.disabled = true;
        closeBtn.hidden = true;
        confirmCountInput.focus();
    }

    function escapeHtml(value) {
        var div = document.createElement("div");
        div.textContent = value == null ? "" : String(value);
        return div.innerHTML;
    }

    function loadPreviewAndGoToStep2() {
        var years = getSelectedYears();
        clearStep1Error();
        nextBtn.disabled = true;
        nextBtn.textContent = "Consultando...";
        showStep2Loading();

        fetch(config.previewUrl + "?years=" + encodeURIComponent(String(years)), {
            credentials: "same-origin",
            headers: {
                Accept: "application/json",
            },
        })
            .then(function (response) {
                return response.json().then(function (payload) {
                    if (!response.ok) {
                        throw new Error(payload.message || "No se pudo obtener la vista previa.");
                    }
                    return payload;
                });
            })
            .then(function (data) {
                renderReview(data);
            })
            .catch(function (error) {
                showStep1();
                showStep1Error(error.message || "No se pudo obtener la vista previa.");
            })
            .finally(function () {
                nextBtn.disabled = false;
                nextBtn.textContent = "Siguiente";
            });
    }

    function openModal() {
        resetStep1View();
        resetStep2View();
        showStep1();
        state.previewCount = 0;
        state.inactivityYears = getSelectedYears();
        modal.classList.add("show");
        modal.setAttribute("aria-hidden", "false");
    }

    function closeModal() {
        modal.classList.remove("show");
        modal.setAttribute("aria-hidden", "true");
        showStep1();
        resetStep2View();
        resetStep1View();
    }

    if (openBtn) {
        openBtn.addEventListener("click", openModal);
    }

    nextBtn.addEventListener("click", loadPreviewAndGoToStep2);
    backBtn.addEventListener("click", showStep1);
    confirmCountInput.addEventListener("input", updateSubmitState);
    confirmAck.addEventListener("change", updateSubmitState);

    modal.querySelectorAll("[data-modal-close]").forEach(function (btn) {
        btn.addEventListener("click", function (event) {
            event.preventDefault();
            closeModal();
        });
    });

    bindDismissibleModalById("inactiveClientsPurgeModal", {
        onClose: closeModal,
        allowBackdrop: false,
    });
})();
