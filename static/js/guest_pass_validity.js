(function () {
    'use strict';

    function formatGuestDate(isoDate) {
        if (!isoDate) {
            return '';
        }
        var parts = isoDate.split('-');
        if (parts.length !== 3) {
            return isoDate;
        }
        return parts[2] + '/' + parts[1] + '/' + parts[0];
    }

    function todayIsoDate() {
        return new Date().toISOString().slice(0, 10);
    }

    window.initGuestPassValidity = function (options) {
        options = options || {};
        var canCustom = !!options.canCustom;

        var validFromInput = document.getElementById('valid_from');
        var validUntilInput = document.getElementById('valid_until');
        var validityText = document.getElementById('guest-pass-validity-text');
        var presetsContainer = document.getElementById('guest-pass-presets');
        var customToggle = document.getElementById('guest_pass_custom_toggle');
        var customUntilInput = document.getElementById('custom_valid_until');

        if (!validFromInput || !validUntilInput || !validityText) {
            return;
        }

        function updateValidityText() {
            validityText.textContent = 'Válido desde ' + formatGuestDate(validFromInput.value) +
                ' hasta ' + formatGuestDate(validUntilInput.value);
        }

        function setPresetsDisabled(disabled) {
            if (!presetsContainer) {
                return;
            }
            presetsContainer.classList.toggle('is-disabled', disabled);
            presetsContainer.querySelectorAll('.guest-pass-preset').forEach(function (btn) {
                btn.disabled = disabled;
            });
        }

        function setCustomBlockActive(active) {
            var customBlock = document.getElementById('guest-pass-custom-block');
            if (customBlock) {
                customBlock.classList.toggle('is-active', active);
            }
            if (customUntilInput) {
                customUntilInput.disabled = !active;
            }
        }

        function clearPresetSelection() {
            document.querySelectorAll('.guest-pass-preset').forEach(function (btn) {
                btn.classList.remove('is-active');
            });
        }

        function applyPreset(days, button) {
            var from = new Date();
            var until = new Date(from);
            until.setDate(until.getDate() + parseInt(days, 10));
            validFromInput.value = from.toISOString().slice(0, 10);
            validUntilInput.value = until.toISOString().slice(0, 10);
            document.querySelectorAll('.guest-pass-preset').forEach(function (btn) {
                btn.classList.toggle('is-active', btn === button);
            });
            updateValidityText();
        }

        function applyCustomUntil(isoDate) {
            validFromInput.value = todayIsoDate();
            validUntilInput.value = isoDate;
            updateValidityText();
        }

        function syncCustomMode() {
            var customActive = canCustom && customToggle && customToggle.checked;
            setPresetsDisabled(customActive);
            setCustomBlockActive(customActive);
            if (customActive && customUntilInput && customUntilInput.value) {
                clearPresetSelection();
                applyCustomUntil(customUntilInput.value);
            } else if (!customActive) {
                var activePreset = document.querySelector('.guest-pass-preset.is-active');
                if (activePreset) {
                    applyPreset(activePreset.getAttribute('data-days'), activePreset);
                } else {
                    var firstPreset = document.querySelector('.guest-pass-preset');
                    if (firstPreset) {
                        applyPreset(firstPreset.getAttribute('data-days'), firstPreset);
                    }
                }
            }
        }

        document.querySelectorAll('.guest-pass-preset').forEach(function (btn) {
            btn.addEventListener('click', function () {
                if (customToggle && customToggle.checked) {
                    return;
                }
                if (customToggle) {
                    customToggle.checked = false;
                }
                setCustomBlockActive(false);
                applyPreset(btn.getAttribute('data-days'), btn);
            });
        });

        if (canCustom && customToggle) {
            customToggle.addEventListener('change', function () {
                syncCustomMode();
            });
        }

        if (canCustom && customUntilInput) {
            customUntilInput.min = todayIsoDate();
            customUntilInput.addEventListener('change', function () {
                if (!customToggle || !customToggle.checked || !customUntilInput.value) {
                    return;
                }
                clearPresetSelection();
                applyCustomUntil(customUntilInput.value);
            });
        }

        if (!validFromInput.value) {
            validFromInput.value = todayIsoDate();
        }
        if (!validUntilInput.value) {
            var defaultUntil = new Date();
            defaultUntil.setDate(defaultUntil.getDate() + 1);
            validUntilInput.value = defaultUntil.toISOString().slice(0, 10);
        }
        if (canCustom && customUntilInput && !customUntilInput.value) {
            customUntilInput.value = validUntilInput.value;
        }

        syncCustomMode();
        updateValidityText();
    };
})();
