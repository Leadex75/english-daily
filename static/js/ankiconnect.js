(function () {
  const DEFAULT_URL = 'http://127.0.0.1:8765';
  const DEFAULT_PROXY = './api/ankiconnect';
  const DEFAULT_MODELS = './data/anki_models.json';
  const ALLOWED_ACTIONS = ['version', 'requestPermission', 'modelFieldNames', 'createModel', 'addNotes'];
  const FALLBACK_FIELDS = ['Front', 'Back', 'Example', 'Source', 'Level', 'Language', 'Date', 'Guid'];

  function browserOrigin() {
    try {
      return window.location.origin || 'http://localhost';
    } catch (err) {
      return 'http://localhost';
    }
  }

  function normalizeUrl(value, fallback) {
    const raw = String(value || '').trim();
    return raw || fallback;
  }

  function responseError(response, viaProxy) {
    const err = new Error(`AnkiConnect returned HTTP ${response.status}`);
    err.status = response.status;
    err.kind = viaProxy ? 'proxy' : 'http';
    return err;
  }

  function diagnostic(error) {
    const message = String((error && error.message) || error || '');
    const lowered = message.toLowerCase();
    if (lowered.includes('permission')) {
      return 'Open Anki, choose AnkiConnect › Config, grant access to this browser, then try again.';
    }
    if ((error && (error.kind === 'cors' || error.status === 0)) || lowered.includes('failed to fetch')) {
      return `AnkiConnect could not be reached. Start Anki, then add ${browserOrigin()} to webCorsOriginList if the browser blocked it, or use the desktop app proxy on port 8731.`;
    }
    if (error && error.status === 403) {
      return `AnkiConnect rejected this origin. Add ${browserOrigin()} to webCorsOriginList, or use the desktop app proxy on port 8731.`;
    }
    if (error && (error.status === 502 || lowered.includes('not running') || lowered.includes('unreachable'))) {
      return 'Start Anki with AnkiConnect installed, then try again.';
    }
    return message || 'AnkiConnect is unavailable.';
  }

  function createClient(options) {
    const opts = options || {};
    const directUrl = normalizeUrl(opts.url || opts.ankiConnectUrl, DEFAULT_URL).replace(/\/+$/, '');
    const proxyUrl = opts.proxyUrl === null || opts.proxyUrl === false ? '' : String(opts.proxyUrl || DEFAULT_PROXY);
    const modelUrl = String(opts.modelUrl || DEFAULT_MODELS);
    const send = opts.fetchImpl || (typeof window !== 'undefined' && typeof window.fetch === 'function'
      ? window.fetch.bind(window)
      : null);
    let mode = 'unknown';
    let modelCache = null;

    async function rawRequest(url, payload, viaProxy) {
      if (!send) throw new Error('Network fetch is unavailable');
      const response = await send(url, {
        method: 'POST',
        headers: {
          'Content-Type': viaProxy ? 'application/json' : 'text/plain',
          'Accept': 'application/json',
        },
        body: JSON.stringify({
          action: payload.action,
          version: 6,
          params: payload.params || {},
        }),
      });
      if (!response.ok) throw responseError(response, viaProxy);
      const result = await response.json();
      if (result && result.error) {
        const err = new Error(String(result.error));
        err.kind = 'anki';
        err.status = 502;
        throw err;
      }
      return result ? result.result : null;
    }

    async function detect() {
      if (mode !== 'unknown') return mode;
      if (proxyUrl) {
        try {
          const version = await rawRequest(proxyUrl, { action: 'version' }, true);
          if (Number(version) >= 6) {
            mode = 'proxy';
            return mode;
          }
        } catch (err) {
          if (!(err.status === 404 || err.status === 405)) mode = 'direct';
        }
      }
      mode = 'direct';
      return mode;
    }

    async function invoke(action, params) {
      if (!ALLOWED_ACTIONS.includes(action)) throw new Error(`AnkiConnect action is not allowed: ${action}`);
      await detect();
      const url = mode === 'proxy' ? proxyUrl : directUrl;
      return rawRequest(url, { action, params }, mode === 'proxy');
    }

    async function loadModels() {
      if (modelCache) return modelCache;
      if (!send) return {};
      try {
        const response = await send(modelUrl, { method: 'GET', headers: { 'Accept': 'application/json' } });
        if (!response.ok) return {};
        const payload = await response.json();
        const map = {};
        for (const model of (payload && payload.models) || []) {
          if (model && model.modelName) map[model.modelName] = model;
        }
        modelCache = map;
        return map;
      } catch (err) {
        return {};
      }
    }

    async function verifyModels(notes) {
      const names = [...new Set((notes || []).map((note) => note && note.modelName).filter(Boolean))];
      const models = await loadModels();
      const report = [];
      for (const name of names) {
        const definition = models[name];
        const expected = (definition && definition.inOrderFields) || FALLBACK_FIELDS;
        let fields = [];
        try {
          const result = await invoke('modelFieldNames', { modelName: name });
          if (Array.isArray(result)) fields = result.map(String);
        } catch (err) {
          const lowered = String(err.message || '').toLowerCase();
          if (!lowered.includes('model') || !lowered.includes('not found')) throw err;
        }
        const missingBefore = expected.filter((field) => !fields.includes(field));
        if (definition && missingBefore.length) {
          await invoke('createModel', definition);
          fields = fields.concat(expected.filter((field) => !fields.includes(field)));
        }
        const missing = expected.filter((field) => !fields.includes(field));
        report.push({ modelName: name, fields, expected, missing, created: !fields.length });
        if (missing.length) {
          const err = new Error(`Model ${name} is missing fields: ${missing.join(', ')}`);
          err.kind = 'model';
          throw err;
        }
      }
      return report;
    }

    return {
      url: directUrl,
      proxyUrl,
      get mode() { return mode; },
      diagnostic,
      invoke,
      async check() {
        await detect();
        const version = Number(await invoke('version'));
        if (version < 6) throw new Error('AnkiConnect version 6 or newer is required');
        return { version, mode, url: mode === 'proxy' ? proxyUrl : directUrl };
      },
      async requestPermission() {
        return invoke('requestPermission');
      },
      loadModels,
      verifyModels,
      async addNotes(notes) {
        const list = Array.isArray(notes) ? notes : [];
        const results = await invoke('addNotes', { notes: list });
        const values = Array.isArray(results) ? results : [];
        const added = values.filter((item) => item !== null && item !== false && item !== undefined).length;
        const duplicates = values.filter((item) => item === null || item === false).length;
        return { total: list.length, added, duplicates, failed: list.length - values.length, results: values };
      },
    };
  }

  const api = { createClient, diagnostic, DEFAULT_URL, DEFAULT_PROXY, DEFAULT_MODELS, ALLOWED_ACTIONS };
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  if (typeof window !== 'undefined') window.EDAnkiConnect = api;
}());
