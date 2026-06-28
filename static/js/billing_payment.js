(function () {
    function formatVes(amount) {
        return 'Bs ' + amount.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    window.initBillingPayment = function (config) {
        const select = document.getElementById(config.selectId);
        const btnConfirm = document.getElementById(config.confirmId);
        const priceUsdEl = document.getElementById(config.priceUsdId);
        const priceVesEl = document.getElementById(config.priceVesId);
        const totalVesEl = document.getElementById(config.totalVesId);
        const periodBox = document.getElementById(config.periodBoxId);
        const periodText = document.getElementById(config.periodTextId);
        const alertSuspended = document.getElementById(config.alertSuspendedId);
        const alertFlexible = document.getElementById(config.alertFlexibleId);
        const lateFeeSection = document.getElementById(config.lateFeeSectionId);
        const lateFeeCheck = document.getElementById(config.lateFeeCheckId);
        const lateFeeInput = document.getElementById(config.lateFeeInputId);
        const lateFeeVesEl = document.getElementById(config.lateFeeVesId);
        const cutDaySection = document.getElementById('payment-cut-day-section');
        const cutDayHidden = document.getElementById('payment_cut_day');
        const cutDayDisplay = document.getElementById('payment_cut_day_display');
        const cutDayInitial = document.getElementById('payment_cut_initial');
        const cutDayEditing = document.getElementById('payment_cut_editing');
        const cutDayEditBtn = document.getElementById('payment_cut_day_edit_btn');
        const cutMotivoSection = document.getElementById('payment-cut-motivo-section');
        const cutMotivoPreset = document.getElementById('payment_cut_motivo_preset');
        const cutMotivoCustom = document.getElementById('payment_cut_motivo_custom');
        let paymentCutMotivo = null;

        const tasaDia = config.tasaDia;
        const billingContext = config.billingContext || {};
        const planPreviews = config.planPreviews || {};
        const previewUrl = config.previewUrl || '';
        let lateFeeDefaultApplied = false;
        let previewRequestId = 0;
        let cutDayEditMode = false;

        function getDefaultCutDay() {
            return billingContext.default_cut_day || billingContext.fecha_corte_dia || new Date().getDate();
        }

        function syncCutDayHidden() {
            if (!cutDayHidden || !cutDayDisplay) return;
            cutDayHidden.value = cutDayDisplay.value;
        }

        function getSelectedCutDay() {
            if (cutDayHidden && cutDayHidden.value) {
                return parseInt(cutDayHidden.value, 10);
            }
            return getDefaultCutDay();
        }

        function ensurePaymentCutMotivo() {
            if (paymentCutMotivo || !cutMotivoPreset || !window.initCutDateMotivoFields) {
                return;
            }
            paymentCutMotivo = initCutDateMotivoFields({
                presetId: 'payment_cut_motivo_preset',
                customWrapId: 'payment_cut_motivo_custom_wrap',
                customId: 'payment_cut_motivo_custom',
            });
        }

        function isPaymentCutMotivoValid() {
            if (!cutMotivoSection || cutMotivoSection.style.display === 'none') {
                return true;
            }
            if (!cutMotivoPreset || !cutMotivoPreset.value) {
                return false;
            }
            if (cutMotivoPreset.value === '__other__') {
                return !!(cutMotivoCustom && cutMotivoCustom.value.trim());
            }
            return true;
        }

        window.checkoutPaymentCutMotivoValid = isPaymentCutMotivoValid;

        window.collectCheckoutPaymentErrors = function () {
            if (isPaymentCutMotivoValid()) {
                return [];
            }
            if (!cutMotivoSection || cutMotivoSection.style.display === 'none') {
                return [];
            }
            if (cutMotivoPreset && cutMotivoPreset.value === '__other__') {
                return ['Describa el motivo del cambio de fecha de corte.'];
            }
            return ['Seleccione un motivo para el cambio de fecha de corte.'];
        };

        function refreshCheckoutSubmit() {
            if (window.checkoutRefreshSubmit) {
                window.checkoutRefreshSubmit();
            }
        }

        function updateCutMotivoVisibility() {
            if (!cutMotivoSection || !cutDayDisplay || !cutDayInitial) return;
            const changed = parseInt(cutDayDisplay.value, 10) !== parseInt(cutDayInitial.value, 10);
            const showMotivo = cutDayEditMode && changed;
            cutMotivoSection.style.display = showMotivo ? 'block' : 'none';
            if (cutMotivoPreset) {
                cutMotivoPreset.required = showMotivo;
                if (!showMotivo && paymentCutMotivo) {
                    paymentCutMotivo.reset();
                } else if (showMotivo) {
                    ensurePaymentCutMotivo();
                }
            }
            refreshCheckoutSubmit();
        }

        function resetCutDayEditor() {
            cutDayEditMode = false;
            const defaultDay = getDefaultCutDay();
            if (cutDayHidden) cutDayHidden.value = defaultDay;
            if (cutDayInitial) cutDayInitial.value = defaultDay;
            if (cutDayEditing) cutDayEditing.value = '0';
            if (cutDayDisplay) {
                cutDayDisplay.value = defaultDay;
                cutDayDisplay.disabled = true;
            }
            if (cutDayEditBtn) {
                cutDayEditBtn.style.display = '';
            }
            if (cutMotivoPreset) {
                cutMotivoPreset.required = false;
            }
            if (cutMotivoCustom) {
                cutMotivoCustom.required = false;
            }
            if (paymentCutMotivo) {
                paymentCutMotivo.reset();
            }
            if (cutMotivoSection) cutMotivoSection.style.display = 'none';
        }

        function enableCutDayEditor() {
            cutDayEditMode = true;
            if (cutDayEditing) cutDayEditing.value = '1';
            if (cutDayDisplay) {
                cutDayDisplay.disabled = false;
                cutDayDisplay.focus();
                cutDayDisplay.select();
            }
            if (cutDayEditBtn) {
                cutDayEditBtn.style.display = 'none';
            }
            updateCutMotivoVisibility();
        }

        const periodDetail = document.getElementById('payment-period-detail');

        function applyPreviewData(preview, billingType) {
            if (!periodBox || !periodText || !preview.inicio || !preview.fin) {
                if (periodBox) periodBox.style.display = 'none';
                return;
            }
            periodBox.style.display = 'block';
            periodText.textContent = preview.inicio + '  →  ' + preview.fin;

            if (!periodDetail) return;

            if (billingType === 'FIXED') {
                const cutDay = preview.cut_day != null ? preview.cut_day : getSelectedCutDay();
                const storedCut = preview.stored_cut_day != null
                    ? preview.stored_cut_day
                    : (billingContext.fecha_corte_dia != null ? billingContext.fecha_corte_dia : null);
                let detail = 'Membresía mensual con corte el día ' + cutDay + ' de cada mes.';
                if (storedCut != null && storedCut !== cutDay) {
                    detail += ' Al confirmar, el corte del afiliado cambiará del día ' + storedCut + ' al día ' + cutDay + '.';
                } else if (storedCut == null) {
                    detail += ' Al confirmar, ese día quedará como corte del afiliado.';
                }
                periodDetail.textContent = detail;
            } else {
                const duracion = preview.duracion || (planPreviews[select.value] && planPreviews[select.value].duracion) || '';
                periodDetail.textContent = duracion
                    ? 'Pase flexible · ' + duracion
                    : 'Pase flexible · vigencia según días del plan.';
            }
        }

        function fetchPeriodPreview(planId, billingType) {
            if (!previewUrl || !planId) {
                return;
            }

            if (billingType !== 'FIXED') {
                applyPreviewData(planPreviews[planId] || {}, billingType);
                return;
            }

            const cutDay = getSelectedCutDay();
            if (!cutDay || cutDay < 1 || cutDay > 31) {
                return;
            }

            const requestId = ++previewRequestId;
            const url = previewUrl + '?plan_id=' + encodeURIComponent(planId) +
                '&payment_cut_day=' + encodeURIComponent(cutDay);

            fetch(url, { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                .then(function (response) { return response.json(); })
                .then(function (data) {
                    if (requestId !== previewRequestId) {
                        return;
                    }
                    if (data.error) {
                        return;
                    }
                    applyPreviewData(data, billingType);
                })
                .catch(function () {});
        }

        function recalcTotal(cuotaVes, membershipUsd) {
            let multaVes = 0;
            let multaUsd = 0;
            if (lateFeeSection && lateFeeSection.style.display !== 'none' && lateFeeCheck && lateFeeCheck.checked && lateFeeInput) {
                multaUsd = window.parseUsdAmount(lateFeeInput.value);
                multaVes = multaUsd * tasaDia;
            }
            if (lateFeeVesEl) lateFeeVesEl.textContent = formatVes(multaVes);
            if (totalVesEl) totalVesEl.textContent = 'Total: ' + formatVes(cuotaVes + multaVes);
            if (window.checkoutSetMembershipTotals) {
                window.checkoutSetMembershipTotals(
                    cuotaVes,
                    multaVes,
                    membershipUsd != null ? membershipUsd : 0,
                    multaUsd
                );
            }
            if (window.checkoutRefreshPaymentMethodSummary) {
                window.checkoutRefreshPaymentMethodSummary();
            }
        }

        function updatePrice() {
            if (!select || !btnConfirm) return;

            if (!select.value) {
                if (priceUsdEl) priceUsdEl.textContent = config.emptyUsdLabel || 'Precio: $0.00';
                if (priceVesEl) priceVesEl.textContent = 'Bs 0.00';
                if (periodBox) periodBox.style.display = 'none';
                if (alertSuspended) alertSuspended.style.display = 'none';
                if (alertFlexible) alertFlexible.style.display = 'none';
                if (lateFeeSection) lateFeeSection.style.display = 'none';
                if (cutDaySection) cutDaySection.style.display = 'none';
                if (window.checkoutSetMembershipTotals) {
                    window.checkoutSetMembershipTotals(0, 0, 0, 0);
                } else if (totalVesEl) {
                    totalVesEl.textContent = 'Total: Bs 0.00';
                }
                if (window.checkoutRefreshSubmit) {
                    window.checkoutRefreshSubmit();
                }
                btnConfirm.disabled = false;
                return;
            }

            if (tasaDia <= 0 || isNaN(tasaDia)) {
                if (window.checkoutRefreshSubmit) {
                    window.checkoutRefreshSubmit();
                }
                if (btnConfirm) {
                    btnConfirm.disabled = false;
                }
                return;
            }

            const option = select.options[select.selectedIndex];
            const priceUsd = window.parseUsdAmount(option.getAttribute('data-usd'));
            const billingType = option.getAttribute('data-billing-type');
            const priceVes = priceUsd * tasaDia;

            if (priceUsdEl) {
                priceUsdEl.textContent = (config.usdPrefix || 'Precio: ') + '$' + priceUsd.toFixed(2);
            }
            if (priceVesEl) priceVesEl.textContent = formatVes(priceVes);

            const isFixed = billingType === 'FIXED';
            if (cutDaySection) {
                cutDaySection.style.display = isFixed ? 'block' : 'none';
            }
            if (!isFixed) {
                resetCutDayEditor();
            }

            fetchPeriodPreview(select.value, billingType);

            const showSuspended = isFixed && billingContext.fixed_status === 'SUSPENDED';
            const showFlexibleWarn = billingType === 'FLEXIBLE' && billingContext.warnings_on_flexible_purchase;

            if (alertSuspended) {
                alertSuspended.style.display = showSuspended ? 'block' : 'none';
                if (showSuspended && billingContext.unpaid_period_count > 0) {
                    alertSuspended.textContent =
                        'Suscripción fija suspendida. Periodos impagos (informativo): ' +
                        billingContext.unpaid_period_count + '.';
                }
            }

            if (alertFlexible) {
                alertFlexible.style.display = showFlexibleWarn ? 'block' : 'none';
            }

            if (lateFeeSection && lateFeeCheck && lateFeeInput) {
                lateFeeSection.style.display = showSuspended ? 'block' : 'none';
                if (showSuspended) {
                    if (!lateFeeDefaultApplied) {
                        lateFeeCheck.checked = !!billingContext.default_apply_late_fee;
                        lateFeeDefaultApplied = true;
                    }
                    if (!lateFeeInput.value) {
                        lateFeeInput.value = parseFloat(billingContext.suggested_late_fee_usd || 0).toFixed(2);
                    }
                } else {
                    lateFeeCheck.checked = false;
                    lateFeeDefaultApplied = false;
                }
            }

            recalcTotal(priceVes, priceUsd);
            if (window.checkoutRefreshSubmit) {
                window.checkoutRefreshSubmit();
            } else if (btnConfirm) {
                btnConfirm.disabled = false;
            }
        }

        if (select) {
            select.addEventListener('change', function () {
                resetCutDayEditor();
                updatePrice();
            });
        }
        if (lateFeeCheck) {
            lateFeeCheck.addEventListener('change', function () {
                const option = select.options[select.selectedIndex];
                if (!option || !option.value) return;
                const priceUsd = window.parseUsdAmount(option.getAttribute('data-usd'));
                recalcTotal(priceUsd * tasaDia, priceUsd);
            });
        }
        if (lateFeeInput) {
            lateFeeInput.addEventListener('input', function () {
                const option = select.options[select.selectedIndex];
                if (!option || !option.value) return;
                const priceUsd = window.parseUsdAmount(option.getAttribute('data-usd'));
                recalcTotal(priceUsd * tasaDia, priceUsd);
            });
        }
        function onCutDayFieldChange() {
            syncCutDayHidden();
            updateCutMotivoVisibility();
            const option = select.options[select.selectedIndex];
            if (!option || !option.value) return;
            fetchPeriodPreview(option.value, option.getAttribute('data-billing-type'));
        }

        if (cutDayDisplay) {
            cutDayDisplay.addEventListener('input', onCutDayFieldChange);
            cutDayDisplay.addEventListener('change', onCutDayFieldChange);
        }
        if (cutDayEditBtn) {
            cutDayEditBtn.addEventListener('click', enableCutDayEditor);
        }
        if (cutMotivoPreset) {
            cutMotivoPreset.addEventListener('change', refreshCheckoutSubmit);
        }
        if (cutMotivoCustom) {
            cutMotivoCustom.addEventListener('input', refreshCheckoutSubmit);
        }

        ensurePaymentCutMotivo();

        updatePrice();

        return {
            reset: function () {
                if (select) select.value = '';
                if (lateFeeInput) lateFeeInput.value = '';
                resetCutDayEditor();
                lateFeeDefaultApplied = false;
                updatePrice();
            },
        };
    };
})();
