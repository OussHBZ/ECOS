// Retry identity survives reload within the tab; clinical text is never stored.
(() => {
    const pending = new Map();
    window.kardioxDelivery = {
        async key(url, value) {
            const slot = `kardiox:delivery:${url}`;
            const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
            const digest = Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, '0')).join('');
            let previous = pending.get(slot);
            try { previous = JSON.parse(sessionStorage.getItem(slot)) || previous; } catch (_) {}
            if (previous?.digest === digest) return previous.key;
            const entry = {digest, key: crypto.randomUUID()};
            pending.set(slot, entry);
            try { sessionStorage.setItem(slot, JSON.stringify(entry)); } catch (_) {}
            return entry.key;
        },
        clear(url) {
            const slot = `kardiox:delivery:${url}`;
            pending.delete(slot);
            try { sessionStorage.removeItem(slot); } catch (_) {}
        }
    };
})();
