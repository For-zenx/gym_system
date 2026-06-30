(function (global) {
    function collectClassCheckoutErrors(tasaDia) {
        const errors = [];
        if (tasaDia <= 0 || isNaN(tasaDia)) {
            errors.push('No hay tasa de cambio configurada. Configure la tasa antes de cobrar.');
        }
        if (typeof global.collectCheckoutPaymentMethodErrors === 'function') {
            global.collectCheckoutPaymentMethodErrors().forEach(function (message) {
                if (
                    message.indexOf('membresía') === -1 &&
                    message.indexOf('productos') === -1
                ) {
                    errors.push(message);
                }
            });
        }
        return errors;
    }

    function initClassCheckout(config) {
        const tasaDia = config && config.tasaDia ? config.tasaDia : 0;
        const form = document.getElementById('class-checkout-form');
        const submitBtn = document.getElementById('class-checkout-submit');

        if (typeof global.initCheckoutPaymentMethod === 'function') {
            global.initCheckoutPaymentMethod({ tasaDia: tasaDia });
        }

        function refreshSubmit() {
            if (!submitBtn) {
                return;
            }
            submitBtn.disabled = collectClassCheckoutErrors(tasaDia).length > 0;
        }

        global.checkoutRefreshSubmit = refreshSubmit;
        refreshSubmit();

        if (!form) {
            return;
        }

        form.addEventListener('submit', function (event) {
            const errors = collectClassCheckoutErrors(tasaDia);
            if (errors.length) {
                event.preventDefault();
                if (typeof global.showCheckoutErrorsModal === 'function') {
                    global.showCheckoutErrorsModal(errors);
                }
            }
        });

        if (typeof global.bindDismissibleModalById === 'function') {
            global.bindDismissibleModalById('checkoutErrorsModal', {
                onClose: global.closeCheckoutErrorsModal,
            });
        }

        if (tasaDia <= 0 || isNaN(tasaDia)) {
            if (typeof global.showCheckoutErrorsModal === 'function') {
                global.showCheckoutErrorsModal(collectClassCheckoutErrors(tasaDia));
            }
        }
    }

    global.initClassCheckout = initClassCheckout;
    global.collectClassCheckoutErrors = collectClassCheckoutErrors;
})(window);
