(function (global) {
    function showCheckoutErrorsModal(errors) {
        const modal = document.getElementById('checkoutErrorsModal');
        const list = document.getElementById('checkout-errors-list');
        if (!modal || !list || !errors.length) {
            return;
        }
        list.innerHTML = '';
        errors.forEach(function (message) {
            const item = document.createElement('li');
            item.textContent = message;
            list.appendChild(item);
        });
        modal.classList.add('show');
    }

    function closeCheckoutErrorsModal() {
        const modal = document.getElementById('checkoutErrorsModal');
        if (modal) {
            modal.classList.remove('show');
        }
    }

    function collectCheckoutErrors(tasaDia) {
        const errors = [];
        if (tasaDia <= 0 || isNaN(tasaDia)) {
            errors.push('No hay tasa de cambio configurada para hoy. Configure la tasa antes de cobrar.');
        }
        if (typeof global.collectCheckoutProductErrors === 'function') {
            global.collectCheckoutProductErrors().forEach(function (message) {
                errors.push(message);
            });
        }
        if (typeof global.collectCheckoutPaymentErrors === 'function') {
            global.collectCheckoutPaymentErrors().forEach(function (message) {
                errors.push(message);
            });
        }
        if (typeof global.collectCheckoutPaymentMethodErrors === 'function') {
            global.collectCheckoutPaymentMethodErrors().forEach(function (message) {
                errors.push(message);
            });
        }
        return errors;
    }

    function bindCheckoutFormValidation(form, tasaDia) {
        if (!form) {
            return;
        }
        form.addEventListener('submit', function (event) {
            const errors = collectCheckoutErrors(tasaDia);
            if (errors.length) {
                event.preventDefault();
                showCheckoutErrorsModal(errors);
            }
        });
    }

    global.showCheckoutErrorsModal = showCheckoutErrorsModal;
    global.closeCheckoutErrorsModal = closeCheckoutErrorsModal;
    global.collectCheckoutErrors = collectCheckoutErrors;
    global.bindCheckoutFormValidation = bindCheckoutFormValidation;
})(window);
