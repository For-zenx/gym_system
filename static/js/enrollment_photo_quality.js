(function (global) {
    'use strict';

    var GRADES = ['no_face', 'risky', 'acceptable', 'good', 'excellent'];

    var STATUS_MESSAGES = {
        acceptable: 'Foto aceptable — puede continuar; si hay tiempo, tome otra.',
        good: 'Foto buena — puede continuar.',
        excellent: 'Foto excelente — puede continuar.',
        risky: 'Foto riesgosa — se recomienda tomar otra.',
    };

    var STATUS_CLASS = {
        acceptable: 'acceptable',
        good: 'accepted',
        excellent: 'accepted',
        risky: 'risky',
        no_face: 'rejected',
        verifying: 'verifying',
        pending: 'pending',
    };

    function setStatusEl(statusEl, state, message) {
        if (!statusEl) {
            return;
        }
        statusEl.className = 'enrollment-terms-status enrollment-terms-status--' + (STATUS_CLASS[state] || state);
        statusEl.textContent = message;
    }

    function ensureFloatingTooltip() {
        var tooltip = document.getElementById('enrollment-quality-tooltip');
        if (!tooltip) {
            tooltip = document.createElement('div');
            tooltip.id = 'enrollment-quality-tooltip';
            tooltip.className = 'enrollment-quality-bar__tooltip-floating';
            tooltip.setAttribute('role', 'tooltip');
            tooltip.hidden = true;
        }
        if (tooltip.parentElement !== document.body) {
            document.body.appendChild(tooltip);
        }
        return tooltip;
    }

    function initQualityBarTooltips(root) {
        if (!root || root.dataset.tooltipsInit === '1') {
            return;
        }
        root.dataset.tooltipsInit = '1';

        var tooltip = ensureFloatingTooltip();
        var segments = root.querySelectorAll('.enrollment-quality-bar__segment');

        function hideTooltip() {
            tooltip.hidden = true;
        }

        function showTooltipFor(segment) {
            var message = segment.getAttribute('data-tooltip') || '';
            if (!message) {
                hideTooltip();
                return;
            }
            tooltip.textContent = message;
            tooltip.hidden = false;
            tooltip.style.left = (segment.getBoundingClientRect().left + segment.offsetWidth / 2) + 'px';
            tooltip.style.top = (segment.getBoundingClientRect().bottom + 8) + 'px';
        }

        segments.forEach(function (segment) {
            segment.addEventListener('mouseenter', function () {
                showTooltipFor(segment);
            });
            segment.addEventListener('mouseleave', hideTooltip);
            segment.addEventListener('focus', function () {
                showTooltipFor(segment);
            });
            segment.addEventListener('blur', hideTooltip);
        });

        global.addEventListener('scroll', hideTooltip, true);
        global.addEventListener('resize', hideTooltip);
    }

    function createQualityBar(root) {
        if (!root) {
            return {
                setIdle: function () {},
                setVerifying: function () {},
                setGrade: function () {},
            };
        }

        initQualityBarTooltips(root);

        var segments = root.querySelectorAll('.enrollment-quality-bar__segment');

        function clearActive() {
            root.classList.remove(
                'enrollment-quality-bar--verifying',
                'enrollment-quality-bar--active'
            );
            segments.forEach(function (segment) {
                segment.classList.remove('is-active');
            });
        }

        return {
            setIdle: function () {
                clearActive();
                root.classList.add('enrollment-quality-bar--idle');
            },
            setVerifying: function () {
                clearActive();
                root.classList.remove('enrollment-quality-bar--idle');
                root.classList.add('enrollment-quality-bar--verifying');
            },
            setGrade: function (grade) {
                clearActive();
                root.classList.remove('enrollment-quality-bar--idle');
                root.classList.add('enrollment-quality-bar--active');
                if (grade && GRADES.indexOf(grade) !== -1) {
                    var active = root.querySelector('[data-grade="' + grade + '"]');
                    if (active) {
                        active.classList.add('is-active');
                    }
                }
            },
        };
    }

    function createRiskyModal(modalRoot) {
        var countdownEl = modalRoot ? modalRoot.querySelector('#enrollment-risky-countdown') : null;
        var continueBtn = modalRoot ? modalRoot.querySelector('#enrollment-risky-continue') : null;
        var cancelBtn = modalRoot ? modalRoot.querySelector('#enrollment-risky-cancel') : null;
        var timerId = null;
        var onContinueCallback = null;

        function clearTimer() {
            if (timerId !== null) {
                global.clearTimeout(timerId);
                timerId = null;
            }
        }

        function closeModal() {
            clearTimer();
            if (!modalRoot) {
                return;
            }
            modalRoot.classList.remove('show');
            modalRoot.setAttribute('aria-hidden', 'true');
            if (continueBtn) {
                continueBtn.disabled = true;
            }
            onContinueCallback = null;
        }

        function openModal(onContinue) {
            if (!modalRoot) {
                if (typeof onContinue === 'function') {
                    onContinue();
                }
                return;
            }

            clearTimer();
            onContinueCallback = onContinue;
            modalRoot.classList.add('show');
            modalRoot.setAttribute('aria-hidden', 'false');
            if (continueBtn) {
                continueBtn.disabled = true;
            }

            var remaining = 10;
            function tick() {
                if (countdownEl) {
                    countdownEl.innerHTML = remaining > 0
                        ? 'Espere <strong>' + remaining + '</strong> segundos para poder continuar…'
                        : 'Ya puede continuar con esta foto si lo desea.';
                }
                if (remaining <= 0) {
                    if (continueBtn) {
                        continueBtn.disabled = false;
                    }
                    timerId = null;
                    return;
                }
                remaining -= 1;
                timerId = global.setTimeout(tick, 1000);
            }
            tick();
        }

        if (cancelBtn) {
            cancelBtn.addEventListener('click', closeModal);
        }
        if (continueBtn) {
            continueBtn.addEventListener('click', function () {
                if (continueBtn.disabled) {
                    return;
                }
                var callback = onContinueCallback;
                closeModal();
                if (typeof callback === 'function') {
                    callback();
                }
            });
        }
        if (modalRoot && global.bindDismissibleModal) {
            global.bindDismissibleModal(modalRoot, {
                onClose: closeModal,
                canClose: function () {
                    return true;
                },
            });
        }

        return {
            open: openModal,
            close: closeModal,
        };
    }

    function createGate(options) {
        options = options || {};
        var statusEl = options.statusEl || null;
        var validateUrl = options.validateUrl || '';
        var getCsrfToken = options.getCsrfToken || function () { return ''; };
        var idleMessage = options.idleMessage || 'Esperando foto en la tablet';
        var onStateChange = options.onStateChange || function () {};

        var qualityBar = createQualityBar(options.barRoot);
        var riskyModal = createRiskyModal(options.riskyModalRoot);

        var state = {
            ready: false,
            rejected: false,
            verifying: false,
            grade: null,
            requiresOverride: false,
            overrideGranted: false,
            rejectMessage: '',
        };

        var photoValidateAbort = null;

        function notify() {
            onStateChange(Object.assign({}, state));
        }

        function abortValidation() {
            if (photoValidateAbort) {
                photoValidateAbort.abort();
                photoValidateAbort = null;
            }
        }

        function resetIdle(message) {
            abortValidation();
            state.ready = false;
            state.rejected = false;
            state.verifying = false;
            state.grade = null;
            state.requiresOverride = false;
            state.overrideGranted = false;
            state.rejectMessage = '';
            qualityBar.setIdle();
            setStatusEl(statusEl, 'pending', message || idleMessage);
            notify();
        }

        function applyRejected(message, grade) {
            state.ready = false;
            state.rejected = true;
            state.verifying = false;
            state.grade = grade || 'no_face';
            state.requiresOverride = false;
            state.overrideGranted = false;
            state.rejectMessage = message
                || 'La foto no es válida: no se detectó una cara usable. Use Tomar otra foto.';
            qualityBar.setGrade(state.grade);
            setStatusEl(statusEl, 'no_face', state.rejectMessage);
            notify();
        }

        function applyAccepted(data) {
            var grade = data.grade || 'good';
            state.ready = true;
            state.rejected = false;
            state.verifying = false;
            state.grade = grade;
            state.requiresOverride = !!data.requires_override;
            state.overrideGranted = false;
            state.rejectMessage = '';
            qualityBar.setGrade(grade);
            setStatusEl(statusEl, grade, STATUS_MESSAGES[grade] || 'Foto lista');
            notify();
        }

        function validate(imageDataUrl) {
            abortValidation();
            state.ready = false;
            state.rejected = false;
            state.verifying = true;
            state.grade = null;
            state.requiresOverride = false;
            state.overrideGranted = false;
            state.rejectMessage = '';
            qualityBar.setVerifying();
            setStatusEl(statusEl, 'verifying', 'Analizando foto facial…');
            notify();

            if (!validateUrl) {
                applyRejected('No se pudo verificar la foto con el servidor. Use Tomar otra foto.');
                return;
            }

            var controller = new AbortController();
            photoValidateAbort = controller;
            var formData = new FormData();
            formData.append('csrfmiddlewaretoken', getCsrfToken());
            formData.append('foto_frente_base64', imageDataUrl);

            global.fetch(validateUrl, {
                method: 'POST',
                body: formData,
                credentials: 'same-origin',
                signal: controller.signal,
            })
                .then(function (response) {
                    return response.json().then(function (data) {
                        return { ok: response.ok, data: data };
                    });
                })
                .then(function (result) {
                    if (photoValidateAbort !== controller) {
                        return;
                    }
                    photoValidateAbort = null;

                    if (result.ok && result.data.status === 'ok') {
                        applyAccepted(result.data);
                        return;
                    }

                    var message = result.data && result.data.message
                        ? ('La foto no es válida. ' + result.data.message + ' Use Tomar otra foto.')
                        : null;
                    applyRejected(message, (result.data && result.data.grade) || 'no_face');
                })
                .catch(function (err) {
                    if (err && err.name === 'AbortError') {
                        return;
                    }
                    if (photoValidateAbort !== controller) {
                        return;
                    }
                    photoValidateAbort = null;
                    applyRejected('No se pudo verificar la foto con el servidor. Use Tomar otra foto.');
                });
        }

        return {
            resetIdle: resetIdle,
            validate: validate,
            getState: function () {
                return Object.assign({}, state);
            },
            grantRiskyOverride: function () {
                state.overrideGranted = true;
                notify();
            },
            needsRiskyConfirmation: function () {
                return state.ready && state.requiresOverride && !state.overrideGranted;
            },
            confirmRiskyIfNeeded: function (onConfirmed) {
                if (!state.ready) {
                    return false;
                }
                if (state.rejected) {
                    return false;
                }
                if (!state.requiresOverride || state.overrideGranted) {
                    return true;
                }
                riskyModal.open(function () {
                    state.overrideGranted = true;
                    notify();
                    if (typeof onConfirmed === 'function') {
                        onConfirmed();
                    }
                });
                return false;
            },
        };
    }

    global.EnrollmentPhotoQuality = {
        createGate: createGate,
        STATUS_MESSAGES: STATUS_MESSAGES,
    };

    document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.enrollment-quality-bar').forEach(initQualityBarTooltips);
    });
}(window));
