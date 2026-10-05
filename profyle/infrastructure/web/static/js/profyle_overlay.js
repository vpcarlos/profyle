(function() {
    const header = document.createElement('div');
    header.innerText = 'Profyle Trace View';
    header.className = 'profyle-header';

    // Perfetto rebuilds the DOM, so re-attach the header whenever it disappears.
    function ensureElements() {
        if (document.body && !document.body.contains(header)) {
            document.body.appendChild(header);
        }
    }

    const observer = new MutationObserver(ensureElements);
    observer.observe(document, { childList: true, subtree: true });

    if (document.body) ensureElements();
    else document.addEventListener('DOMContentLoaded', ensureElements);
})();
