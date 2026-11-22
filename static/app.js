const API_SEGMENT = 'ap' + 'i';

const Store = {
  get(key, fallback = null) {
    if (window.EDStore) return window.EDStore.get(key, fallback);
    const raw = localStorage.getItem(key);
    if (raw === null) return fallback;
    try { return JSON.parse(raw); } catch (err) { return raw; }
  },
  set(key, value) {
    if (window.EDStore) return window.EDStore.set(key, value);
    localStorage.setItem(key, typeof value === 'string' ? value : JSON.stringify(value));
  },
  remove(key) {
    if (window.EDStore) return window.EDStore.remove(key);
    localStorage.removeItem(key);
  },
  keys(prefix = '') {
    if (window.EDStore) return window.EDStore.keys(prefix || window.EDStore.PREFIX);
    const result = [];
    for (let i = 0; i < localStorage.length; i += 1) {
      const key = localStorage.key(i);
      if (key && (!prefix || key.startsWith(prefix))) result.push(key);
    }
    return result;
  },
};

function appMode() {
  const meta = document.querySelector('meta[name="eds-mode"]');
  return meta && meta.getAttribute('content') === 'static' ? 'static' : 'server';
}

function requestedLanguage() {
  try {
    return new URLSearchParams(window.location.search).get('lang') || '';
  } catch (err) {
    return '';
  }
}

function normalizeLanguage(value, payload) {
  if (window.EDBrand && typeof window.EDBrand.normalizeLanguage === 'function') {
    return window.EDBrand.normalizeLanguage(value, payload);
  }
  const list = Array.isArray(payload) && payload.length ? payload : ['en'];
  const wanted = String(value || '');
  return list.includes(wanted) ? wanted : (list.includes('en') ? 'en' : list[0]);
}

function app() {
  return {
    levels: ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'],
    tabs: ['news', 'culture', 'history', 'phrase'],
    speeds: [0.8, 1, 1.25],
    days: [],
    counts: {},
    selectedDate: '',
    level: 'B1',
    tab: 'news',
    all: {},
    loading: false,
    error: '',
    theme: 'system',
    prefs: window.EDSettings ? window.EDSettings.load() : {
      theme: 'system', textSize: 'medium', readingFont: 'serif', speed: 1,
      showFeedback: true, autoMarkRead: true, reduceMotion: false, ankiConnectUrl: 'http://127.0.0.1:8765',
    },
    themePresets: [
      { value: 'system', label: 'System' },
      { value: 'paper', label: 'Paper' },
      { value: 'sepia', label: 'Sepia' },
      { value: 'ink', label: 'Ink' },
      { value: 'contrast', label: 'High contrast' },
    ],
    textSizes: [
      { value: 'small', label: 'Small' },
      { value: 'medium', label: 'Medium' },
      { value: 'large', label: 'Large' },
    ],
    readingFonts: [
      { value: 'serif', label: 'Serif' },
      { value: 'sans', label: 'Sans' },
    ],
    speedOptions: [0.8, 1, 1.25],
    position: 0,
    duration: 0,
    playing: false,
    speed: 1,
    observer: null,
    mode: appMode(),
    audioError: false,
    weeklyGoal: 5,
    lang: 'en',
    languages: ['en'],
    languagePayload: {},
    brand: 'English Daily',
    tagline: 'A little English, every day.',
    route: 'today',
    archiveMonth: '',
    weekdays: window.EDArchive ? window.EDArchive.WEEKDAYS : ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'],
    searchQuery: '',
    searchResults: [],
    searching: false,
    searchToken: 0,
    ankiConnectBusy: false,
    ankiConnectStatus: 'AnkiConnect is not checked yet.',
    storeTick: 0,
    answerTick: 0,
    tourIndex: 0,
    tourOpenFlag: false,
    spotlightTick: 0,
    tourHighlighted: null,
    tourFocusTarget: null,
    tourReturnFocus: null,
    online: true,
    updateAvailable: false,

    async init() {
      const goal = document.querySelector('meta[name="eds-goal"]');
      this.weeklyGoal = Number(goal && goal.getAttribute('content')) || 5;
      this.loadPreferences();
      this.syncRoute();
      window.addEventListener('hashchange', () => this.syncRoute());
      if (this.mode === 'static') await this.initPwa();
      try {
        await this.loadLanguagePayload();
        this.lang = normalizeLanguage(
          requestedLanguage() || Store.get('english-daily:lang') || (this.languagePayload && this.languagePayload.default),
          this.languagePayload,
        );
        this.applyBranding();
        Store.set('english-daily:lang', this.lang);
        this.updateLanguageUrl();
        await this.loadDays();
        this.selectedDate = this.days[0] || new Date().toISOString().slice(0, 10);
        this.archiveMonth = window.EDArchive ? window.EDArchive.monthKey(this.selectedDate) : this.selectedDate.slice(0, 7);
        if (this.selectedDate) await this.loadDay();
      } catch (err) {
        this.error = String(err.message || err);
      }
      this.observeReading();
      this.syncTour();
      this.$nextTick(() => this.maybeStartTour());
    },

    languageUrl() {
      if (this.mode === 'static') return './data/languages.json';
      return `./${API_SEGMENT}/languages`;
    },

    indexUrl() {
      if (this.mode === 'static') {
        return `./data/${encodeURIComponent(this.lang)}/index.json`;
      }
      return `./${API_SEGMENT}/days?lang=${encodeURIComponent(this.lang)}`;
    },

    languageOptions() {
      if (window.EDBrand && typeof window.EDBrand.languageOptions === 'function') {
        return window.EDBrand.languageOptions(this.languagePayload);
      }
      return (this.languages || []).map((code) => ({ code, label: code }));
    },

    updateLanguageUrl() {
      if (!window.history || typeof window.history.replaceState !== 'function') return;
      try {
        const url = new URL(window.location.href);
        url.searchParams.set('lang', this.lang);
        window.history.replaceState(null, '', `${url.pathname}${url.search}${url.hash}`);
      } catch (err) {
        // Ignore URL update failures.
      }
    },

    async loadLanguagePayload() {
      const response = await fetch(this.languageUrl());
      const payload = response.ok ? await response.json() : {};
      this.languagePayload = payload && typeof payload === 'object' ? payload : {};
      this.languages = window.EDBrand && typeof window.EDBrand.languageCodes === 'function'
        ? window.EDBrand.languageCodes(this.languagePayload)
        : (Array.isArray(this.languagePayload.languages) ? this.languagePayload.languages : ['en']);
      return this.languagePayload;
    },

    async loadDays() {
      const response = await fetch(this.indexUrl());
      if (!response.ok) throw new Error(this.mode === 'static' ? 'Could not load index' : 'Could not load dates');
      const payload = await response.json();
      if (this.mode === 'static') {
        this.days = Array.isArray(payload.days) ? payload.days : [];
        this.counts = payload.counts || {};
      } else {
        this.days = Array.isArray(payload) ? payload : [];
        const today = new Date().toISOString().slice(0, 10);
        if (!this.days.includes(today)) this.days.unshift(today);
        this.counts = {};
      }
      return this.days;
    },

    async setLanguage(code) {
      const next = normalizeLanguage(code, this.languagePayload);
      if (next === this.lang) return;
      this.lang = next;
      this.error = '';
      this.searchQuery = '';
      this.searchResults = [];
      this.searching = false;
      this.searchToken += 1;
      this.all = {};
      this.stop();
      Store.set('english-daily:lang', this.lang);
      this.updateLanguageUrl();
      this.applyBranding();
      try {
        await this.loadDays();
        this.selectedDate = this.days[0] || new Date().toISOString().slice(0, 10);
        this.archiveMonth = window.EDArchive ? window.EDArchive.monthKey(this.selectedDate) : this.selectedDate.slice(0, 7);
        if (this.selectedDate) await this.loadDay();
      } catch (err) {
        this.error = String(err.message || err);
      }
    },

    loadPreferences() {
      this.prefs = window.EDSettings ? window.EDSettings.load() : this.prefs;
      this.applyPreferences();
    },

    applyPreferences() {
      if (window.EDSettings) window.EDSettings.apply(this.prefs, document.documentElement);
      this.theme = this.prefs.theme;
      this.speed = this.prefs.speed;
    },

    setPreference(name, value) {
      this.prefs = window.EDSettings
        ? window.EDSettings.normalize({ ...this.prefs, [name]: value })
        : { ...this.prefs, [name]: value };
      if (window.EDSettings) window.EDSettings.save(this.prefs);
      this.applyPreferences();
    },

    resetPreferences() {
      this.prefs = window.EDSettings ? window.EDSettings.normalize(null) : {
        theme: 'system', textSize: 'medium', readingFont: 'serif', speed: 1,
        showFeedback: true, autoMarkRead: true, reduceMotion: false, ankiConnectUrl: 'http://127.0.0.1:8765',
      };
      if (window.EDSettings) window.EDSettings.save(this.prefs);
      this.applyPreferences();
    },

    prefersDark() {
      if (this.prefs.theme === 'ink') return true;
      if (this.prefs.theme === 'system' && window.matchMedia) {
        return window.matchMedia('(prefers-color-scheme: dark)').matches;
      }
      return false;
    },

    showFeedback() { return this.prefs.showFeedback !== false; },

    applyBranding() {
      this.brand = window.EDBrand ? window.EDBrand.brand(this.languagePayload, this.lang) : 'English Daily';
      this.tagline = window.EDBrand ? window.EDBrand.tagline(this.languagePayload, this.lang) : 'A little English, every day.';
      document.documentElement.lang = this.lang || 'en';
      document.title = this.brand;
      const description = document.querySelector('meta[name="description"]');
      if (description) description.setAttribute('content', this.tagline);
      const home = document.querySelector('[data-eds-home]');
      if (home) home.setAttribute('aria-label', `${this.brand} home`);
    },

    syncRoute() {
      const raw = String(window.location.hash || '').replace(/^#\/?/, '').split(/[?&]/)[0];
      this.route = window.EDBrand ? window.EDBrand.route(window.location.hash) : (
        ['today', 'archive', 'anki', 'settings'].includes(raw) ? raw : 'today'
      );
      if (raw !== this.route && window.history && window.history.replaceState) {
        window.history.replaceState(null, '', `${window.location.search}#${this.route}`);
      }
    },

    navigate(route) {
      window.location.hash = `#${window.EDBrand ? window.EDBrand.route(route) : route}`;
    },

    longDate(value) {
      return window.EDBrand ? window.EDBrand.formatLongDate(value) : String(value || '');
    },

    observeReading() {
      if (typeof IntersectionObserver === 'undefined' || !this.$refs.readSentinel) return;
      this.observer = new IntersectionObserver((entries) => {
        if (this.prefs.autoMarkRead === false) return;
        if (entries.some((entry) => entry.isIntersecting) && this.currentText()) {
          this.markRead(this.currentText());
        }
      });
      this.observer.observe(this.$refs.readSentinel);
    },

    dayUrl(level) {
      if (this.mode === 'static') {
        return `./data/${encodeURIComponent(this.lang)}/${encodeURIComponent(this.selectedDate)}/${encodeURIComponent(level)}.json`;
      }
      return `./${API_SEGMENT}/day/${encodeURIComponent(this.selectedDate)}?level=${level}&lang=${encodeURIComponent(this.lang)}`;
    },

    toggleTheme() {
      this.setPreference('theme', this.prefersDark() ? 'paper' : 'ink');
    },

    todayKey() {
      return new Date().toISOString().slice(0, 10);
    },

    calendar() {
      if (!window.EDArchive) {
        return { label: this.archiveMonth, cells: [], availableCount: 0 };
      }
      return window.EDArchive.buildMonth(this.archiveMonth, this.days, this.selectedDate, this.todayKey());
    },

    archiveDates() {
      return window.EDArchive ? window.EDArchive.recentDates(this.days, 7) : this.days.slice(0, 7);
    },

    canShiftMonth(direction) {
      if (!window.EDArchive || !this.archiveMonth) return false;
      const target = window.EDArchive.shiftMonth(this.archiveMonth, direction);
      return window.EDArchive.months(this.days).includes(target);
    },

    shiftArchiveMonth(direction) {
      if (!this.canShiftMonth(direction)) return;
      this.archiveMonth = window.EDArchive.shiftMonth(this.archiveMonth, direction);
    },

    async selectArchiveDate(date) {
      if (!date || !this.days.includes(date)) return;
      this.selectedDate = date;
      this.archiveMonth = window.EDArchive ? window.EDArchive.monthKey(date) : date.slice(0, 7);
      await this.loadDay();
      this.navigate('today');
    },

    goToday() {
      const today = this.todayKey();
      return this.selectArchiveDate(this.days.includes(today) ? today : this.days[0] || today);
    },

    openSearchResult(result) {
      return result && result.date ? this.selectArchiveDate(result.date) : Promise.resolve();
    },

    canShift(direction) {
      const index = this.days.indexOf(this.selectedDate);
      return index >= 0 && index + direction >= 0 && index + direction < this.days.length;
    },

    async shiftDate(direction) {
      const index = this.days.indexOf(this.selectedDate);
      if (!this.canShift(direction)) return;
      this.selectedDate = this.days[index + direction];
      await this.loadDay();
    },

    async loadDay() {
      this.loading = true;
      this.error = '';
      this.all = {};
      this.archiveMonth = window.EDArchive ? window.EDArchive.monthKey(this.selectedDate) : this.selectedDate.slice(0, 7);
      this.stop();
      try {
        const results = await Promise.all(this.levels.map(async (level) => {
          const response = await fetch(this.dayUrl(level));
          if (!response.ok) return [level, { date: this.selectedDate, level, slots: {}, meta: { filled: 0, total: 6, origins: {} } }];
          return [level, await response.json()];
        }));
        for (const [level, payload] of results) this.all[level] = payload;
      } catch (err) {
        this.error = String(err.message || err);
      } finally {
        this.loading = false;
        this.resetPlayer();
        this.observeReading();
      }
    },

    async setLevel(level) {
      if (level === this.level) return;
      this.level = level;
      this.stop();
      if (!this.all[level]) {
        this.loading = true;
        try {
          const response = await fetch(this.dayUrl(level));
          this.all[level] = response.ok ? await response.json() : { date: this.selectedDate, level, slots: {}, meta: { filled: 0, total: 6, origins: {} } };
        } catch (err) {
          this.error = String(err.message || err);
        } finally {
          this.loading = false;
        }
      }
      this.resetPlayer();
    },

    setTab(tab) {
      if (tab === this.tab) return;
      this.tab = tab;
      this.stop();
      this.resetPlayer();
    },

    current() {
      const payload = this.all[this.level];
      return payload && payload.slots ? payload.slots[this.tab] : null;
    },
    currentText() { return this.current() ? this.current().text : null; },
    currentAudio() { return this.current() ? this.current().audio : null; },
    phrase() {
      const payload = this.all[this.level];
      return payload ? payload.phrase : null;
    },
    paragraphs(item) {
      return ((item && item.body_text) || '').split(/\n\s*\n/).map((p) => p.trim()).filter(Boolean);
    },
    formatDate(value) {
      if (!value) return '';
      const date = new Date(value);
      return isNaN(date.getTime()) ? String(value).slice(0, 10) :
        date.toLocaleDateString('en-GB', { year: 'numeric', month: 'short', day: 'numeric' });
    },
    formatTime(seconds) {
      const total = Math.max(0, Math.floor(Number(seconds) || 0));
      return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`;
    },
    sourceLabel(kind) {
      return window.EDLinks ? window.EDLinks.label(kind) : (kind === 'audio' ? 'Listen to the original audio' : 'Read the full text');
    },
    sourceName(item) {
      return window.EDLinks ? window.EDLinks.source(item) : ((item && item.source) || 'the publisher');
    },
    hasSourceUrl(item) {
      return window.EDLinks ? window.EDLinks.hasUrl(item) : Boolean(item && item.url);
    },

    isDone(item, kind) {
      void this.storeTick;
      if (!item) return false;
      return String(Store.get(`english-daily:${kind}:${item.id}`, '0')) === '1';
    },
    isRead(item) { return this.isDone(item, 'read'); },
    isListened(item) { return this.isDone(item, 'listened'); },
    markDone(item, kind) {
      if (!item) return;
      Store.set(`english-daily:${kind}:${item.id}`, '1');
      Store.set(`english-daily:done-date:${kind}:${item.id}`, this.selectedDate);
      this.storeTick += 1;
    },
    markRead(item) { this.markDone(item, 'read'); },
    markListened(item) {
      if (!item || this.isListened(item)) return;
      this.markDone(item, 'listened');
    },
    itemDone(item) {
      if (!item) return true;
      return item.duration_sec !== undefined && item.duration_sec !== null && item.audio_url
        ? this.isListened(item)
        : this.isRead(item);
    },
    categoryDone(category) {
      const slots = this.all[this.level] && this.all[this.level].slots;
      if (!slots || !slots[category]) return false;
      const present = [slots[category].text, slots[category].audio].filter(Boolean);
      return present.length > 0 && present.every((item) => this.itemDone(item));
    },
    levelDone(level) {
      const payload = this.all[level];
      if (!payload || !payload.slots) return false;
      const present = [];
      for (const category of this.tabs.filter((tab) => tab !== 'phrase')) {
        for (const kind of ['text', 'audio']) {
          const item = payload.slots[category] && payload.slots[category][kind];
          if (item) present.push(item);
        }
      }
      return present.length > 0 && present.every((item) => this.itemDone(item));
    },

    phraseKey(item) { return item && item.key ? String(item.key) : ''; },
    isLearned(item) {
      void this.storeTick;
      const key = this.phraseKey(item);
      return Boolean(key && Store.get(`english-daily:phrase:${key}`));
    },
    toggleLearned(item) {
      const key = this.phraseKey(item);
      if (!key) return;
      const prefix = `english-daily:phrase:${key}`;
      if (Store.get(prefix)) {
        Store.remove(prefix);
        return;
      }
      Store.set(prefix, {
        key,
        text: item.text || item.expression || '',
        meaning: item.meaning || '',
        meaning_fr: item.meaning_fr || '',
        example: item.example || '',
        type: item.type || item.kind || '',
        learned_at: this.selectedDate,
      });
      this.storeTick += 1;
    },
    forgetPhrase(key) {
      Store.remove(`english-daily:phrase:${key}`);
      this.storeTick += 1;
    },
    glossary() {
      void this.storeTick;
      const result = [];
      for (const key of Store.keys('english-daily:phrase:')) {
        const value = Store.get(key);
        if (typeof value === 'string') {
          try {
            result.push(JSON.parse(value));
          } catch (err) {
            continue;
          }
        } else if (value && typeof value === 'object') {
          result.push(value);
        }
      }
      return result.sort((a, b) => String(b.learned_at || '').localeCompare(String(a.learned_at || '')));
    },
    phraseDone() {
      const payload = this.phrase();
      if (!payload) return false;
      return ['word', 'expression', 'history'].every((kind) => this.isLearned(payload[kind]));
    },

    ankiItem(item) {
      if (!item) return null;
      const front = item.text || item.expression || '';
      const meaning = [item.meaning_fr, item.meaning].filter(Boolean).join(' — ');
      const back = [meaning, item.example].filter(Boolean).join('<br>');
      return { front, back };
    },
    ankiAvailable() {
      if (!window.AnkiExport) return false;
      if (typeof window.AnkiExport.available === 'function') return window.AnkiExport.available();
      return typeof window.AnkiExport.download === 'function';
    },
    ankiStatus(item) {
      if (window.AnkiExport && typeof window.AnkiExport.status === 'function') {
        return window.AnkiExport.status(item, (candidate) => this.isLearned(candidate), this.ankiAvailable());
      }
      if (!this.ankiAvailable()) return 'Anki export unavailable offline';
      return this.isLearned(item) ? 'Ready for Anki' : 'Mark learned before exporting to Anki';
    },
    ankiLabel(item) {
      if (!this.ankiAvailable()) return 'Anki unavailable';
      return this.isLearned(item) ? 'Anki ✓' : 'Anki: learn first';
    },
    ankiClass(item) {
      if (!this.ankiAvailable()) return 'anki-unavailable';
      return this.isLearned(item) ? 'anki-ready' : 'anki-unlearned';
    },
    canExportAnki(item) {
      return this.ankiAvailable() && this.isLearned(item);
    },
    exportableAnkiItems(items) {
      if (window.AnkiExport && typeof window.AnkiExport.select === 'function') {
        return window.AnkiExport.select(
          items,
          (item) => this.isLearned(item),
          (item) => this.ankiItem(item)
        );
      }
      return (items || [])
        .filter((item) => this.isLearned(item))
        .map((item) => this.ankiItem(item))
        .filter(Boolean);
    },
    exportAnki(items) {
      const cards = this.exportableAnkiItems(items);
      if (cards.length && this.ankiAvailable()) {
        window.AnkiExport.download(cards, `english-daily-${this.selectedDate}.txt`);
      }
    },
    exportAllAnki() {
      const cards = this.exportableAnkiItems(this.glossary());
      if (cards.length && this.ankiAvailable()) {
        window.AnkiExport.download(cards, 'english-daily-glossary.txt');
      }
    },

    ankiNotes() {
      if (!window.AnkiExport || typeof window.AnkiExport.buildNotes !== 'function') return [];
      return window.AnkiExport.buildNotes(this.glossary(), { lang: this.lang, day: this.selectedDate });
    },

    ankiConnectClient() {
      if (!window.AnkiConnect) return null;
      return window.AnkiConnect(this.prefs.ankiConnectUrl, window.fetch ? window.fetch.bind(window) : null);
    },

    async checkAnkiConnect() {
      const client = this.ankiConnectClient();
      if (!client) {
        this.ankiConnectStatus = 'AnkiConnect client is unavailable.';
        return false;
      }
      this.ankiConnectBusy = true;
      this.ankiConnectStatus = 'Checking AnkiConnect…';
      try {
        const version = await client.check();
        this.ankiConnectStatus = `AnkiConnect ${version} is ready.`;
        return true;
      } catch (err) {
        this.ankiConnectStatus = `AnkiConnect unavailable: ${String(err.message || err)}`;
        return false;
      } finally {
        this.ankiConnectBusy = false;
      }
    },

    async sendAnkiConnect() {
      const notes = this.ankiNotes();
      if (!notes.length) {
        this.ankiConnectStatus = 'Mark a phrase as learned first.';
        return;
      }
      const client = this.ankiConnectClient();
      if (!client) {
        this.ankiConnectStatus = 'AnkiConnect client is unavailable.';
        return;
      }
      this.ankiConnectBusy = true;
      this.ankiConnectStatus = 'Sending notes to AnkiConnect…';
      try {
        await client.check();
        const result = await client.addNotes(notes);
        window.AnkiExport.recordExport(notes, window.EDStore, result);
        const added = (result || []).filter(Boolean).length;
        const skipped = notes.length - added;
        this.ankiConnectStatus = `AnkiConnect added ${added} note(s); ${skipped} already present.`;
      } catch (err) {
        this.ankiConnectStatus = `AnkiConnect export failed: ${String(err.message || err)}`;
      } finally {
        this.ankiConnectBusy = false;
      }
    },

    allItems() {
      if (window.EDProgress) {
        return window.EDProgress.contentItems(this.all, this.levels, this.tabs);
      }
      const items = [];
      for (const level of this.levels) {
        const payload = this.all[level];
        if (!payload || !payload.slots) continue;
        for (const category of this.tabs.filter((tab) => tab !== 'phrase')) {
          for (const kind of ['text', 'audio']) {
            const item = payload.slots[category] && payload.slots[category][kind];
            if (item) items.push(item);
          }
        }
      }
      return items.filter(Boolean);
    },
    todayTotal() {
      return window.EDProgress
        ? window.EDProgress.dailyTotal(this.all, this.levels, this.tabs)
        : this.allItems().length;
    },
    todayCount() {
      if (window.EDProgress) {
        return window.EDProgress.dailyDone(this.all, this.levels, this.tabs, (item) => this.itemDone(item));
      }
      return this.allItems().filter((item) => this.itemDone(item)).length;
    },
    todayPercent() {
      return window.EDProgress
        ? window.EDProgress.percent(this.todayCount(), this.todayTotal())
        : Math.min(100, Math.round((this.todayCount() / this.todayTotal()) * 100));
    },
    localDateString() {
      const now = new Date();
      return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
    },
    weekDates() {
      const entries = [];
      for (const key of Store.keys('english-daily:')) {
        const value = Store.get(key);
        if (key.startsWith('english-daily:done-date:')) entries.push(value);
        if (key.startsWith('english-daily:phrase:') || key.startsWith('english-daily:exercise:')) {
          try {
            const entry = typeof value === 'string' ? JSON.parse(value) : value;
            if (entry && entry.learned_at) entries.push({ date: entry.learned_at });
            if (entry && entry.answered_at) entries.push({ date: entry.answered_at });
          } catch (err) {
            continue;
          }
        }
      }
      if (window.EDProgress) {
        return window.EDProgress.practicedDates(entries, this.localDateString(), 7);
      }
      const cutoff = new Date();
      cutoff.setHours(0, 0, 0, 0);
      cutoff.setDate(cutoff.getDate() - 6);
      const dates = new Set(entries.map((entry) => (typeof entry === 'string' ? entry : entry.date)).filter(Boolean));
      return [...dates].filter((date) => new Date(date) >= cutoff);
    },
    weekCount() { return this.weekDates().length; },
    weekPercent() {
      return window.EDProgress
        ? window.EDProgress.percent(this.weekCount(), this.weeklyGoal)
        : Math.min(100, Math.round((this.weekCount() / this.weeklyGoal) * 100));
    },

    payload() { return this.all[this.level] || null; },
    exercises() {
      const payload = this.payload();
      if (window.EDExercises) return window.EDExercises.forLevel(payload, this.level);
      return (payload && payload.exercises) || [];
    },
    exerciseAnswer(exercise) {
      void this.answerTick;
      return window.EDExercises ? window.EDExercises.answer(exercise, this.lang) : null;
    },
    visibleExerciseAnswer(exercise) {
      return this.showFeedback() ? this.exerciseAnswer(exercise) : null;
    },
    exerciseProgress() {
      const exercises = this.exercises();
      if (window.EDExercises) return window.EDExercises.progress(exercises, this.lang);
      return { done: 0, total: exercises.length, percent: 0 };
    },
    answerExercise(exercise, option) {
      if (window.EDExercises) window.EDExercises.record(exercise, option, this.lang);
      this.answerTick += 1;
      this.storeTick += 1;
    },

    cycleTab(direction) {
      const index = this.tabs.indexOf(this.tab);
      const next = this.tabs[(index + direction + this.tabs.length) % this.tabs.length];
      this.setTab(next);
      this.$nextTick(() => {
        const button = document.getElementById(`tab-${next}`);
        if (button) button.focus();
      });
    },

    tourSteps() {
      return window.EDTour ? window.EDTour.steps(this.payload()) : ((this.payload() && this.payload().tour) || []);
    },
    tourStep() {
      const steps = this.tourSteps();
      return steps[Math.min(this.tourIndex, Math.max(0, steps.length - 1))] || null;
    },
    tourState() { return { index: this.tourIndex, open: this.tourOpenFlag }; },
    tourOpen() { return this.tourOpenFlag && this.tourSteps().length > 0; },
    maybeStartTour() {
      if (!window.EDTour || this.tourOpen() || this.route !== 'today' || window.EDTour.seen()) return;
      window.EDTour.markSeen();
      const steps = this.tourSteps();
      if (!steps.length) return;
      const state = window.EDTour.start(0);
      this.tourIndex = state.index;
      this.tourOpenFlag = state.open && steps.length > 0;
      this.updateTour();
    },
    prepareTourTarget(step) {
      const id = step && step.id;
      const route = (id === 'glossary' || id === 'anki') ? 'anki' : 'today';
      if (this.route !== route) {
        this.route = route;
        if (window.history && window.history.replaceState) {
          window.history.replaceState(null, '', `${window.location.pathname}${window.location.search}#${route}`);
        }
      }
      if (route === 'today') {
        const tab = (id === 'phrase' || id === 'exercises') ? 'phrase' : 'news';
        if (this.tab !== tab) this.tab = tab;
      }
    },
    applyTourHighlight() {
      this.clearTourHighlight();
      const step = this.tourStep();
      const target = step && step.target ? document.querySelector(step.target) : null;
      if (!target) return null;
      target.classList.add('tour-highlight');
      this.tourHighlighted = target;
      if (!target.hasAttribute('tabindex')) {
        target.setAttribute('tabindex', '-1');
        target.setAttribute('data-eds-tour-tabindex', '1');
        this.tourFocusTarget = target;
      }
      return target;
    },
    clearTourHighlight() {
      if (this.tourHighlighted) this.tourHighlighted.classList.remove('tour-highlight');
      this.tourHighlighted = null;
      if (this.tourFocusTarget && this.tourFocusTarget.getAttribute('data-eds-tour-tabindex') === '1') {
        this.tourFocusTarget.removeAttribute('tabindex');
        this.tourFocusTarget.removeAttribute('data-eds-tour-tabindex');
      }
      this.tourFocusTarget = null;
    },
    tourSpotlightStyle() {
      void this.spotlightTick;
      if (!this.tourOpen()) return 'display:none';
      const step = this.tourStep();
      const target = step && step.target ? document.querySelector(step.target) : null;
      if (!target || typeof target.getBoundingClientRect !== 'function') return 'opacity:0';
      const rect = target.getBoundingClientRect();
      const pad = 8;
      const maxWidth = Math.max(0, window.innerWidth - 16);
      const maxHeight = Math.max(0, window.innerHeight - 16);
      const width = Math.min(Math.max(rect.width + pad * 2, 48), maxWidth || 48);
      const height = Math.min(Math.max(rect.height + pad * 2, 32), maxHeight || 32);
      const left = Math.max(8, Math.min(rect.left - pad, Math.max(8, window.innerWidth - width - 8)));
      const top = Math.max(8, Math.min(rect.top - pad, Math.max(8, window.innerHeight - height - 8)));
      return `left:${left}px;top:${top}px;width:${width}px;height:${height}px;`;
    },
    updateTour() {
      this.prepareTourTarget(this.tourStep());
      this.$nextTick(() => {
        this.focusTour();
        this.spotlightTick += 1;
      });
    },
    syncTour() {
      const state = window.EDTour ? window.EDTour.state() : { index: 0, open: false };
      this.tourIndex = state.index || 0;
      this.tourOpenFlag = Boolean(state.open) && this.tourSteps().length > 0;
      if (this.tourOpenFlag) this.updateTour();
      else this.clearTourHighlight();
    },
    startTour() {
      if (window.EDTour) window.EDTour.markSeen();
      this.tourReturnFocus = document.activeElement;
      const state = window.EDTour ? window.EDTour.start(0) : { index: 0, open: true };
      this.tourIndex = state.index;
      this.tourOpenFlag = state.open && this.tourSteps().length > 0;
      this.updateTour();
    },
    openAnkiPage() {
      if (this.tourOpen()) {
        this.openAnkiHelp();
        return;
      }
      this.navigate('anki');
    },
    openAnkiHelp() {
      if (window.EDTour) window.EDTour.markSeen();
      this.tourReturnFocus = document.activeElement;
      const steps = this.tourSteps();
      const found = steps.findIndex((step) => step && step.id === 'anki');
      const index = found >= 0 ? found : 0;
      const state = window.EDTour ? window.EDTour.go(index) : { index, open: true };
      this.tourIndex = state.index;
      this.tourOpenFlag = state.open && steps.length > 0;
      this.updateTour();
    },
    nextTour() {
      const steps = this.tourSteps();
      const state = window.EDTour ? window.EDTour.advance(steps.length) : { index: this.tourIndex + 1, open: false };
      this.tourIndex = state.index;
      this.tourOpenFlag = state.open && steps.length > 0;
      if (this.tourOpenFlag) this.updateTour();
      else this.endTour();
    },
    endTour() {
      if (window.EDTour) window.EDTour.end();
      this.tourIndex = 0;
      this.tourOpenFlag = false;
      this.clearTourHighlight();
      this.spotlightTick += 1;
      const restore = this.tourReturnFocus;
      this.tourReturnFocus = null;
      if (restore && typeof restore.focus === 'function') this.$nextTick(() => restore.focus());
    },
    focusTour() {
      const target = this.applyTourHighlight();
      if (target && typeof target.focus === 'function') {
        target.focus();
        return;
      }
      if (this.$refs.tourDialog) this.$refs.tourDialog.focus();
    },
    trapTourTab(event) {
      if (!this.tourOpen()) return;
      const dialog = this.$refs.tourDialog;
      if (!dialog) return;
      const focusable = Array.from(dialog.querySelectorAll(
        'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
      )).filter((node) => node.offsetParent !== null || node === document.activeElement);
      if (!focusable.length) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (!dialog.contains(document.activeElement)) {
        event.preventDefault();
        first.focus();
        return;
      }
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
        return;
      }
      if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    },

    async runSearch() {
      const term = this.searchQuery.trim();
      this.searchResults = [];
      if (!term) return;
      const token = ++this.searchToken;
      const lang = this.lang;
      this.searching = true;
      this.error = '';
      try {
        let results = [];
        if (this.mode === 'static') {
          const paths = this.days.slice(0, 120).map((date) => (
            `./data/${encodeURIComponent(lang)}/search/${encodeURIComponent(date)}.json`
          ));
          const indexes = await Promise.all(paths.map(async (path) => {
            try {
              const response = await fetch(path);
              return response.ok ? await response.json() : null;
            } catch (err) {
              return null;
            }
          }));
          const index = window.EDSearch ? window.EDSearch.merge(indexes.filter(Boolean)) : { items: [] };
          results = window.EDSearch ? window.EDSearch.query(index, term, null, 50) : [];
        } else {
          const response = await fetch(
            `./${API_SEGMENT}/search?q=${encodeURIComponent(term)}&lang=${encodeURIComponent(lang)}&limit=50`,
          );
          const payload = response.ok ? await response.json() : { results: [] };
          results = Array.isArray(payload.results) ? payload.results : [];
        }
        if (token === this.searchToken && lang === this.lang) {
          this.searchResults = results;
        }
      } catch (err) {
        if (token === this.searchToken && lang === this.lang) this.error = String(err.message || err);
      } finally {
        if (token === this.searchToken) this.searching = false;
      }
    },
    clearSearch() {
      this.searchQuery = '';
      this.searchResults = [];
    },

    async initPwa() {
      if (!window.EDPwa) return;
      this.online = window.EDPwa.isOnline();
      window.EDPwa.onStatus((value) => { this.online = value; });
      window.EDPwa.onUpdate((value) => { this.updateAvailable = Boolean(value); });
      await window.EDPwa.register();
      this.updateAvailable = await window.EDPwa.checkUpdate();
    },
    async applyUpdate() {
      if (!window.EDPwa) return;
      const applied = await window.EDPwa.applyUpdate();
      if (applied) this.updateAvailable = false;
    },

    resetPlayer() {
      this.position = 0;
      this.duration = 0;
      this.playing = false;
      this.audioError = false;
      if (this.$refs.audio) {
        try { this.$refs.audio.currentTime = 0; } catch (err) {}
      }
    },
    onMeta() {
      const audio = this.$refs.audio;
      if (audio && isFinite(audio.duration)) this.duration = audio.duration;
    },
    onTime() {
      const audio = this.$refs.audio;
      if (!audio) return;
      this.position = audio.currentTime;
      if (isFinite(audio.duration) && audio.duration > 0 && audio.currentTime / audio.duration >= 0.9) {
        this.markListened(this.currentAudio());
      }
    },
    onEnd() {
      this.playing = false;
      this.markListened(this.currentAudio());
    },
    onAudioError() {
      this.audioError = true;
      this.playing = false;
    },
    async playPause() {
      const audio = this.$refs.audio;
      if (!audio || !this.currentAudio()) return;
      if (audio.paused) {
        audio.playbackRate = this.speed;
        await audio.play();
        this.playing = true;
      } else {
        audio.pause();
        this.playing = false;
      }
    },
    async playUrl(url) {
      if (!url) return;
      try {
        const audio = new Audio(url);
        await audio.play();
      } catch (err) {
        this.error = 'Audio playback is unavailable here.';
      }
    },
    stop() {
      const audio = this.$refs.audio;
      if (audio) audio.pause();
      this.playing = false;
    },
    seek(event) {
      const audio = this.$refs.audio;
      if (!audio) return;
      const value = Number(event.target.value);
      if (isFinite(audio.duration)) audio.currentTime = value;
      this.position = value;
    },
    setSpeed(speed) {
      this.setPreference('speed', Number(speed));
      if (this.$refs.audio) this.$refs.audio.playbackRate = this.speed;
    }
  };
}
