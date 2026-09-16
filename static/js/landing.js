(() => {
    'use strict';
    const header = document.querySelector('#landing-proposal .lp-nav');
    if (!header) return;
    const brand = header.querySelector('.lp-brand');
    const links = header.querySelector('.lp-navlinks');
    const reducedMotion = window.matchMedia('(prefers-reduced-motion: reduce)');
    let frame = null;
    let dimensions;

    function measure() {
        const width = header.clientWidth;
        const padding = width * 0.05;
        const brandWidth = brand.offsetWidth;
        dimensions = {
            padding,
            centeredLeft: (width - brandWidth) / 2,
            linksCenteredLeft: (width - links.offsetWidth) / 2,
            linksCompactLeft: width - padding - links.offsetWidth,
            compactScale: Math.min(0.52, (width - padding * 2 - links.offsetWidth - 18) / brandWidth),
        };
        schedule();
    }

    function draw() {
        frame = null;
        // No document height changes: the original header space stays in flow.
        let progress = Math.min(1, Math.max(0, window.scrollY / 284));
        if (reducedMotion.matches) progress = progress >= 0.5 ? 1 : 0;
        const { padding, centeredLeft, compactScale, linksCenteredLeft, linksCompactLeft } = dimensions;
        header.style.setProperty('--header-height', `${360 - 284 * progress}px`);
        header.style.setProperty('--brand-top', `${132 - 94 * progress}px`);
        header.style.setProperty('--brand-left', `${centeredLeft + (padding - centeredLeft) * progress}px`);
        header.style.setProperty('--brand-scale', `${1 + (compactScale - 1) * progress}`);
        header.style.setProperty('--links-left', `${linksCenteredLeft + (linksCompactLeft - linksCenteredLeft) * progress}px`);
        header.style.setProperty('--links-top', `${278 - 262 * progress}px`);
        header.style.setProperty('--tagline-opacity', `${Math.max(0, 1 - progress * 3)}`);
        header.style.setProperty('--tagline-offset', `${-30 * progress}px`);
        header.querySelector('.lp-header-tagline').setAttribute('aria-hidden', String(progress >= 1 / 3));
        header.classList.add('is-ready');
    }

    function schedule() {
        if (frame === null) frame = requestAnimationFrame(draw);
    }

    window.addEventListener('scroll', schedule, { passive: true });
    window.addEventListener('resize', measure);
    window.addEventListener('pageshow', measure);
    reducedMotion.addEventListener('change', schedule);
    measure();
    if (document.fonts) document.fonts.ready.then(measure);
})();
