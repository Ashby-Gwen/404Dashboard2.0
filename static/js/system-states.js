(function () {
    'use strict';

    const tasks = new Map();
    let taskSequence = 0;
    let interruptionRequest = null;

    function ensureInterface() {
        if (!document.body || document.getElementById('systemStateRoot')) return;

        const root = document.createElement('div');
        root.id = 'systemStateRoot';
        root.innerHTML = `
            <div id="systemFeedbackRegion" class="system-feedback-region" aria-live="polite"></div>
            <div id="systemLoadingOverlay" class="system-loading-overlay" hidden aria-live="polite" aria-busy="true">
                <div class="system-loading-card">
                    <span class="system-spinner" aria-hidden="true"></span>
                    <strong id="systemLoadingTitle">Working...</strong>
                    <span id="systemLoadingMessage"></span>
                </div>
            </div>
            <div id="systemInterruptionModal" class="system-modal-backdrop" hidden>
                <section class="system-modal" role="dialog" aria-modal="true" aria-labelledby="systemInterruptionTitle">
                    <h2 id="systemInterruptionTitle">Process Interruption</h2>
                    <p id="systemInterruptionMessage"></p>
                    <div class="system-modal-actions">
                        <button type="button" class="btn btn-outline" data-system-cancel>Cancel</button>
                        <button type="button" class="btn btn-primary" data-system-proceed>Proceed</button>
                    </div>
                </section>
            </div>`;
        document.body.appendChild(root);

        root.querySelector('[data-system-cancel]').addEventListener('click', resolveInterruption.bind(null, false));
        root.querySelector('[data-system-proceed]').addEventListener('click', resolveInterruption.bind(null, true));
    }

    function resolveInterruption(shouldProceed) {
        if (!interruptionRequest) return;
        const request = interruptionRequest;
        interruptionRequest = null;
        document.getElementById('systemInterruptionModal').hidden = true;

        if (!shouldProceed && request.activeTask.status === 'interruption-pending') {
            request.activeTask.status = 'running';
            request.activeTask.resumeWaiters.splice(0).forEach(resolve => resolve());
        }
        request.resolve(shouldProceed);
    }

    function requestInterruption(activeTask, newTaskName) {
        ensureInterface();
        activeTask.status = 'interruption-pending';
        document.getElementById('systemInterruptionMessage').textContent =
            `${activeTask.name} is in progress. If you proceed with ${newTaskName}, you will lose current progress. Proceed?`;
        document.getElementById('systemInterruptionModal').hidden = false;

        return new Promise(resolve => {
            interruptionRequest = { activeTask, resolve };
        });
    }

    function activeOverlayTask() {
        return Array.from(tasks.values())
            .filter(task => task.showOverlay && ['running', 'interruption-pending'].includes(task.status))
            .sort((left, right) => right.id - left.id)[0];
    }

    function renderOverlay() {
        ensureInterface();
        const overlay = document.getElementById('systemLoadingOverlay');
        const task = activeOverlayTask();
        overlay.hidden = !task;
        if (!task) return;
        document.getElementById('systemLoadingTitle').textContent = task.name;
        document.getElementById('systemLoadingMessage').textContent = task.message || 'Please wait.';
    }

    function createProgress(container, options = {}) {
        const target = typeof container === 'string' ? document.querySelector(container) : container;
        if (!target) return null;

        target.innerHTML = `
            <div class="system-progress" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
                <div class="system-progress-track">
                    <div class="system-progress-bar"></div>
                </div>
                <div class="system-progress-copy">
                    <span class="system-progress-label">${options.label || 'Progress'}</span>
                    <strong class="system-progress-value">0%</strong>
                </div>
            </div>`;

        const element = target.firstElementChild;
        const bar = element.querySelector('.system-progress-bar');
        const valueLabel = element.querySelector('.system-progress-value');

        return {
            element,
            set(value, label) {
                const percentage = Math.max(0, Math.min(100, Number(value) || 0));
                element.classList.remove('is-indeterminate');
                element.setAttribute('aria-valuenow', String(percentage));
                bar.style.width = `${percentage}%`;
                valueLabel.textContent = `${Math.round(percentage)}%`;
                if (label) element.querySelector('.system-progress-label').textContent = label;
            },
            setIndeterminate(label) {
                element.classList.add('is-indeterminate');
                element.removeAttribute('aria-valuenow');
                if (label) element.querySelector('.system-progress-label').textContent = label;
                valueLabel.textContent = '';
            },
            reset() {
                this.set(0, options.label || 'Progress');
            },
            remove() {
                target.innerHTML = '';
            }
        };
    }

    function feedback(type, message, options = {}) {
        ensureInterface();
        const normalizedType = ['success', 'warning', 'error'].includes(type) ? type : 'warning';
        const item = document.createElement('div');
        item.className = `system-feedback system-feedback-${normalizedType}`;
        item.setAttribute('role', normalizedType === 'error' ? 'alert' : 'status');
        item.innerHTML = `
            <div>
                <strong></strong>
                <p></p>
            </div>
            <button type="button" aria-label="Dismiss message">&times;</button>`;
        item.querySelector('strong').textContent =
            options.title || normalizedType.charAt(0).toUpperCase() + normalizedType.slice(1);
        item.querySelector('p').textContent = message;
        item.querySelector('button').addEventListener('click', () => item.remove());
        document.getElementById('systemFeedbackRegion').appendChild(item);

        const dismissAfter = options.dismissAfter !== undefined
            ? options.dismissAfter
            : normalizedType === 'success' ? 3500 : 0;
        if (dismissAfter > 0) window.setTimeout(() => item.remove(), dismissAfter);
        return item;
    }

    const errorTypes = {
        validation: {
            title: 'Check the Information',
            message: 'Some information is missing or needs correction.',
            action: 'Review the highlighted fields, then try again.'
        },
        authentication: {
            title: 'Sign In Required',
            message: 'Your session could not be verified.',
            action: 'Sign in again to continue.'
        },
        permission: {
            title: 'Access Not Allowed',
            message: 'Your account does not have permission to perform this action.',
            action: 'Contact an administrator if you believe this is incorrect.'
        },
        database: {
            title: 'Database Unavailable',
            message: 'The system could not complete the database request.',
            action: 'Wait a moment, then try again.'
        },
        network: {
            title: 'Connection Problem',
            message: 'The system could not reach the server.',
            action: 'Check your connection and try again.'
        },
        server: {
            title: 'Server Error',
            message: 'Something went wrong while processing the request.',
            action: 'Try again. If the issue continues, contact an administrator.'
        },
        empty: {
            title: 'No Results Found',
            message: 'There is no data to show for the current filters.',
            action: 'Adjust the filters or add records first.'
        }
    };

    function errorState(type = 'server', options = {}) {
        const config = { ...(errorTypes[type] || errorTypes.server), ...options };
        const details = config.details
            ? `<details class="system-error-details"><summary>Technical details</summary><pre>${escapeHtml(config.details)}</pre></details>`
            : '';
        return `
            <section class="system-error-state system-error-${type}" role="${type === 'empty' ? 'status' : 'alert'}">
                <strong>${escapeHtml(config.title)}</strong>
                <p>${escapeHtml(config.message)}</p>
                <span>${escapeHtml(config.action)}</span>
                ${details}
            </section>`;
    }

    function renderError(container, type = 'server', options = {}) {
        const target = typeof container === 'string' ? document.querySelector(container) : container;
        if (!target) return null;
        target.innerHTML = errorState(type, options);
        return target.firstElementChild;
    }

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function skeleton(options = {}) {
        const rows = Math.max(1, Number(options.rows) || 4);
        const columns = Math.max(1, Number(options.columns) || 3);
        const rowHtml = Array.from({ length: rows }, () =>
            `<div class="system-skeleton-row" style="grid-template-columns: repeat(${columns}, minmax(0, 1fr));">
                ${Array.from({ length: columns }, () => '<span class="system-skeleton-block"></span>').join('')}
            </div>`
        ).join('');
        return `<div class="system-skeleton" aria-label="Loading content">${rowHtml}</div>`;
    }

    const buttonStates = new WeakMap();
    let pendingActionButton = null;

    function isButtonLike(element) {
        return element?.closest?.('button, input[type="submit"], input[type="button"], a.btn, .btn');
    }

    function shouldManageButton(button) {
        if (!button || button.dataset.noLoading === 'true') return false;
        if (button.classList.contains('tab-btn') || button.classList.contains('filter-btn') || button.classList.contains('report-tab')) return false;
        return true;
    }

    function setButtonLoading(button, isLoading, label = 'Processing...') {
        if (!shouldManageButton(button)) return;
        if (isLoading) {
            if (buttonStates.has(button)) return;
            buttonStates.set(button, {
                html: button.innerHTML,
                value: button.value,
                disabled: button.disabled,
                ariaBusy: button.getAttribute('aria-busy'),
                ariaDisabled: button.getAttribute('aria-disabled')
            });
            button.classList.add('is-loading');
            button.setAttribute('aria-busy', 'true');
            if (button.tagName === 'A') button.setAttribute('aria-disabled', 'true');
            if ('disabled' in button) button.disabled = true;
            if (button.tagName === 'INPUT') {
                button.value = label;
            } else {
                button.innerHTML = `<span class="button-spinner" aria-hidden="true"></span><span>${escapeHtml(label)}</span>`;
            }
            return;
        }
        const previous = buttonStates.get(button);
        if (!previous) return;
        button.classList.remove('is-loading');
        button.innerHTML = previous.html;
        if (button.tagName === 'INPUT') button.value = previous.value;
        button.disabled = previous.disabled;
        if (previous.ariaBusy === null) button.removeAttribute('aria-busy');
        else button.setAttribute('aria-busy', previous.ariaBusy);
        if (previous.ariaDisabled === null) button.removeAttribute('aria-disabled');
        else button.setAttribute('aria-disabled', previous.ariaDisabled);
        buttonStates.delete(button);
        if (window.lucide?.createIcons) window.lucide.createIcons();
    }

    async function withButtonLoading(button, operation, label = 'Processing...') {
        setButtonLoading(button, true, label);
        try {
            return await operation();
        } finally {
            setButtonLoading(button, false);
        }
    }

    function initializeGlobalButtonLoading(root = document) {
        if (root !== document) return;
        if (!window.__syluxentFetchLoadingPatched) {
            window.__syluxentFetchLoadingPatched = true;
            const nativeFetch = window.fetch.bind(window);
            window.fetch = (...args) => {
                const button = pendingActionButton;
                pendingActionButton = null;
                if (button) setButtonLoading(button, true);
                return nativeFetch(...args)
                    .finally(() => {
                        if (button) setButtonLoading(button, false);
                    });
            };
        }
        if (!document.documentElement.dataset.syluxentButtonLoading) {
            document.documentElement.dataset.syluxentButtonLoading = 'true';
            document.addEventListener('click', event => {
                const button = isButtonLike(event.target);
                if (!shouldManageButton(button)) return;
                pendingActionButton = button;
                window.setTimeout(() => {
                    if (pendingActionButton === button) pendingActionButton = null;
                }, 800);
            }, true);
            document.addEventListener('submit', event => {
                if (event.defaultPrevented) return;
                const form = event.target;
                const submitter = event.submitter || form.querySelector('button[type="submit"], input[type="submit"]');
                if (!shouldManageButton(submitter)) return;
                if (form.dataset.submitting === 'true') {
                    event.preventDefault();
                    return;
                }
                form.dataset.submitting = 'true';
                setButtonLoading(submitter, true, 'Submitting...');
            });
        }
    }

    function cleanupTask(task, reason) {
        if (task.progress) task.progress.reset();
        task.temporaryData = {};
        if (typeof task.cleanup === 'function') task.cleanup(reason);
    }

    function terminateTask(task, reason = 'cancelled') {
        if (!task || !['running', 'interruption-pending'].includes(task.status)) return;
        task.status = 'cancelled';
        task.controller.abort(reason);
        task.resumeWaiters.splice(0).forEach(resolve => resolve());
        cleanupTask(task, reason);
        if (tasks.get(task.scope)?.id === task.id) tasks.delete(task.scope);
        renderOverlay();
    }

    async function run(options, executor) {
        ensureInterface();
        const scope = options.scope || 'default';
        const name = options.name || 'Task';
        const activeTask = tasks.get(scope);

        if (activeTask && ['running', 'interruption-pending'].includes(activeTask.status)) {
            const shouldProceed = await requestInterruption(activeTask, name);
            if (!shouldProceed) return { cancelled: true, reason: 'interruption-declined' };
            terminateTask(activeTask, 'interrupted');
        }

        const task = {
            id: ++taskSequence,
            scope,
            name,
            status: 'running',
            message: options.message || '',
            showOverlay: options.showOverlay !== false,
            controller: new AbortController(),
            cleanup: options.cleanup,
            progress: options.progress || null,
            resumeWaiters: [],
            temporaryData: options.temporaryData || {}
        };
        tasks.set(scope, task);
        renderOverlay();

        const context = {
            signal: task.controller.signal,
            task,
            setMessage(message) {
                task.message = message;
                renderOverlay();
            },
            setProgress(value, label) {
                if (task.progress) task.progress.set(value, label);
            },
            setIndeterminate(label) {
                if (task.progress) task.progress.setIndeterminate(label);
            },
            async checkpoint() {
                if (task.status === 'interruption-pending') {
                    await new Promise(resolve => task.resumeWaiters.push(resolve));
                }
                if (task.controller.signal.aborted) {
                    throw new DOMException('Task aborted', 'AbortError');
                }
            }
        };

        try {
            const result = await executor(context);
            if (task.controller.signal.aborted) {
                return { cancelled: true, reason: task.controller.signal.reason || 'aborted' };
            }
            task.status = 'completed';
            return result;
        } catch (error) {
            if (error && error.name === 'AbortError') {
                return { cancelled: true, reason: task.controller.signal.reason || 'aborted' };
            }
            task.status = 'failed';
            throw error;
        } finally {
            if (tasks.get(scope)?.id === task.id) tasks.delete(scope);
            if (interruptionRequest?.activeTask.id === task.id) {
                const request = interruptionRequest;
                interruptionRequest = null;
                document.getElementById('systemInterruptionModal').hidden = true;
                request.resolve(false);
            }
            renderOverlay();
        }
    }

    function getTask(scope) {
        return tasks.get(scope) || null;
    }

    const dataCache = {
        prefix: 'syluxentDataCache:',
        ttl: 10 * 60 * 1000,
        key(scope, key) {
            return `${this.prefix}${scope}:${key}`;
        },
        get(scope, key) {
            try {
                const cached = sessionStorage.getItem(this.key(scope, key));
                if (!cached) return null;
                const payload = JSON.parse(cached);
                if (!payload || Date.now() - Number(payload.savedAt || 0) > Number(payload.ttl || this.ttl)) {
                    sessionStorage.removeItem(this.key(scope, key));
                    return null;
                }
                return payload.data;
            } catch {
                return null;
            }
        },
        set(scope, key, data, ttl = this.ttl) {
            try {
                sessionStorage.setItem(this.key(scope, key), JSON.stringify({
                    savedAt: Date.now(),
                    ttl,
                    data
                }));
            } catch {
                // Storage can be unavailable or full; callers should still continue normally.
            }
            return data;
        },
        async remember(scope, key, loader, ttl = this.ttl) {
            const cached = this.get(scope, key);
            if (cached) return cached;
            const data = await loader();
            return this.set(scope, key, data, ttl);
        },
        clear(scope = '') {
            try {
                const targetPrefix = scope ? `${this.prefix}${scope}:` : this.prefix;
                Object.keys(sessionStorage)
                    .filter(key => key.startsWith(targetPrefix))
                    .forEach(key => sessionStorage.removeItem(key));
            } catch {
                // Ignore cache cleanup failures; fresh server requests remain the fallback.
            }
        }
    };

    const ashbyBible = {
        version: 'en-kjv',
        startDate: '2026-01-01',
        cacheKey: 'syluxentGospelVerses:v1',
        books: [
            { id: 'matthew', label: 'Matthew', chapters: 28 },
            { id: 'mark', label: 'Mark', chapters: 16 },
            { id: 'luke', label: 'Luke', chapters: 24 },
            { id: 'john', label: 'John', chapters: 21 }
        ]
    };

    const themeBrandingAssets = {
        dark: {
            navLogo: 'dark-theme-nav-logo.png',
            favicon: 'dark-theme-favicon.png'
        },
        light: {
            navLogo: 'light-theme-navbar-logo.png',
            favicon: 'light-theme-favicon.png'
        },
        contrast: {
            navLogo: 'contrast-theme-nav-logo.png',
            favicon: 'contrast-theme-favicon.png'
        },
        rose: {
            navLogo: 'rose-theme-nav-logo.png',
            favicon: 'rose-theme-favicon.png'
        },
        ashby: {
            navLogo: 'ashby-theme-nav-logo.png',
            favicon: 'ashby-theme-favicon.png'
        }
    };

    const themePresetPalettes = {
        dark: { bg: '#0F1115', bg2: '#1A1D24', orange: '#F97316' },
        light: { bg: '#F8FAFC', bg2: '#F8FAFC', orange: '#F97316' },
        contrast: { bg: '#111827', bg2: '#1F2937', orange: '#F59E0B' },
        rose: { bg: '#F1F4F0', bg2: '#F1F4F0', orange: '#4A7C59' },
        ashby: { bg: '#FBFAF8', bg2: '#FBFAF8', orange: '#D4AF37' }
    };

    function cssVariable(name) {
        return getComputedStyle(document.documentElement).getPropertyValue(name).trim().toUpperCase();
    }

    function detectPresetThemeMode() {
        const bg = cssVariable('--bg');
        const bg2 = cssVariable('--bg-2');
        const orange = cssVariable('--orange');
        return Object.entries(themePresetPalettes).find(([, palette]) => {
            return bg === palette.bg &&
                bg2 === palette.bg2 &&
                orange === palette.orange;
        })?.[0] || '';
    }

    function detectThemeMode() {
        const explicitMode = document.body?.dataset.themeMode || document.documentElement.dataset.themeMode;
        if (themeBrandingAssets[explicitMode]) return explicitMode;
        const presetMode = detectPresetThemeMode();
        if (presetMode) return presetMode;
        if (isAshbyMode()) return 'ashby';
        if (isHighContrastPalette()) return 'contrast';
        if (isDarkPalette()) return 'dark';
        return 'light';
    }

    function themeAssetPath(folder, filename) {
        return `/static/images/${folder}/${filename}`;
    }

    function updateThemeBranding(mode = '') {
        if (!document.documentElement) return;
        const activeMode = themeBrandingAssets[mode] ? mode : detectThemeMode();
        const assets = themeBrandingAssets[activeMode] || themeBrandingAssets.light;
        const logoSrc = themeAssetPath('icons', assets.navLogo);
        const faviconSrc = themeAssetPath('favicon', assets.favicon);

        document.querySelectorAll('.nav-logo').forEach(logo => {
            let image = logo.querySelector('img[data-theme-nav-logo]');
            if (!image) {
                image = document.createElement('img');
                image.dataset.themeNavLogo = 'true';
                image.alt = '404 Dashboard';
                image.decoding = 'async';
            }

            let label = logo.querySelector('[data-theme-nav-label]');
            if (!label) {
                label = document.createElement('span');
                label.dataset.themeNavLabel = 'true';
            }
            label.textContent = '404 Dashboard';

            if (logo.children.length !== 2 || logo.children[0] !== image || logo.children[1] !== label) {
                logo.replaceChildren(image, label);
            }

            if (image.getAttribute('src') !== logoSrc) {
                image.src = logoSrc;
            }
        });

        let favicon = document.querySelector('link[rel="icon"][data-theme-favicon]');
        if (!favicon) {
            favicon = document.createElement('link');
            favicon.rel = 'icon';
            favicon.type = 'image/png';
            favicon.dataset.themeFavicon = 'true';
            document.head.appendChild(favicon);
        }
        if (favicon.getAttribute('href') !== faviconSrc) {
            favicon.href = faviconSrc;
        }
    }

    function isAshbyMode() {
        const mode = document.body?.dataset.themeMode || document.documentElement.dataset.themeMode;
        if (mode === 'ashby') return true;
        const bg = cssVariable('--bg');
        const bg2 = cssVariable('--bg-2');
        const highlight = cssVariable('--orange');
        return (bg === '#FBFAF8' && bg2 === '#FBFAF8' && highlight === '#D4AF37') ||
            (bg === '#FFFFFF' && bg2 === '#F7E7B5' && highlight === '#C99700');
    }

    function isDarkPalette() {
        const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg').trim();
        const hex = bg.match(/^#([0-9a-f]{6})$/i);
        if (!hex) return false;
        const value = hex[1];
        const red = parseInt(value.slice(0, 2), 16);
        const green = parseInt(value.slice(2, 4), 16);
        const blue = parseInt(value.slice(4, 6), 16);
        const luminance = (0.2126 * red + 0.7152 * green + 0.0722 * blue) / 255;
        return luminance < 0.35;
    }

    function isHighContrastPalette() {
        const bg = cssVariable('--bg');
        const bg2 = cssVariable('--bg-2');
        const orange = cssVariable('--orange');
        const text = cssVariable('--text');
        return (bg === '#000000' && orange === '#FF9800') ||
            (bg === '#111827' && bg2 === '#1F2937' && orange === '#F59E0B') ||
            bg === '#020B1F' ||
            bg2 === '#061A3A' ||
            text.includes('255, 152, 0') ||
            text.includes('255, 138, 0');
    }

    function syncThemeMode() {
        if (!document.body) return;
        const mode = detectThemeMode();
        document.body.dataset.themeMode = mode;
        document.documentElement.dataset.themeMode = mode;
        updateThemeBranding(mode);
        if (mode !== 'ashby') {
            document.body.classList.remove('ashby-sidebar-collapsed');
            delete document.body.dataset.ashbyVerseInitialized;
        }
    }

    function ensureAshbySidebar() {
        if (!document.body || document.getElementById('ashbyVerseSidebar')) return;

        document.body.classList.add('ashby-sidebar-collapsed');

        const sidebar = document.createElement('aside');
        sidebar.id = 'ashbyVerseSidebar';
        sidebar.className = 'ashby-verse-sidebar';
        sidebar.setAttribute('aria-live', 'polite');
        sidebar.innerHTML = `
            <h2>Daily Gospel</h2>
            <div class="ashby-verse-ref" data-ashby-ref>Loading...</div>
            <p class="ashby-verse-text" data-ashby-text></p>
            <div class="ashby-verse-status" data-ashby-status>Preparing today's verse.</div>`;
        document.body.appendChild(sidebar);

        const toggle = document.createElement('button');
        toggle.id = 'ashbyVerseToggle';
        toggle.className = 'ashby-verse-toggle';
        toggle.type = 'button';
        toggle.innerHTML = `
            <span class="ashby-verse-toggle-symbol" aria-hidden="true">
                <iframe src="https://ashby-gwen.github.io/dashboardSymbols/ichthys.html" title="" tabindex="-1" loading="lazy"></iframe>
            </span>
            <span class="ashby-verse-toggle-label" data-ashby-toggle-label></span>`;
        document.body.appendChild(toggle);
        updateAshbyToggle();
        toggle.addEventListener('click', () => {
            document.body.classList.toggle('ashby-sidebar-collapsed');
            updateAshbyToggle();
        });
    }

    function updateAshbyToggle() {
        const toggle = document.getElementById('ashbyVerseToggle');
        if (!toggle || !document.body) return;
        const isCollapsed = document.body.classList.contains('ashby-sidebar-collapsed');
        const label = isCollapsed ? 'Show Gospel' : 'Close Gospel';
        const labelNode = toggle.querySelector('[data-ashby-toggle-label]');
        if (labelNode) labelNode.textContent = label;
        toggle.setAttribute('aria-label', label);
        toggle.setAttribute('aria-expanded', String(!isCollapsed));
    }

    function gospelChapterUrl(book, chapter) {
        return `https://cdn.jsdelivr.net/gh/wldeh/bible-api/bibles/${ashbyBible.version}/books/${book}/chapters/${chapter}.json`;
    }

    function normalizeVerse(raw, bookLabel) {
        return {
            book: raw.book || bookLabel,
            chapter: Number(raw.chapter),
            verse: Number(raw.verse),
            text: raw.text || ''
        };
    }

    async function fetchGospelVerses() {
        const cached = localStorage.getItem(ashbyBible.cacheKey);
        if (cached) {
            try {
                const parsed = JSON.parse(cached);
                if (Array.isArray(parsed) && parsed.length) return parsed;
            } catch {
                localStorage.removeItem(ashbyBible.cacheKey);
            }
        }

        const ordered = [];
        for (const book of ashbyBible.books) {
            for (let chapter = 1; chapter <= book.chapters; chapter += 1) {
                const response = await fetch(gospelChapterUrl(book.id, chapter));
                if (!response.ok) throw new Error(`Unable to load ${book.label} ${chapter}.`);
                const payload = await response.json();
                const rows = Array.isArray(payload.data) ? payload.data : [];
                ordered.push(...rows.map(row => normalizeVerse(row, book.label)));
            }
        }
        localStorage.setItem(ashbyBible.cacheKey, JSON.stringify(ordered));
        return ordered;
    }

    function verseForToday(verses) {
        const start = new Date(`${ashbyBible.startDate}T00:00:00`);
        const today = new Date();
        const todayUtc = Date.UTC(today.getFullYear(), today.getMonth(), today.getDate());
        const startUtc = Date.UTC(start.getFullYear(), start.getMonth(), start.getDate());
        const dayIndex = Math.max(0, Math.floor((todayUtc - startUtc) / 86400000));
        return verses[dayIndex % verses.length];
    }

    async function renderAshbyVerse() {
        syncThemeMode();
        ensureAshbySidebar();
        const sidebar = document.getElementById('ashbyVerseSidebar');
        const ref = sidebar.querySelector('[data-ashby-ref]');
        const text = sidebar.querySelector('[data-ashby-text]');
        const status = sidebar.querySelector('[data-ashby-status]');

        if (!isAshbyMode()) {
            return;
        }

        document.body.dataset.themeMode = 'ashby';
        document.documentElement.dataset.themeMode = 'ashby';
        if (!document.body.dataset.ashbyVerseInitialized) {
            document.body.classList.add('ashby-sidebar-collapsed');
            document.body.dataset.ashbyVerseInitialized = 'true';
            updateAshbyToggle();
        }
        try {
            const verses = await fetchGospelVerses();
            const verse = verseForToday(verses);
            ref.textContent = `${verse.book} ${verse.chapter}:${verse.verse}`;
            text.textContent = verse.text;
            status.textContent = 'Matthew, Mark, Luke, and John repeat in daily order.';
        } catch (error) {
            ref.textContent = 'Daily Gospel';
            text.textContent = '';
            status.textContent = error.message || 'Unable to load today\'s verse.';
        }
    }

    const futureDateWarningMessage = 'Possible date error detected. The selected date is in the future. Please review before continuing.';

    function localDateInputToday() {
        const today = new Date();
        today.setMinutes(today.getMinutes() - today.getTimezoneOffset());
        return today.toISOString().slice(0, 10);
    }

    function isFutureDateValue(value) {
        if (!value) return false;
        return value > localDateInputToday();
    }

    function renderDateWarning(input) {
        if (!input || input.type !== 'date') return;
        const parent = input.closest('.form-group') || input.parentElement;
        if (!parent) return;
        let warning = parent.querySelector(`.future-date-warning[data-for="${input.id || input.name || 'date'}"]`);
        if (isFutureDateValue(input.value)) {
            if (!warning) {
                warning = document.createElement('div');
                warning.className = 'future-date-warning';
                warning.dataset.for = input.id || input.name || 'date';
                parent.appendChild(warning);
            }
            warning.textContent = futureDateWarningMessage;
            input.classList.add('has-future-date-warning');
        } else {
            if (warning) warning.remove();
            input.classList.remove('has-future-date-warning');
        }
    }

    function initializeFutureDateWarnings(root = document) {
        root.querySelectorAll('input[type="date"]').forEach(input => {
            renderDateWarning(input);
            if (input.dataset.futureDateWatcher === 'true') return;
            input.dataset.futureDateWatcher = 'true';
            input.addEventListener('input', () => renderDateWarning(input));
            input.addEventListener('change', () => renderDateWarning(input));
        });
    }

    function initializeLogoutCacheCleanup(root = document) {
        root.querySelectorAll('a[href$="/logout"]').forEach(link => {
            if (link.dataset.syluxentLogoutCleanup === 'true') return;
            link.dataset.syluxentLogoutCleanup = 'true';
            link.addEventListener('click', () => dataCache.clear());
        });
    }

    function initializeEvaluationModal() {
        if (!document.body || document.getElementById('evaluationModalRoot')) return;
        if (!document.querySelector('a[href$="/logout"]')) return;

        const root = document.createElement('div');
        root.id = 'evaluationModalRoot';
        root.innerHTML = `
            <a href="/evaluation" class="evaluation-launcher btn btn-outline btn-sm" aria-label="Evaluate System">
                <img class="evaluation-launcher-icon" src="/static/images/icons/evaluation-icon.png" alt="">
                <span class="evaluation-launcher-label">Evaluate System</span>
            </a>`;
        document.body.appendChild(root);
    }

    function showServerWarnings(warnings = []) {
        if (!Array.isArray(warnings) || !warnings.length) return;
        warnings.slice(0, 5).forEach(item => {
            const field = item.field ? `${item.field}: ` : '';
            feedback('warning', `${field}${item.message || futureDateWarningMessage}`, {
                title: 'Review Date',
                dismissAfter: 0
            });
        });
        if (warnings.length > 5) {
            feedback('warning', `${warnings.length - 5} more future-date warning(s) were detected. Please review the uploaded rows.`, {
                title: 'Review Dates',
                dismissAfter: 0
            });
        }
    }

    const api = {
        tasks,
        run,
        getTask,
        terminate(scope, reason) {
            terminateTask(tasks.get(scope), reason);
        },
        createProgress,
        feedback,
        errorState,
        renderError,
        skeleton,
        showSuccess(message, options) {
            return feedback('success', message, options);
        },
        showWarning(message, options) {
            return feedback('warning', message, options);
        },
        showError(message, options) {
            return feedback('error', message, options);
        },
        dataCache,
        cacheData(scope, key, data, ttl) {
            return dataCache.set(scope, key, data, ttl);
        },
        getCachedData(scope, key) {
            return dataCache.get(scope, key);
        },
        rememberData(scope, key, loader, ttl) {
            return dataCache.remember(scope, key, loader, ttl);
        },
        clearDataCache(scope) {
            dataCache.clear(scope);
        },
        initializeFutureDateWarnings,
        showServerWarnings,
        setButtonLoading,
        withButtonLoading
    };

    window.GlobalTaskStatus = api;
    window.SyluxentUI = api;
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', () => {
            ensureInterface();
            initializeGlobalButtonLoading();
            initializeFutureDateWarnings();
            initializeLogoutCacheCleanup();
            initializeEvaluationModal();
            updateThemeBranding();
            renderAshbyVerse();
        }, { once: true });
    } else {
        ensureInterface();
        initializeGlobalButtonLoading();
        initializeFutureDateWarnings();
        initializeLogoutCacheCleanup();
        initializeEvaluationModal();
        updateThemeBranding();
        renderAshbyVerse();
    }
    document.addEventListener('syluxent-content-updated', event => {
        initializeFutureDateWarnings(event.target || document);
        initializeLogoutCacheCleanup(event.target || document);
        initializeEvaluationModal();
        updateThemeBranding();
    });
    new MutationObserver(mutations => {
        if (mutations.some(mutation => Array.from(mutation.addedNodes).some(node => node.nodeType === 1 && (node.matches?.('input[type="date"]') || node.querySelector?.('input[type="date"]'))))) {
            initializeFutureDateWarnings();
        }
        if (mutations.some(mutation => Array.from(mutation.addedNodes).some(node => node.nodeType === 1 && (node.matches?.('.nav-logo') || node.querySelector?.('.nav-logo'))))) {
            updateThemeBranding();
        }
    }).observe(document.documentElement, { childList: true, subtree: true });
    window.addEventListener('syluxent-theme-mode', event => {
        updateThemeBranding(event.detail?.mode);
        renderAshbyVerse();
    });
})();
