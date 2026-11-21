window.EDPwa = (() => {
  let registration = null;
  let reloadHandler = null;

  function isOnline() {
    return typeof navigator.onLine === 'boolean' ? navigator.onLine : true;
  }

  async function register() {
    if (!('serviceWorker' in navigator) || location.protocol === 'file:') return null;
    try {
      registration = await navigator.serviceWorker.register('./sw.js');
      if (registration.waiting) {
        registration.addEventListener('updatefound', () => {});
      }
      return registration;
    } catch (err) {
      return null;
    }
  }

  function onStatus(callback) {
    if (typeof callback !== 'function') return;
    window.addEventListener('online', () => callback(true));
    window.addEventListener('offline', () => callback(false));
  }

  function onUpdate(callback) {
    reloadHandler = callback;
    if ('serviceWorker' in navigator) {
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        if (reloadHandler) reloadHandler();
      });
    }
    if (registration && registration.addEventListener) {
      registration.addEventListener('updatefound', () => {
        const worker = registration.installing;
        if (!worker) return;
        worker.addEventListener('statechange', () => {
          if (worker.state === 'installed' && navigator.serviceWorker.controller) callback(true);
        });
      });
    }
  }

  async function checkUpdate() {
    if (!registration) return false;
    try {
      await registration.update();
      return Boolean(registration.waiting || registration.installing);
    } catch (err) {
      return false;
    }
  }

  async function applyUpdate() {
    if (registration && registration.waiting) {
      registration.waiting.postMessage({ type: 'SKIP_WAITING' });
      return true;
    }
    return checkUpdate();
  }

  return { register, isOnline, onStatus, onUpdate, checkUpdate, applyUpdate };
})();
