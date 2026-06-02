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

        function refreshPickerOptions() {
            if (!picker) {
                return;
            }
            const added = getAddedIds();
            Array.from(picker.options).forEach(function (opt) {
                if (!opt.value) {
                    opt.disabled = false;
                    return;
                }
                opt.disabled = added.indexOf(opt.value) !== -1;
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
            const planSelect = document.getElementById('plan_id');
            return planSelect && planSelect.value;
        }

        function hasProductsSelected() {
            const totals = getProductsTotals();
            return totals.usd > 0;
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

            if (confirmBtn) {
                const canSubmit = (hasPlanSelected() || hasProductsSelected()) && tasaDia > 0 && !isNaN(tasaDia);
                confirmBtn.disabled = !canSubmit;
            }
        }

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
            info.appendChild(nameEl);
            info.appendChild(metaEl);

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

            const removeBtn = document.createElement('button');
            removeBtn.type = 'button';
            removeBtn.className = 'btn btn-secondary checkout-product-line-remove';
            removeBtn.textContent = 'Quitar';

            line.appendChild(hidden);
            line.appendChild(info);
            line.appendChild(qtyLabel);
            line.appendChild(removeBtn);

            qtyInput.addEventListener('input', refreshSummary);
            removeBtn.addEventListener('click', function () {
                line.remove();
                refreshPickerOptions();
                refreshSummary();
            });

            return line;
        }

        function addProductFromPicker() {
            if (!picker || !picker.value) {
                return;
            }
            const item = catalogById(picker.value);
            if (!item) {
                return;
            }
            const qty = Math.max(1, parseInt(pickerQty && pickerQty.value, 10) || 1);
            if (linesContainer.querySelector('[data-item-id="' + item.id + '"]')) {
                return;
            }
            linesContainer.appendChild(buildLineElement(item, qty));
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

        refreshPickerOptions();
        refreshSummary();
    };
})();
