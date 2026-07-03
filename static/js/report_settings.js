(function () {
    const list = document.getElementById('report-recipient-list');
    const addBtn = document.getElementById('report-recipient-add');
    const maxRecipients = window.REPORT_SETTINGS_MAX_RECIPIENTS || 5;

    if (!list || !addBtn) {
        return;
    }

    function getRows() {
        return Array.from(list.querySelectorAll('[data-recipient-row]'));
    }

    function renumberRows() {
        const rows = getRows();
        rows.forEach(function (row, index) {
            const number = index + 1;
            const label = row.querySelector('.report-recipient-label');
            const input = row.querySelector('[data-recipient-input]');
            const removeBtn = row.querySelector('[data-remove-recipient]');

            if (label) {
                label.textContent = 'Destinatario ' + number;
            }
            if (input) {
                input.name = 'recipient_email_' + number;
            }
            if (removeBtn) {
                removeBtn.hidden = rows.length <= 1;
            }
        });

        addBtn.hidden = rows.length >= maxRecipients;
    }

    function createRow(value) {
        const row = document.createElement('div');
        row.className = 'config-form-group report-recipient-row';
        row.setAttribute('data-recipient-row', '');

        row.innerHTML =
            '<div class="report-recipient-row-header">' +
            '<label class="report-recipient-label">Destinatario</label>' +
            '<button type="button" class="btn-link-muted report-recipient-remove" data-remove-recipient>Quitar</button>' +
            '</div>' +
            '<input type="email" value="" placeholder="ejemplo@correo.com" autocomplete="email" data-recipient-input>';

        const input = row.querySelector('[data-recipient-input]');
        if (input && value) {
            input.value = value;
        }

        row.querySelector('[data-remove-recipient]').addEventListener('click', function () {
            row.remove();
            renumberRows();
        });

        return row;
    }

    addBtn.addEventListener('click', function () {
        if (getRows().length >= maxRecipients) {
            return;
        }
        list.appendChild(createRow(''));
        renumberRows();
        const rows = getRows();
        const lastInput = rows[rows.length - 1].querySelector('[data-recipient-input]');
        if (lastInput) {
            lastInput.focus();
        }
    });

    list.addEventListener('click', function (event) {
        const removeBtn = event.target.closest('[data-remove-recipient]');
        if (!removeBtn) {
            return;
        }
        const row = removeBtn.closest('[data-recipient-row]');
        if (!row || getRows().length <= 1) {
            return;
        }
        row.remove();
        renumberRows();
    });

    renumberRows();
})();
