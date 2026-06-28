(function (global) {
    function textOrDash(value) {
        return value && String(value).trim() ? String(value).trim() : '—';
    }

    function isElementVisible(el) {
        if (!el || el.hidden) {
            return false;
        }
        const style = window.getComputedStyle(el);
        return style.display !== 'none' && style.visibility !== 'hidden';
    }

    function getPlanSelection() {
        const planSelect = document.getElementById('plan_id');
        if (!planSelect || !planSelect.value) {
            return null;
        }
        const option = planSelect.options[planSelect.selectedIndex];
        return {
            id: planSelect.value,
            label: option ? option.textContent.trim() : '',
        };
    }

    function getProductLines() {
        const lines = [];
        const container = document.getElementById('checkout-product-lines');
        if (!container) {
            return lines;
        }

        container.querySelectorAll('.checkout-product-line').forEach(function (line) {
            const nameEl = line.querySelector('.checkout-product-line-name');
            const qtyInput = line.querySelector('.checkout-product-line-qty');
            const lockerSelect = line.querySelector('.checkout-locker-select');
            const qty = qtyInput ? parseInt(qtyInput.value, 10) || 1 : 1;
            const entry = {
                name: nameEl ? nameEl.textContent.trim() : 'Producto',
                qty: qty,
            };
            if (lockerSelect && lockerSelect.value) {
                const lockerOption = lockerSelect.options[lockerSelect.selectedIndex];
                entry.locker = lockerOption ? lockerOption.textContent.trim() : lockerSelect.value;
            }
            lines.push(entry);
        });
        return lines;
    }

    function getLateFeeInfo(tasaDia) {
        const checkbox = document.getElementById('apply_late_fee');
        const input = document.getElementById('late_fee_usd');
        if (!checkbox || !checkbox.checked || !input) {
            return null;
        }
        const usd = global.parseUsdAmount ? global.parseUsdAmount(input.value) : parseFloat(input.value) || 0;
        if (usd <= 0) {
            return null;
        }
        const ves = usd * (tasaDia || 0);
        return {
            usd: global.formatUsd ? global.formatUsd(usd) : ('$' + usd.toFixed(2)),
            ves: 'Bs ' + ves.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
        };
    }

    function readDualTotal(usdId, vesId) {
        const usdEl = document.getElementById(usdId);
        const vesEl = document.getElementById(vesId);
        const usd = usdEl ? usdEl.textContent.trim() : '$0.00';
        const ves = vesEl ? vesEl.textContent.trim() : 'Bs 0,00';
        return usd + ' · ' + ves;
    }

    function buildCheckoutConfirmSummary(tasaDia) {
        const plan = getPlanSelection();
        const periodTextEl = document.getElementById('payment-period-text');
        const periodDetailEl = document.getElementById('payment-period-detail');
        const cutDaySection = document.getElementById('payment-cut-day-section');
        const cutDayDisplay = document.getElementById('payment_cut_day_display');
        const clientNameEl = document.querySelector('.charge-checkout-client-name');
        const clientCedulaEl = document.querySelector('.charge-checkout-client-meta dd');

        return {
            clientName: clientNameEl ? clientNameEl.textContent.trim() : '',
            clientCedula: clientCedulaEl ? clientCedulaEl.textContent.trim() : '',
            plan: plan,
            periodText: periodTextEl ? periodTextEl.textContent.trim() : '',
            periodDetail: periodDetailEl ? periodDetailEl.textContent.trim() : '',
            cutDay:
                isElementVisible(cutDaySection) && cutDayDisplay
                    ? cutDayDisplay.value
                    : null,
            products: getProductLines(),
            lateFee: getLateFeeInfo(tasaDia),
            totals: {
                membership: readDualTotal('checkout-membership-subtotal-usd', 'checkout-membership-subtotal'),
                products: readDualTotal('checkout-products-subtotal-usd', 'checkout-products-subtotal'),
                lateFee: readDualTotal('checkout-latefee-subtotal-usd', 'checkout-latefee-subtotal'),
                grand: readDualTotal('checkout-grand-total-usd', 'checkout-grand-total'),
            },
        };
    }

    function setSectionVisible(section, visible) {
        if (!section) {
            return;
        }
        section.hidden = !visible;
    }

    function showCheckoutConfirmModal(summary) {
        const modal = document.getElementById('checkoutConfirmModal');
        if (!modal || !summary) {
            return;
        }

        const nameEl = document.getElementById('checkout-confirm-client-name');
        const cedulaEl = document.getElementById('checkout-confirm-client-cedula');
        if (nameEl && summary.clientName) {
            nameEl.textContent = summary.clientName;
        }
        if (cedulaEl && summary.clientCedula) {
            cedulaEl.textContent = summary.clientCedula;
        }

        const membershipSection = document.getElementById('checkout-confirm-membership-section');
        const noMembershipSection = document.getElementById('checkout-confirm-no-membership-section');
        const planEl = document.getElementById('checkout-confirm-plan');
        const periodEl = document.getElementById('checkout-confirm-period');
        const periodDetailEl = document.getElementById('checkout-confirm-period-detail');
        const cutDayEl = document.getElementById('checkout-confirm-cut-day');

        if (summary.plan) {
            setSectionVisible(membershipSection, true);
            setSectionVisible(noMembershipSection, false);
            if (planEl) {
                planEl.textContent = summary.plan.label;
            }
            if (periodEl) {
                periodEl.textContent = summary.periodText || 'Vigencia según plan seleccionado';
            }
            if (periodDetailEl) {
                periodDetailEl.textContent = summary.periodDetail || '';
                periodDetailEl.hidden = !summary.periodDetail;
            }
            if (cutDayEl) {
                if (summary.cutDay) {
                    cutDayEl.textContent = 'Día de corte: ' + summary.cutDay;
                    cutDayEl.hidden = false;
                } else {
                    cutDayEl.hidden = true;
                }
            }
        } else {
            setSectionVisible(membershipSection, false);
            setSectionVisible(noMembershipSection, true);
        }

        const productsSection = document.getElementById('checkout-confirm-products-section');
        const productsList = document.getElementById('checkout-confirm-products-list');
        if (productsList) {
            productsList.innerHTML = '';
        }
        if (summary.products.length) {
            setSectionVisible(productsSection, true);
            summary.products.forEach(function (item) {
                const li = document.createElement('li');
                let text = item.name + ' × ' + item.qty;
                if (item.locker) {
                    text += ' · Casillero ' + item.locker;
                }
                li.textContent = text;
                productsList.appendChild(li);
            });
        } else {
            setSectionVisible(productsSection, false);
        }

        const lateFeeSection = document.getElementById('checkout-confirm-latefee-section');
        const lateFeeEl = document.getElementById('checkout-confirm-latefee');
        const lateFeeTotalRow = document.getElementById('checkout-confirm-latefee-total-row');
        if (summary.lateFee) {
            setSectionVisible(lateFeeSection, true);
            if (lateFeeEl) {
                lateFeeEl.textContent = summary.lateFee.usd + ' · ' + summary.lateFee.ves;
            }
            if (lateFeeTotalRow) {
                lateFeeTotalRow.hidden = false;
            }
        } else {
            setSectionVisible(lateFeeSection, false);
            if (lateFeeTotalRow) {
                lateFeeTotalRow.hidden = true;
            }
        }

        const membershipTotalEl = document.getElementById('checkout-confirm-membership-total');
        const productsTotalEl = document.getElementById('checkout-confirm-products-total');
        const lateFeeTotalEl = document.getElementById('checkout-confirm-latefee-total');
        const grandTotalEl = document.getElementById('checkout-confirm-grand-total');

        if (membershipTotalEl) {
            membershipTotalEl.textContent = summary.totals.membership;
        }
        if (productsTotalEl) {
            productsTotalEl.textContent = summary.totals.products;
        }
        if (lateFeeTotalEl) {
            lateFeeTotalEl.textContent = summary.totals.lateFee;
        }
        if (grandTotalEl) {
            grandTotalEl.textContent = summary.totals.grand;
        }

        const paymentSection = document.getElementById('checkout-confirm-payment-section');
        const paymentLabelEl = document.getElementById('checkout-confirm-payment-label');
        const paymentSplitsList = document.getElementById('checkout-confirm-payment-splits');
        const paymentSummary =
            typeof global.getCheckoutPaymentMethodSummary === 'function'
                ? global.getCheckoutPaymentMethodSummary()
                : null;
        if (paymentSection) {
            if (paymentSummary) {
                setSectionVisible(paymentSection, true);
                if (paymentLabelEl) {
                    paymentLabelEl.textContent = paymentSummary.label;
                }
                if (paymentSplitsList) {
                    paymentSplitsList.innerHTML = '';
                    if (paymentSummary.splits.length) {
                        paymentSummary.splits.forEach(function (entry) {
                            const li = document.createElement('li');
                            li.textContent = entry.label + ' · ' + entry.amount;
                            paymentSplitsList.appendChild(li);
                        });
                        paymentSplitsList.hidden = false;
                    } else {
                        paymentSplitsList.hidden = true;
                    }
                }
            } else {
                setSectionVisible(paymentSection, false);
            }
        }

        modal.classList.add('show');
        modal.setAttribute('aria-hidden', 'false');
    }

    function closeCheckoutConfirmModal() {
        const modal = document.getElementById('checkoutConfirmModal');
        if (modal) {
            modal.classList.remove('show');
            modal.setAttribute('aria-hidden', 'true');
        }
    }

    function bindCheckoutConfirmFlow(form, btn, tasaDia) {
        const submitBtn = document.getElementById('checkout-confirm-submit-btn');
        const cancelBtn = document.getElementById('checkout-confirm-cancel-btn');

        if (btn) {
            btn.addEventListener('click', function () {
                const errors =
                    typeof global.collectCheckoutErrors === 'function'
                        ? global.collectCheckoutErrors(tasaDia)
                        : [];
                if (errors.length) {
                    if (typeof global.showCheckoutErrorsModal === 'function') {
                        global.showCheckoutErrorsModal(errors);
                    }
                    return;
                }
                showCheckoutConfirmModal(buildCheckoutConfirmSummary(tasaDia));
            });
        }

        if (cancelBtn) {
            cancelBtn.addEventListener('click', closeCheckoutConfirmModal);
        }

        if (submitBtn && form) {
            submitBtn.addEventListener('click', function () {
                const errors =
                    typeof global.collectCheckoutErrors === 'function'
                        ? global.collectCheckoutErrors(tasaDia)
                        : [];
                if (errors.length) {
                    closeCheckoutConfirmModal();
                    if (typeof global.showCheckoutErrorsModal === 'function') {
                        global.showCheckoutErrorsModal(errors);
                    }
                    return;
                }
                closeCheckoutConfirmModal();
                if (typeof form.requestSubmit === 'function') {
                    form.requestSubmit();
                } else {
                    form.submit();
                }
            });
        }
    }

    global.buildCheckoutConfirmSummary = buildCheckoutConfirmSummary;
    global.showCheckoutConfirmModal = showCheckoutConfirmModal;
    global.closeCheckoutConfirmModal = closeCheckoutConfirmModal;
    global.bindCheckoutConfirmFlow = bindCheckoutConfirmFlow;
})(window);
