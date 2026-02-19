(() => {
  const endpoint = window.BLOG_ANALYTICS_ENDPOINT || null;
  const debug = window.location.search.includes('debugAnalytics');

  function track(eventName, metadata = {}) {
    if (!eventName) return;

    if (typeof window.plausible === 'function') {
      window.plausible(eventName, { props: metadata });
    }

    if (endpoint) {
      const payload = {
        name: eventName,
        url: window.location.href,
        domain: window.location.hostname,
        meta: metadata,
        ts: Date.now()
      };

      try {
        const blob = new Blob([JSON.stringify(payload)], { type: 'application/json' });
        if (!navigator.sendBeacon || !navigator.sendBeacon(endpoint, blob)) {
          fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
            keepalive: true
          }).catch(() => {});
        }
      } catch (error) {
        console.warn('Blog analytics beacon failed', error);
      }
    } else if (debug) {
      console.info('[blog analytics]', eventName, metadata);
    }
  }

  window.blogAnalytics = { track };
})();
