(function () {
    function formatVes(amount) {
        return 'Bs ' + amount.toLocaleString('es-VE', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    }

    function setDualSubtotal(usdEl, vesEl, usd, ves) {
        if (usdEl) {
            usdEl.textContent = window.formatUsd(usd);
        }
        if (vesEl) {
            vesEl.textContent = formatVes(ves);
        }
    }

    window.initCheckoutProducts = function (config) {
        const tasaDia = config.tasaDia;
        const catalog = config.catalog || [];
        const availableLockers = config.availableLockers || [];
        const planPreviews = config.planPreviews || {};
        const confirmBtn = document.getElementById(config.confirmId || 'btnConfirm');
        const linesContainer = document.getElementById(config.linesContainerId || 'checkout-product-lines');
        const picker = document.getElementById(config.pickerId || 'checkout-product-picker');
        const pickerQty = document.getElementById(config.pickerQtyId || 'checkout-product-picker-qty');
        const addBtn = document.getElementById(config.addBtnId || 'checkout-product-add-btn');
        const productsOnlyNotice = document.getElementById(config.productsOnlyNoticeId);

        const membershipUsdEl = document.getElementById(config.membershipSubtotalUsdId);
        const membershipVesEl = document.getElementById(config.membershipSubtotalId);
        const productsUsdEl = document.getElementById(config.productsSubtotalUsdId);
        const productsVesEl = document.getElementById(config.productsSubtotalId);
        const lateFeeUsdEl = document.getElementById(config.lateFeeSubtotalUsdId);
        const lateFeeVesEl = document.getElementById(config.lateFeeSubtotalId);
        const totalUsdEl = document.getElementById(config.grandTotalUsdId);
        const totalVesEl = document.getElementById(config.grandTotalId);

        let membershipSubtotalVes = 0;
        let membershipSubtotalUsd = 0;
        let lateFeeSubtotalVes = 0;
        let lateFeeSubtotalUsd = 0;

        function catalogById(id) {
            return catalog.find(function (item) {
                return String(item.id) === String(id);
            });
        }

        function getSelectedPlanId() {
            const planSelect = document.getElementById('plan_id');
            return planSelect && planSelect.value ? planSelect.value : '';
        }

        function getSelectedPlanPreview() {
            const planId = getSelectedPlanId();
            if (!planId) {
                return null;
            }
            return planPreviews[planId] || null;
        }

        function getAddedIds() {
            const ids = [];
            if (!linesContainer) {
                return ids;
            }
            linesContainer.querySelectorAll('.checkout-product-line').forEach(function (line) {
                ids.push(line.getAttribute('data-item-id'));
            });
            return ids;
        }

        function isSingleUnitItem(item) {
            return item && (item.item_type === 'SERVICE' || item.requires_locker_assignment);
        }

        function refreshPickerQtyVisibility() {
            if (!picker || !pickerQty) {
                return;
            }
            const qtyField = pickerQty.closest('.checkout-product-field--qty');
            if (!qtyField) {
                return;
            }
            const item = picker.value ? catalogById(picker.value) : null;
            qtyField.style.display = isSingleUnitItem(item) ? 'none' : '';
            if (isSingleUnitItem(item)) {
                pickerQty.value = '1';
            }
        }

        function isServiceItem(item) {
            return item && item.item_type === 'SERVICE';
        }

        function refreshPickerOptions() {
            if (!picker) {
                return;
            }
            const added = getAddedIds();
            const hasPlan = !!getSelectedPlanId();
            Array.from(picker.options).forEach(function (opt) {
                if (!opt.value) {
                    opt.disabled = false;
                    return;
                }
                const item = catalogById(opt.value);
                const isService = item && isServiceItem(item);
                opt.disabled = added.indexOf(opt.value) !== -1 || (isService && !hasPlan);
            });
            if (picker.value && picker.options[picker.selectedIndex].disabled) {
                picker.value = '';
            }
        }

        function getProductsTotals() {
            let usd = 0;
            let ves = 0;
            if (!linesContainer) {
                return { usd: 0, ves: 0 };
            }
            linesContainer.querySelectorAll('.checkout-product-line').forEach(function (line) {
                const itemId = line.getAttribute('data-item-id');
                const item = catalogById(itemId);
                if (!item) {
                    return;
                }
                const qtyInput = line.querySelector('.checkout-product-line-qty');
                const qty = parseInt(qtyInput && qtyInput.value, 10) || 0;
                const priceUsd = window.parseUsdAmount(item.price_usd);
                if (qty > 0) {
                    usd += priceUsd * qty;
                    ves += priceUsd * tasaDia * qty;
                }
            });
            return { usd: usd, ves: ves };
        }

        function hasPlanSelected() {
            return !!getSelectedPlanId();
        }

        function hasProductsSelected() {
            const totals = getProductsTotals();
            return totals.usd > 0;
        }

        function hasServiceLinesSelected() {
            if (!linesContainer) {
                return false;
            }
            let found = false;
            linesContainer.querySelectorAll('.checkout-product-line').forEach(function (line) {
                if (line.getAttribute('data-requires-plan') === '1') {
                    found = true;
                }
            });
            return found;
        }

        function areLockerLinesValid() {
            if (!linesContainer) {
                return true;
            }
            let valid = true;
            linesContainer.querySelectorAll('.checkout-product-line').forEach(function (line) {
                if (line.getAttribute('data-requires-locker') !== '1') {
                    return;
                }
                const locker = line.querySelector('.checkout-locker-select');
                if (!locker || !locker.value) {
                    valid = false;
                }
            });
            return valid;
        }

        function updateLockerPeriodFields() {
            if (!linesContainer) {
                return;
            }
            const preview = getSelectedPlanPreview();
            linesContainer.querySelectorAll('.checkout-product-line[data-requires-locker="1"]').forEach(function (line) {
                const startInput = line.querySelector('.checkout-locker-start');
                const endInput = line.querySelector('.checkout-locker-end');
                const periodText = line.querySelector('.checkout-locker-period-text');
                if (preview && preview.fecha_inicio_iso && preview.fecha_fin_iso) {
                    if (startInput) {
                        startInput.value = preview.fecha_inicio_iso;
                    }
                    if (endInput) {
                        endInput.value = preview.fecha_fin_iso;
                    }
                    if (periodText) {
                        periodText.textContent = preview.inicio + ' al ' + preview.fin;
                    }
                } else if (periodText) {
                    periodText.textContent = 'Seleccione un plan para ver el periodo';
                }
            });
        }

        function refreshSummary() {
            const productTotals = getProductsTotals();
            setDualSubtotal(membershipUsdEl, membershipVesEl, membershipSubtotalUsd, membershipSubtotalVes);
            setDualSubtotal(productsUsdEl, productsVesEl, productTotals.usd, productTotals.ves);
            setDualSubtotal(lateFeeUsdEl, lateFeeVesEl, lateFeeSubtotalUsd, lateFeeSubtotalVes);

            const grandUsd = membershipSubtotalUsd + productTotals.usd + lateFeeSubtotalUsd;
            const grandVes = membershipSubtotalVes + productTotals.ves + lateFeeSubtotalVes;
            setDualSubtotal(totalUsdEl, totalVesEl, grandUsd, grandVes);

            const productsOnly = !hasPlanSelected() && hasProductsSelected();
            if (productsOnlyNotice) {
                productsOnlyNotice.style.display = productsOnly ? 'block' : 'none';
            }

            refreshPickerOptions();
            updateLockerPeriodFields();
            refreshPickerQtyVisibility();

            if (confirmBtn) {
                confirmBtn.disabled = false;
            }
            if (window.checkoutRefreshPaymentMethodSummary) {
                window.checkoutRefreshPaymentMethodSummary();
            }
        }

        window.collectCheckoutProductErrors = function () {
            const errors = [];
            const originInput = document.querySelector('#checkoutForm input[name="origin"]');
            const isEnrollment = originInput && originInput.value === 'enrollment';

            if (!hasPlanSelected() && !hasProductsSelected()) {
                errors.push('Seleccione una membresía y/o al menos un producto para cobrar.');
            } else if (isEnrollment && !hasPlanSelected()) {
                errors.push('El cobro inicial del enrolamiento requiere seleccionar un plan de membresía.');
            }
            if (hasServiceLinesSelected() && !hasPlanSelected()) {
                errors.push('Los servicios ligados al plan requieren una membresía en el mismo cobro.');
            }
            if (!areLockerLinesValid()) {
                errors.push('Seleccione un casillero para cada línea de alquiler de casillero.');
            }
            return errors;
        };

        window.checkoutSetMembershipTotals = function (membershipVes, lateFeeVes, membershipUsd, lateFeeUsd) {
            membershipSubtotalVes = membershipVes || 0;
            lateFeeSubtotalVes = lateFeeVes || 0;
            membershipSubtotalUsd = membershipUsd != null ? membershipUsd : (tasaDia > 0 ? membershipSubtotalVes / tasaDia : 0);
            lateFeeSubtotalUsd = lateFeeUsd != null ? lateFeeUsd : (tasaDia > 0 ? lateFeeSubtotalVes / tasaDia : 0);
            refreshSummary();
        };

        window.checkoutRefreshSubmit = refreshSummary;

        function buildLineElement(item, qty) {
            const line = document.createElement('div');
            line.className = 'checkout-product-line';
            line.setAttribute('data-item-id', String(item.id));
            if (item.requires_locker_assignment) {
                line.setAttribute('data-requires-locker', '1');
            }
            if (isServiceItem(item)) {
                line.setAttribute('data-requires-plan', '1');
            }

            const priceUsd = window.parseUsdAmount(item.price_usd);
            const typeLabel = item.item_type === 'SERVICE' ? 'Servicio' : 'Producto';

            const hidden = document.createElement('input');
            hidden.type = 'hidden';
            hidden.name = 'product_ids';
            hidden.value = String(item.id);

            const info = document.createElement('div');
            info.className = 'checkout-product-line-info';
            const nameEl = document.createElement('span');
            nameEl.className = 'checkout-product-line-name';
            nameEl.textContent = item.name;
            const metaEl = document.createElement('span');
            metaEl.className = 'checkout-product-line-meta';
            metaEl.textContent = typeLabel + ' · ' + window.formatUsd(priceUsd) + ' c/u';
            if (item.requires_locker_assignment) {
                metaEl.textContent += ' · requiere casillero';
            }
            if (isServiceItem(item)) {
                metaEl.textContent += ' · ligado al plan';
            }
            info.appendChild(nameEl);
            info.appendChild(metaEl);

            line.appendChild(hidden);
            line.appendChild(info);

            if (isSingleUnitItem(item)) {
                const qtyHidden = document.createElement('input');
                qtyHidden.type = 'hidden';
                qtyHidden.className = 'checkout-product-line-qty';
                qtyHidden.name = 'product_qty_' + item.id;
                qtyHidden.value = '1';
                line.appendChild(qtyHidden);
            } else {
                const qtyLabel = document.createElement('label');
                qtyLabel.className = 'checkout-product-line-qty-label';
                qtyLabel.appendChild(document.createTextNode('Cant.'));
                const qtyInput = document.createElement('input');
                qtyInput.type = 'number';
                qtyInput.className = 'checkout-product-line-qty form-control';
                qtyInput.name = 'product_qty_' + item.id;
                qtyInput.min = '1';
                qtyInput.value = String(qty);
                qtyLabel.appendChild(qtyInput);
                line.appendChild(qtyLabel);
                qtyInput.addEventListener('input', refreshSummary);
            }

            const lockerFields = buildLockerFields(item);
            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'btn btn-secondary checkout-product-line-remove';
            removeBtn.textContent = 'Quitar';

            if (lockerFields) {
                line.classList.add('checkout-product-line--locker');
                line.appendChild(lockerFields);
            }
            line.appendChild(removeBtn);

            removeBtn.addEventListener('click', function () {
                line.remove();
                refreshPickerOptions();
                refreshSummary();
            });

            return line;
        }

        function buildLockerFields(item) {
            if (!item.requires_locker_assignment) {
                return null;
            }

            const wrap = document.createElement('div');
            wrap.className = 'checkout-locker-fields';

            const lockerLabel = document.createElement('label');
            lockerLabel.className = 'checkout-locker-field checkout-locker-field--locker';
            lockerLabel.appendChild(document.createTextNode('Casillero'));
            const lockerSelect = document.createElement('select');
            lockerSelect.className = 'checkout-locker-select form-control';
            lockerSelect.name = 'locker_id_' + item.id;

            const emptyOpt = document.createElement('option');
            emptyOpt.value = '';
            emptyOpt.textContent = availableLockers.length ? 'Seleccione casillero' : 'No hay casilleros disponibles';
            lockerSelect.appendChild(emptyOpt);
            availableLockers.forEach(function (locker) {
                const opt = document.createElement('option');
                opt.value = String(locker.id);
                opt.textContent = 'Casillero ' + locker.number;
                lockerSelect.appendChild(opt);
            });
            lockerLabel.appendChild(lockerSelect);

            const periodLabel = document.createElement('div');
            periodLabel.className = 'checkout-locker-field checkout-locker-period';
            periodLabel.appendChild(document.createTextNode('Periodo del plan: '));
            const periodText = document.createElement('span');
            periodText.className = 'checkout-locker-period-text';
            periodText.textContent = 'Seleccione un plan para ver el periodo';
            periodLabel.appendChild(periodText);

            const startInput = document.createElement('input');
            startInput.type = 'hidden';
            startInput.className = 'checkout-locker-start';
            startInput.name = 'locker_start_' + item.id;

            const endInput = document.createElement('input');
            endInput.type = 'hidden';
            endInput.className = 'checkout-locker-end';
            endInput.name = 'locker_end_' + item.id;

            wrap.appendChild(lockerLabel);
            wrap.appendChild(periodLabel);
            wrap.appendChild(startInput);
            wrap.appendChild(endInput);

            lockerSelect.addEventListener('change', refreshSummary);
            return wrap;
        }

        function addProductFromPicker() {
            if (!picker || !picker.value) {
                return;
            }
            const item = catalogById(picker.value);
            if (!item) {
                return;
            }
            if (isServiceItem(item) && !hasPlanSelected()) {
                alert('Los servicios requieren seleccionar un plan de membresía.');
                return;
            }
            if (item.requires_locker_assignment && !availableLockers.length) {
                alert('No hay casilleros disponibles para asignar.');
                return;
            }
            const qty = Math.max(1, parseInt(pickerQty && pickerQty.value, 10) || 1);
            if (linesContainer.querySelector('[data-item-id="' + item.id + '"]')) {
                return;
            }
            const lineQty = isSingleUnitItem(item) ? 1 : qty;
            linesContainer.appendChild(buildLineElement(item, lineQty));
            picker.value = '';
            if (pickerQty) {
                pickerQty.value = '1';
            }
            refreshPickerOptions();
            refreshSummary();
        }

        if (addBtn) {
            addBtn.addEventListener('click', addProductFromPicker);
        }

        if (picker) {
            picker.addEventListener('change', refreshPickerQtyVisibility);
        }

        const planSelect = document.getElementById('plan_id');
        if (planSelect) {
            planSelect.addEventListener('change', refreshSummary);
        }

        refreshPickerOptions();
        refreshSummary();
    };
})();
