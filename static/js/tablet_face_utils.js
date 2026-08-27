// tablet_face_utils.js — Detección facial compartida (tablets acceso y enrolamiento)

const TabletFaceUtils = (function () {
    const MIN_DETECTION_SCORE = 0.60;
    const STABILITY_MS = 800;
    // Enrolamiento: min 0.65 fuerza acercarse; max alto evita «Aléjese» casi al llegar al min.
    const OVAL_MIN_FACE_WIDTH_RATIO = 0.60;
    const OVAL_MAX_FACE_WIDTH_RATIO = 1.20;

    function getFaceDetection(faceResult) {
        if (!faceResult) {
            return null;
        }
        return faceResult.detection || faceResult;
    }

    function isFrontalPose(ratio) {
        return ratio > 0.65 && ratio < 1.45;
    }

    function getPoseRatio(faceResult) {
        const landmarks = faceResult && faceResult.landmarks;
        if (!landmarks) {
            return null;
        }
        const nose = landmarks.getNose()[3];
        const jawOutline = landmarks.getJawOutline();
        const distLeft = Math.abs(nose.x - jawOutline[0].x);
        const distRight = Math.abs(jawOutline[16].x - nose.x);
        if (!distRight) {
            return null;
        }
        return distLeft / distRight;
    }

    function mapFaceBoxToDisplay(box, videoEl) {
        const videoWidth = videoEl.videoWidth;
        const videoHeight = videoEl.videoHeight;
        if (!videoWidth || !videoHeight || !box) {
            return null;
        }

        const elementWidth = videoEl.clientWidth;
        const elementHeight = videoEl.clientHeight;
        const videoAspect = videoWidth / videoHeight;
        const elementAspect = elementWidth / elementHeight;

        let renderedWidth;
        let renderedHeight;
        let offsetX;
        let offsetY;

        if (videoAspect > elementAspect) {
            renderedHeight = elementHeight;
            renderedWidth = videoWidth * (elementHeight / videoHeight);
            offsetX = (renderedWidth - elementWidth) / 2;
            offsetY = 0;
        } else {
            renderedWidth = elementWidth;
            renderedHeight = videoHeight * (elementWidth / videoWidth);
            offsetX = 0;
            offsetY = (renderedHeight - elementHeight) / 2;
        }

        const scaleX = renderedWidth / videoWidth;
        const scaleY = renderedHeight / videoHeight;
        let x = (box.x * scaleX) - offsetX;
        let y = (box.y * scaleY) - offsetY;
        let width = box.width * scaleX;
        let height = box.height * scaleY;

        x = elementWidth - x - width;

        return { x, y, width, height };
    }

    function getMappedFaceInOval(box, videoEl, ovalEl) {
        if (!ovalEl) {
            return null;
        }
        const mapped = mapFaceBoxToDisplay(box, videoEl);
        if (!mapped) {
            return null;
        }
        const ovalRect = ovalEl.getBoundingClientRect();
        return { mapped: mapped, ovalRect: ovalRect };
    }

    function getFaceOvalSizeStatus(box, videoEl, ovalEl) {
        if (!ovalEl) {
            return "ok";
        }
        const info = getMappedFaceInOval(box, videoEl, ovalEl);
        if (!info) {
            return "unknown";
        }
        const ratio = info.mapped.width / info.ovalRect.width;
        if (ratio < OVAL_MIN_FACE_WIDTH_RATIO) {
            return "too_small";
        }
        if (ratio > OVAL_MAX_FACE_WIDTH_RATIO) {
            return "too_large";
        }
        return "ok";
    }

    function faceFitsInOval(box, videoEl, ovalEl) {
        if (!ovalEl) {
            return true;
        }

        const mapped = mapFaceBoxToDisplay(box, videoEl);
        if (!mapped) {
            return false;
        }

        const videoRect = videoEl.getBoundingClientRect();
        const ovalRect = ovalEl.getBoundingClientRect();

        const faceCenterX = videoRect.left + mapped.x + (mapped.width / 2);
        const faceCenterY = videoRect.top + mapped.y + (mapped.height / 2);
        const ovalCenterX = ovalRect.left + (ovalRect.width / 2);
        const ovalCenterY = ovalRect.top + (ovalRect.height / 2);
        const radiusX = ovalRect.width / 2;
        const radiusY = ovalRect.height / 2;

        const dx = (faceCenterX - ovalCenterX) / radiusX;
        const dy = (faceCenterY - ovalCenterY) / radiusY;
        if ((dx * dx) + (dy * dy) > 1) {
            return false;
        }
        if (mapped.width < ovalRect.width * OVAL_MIN_FACE_WIDTH_RATIO) {
            return false;
        }
        if (mapped.width > ovalRect.width * OVAL_MAX_FACE_WIDTH_RATIO) {
            return false;
        }
        return true;
    }

    function meetsCaptureCriteria(faceResult, resizedResult, videoEl, ovalEl) {
        const detection = getFaceDetection(faceResult);
        const resizedDetection = getFaceDetection(resizedResult);

        if (!detection || !resizedDetection || !resizedDetection.box) {
            return false;
        }
        if (detection.score < MIN_DETECTION_SCORE) {
            return false;
        }
        if (!faceCenterInOval(resizedDetection.box, videoEl, ovalEl)) {
            return false;
        }
        if (getFaceOvalSizeStatus(resizedDetection.box, videoEl, ovalEl) !== "ok") {
            return false;
        }

        const ratio = getPoseRatio(faceResult);
        if (ratio === null) {
            return false;
        }
        return isFrontalPose(ratio);
    }

    const ENROLLMENT_COACH_CENTER = "Centre su cara";
    const ENROLLMENT_COACH_APPROACH = "Acérquese";
    const ENROLLMENT_COACH_RECEDE = "Aléjese";
    const ENROLLMENT_COACH_FRONT = "Mire de frente";
    const ENROLLMENT_COACH_HOLD = "Quédese quieto…";
    const ENROLLMENT_BUBBLE_CAPTURING = "Capturando...";
    const ENROLLMENT_COACH_MESSAGES = {
        "Centre su cara": true,
        "Acérquese": true,
        "Aléjese": true,
        "Mire de frente": true,
        "Quédese quieto…": true,
    };

    function isEnrollmentCoachMessage(message) {
        return !!(message && ENROLLMENT_COACH_MESSAGES[message]);
    }

    /**
     * Mensaje de guía de enrolamiento, o null si ya cumple criterios (el bucle pone estabilidad).
     * Distancia (Acérquese/Aléjese) tiene prioridad sobre centrar si hay cara detectada.
     */
    function getEnrollmentHudMessage(faceResult, resizedResult, videoEl, ovalEl) {
        const detection = getFaceDetection(faceResult);
        const resizedDetection = getFaceDetection(resizedResult);

        if (!detection || !resizedDetection || !resizedDetection.box) {
            return ENROLLMENT_COACH_CENTER;
        }
        if (detection.score < MIN_DETECTION_SCORE) {
            return ENROLLMENT_COACH_CENTER;
        }

        const sizeStatus = getFaceOvalSizeStatus(resizedDetection.box, videoEl, ovalEl);
        if (sizeStatus === "too_small" || sizeStatus === "unknown") {
            return ENROLLMENT_COACH_APPROACH;
        }
        if (sizeStatus === "too_large") {
            return ENROLLMENT_COACH_RECEDE;
        }
        if (!faceCenterInOval(resizedDetection.box, videoEl, ovalEl)) {
            return ENROLLMENT_COACH_CENTER;
        }

        const ratio = getPoseRatio(faceResult);
        if (ratio === null || !isFrontalPose(ratio)) {
            return ENROLLMENT_COACH_FRONT;
        }

        return null;
    }

    /**
     * Guía grande en overlay; la burbuja inferior solo para Capturando...
     */
    function createEnrollmentHudController(hudEl, coachOptions) {
        const COACH_HOLD_MS = 800;
        coachOptions = coachOptions || {};
        const coachEl = coachOptions.coachEl || null;
        const coachTextEl = coachOptions.coachTextEl || null;
        const hudBubbleEl = coachOptions.hudBubbleEl || (hudEl && hudEl.parentElement) || null;

        let shown = null;
        let coachShown = null;
        let coachPending = null;
        let coachPendingSince = 0;

        function setCoachVisible(visible) {
            if (!coachEl) {
                return;
            }
            if (visible) {
                coachEl.classList.remove("hidden");
                if (hudBubbleEl) {
                    hudBubbleEl.classList.add("hidden");
                }
            } else {
                coachEl.classList.add("hidden");
            }
        }

        function showHudBubble() {
            if (hudBubbleEl) {
                hudBubbleEl.classList.remove("hidden");
            }
        }

        function hideHudBubble() {
            if (hudBubbleEl) {
                hudBubbleEl.classList.add("hidden");
            }
        }

        function commitHud(message) {
            if (!hudEl || !message) {
                return;
            }
            shown = message;
            hudEl.textContent = message;
            showHudBubble();
        }

        function commitCoach(label) {
            if (!label) {
                return;
            }
            if (label === coachShown) {
                setCoachVisible(true);
                return;
            }
            coachShown = label;
            coachPending = null;
            if (coachTextEl) {
                coachTextEl.textContent = label;
            }
            setCoachVisible(true);
        }

        function hideCoachImmediate() {
            coachShown = null;
            coachPending = null;
            coachPendingSince = 0;
            setCoachVisible(false);
        }

        function show(message, now, options) {
            options = options || {};
            now = now || Date.now();
            if (!message) {
                return;
            }
            if (isEnrollmentCoachMessage(message)) {
                hideHudBubble();
                if (options.immediate) {
                    commitCoach(message);
                    return;
                }
                if (message === coachShown) {
                    coachPending = null;
                    setCoachVisible(true);
                    return;
                }
                if (message !== coachPending) {
                    coachPending = message;
                    coachPendingSince = now;
                    return;
                }
                if (now - coachPendingSince >= COACH_HOLD_MS) {
                    commitCoach(message);
                }
                return;
            }

            // Burbuja solo para Capturando...; otros textos (p. ej. error cámara) también en burbuja.
            hideCoachImmediate();
            commitHud(message);
        }

        function hideCoach() {
            hideCoachImmediate();
            hideHudBubble();
            shown = null;
        }

        function reset(initialMessage) {
            shown = null;
            coachShown = null;
            coachPending = null;
            coachPendingSince = 0;
            if (initialMessage && isEnrollmentCoachMessage(initialMessage)) {
                if (coachTextEl) {
                    coachTextEl.textContent = initialMessage;
                }
                coachShown = initialMessage;
                setCoachVisible(true);
                return;
            }
            setCoachVisible(false);
            hideHudBubble();
            if (initialMessage && hudEl) {
                shown = initialMessage;
                hudEl.textContent = initialMessage;
            }
        }

        return {
            show: show,
            reset: reset,
            hideCoach: hideCoach,
        };
    }

    function detectorOptions() {
        return new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.4 });
    }

    const ACCESS_MIN_SCORE = 0.55;
    const ACCESS_MIN_FACE_PX = 60;

    function accessDetectorOptions() {
        return new faceapi.TinyFaceDetectorOptions({ inputSize: 320, scoreThreshold: 0.4 });
    }

    function faceCenterInOval(box, videoEl, ovalEl) {
        if (!ovalEl) {
            return true;
        }
        const mapped = mapFaceBoxToDisplay(box, videoEl);
        if (!mapped) {
            return false;
        }
        const videoRect = videoEl.getBoundingClientRect();
        const ovalRect = ovalEl.getBoundingClientRect();
        const faceCenterX = videoRect.left + mapped.x + (mapped.width / 2);
        const faceCenterY = videoRect.top + mapped.y + (mapped.height / 2);
        const ovalCenterX = ovalRect.left + (ovalRect.width / 2);
        const ovalCenterY = ovalRect.top + (ovalRect.height / 2);
        const dx = (faceCenterX - ovalCenterX) / (ovalRect.width / 2);
        const dy = (faceCenterY - ovalCenterY) / (ovalRect.height / 2);
        return ((dx * dx) + (dy * dy)) <= 1.2;
    }

    function meetsAccessCaptureCriteria(detection, resizedDetection, videoEl, ovalEl) {
        const det = getFaceDetection(detection);
        const resized = getFaceDetection(resizedDetection);
        if (!det || !resized || !resized.box) {
            return false;
        }
        if (det.score < ACCESS_MIN_SCORE) {
            return false;
        }
        if (resized.box.width < ACCESS_MIN_FACE_PX) {
            return false;
        }
        // En acceso el óvalo es guía visual; validación suave para respuesta rápida.
        if (!ovalEl) {
            return true;
        }
        return faceCenterInOval(resized.box, videoEl, ovalEl);
    }

    return {
        MIN_DETECTION_SCORE: MIN_DETECTION_SCORE,
        STABILITY_MS: STABILITY_MS,
        OVAL_MIN_FACE_WIDTH_RATIO: OVAL_MIN_FACE_WIDTH_RATIO,
        OVAL_MAX_FACE_WIDTH_RATIO: OVAL_MAX_FACE_WIDTH_RATIO,
        getFaceDetection: getFaceDetection,
        mapFaceBoxToDisplay: mapFaceBoxToDisplay,
        faceFitsInOval: faceFitsInOval,
        meetsCaptureCriteria: meetsCaptureCriteria,
        ENROLLMENT_COACH_CENTER: ENROLLMENT_COACH_CENTER,
        ENROLLMENT_COACH_HOLD: ENROLLMENT_COACH_HOLD,
        ENROLLMENT_BUBBLE_CAPTURING: ENROLLMENT_BUBBLE_CAPTURING,
        getEnrollmentHudMessage: getEnrollmentHudMessage,
        createEnrollmentHudController: createEnrollmentHudController,
        meetsAccessCaptureCriteria: meetsAccessCaptureCriteria,
        detectorOptions: detectorOptions,
        accessDetectorOptions: accessDetectorOptions,
    };
})();
