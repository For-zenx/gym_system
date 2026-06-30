(function (global) {
    const VES_SPLIT_METHODS = [
        { value: 'CASH_VES', label: 'Efectivo Bs' },
        { value: 'DEBIT', label: 'Débito' },
        { value: 'MOBILE', label: 'Pago móvil' },
    ];
    const USD_SPLIT_METHOD = { value: 'CASH_USD', label: 'Efectivo $' };

    const METHOD_LABELS = {
        CASH_VES: 'Efectivo Bs',
        CASH_USD: 'Efectivo $',
        DEBIT: 'Débito',
        MOBILE: 'Pago móvil',
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

    function toggleMixedPanel() {
        const panel = document.getElementById('checkout-payment-mixed-panel');
        if (!panel) {
            return;
        }
        const isMixed = getSelectedPaymentMethod() === 'MIXED';
        panel.hidden = !isMixed;
        if (isMixed) {
            refreshMixedSummary();
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
        return {
            label: METHOD_LABELS[method] || method,
            splits: [],
        };
    }

    function initCheckoutPaymentMethod(config) {
        tasaDia = config && config.tasaDia ? config.tasaDia : 0;

        document.querySelectorAll('input[name="payment_method"]').forEach(function (input) {
            input.addEventListener('change', function () {
                toggleMixedPanel();
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

        global.checkoutRefreshPaymentMethodSummary = refreshMixedSummary;
        global.collectCheckoutPaymentMethodErrors = collectCheckoutPaymentMethodErrors;
        global.getCheckoutPaymentMethodSummary = getCheckoutPaymentMethodSummary;
        toggleMixedPanel();
    }

    global.initCheckoutPaymentMethod = initCheckoutPaymentMethod;
})(window);
