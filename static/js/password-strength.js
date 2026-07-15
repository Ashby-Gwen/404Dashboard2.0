(function () {
    'use strict';

    const specialCharacters = '!@#$%^&*()-_=+[]{};:,.?';
    const states = [
        { name: 'Empty', className: 'is-empty' },
        { name: 'Weak', className: 'is-weak' },
        { name: 'Fair', className: 'is-fair' },
        { name: 'Good', className: 'is-good' },
        { name: 'Good', className: 'is-good' },
        { name: 'Strong', className: 'is-strong' },
    ];

    function includesSpecialCharacter(password) {
        return Array.from(password).some((char) => specialCharacters.indexOf(char) !== -1);
    }

    function getPasswordChecks(password, confirmPassword) {
        const hasPassword = password.length > 0;
        return {
            length: password.length >= 8,
            uppercase: /[A-Z]/.test(password),
            lowercase: /[a-z]/.test(password),
            number: /\d/.test(password),
            special: includesSpecialCharacter(password),
            match: hasPassword && confirmPassword.length > 0 && password === confirmPassword,
        };
    }

    function getMissingMessage(checks, password, confirmPassword, hasConfirmInput) {
        if (!password) {
            return 'Start typing a password.';
        }
        if (!checks.length) {
            return 'Missing at least 8 characters.';
        }
        if (!checks.uppercase) {
            return 'Missing uppercase letter.';
        }
        if (!checks.lowercase) {
            return 'Missing lowercase letter.';
        }
        if (!checks.number) {
            return 'Missing number.';
        }
        if (!checks.special) {
            return 'Missing special character.';
        }
        if (hasConfirmInput && confirmPassword && !checks.match) {
            return 'Passwords do not match yet.';
        }
        if (hasConfirmInput && !confirmPassword) {
            return 'Confirm this password to finish.';
        }
        return 'Strong password.';
    }

    function updateCheckItem(root, key, passed) {
        const item = root.querySelector(`[data-strength-check="${key}"]`);
        if (!item) {
            return;
        }
        item.classList.toggle('is-met', passed);
        item.classList.toggle('is-missing', !passed);
    }

    function initPasswordStrength(root) {
        const passwordInput = document.querySelector(root.dataset.passwordInput || '');
        const confirmInput = document.querySelector(root.dataset.confirmPasswordInput || '');
        const isOptional = root.dataset.passwordOptional === 'true';
        const label = root.querySelector('[data-strength-label]');
        const score = root.querySelector('[data-strength-score]');
        const status = root.querySelector('[data-strength-status]');
        const track = root.querySelector('[data-strength-panel] [role="progressbar"], [data-strength-panel][role="progressbar"]');
        const bar = root.querySelector('[data-strength-bar]');

        if (!passwordInput || !label || !score || !status || !track || !bar) {
            return;
        }

        function render() {
            const password = passwordInput.value || '';
            const confirmPassword = confirmInput ? confirmInput.value || '' : '';
            const checks = getPasswordChecks(password, confirmPassword);
            const passedCount = ['length', 'uppercase', 'lowercase', 'number', 'special'].filter((key) => checks[key]).length;
            const state = states[password ? passedCount : 0];
            const percent = (passedCount / 5) * 100;

            root.dataset.passwordScore = String(passedCount);
            root.dataset.passwordStrength = state.className;
            label.textContent = `Password strength: ${state.name}`;
            score.textContent = `${passedCount}/5`;
            status.textContent = getMissingMessage(checks, password, confirmPassword, Boolean(confirmInput));
            track.setAttribute('aria-valuenow', String(passedCount));
            track.setAttribute('aria-valuetext', `${state.name}, ${passedCount} of 5 requirements met`);
            bar.style.width = `${percent}%`;

            ['length', 'uppercase', 'lowercase', 'number', 'special'].forEach((key) => {
                updateCheckItem(root, key, checks[key]);
            });
            updateCheckItem(root, 'match', checks.match);

            if (passwordInput.setCustomValidity) {
                const policyMet = passedCount === 5;
                passwordInput.setCustomValidity(!password && isOptional ? '' : policyMet ? '' : status.textContent);
            }
            if (confirmInput && confirmInput.setCustomValidity) {
                const confirmValid = !password && isOptional ? true : checks.match;
                confirmInput.setCustomValidity(confirmValid ? '' : 'Passwords do not match.');
            }
        }

        passwordInput.addEventListener('input', render);
        if (confirmInput) {
            confirmInput.addEventListener('input', render);
        }
        root.addEventListener('submit', (event) => {
            render();
            const password = passwordInput.value || '';
            if (!password && isOptional) {
                return;
            }
            if (!root.checkValidity()) {
                event.preventDefault();
                root.reportValidity();
            }
        });
        render();
    }

    document.addEventListener('DOMContentLoaded', () => {
        document.querySelectorAll('form[data-password-strength]').forEach(initPasswordStrength);
    });
})();
