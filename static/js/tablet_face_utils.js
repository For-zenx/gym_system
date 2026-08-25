// tablet_face_utils.js — Detección facial compartida (tablets acceso y enrolamiento)

const TabletFaceUtils = (function () {
    const MIN_DETECTION_SCORE = 0.60;
    const STABILITY_MS = 800;
    // Enrolamiento: min 0.65 fuerza acercarse; max alto evita «Aléjese» casi al llegar al min.
    const OVAL_MIN_FACE_WIDTH_RATIO = 0.67;
    const OVAL_MAX_FACE_WIDTH_RATIO = 1.25;

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

    /**
     * Mensaje HUD de enrolamiento, o null si ya cumple criterios (el bucle pone estabilidad).
     */
    function getEnrollmentHudMessage(faceResult, resizedResult, videoEl, ovalEl) {
        const detection = getFaceDetection(faceResult);
        const resizedDetection = getFaceDetection(resizedResult);

        if (!detection || !resizedDetection || !resizedDetection.box) {
            return "Coloque su rostro en el óvalo";
        }
        if (detection.score < MIN_DETECTION_SCORE) {
            return "Coloque su rostro en el óvalo";
        }
        if (!faceCenterInOval(resizedDetection.box, videoEl, ovalEl)) {
            return "Centre su rostro en el óvalo";
        }

        const sizeStatus = getFaceOvalSizeStatus(resizedDetection.box, videoEl, ovalEl);
        if (sizeStatus === "too_small" || sizeStatus === "unknown") {
            return "Acérquese más a la cámara";
        }
        if (sizeStatus === "too_large") {
            return "Aléjese un poco";
        }

        const ratio = getPoseRatio(faceResult);
        if (ratio === null || !isFrontalPose(ratio)) {
            return "Mire de frente a la cámara";
        }

        return null;
    }

    /**
     * Evita parpadeo del HUD: solo cambia el texto tras HOLD_MS con el mismo mensaje.
     * Mensajes de captura/estabilidad pueden ir inmediatos.
     */
    function createEnrollmentHudController(hudEl) {
        const HOLD_MS = 550;
        let shown = null;
        let pending = null;
        let pendingSince = 0;

        function commit(message) {
            if (!hudEl || !message || message === shown) {
                return;
            }
            shown = message;
            pending = null;
            hudEl.textContent = message;
        }

        function show(message, now, options) {
            options = options || {};
            if (!message) {
                return;
            }
            if (options.immediate) {
                commit(message);
                return;
            }
            if (message === shown) {
                pending = null;
                return;
            }
            if (message !== pending) {
                pending = message;
                pendingSince = now || Date.now();
                return;
            }
            if ((now || Date.now()) - pendingSince >= HOLD_MS) {
                commit(message);
            }
        }

        function reset(initialMessage) {
            shown = null;
            pending = null;
            pendingSince = 0;
            if (initialMessage && hudEl) {
                shown = initialMessage;
                hudEl.textContent = initialMessage;
            }
        }

        return {
            show: show,
            reset: reset,
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
        getEnrollmentHudMessage: getEnrollmentHudMessage,
        createEnrollmentHudController: createEnrollmentHudController,
        meetsAccessCaptureCriteria: meetsAccessCaptureCriteria,
        detectorOptions: detectorOptions,
        accessDetectorOptions: accessDetectorOptions,
    };
})();
