(function (global) {
    const VES_SPLIT_METHODS = [
        { value: 'CASH_VES', label: 'Efectivo Bs' },
        { value: 'DEBIT', label: 'Débito' },
        { value: 'MOBILE', label: 'Pago móvil' },
    ];
    const USD_SPLIT_METHOD = { value: 'CASH_USD', label: 'Efectivo $' };

    const USD_CHECKOUT_METHODS = ['CASH_USD', 'ZELLE'];

    const METHOD_LABELS = {
        CASH_VES: 'Efectivo Bs',
        CASH_USD: 'Efectivo $',
        ZELLE: 'Zelle',
        DEBIT: 'Débito',
        MOBILE: 'Pago móvil',
        CASHEA: 'Cashea',
        MIXED: 'Mixto',
    };

    let tasaDia = 0;

    function parseVesText(value) {
        const stripped = String(value || '')
            .replace(/Bs\.?\s*/gi, '')
            .replace(/Total:\s*/gi, '')
            .trim();
        if (global.parseUsdAmount) {
            return global.parseUsdAmount(stripped);
        }
        const normalized = stripped.replace(/\./g, '').replace(',', '.');
        const amount = parseFloat(normalized);
        return isNaN(amount) ? 0 : amount;
    }

    function parseUsdText(value) {
        if (global.parseUsdAmount) {
            return global.parseUsdAmount(value);
        }
        return parseVesText(value);
    }

    function formatVes(amount) {
        return 'Bs ' + amount.toLocaleString('es-VE', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    }

    function formatUsd(amount) {
        if (global.formatUsd) {
            return global.formatUsd(amount);
        }
        return '$' + amount.toFixed(2);
    }

    function getSelectedPaymentMethod() {
        const selected = document.querySelector('input[name="payment_method"]:checked');
        return selected ? selected.value : '';
    }

    function getCheckoutGrandTotalVes() {
        const totalEl = document.getElementById('checkout-grand-total');
        if (totalEl && totalEl.dataset.totalVes) {
            const fromData = parseFloat(totalEl.dataset.totalVes);
            if (!isNaN(fromData) && fromData > 0) {
                return fromData;
            }
        }
        if (totalEl) {
            const parsed = parseVesText(totalEl.textContent);
            if (parsed > 0) {
                return parsed;
            }
        }

        let total = 0;
        ['checkout-membership-subtotal', 'checkout-products-subtotal', 'checkout-latefee-subtotal'].forEach(function (id) {
            const el = document.getElementById(id);
            if (el) {
                total += parseVesText(el.textContent);
            }
        });
        if (total > 0) {
            return total;
        }

        const priceTotalEl = document.getElementById('price_total_ves');
        if (priceTotalEl) {
            return parseVesText(priceTotalEl.textContent);
        }
        return 0;
    }

    function getCheckoutGrandTotalUsd() {
        const totalEl = document.getElementById('checkout-grand-total-usd');
        if (totalEl && totalEl.dataset.totalUsd) {
            const fromData = parseFloat(totalEl.dataset.totalUsd);
            if (!isNaN(fromData) && fromData > 0) {
                return fromData;
            }
        }
        if (totalEl) {
            const parsed = parseUsdText(totalEl.textContent);
            if (parsed > 0) {
                return parsed;
            }
        }
        return 0;
    }

    function getUsdSplitVesAmount() {
        const input = document.getElementById('payment_split_CASH_USD');
        if (!input || tasaDia <= 0) {
            return 0;
        }
        const usd = parseUsdText(input.value);
        if (usd <= 0) {
            return 0;
        }
        return Math.round(usd * tasaDia * 100) / 100;
    }

    function refreshUsdEquivalent() {
        const hintEl = document.getElementById('payment_split_CASH_USD_ves');
        const input = document.getElementById('payment_split_CASH_USD');
        if (!hintEl || !input) {
            return;
        }
        const usd = parseUsdText(input.value);
        if (usd <= 0 || tasaDia <= 0) {
            hintEl.textContent = '';
            return;
        }
        hintEl.textContent = '≈ ' + formatVes(getUsdSplitVesAmount()) + ' (' + formatUsd(usd) + ' × tasa del día)';
    }

    function getMixedSplitAmounts() {
        const amounts = [];

        VES_SPLIT_METHODS.forEach(function (method) {
            const input = document.getElementById('payment_split_' + method.value);
            if (!input) {
                return;
            }
            const amountVes = parseVesText(input.value);
            if (amountVes > 0) {
                amounts.push({
                    method: method.value,
                    label: method.label,
                    amountVes: amountVes,
                    display: formatVes(amountVes),
                });
            }
        });

        const usdInput = document.getElementById('payment_split_CASH_USD');
        if (usdInput) {
            const usd = parseUsdText(usdInput.value);
            const amountVes = getUsdSplitVesAmount();
            if (usd > 0 && amountVes > 0) {
                amounts.push({
                    method: USD_SPLIT_METHOD.value,
                    label: USD_SPLIT_METHOD.label,
                    amountVes: amountVes,
                    amountUsd: usd,
                    display: formatUsd(usd) + ' (' + formatVes(amountVes) + ')',
                });
            }
        }

        return amounts;
    }

    function refreshMixedSummary() {
        const panel = document.getElementById('checkout-payment-mixed-panel');
        if (!panel || panel.hidden) {
            return;
        }

        refreshUsdEquivalent();

        const assignedEl = document.getElementById('checkout-payment-mixed-assigned');
        const targetEl = document.getElementById('checkout-payment-mixed-target');
        const diffWrap = document.getElementById('checkout-payment-mixed-diff-wrap');
        const diffEl = document.getElementById('checkout-payment-mixed-diff');
        const hintEl = document.getElementById('checkout-payment-mixed-hint');

        const target = getCheckoutGrandTotalVes();
        const assigned = getMixedSplitAmounts().reduce(function (sum, entry) {
            return sum + entry.amountVes;
        }, 0);
        const delta = assigned - target;

        if (assignedEl) {
            assignedEl.textContent = formatVes(assigned);
        }
        if (targetEl) {
            targetEl.textContent = formatVes(target);
        }
        if (hintEl) {
            hintEl.hidden = target > 0;
        }

        if (diffWrap && diffEl) {
            if (target <= 0 || Math.abs(delta) < 0.005) {
                diffWrap.hidden = true;
            } else if (delta > 0) {
                diffWrap.hidden = false;
                diffEl.textContent = 'Sobran ' + formatVes(delta) + ' respecto al total del cobro.';
            } else {
                diffWrap.hidden = false;
                diffEl.textContent = 'Faltan ' + formatVes(Math.abs(delta)) + ' para completar el total del cobro.';
            }
        }
    }

    function syncCasheaInstallmentsUi() {
        const installmentsEl = document.getElementById('cashea_installments');
        const customWrap = document.getElementById('cashea_installments_custom_wrap');
        const customInput = document.getElementById('cashea_installments_custom');
        const isOther = Boolean(installmentsEl && installmentsEl.value === 'other');

        if (customWrap) {
            customWrap.hidden = !isOther;
        }
        if (customInput) {
            customInput.disabled = !isOther;
            if (!isOther) {
                customInput.value = '';
            }
        }
    }

    function getCasheaInstallmentsCount() {
        const installmentsEl = document.getElementById('cashea_installments');
        const customInput = document.getElementById('cashea_installments_custom');
        if (!installmentsEl || !installmentsEl.value) {
            return 0;
        }
        if (installmentsEl.value === 'other') {
            return customInput ? parseInt(customInput.value, 10) : 0;
        }
        return parseInt(installmentsEl.value, 10);
    }

    function refreshCasheaSummary() {
        const panel = document.getElementById('checkout-payment-cashea-panel');
        if (!panel || panel.hidden) {
            return;
        }

        syncCasheaInstallmentsUi();

        const initialInput = document.getElementById('cashea_initial_ves');
        const financedInput = document.getElementById('cashea_financed_ves');
        const targetEl = document.getElementById('checkout-payment-cashea-target');
        const diffWrap = document.getElementById('checkout-payment-cashea-diff-wrap');
        const diffEl = document.getElementById('checkout-payment-cashea-diff');
        const hintEl = document.getElementById('checkout-payment-cashea-hint');

        const target = getCheckoutGrandTotalVes();
        const initialRaw = initialInput ? String(initialInput.value || '').trim() : '';
        const initial = initialRaw === '' ? null : parseVesText(initialInput.value);
        let financed = 0;
        if (target > 0 && initial !== null && initial >= 0 && initial < target) {
            financed = Math.round((target - initial) * 100) / 100;
        }

        if (financedInput) {
            financedInput.value = financed > 0 ? formatVes(financed).replace(/^Bs\s*/, '') : '';
        }
        if (targetEl) {
            targetEl.textContent = formatVes(target);
        }
        if (hintEl) {
            hintEl.hidden = target > 0;
        }

        if (diffWrap && diffEl) {
            if (target <= 0 || initial === null) {
                diffWrap.hidden = true;
            } else if (initial < 0) {
                diffWrap.hidden = false;
                diffEl.textContent = 'El inicial no puede ser negativo.';
            } else if (initial >= target) {
                diffWrap.hidden = false;
                diffEl.textContent = 'El inicial debe ser menor al total. Si paga todo, use otra forma de pago.';
            } else {
                diffWrap.hidden = true;
            }
        }
    }

    function togglePaymentPanels() {
        const method = getSelectedPaymentMethod();
        const mixedPanel = document.getElementById('checkout-payment-mixed-panel');
        const casheaPanel = document.getElementById('checkout-payment-cashea-panel');

        if (mixedPanel) {
            mixedPanel.hidden = method !== 'MIXED';
            if (method === 'MIXED') {
                refreshMixedSummary();
            }
        }
        if (casheaPanel) {
            casheaPanel.hidden = method !== 'CASHEA';
            if (method === 'CASHEA') {
                refreshCasheaSummary();
            }
        }
    }

    function collectCheckoutPaymentMethodErrors() {
        const errors = [];
        const method = getSelectedPaymentMethod();
        const total = getCheckoutGrandTotalVes();

        if (!method) {
            errors.push('Seleccione la forma de pago.');
            return errors;
        }

        if (total <= 0) {
            errors.push(
                'Primero indique qué va a cobrar (membresía o productos) para calcular el total del cobro.'
            );
            return errors;
        }

        if (method === 'CASHEA') {
            const initialInput = document.getElementById('cashea_initial_ves');
            const initialRaw = initialInput ? String(initialInput.value || '').trim() : '';
            const initial = initialRaw === '' ? null : parseVesText(initialInput.value);
            const installments = getCasheaInstallmentsCount();

            if (initialRaw === '' || initial === null) {
                errors.push('Indique el monto inicial de Cashea (puede ser 0).');
            } else if (initial < 0) {
                errors.push('El inicial de Cashea no puede ser negativo.');
            } else if (initial >= total) {
                errors.push(
                    'El inicial de Cashea debe ser menor al total del cobro. Si paga el total, use otra forma de pago.'
                );
            }
            if (!installments || installments < 1 || installments > 24) {
                errors.push('Indique la cantidad de cuotas Cashea (1 a 24).');
            }
            return errors;
        }

        if (method !== 'MIXED') {
            return errors;
        }

        const splits = getMixedSplitAmounts();
        if (splits.length < 2) {
            errors.push('El pago mixto requiere al menos dos formas de pago con monto.');
            return errors;
        }

        const assigned = splits.reduce(function (sum, entry) {
            return sum + entry.amountVes;
        }, 0);
        const delta = assigned - total;

        if (Math.abs(delta) >= 0.005) {
            if (delta > 0) {
                errors.push(
                    'El desglose suma ' + formatVes(assigned) + ' pero el total del cobro es ' +
                    formatVes(total) + '. Sobran ' + formatVes(delta) + '.'
                );
            } else {
                errors.push(
                    'El desglose suma ' + formatVes(assigned) + ' pero el total del cobro es ' +
                    formatVes(total) + '. Faltan ' + formatVes(Math.abs(delta)) + '.'
                );
            }
        }

        return errors;
    }

    function getCheckoutPaymentMethodSummary() {
        const method = getSelectedPaymentMethod();
        if (!method) {
            return null;
        }
        if (method === 'MIXED') {
            return {
                label: METHOD_LABELS.MIXED,
                splits: getMixedSplitAmounts().map(function (entry) {
                    return {
                        label: entry.label,
                        amount: entry.display,
                    };
                }),
            };
        }
        if (method === 'CASHEA') {
            const initialInput = document.getElementById('cashea_initial_ves');
            const total = getCheckoutGrandTotalVes();
            const initialRaw = initialInput ? String(initialInput.value || '').trim() : '';
            const initial = initialRaw === '' ? null : parseVesText(initialInput.value);
            const financed = total > 0 && initial !== null && initial >= 0 && initial < total
                ? Math.round((total - initial) * 100) / 100
                : 0;
            const installmentsCount = getCasheaInstallmentsCount();
            const installments = installmentsCount > 0 ? String(installmentsCount) : '';
            const splits = [];
            if (initial !== null && initial >= 0) {
                splits.push({ label: 'Inicial', amount: formatVes(initial) });
            }
            if (financed > 0) {
                splits.push({ label: 'Financiado', amount: formatVes(financed) });
            }
            if (installments) {
                splits.push({ label: 'Cuotas', amount: String(installments) });
            }
            return {
                label: METHOD_LABELS.CASHEA,
                splits: splits,
            };
        }
        if (USD_CHECKOUT_METHODS.indexOf(method) !== -1) {
            const usdTotal = getCheckoutGrandTotalUsd();
            return {
                label: METHOD_LABELS[method] || method,
                splits: usdTotal > 0 ? [{ label: 'Monto', amount: formatUsd(usdTotal) }] : [],
            };
        }
        return {
            label: METHOD_LABELS[method] || method,
            splits: [],
        };
    }

    function refreshActivePaymentSummary() {
        const method = getSelectedPaymentMethod();
        if (method === 'MIXED') {
            refreshMixedSummary();
        } else if (method === 'CASHEA') {
            refreshCasheaSummary();
        }
    }

    function initCheckoutPaymentMethod(config) {
        tasaDia = config && config.tasaDia ? config.tasaDia : 0;

        document.querySelectorAll('input[name="payment_method"]').forEach(function (input) {
            input.addEventListener('change', function () {
                togglePaymentPanels();
                if (global.checkoutRefreshSubmit) {
                    global.checkoutRefreshSubmit();
                }
            });
        });

        VES_SPLIT_METHODS.forEach(function (method) {
            const input = document.getElementById('payment_split_' + method.value);
            if (!input) {
                return;
            }
            input.addEventListener('input', function () {
                refreshMixedSummary();
                if (global.checkoutRefreshSubmit) {
                    global.checkoutRefreshSubmit();
                }
            });
        });

        const usdInput = document.getElementById('payment_split_CASH_USD');
        if (usdInput) {
            usdInput.addEventListener('input', function () {
                refreshMixedSummary();
                if (global.checkoutRefreshSubmit) {
                    global.checkoutRefreshSubmit();
                }
            });
        }

        const casheaInitial = document.getElementById('cashea_initial_ves');
        if (casheaInitial) {
            casheaInitial.addEventListener('input', function () {
                refreshCasheaSummary();
                if (global.checkoutRefreshSubmit) {
                    global.checkoutRefreshSubmit();
                }
            });
        }
        const casheaInstallments = document.getElementById('cashea_installments');
        if (casheaInstallments) {
            casheaInstallments.addEventListener('change', function () {
                refreshCasheaSummary();
                if (global.checkoutRefreshSubmit) {
                    global.checkoutRefreshSubmit();
                }
            });
        }
        const casheaInstallmentsCustom = document.getElementById('cashea_installments_custom');
        if (casheaInstallmentsCustom) {
            casheaInstallmentsCustom.addEventListener('input', function () {
                refreshCasheaSummary();
                if (global.checkoutRefreshSubmit) {
                    global.checkoutRefreshSubmit();
                }
            });
        }

        global.checkoutRefreshPaymentMethodSummary = refreshActivePaymentSummary;
        global.collectCheckoutPaymentMethodErrors = collectCheckoutPaymentMethodErrors;
        global.getCheckoutPaymentMethodSummary = getCheckoutPaymentMethodSummary;
        togglePaymentPanels();
    }

    global.initCheckoutPaymentMethod = initCheckoutPaymentMethod;
})(window);
