(function () {
    /**
     * Parse USD amounts from DOM/JSON (supports 0.9, 0,9, 1.234,56).
     */
    window.parseUsdAmount = function (raw) {
        if (raw === null || raw === undefined) {
            return 0;
        }
        let s = String(raw).trim().replace(/\s/g, '');
        if (!s) {
            return 0;
        }
        if (s.includes(',') && !s.includes('.')) {
            s = s.replace(',', '.');
        } else if (s.includes(',') && s.includes('.')) {
            const lastComma = s.lastIndexOf(',');
            const lastDot = s.lastIndexOf('.');
            if (lastComma > lastDot) {
                s = s.replace(/\./g, '').replace(',', '.');
            } else {
                s = s.replace(/,/g, '');
            }
        }
        const n = parseFloat(s);
        return isNaN(n) ? 0 : n;
    };

    window.formatUsd = function (amount) {
        return '$' + amount.toLocaleString('en-US', {
            minimumFractionDigits: 2,
            maximumFractionDigits: 2,
        });
    };
})();
