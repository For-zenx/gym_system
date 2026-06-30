(function () {
    const form = document.getElementById('class-session-form');
    if (!form) {
        return;
    }

    const instructorSelect = form.querySelector('[name="instructor"]');
    const instructorName = form.querySelector('[name="instructor_name"]');

    function clearTrainerValidity() {
        if (instructorName) {
            instructorName.setCustomValidity('');
        }
    }

    function trainerIsFilled() {
        const hasSelect = instructorSelect && instructorSelect.value;
        const hasName = instructorName && instructorName.value.trim();
        return Boolean(hasSelect || hasName);
    }

    function validateTrainerField() {
        if (!instructorName) {
            return true;
        }
        if (trainerIsFilled()) {
            instructorName.setCustomValidity('');
            return true;
        }
        instructorName.setCustomValidity(
            'Indique el entrenador del listado o escriba su nombre.'
        );
        return false;
    }

    if (instructorSelect) {
        instructorSelect.addEventListener('change', clearTrainerValidity);
    }
    if (instructorName) {
        instructorName.addEventListener('input', clearTrainerValidity);
    }

    form.addEventListener('submit', function (event) {
        if (!validateTrainerField()) {
            event.preventDefault();
            instructorName.reportValidity();
        }
    });
})();
