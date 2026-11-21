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

function normalizeLanguage(value, languages) {
  const list = Array.isArray(languages) && languages.length ? languages : ['en'];
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
      showFeedback: true, autoMarkRead: true, reduceMotion: false,
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
    searchQuery: '',
    searchResults: [],
    searching: false,
    storeTick: 0,
    answerTick: 0,
    tourIndex: 0,
    tourOpenFlag: false,
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
        let languagesPayload = {};
        if (this.mode === 'static') {
          const languagesResponse = await fetch('./data/languages.json');
          languagesPayload = languagesResponse.ok ? await languagesResponse.json() : {};
          this.languages = Array.isArray(languagesPayload.languages) ? languagesPayload.languages : ['en'];
          this.lang = normalizeLanguage(
            requestedLanguage() || Store.get('english-daily:lang') || languagesPayload.default,
            this.languages,
          );
          const response = await fetch(`./data/${encodeURIComponent(this.lang)}/index.json`);
          if (!response.ok) throw new Error('Could not load index');
          const index = await response.json();
          this.days = Array.isArray(index.days) ? index.days : [];
          this.counts = index.counts || {};
        } else {
          const languagesResponse = await fetch(`./${API_SEGMENT}/languages`);
          languagesPayload = languagesResponse.ok ? await languagesResponse.json() : {};
          this.languages = Array.isArray(languagesPayload.languages) ? languagesPayload.languages : ['en'];
          this.lang = normalizeLanguage(
            requestedLanguage() || Store.get('english-daily:lang') || languagesPayload.default,
            this.languages,
          );
          const response = await fetch(`./${API_SEGMENT}/days?lang=${encodeURIComponent(this.lang)}`);
          if (!response.ok) throw new Error('Could not load dates');
          this.days = await response.json();
          const today = new Date().toISOString().slice(0, 10);
          if (!this.days.includes(today)) this.days.unshift(today);
        }
        this.languagePayload = languagesPayload;
        this.applyBranding();
        Store.set('english-daily:lang', this.lang);
        this.selectedDate = this.days[0] || new Date().toISOString().slice(0, 10);
        if (this.selectedDate) await this.loadDay();
      } catch (err) {
        this.error = String(err.message || err);
      }
      this.observeReading();
      this.syncTour();
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
        showFeedback: true, autoMarkRead: true, reduceMotion: false,
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
      document.title = this.brand;
      const description = document.querySelector('meta[name="description"]');
      if (description) description.setAttribute('content', this.tagline);
    },

    syncRoute() {
      const raw = String(window.location.hash || '').replace(/^#\/?/, '').split(/[?&]/)[0];
      this.route = window.EDBrand ? window.EDBrand.route(window.location.hash) : (
        ['today', 'archive', 'glossary', 'settings'].includes(raw) ? raw : 'today'
      );
      if (raw !== this.route && window.history && window.history.replaceState) {
        window.history.replaceState(null, '', `#${this.route}`);
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
      return window.EDExercises ? window.EDExercises.answer(exercise) : null;
    },
    visibleExerciseAnswer(exercise) {
      return this.showFeedback() ? this.exerciseAnswer(exercise) : null;
    },
    exerciseProgress() {
      const exercises = this.exercises();
      if (window.EDExercises) return window.EDExercises.progress(exercises);
      return { done: 0, total: exercises.length, percent: 0 };
    },
    answerExercise(exercise, option) {
      if (window.EDExercises) window.EDExercises.record(exercise, option);
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
    syncTour() {
      const state = window.EDTour ? window.EDTour.state() : { index: 0, open: false };
      this.tourIndex = state.index || 0;
      this.tourOpenFlag = Boolean(state.open) && this.tourSteps().length > 0;
      if (this.tourOpenFlag) this.$nextTick(() => this.focusTour());
    },
    tourOpen() { return this.tourOpenFlag && this.tourSteps().length > 0; },
    startTour() {
      const state = window.EDTour ? window.EDTour.start(0) : { index: 0, open: true };
      this.tourIndex = state.index;
      this.tourOpenFlag = state.open && this.tourSteps().length > 0;
      this.$nextTick(() => this.focusTour());
    },
    openAnkiHelp() {
      const steps = this.tourSteps();
      const found = steps.findIndex((step) => step && step.id === 'anki');
      const index = found >= 0 ? found : 0;
      const state = window.EDTour ? window.EDTour.go(index) : { index, open: true };
      this.tourIndex = state.index;
      this.tourOpenFlag = state.open && steps.length > 0;
      this.$nextTick(() => this.focusTour());
    },
    nextTour() {
      const steps = this.tourSteps();
      const state = window.EDTour ? window.EDTour.advance(steps.length) : { index: this.tourIndex + 1, open: false };
      this.tourIndex = state.index;
      this.tourOpenFlag = state.open && steps.length > 0;
      if (this.tourOpenFlag) this.$nextTick(() => this.focusTour());
    },
    endTour() {
      if (window.EDTour) window.EDTour.end();
      this.tourIndex = 0;
      this.tourOpenFlag = false;
    },
    focusTour() {
      const step = this.tourStep();
      const target = step && step.target ? document.querySelector(step.target) : null;
      if (target && typeof target.focus === 'function') {
        target.setAttribute('tabindex', '-1');
        target.focus();
        return;
      }
      if (this.$refs.tourDialog) this.$refs.tourDialog.focus();
    },

    async runSearch() {
      const term = this.searchQuery.trim();
      this.searchResults = [];
      if (!term) return;
      this.searching = true;
      this.error = '';
      try {
        if (this.mode === 'static') {
          const path = window.EDSearch
            ? window.EDSearch.path(this.payload())
            : `./data/${encodeURIComponent(this.lang)}/search/${encodeURIComponent(this.selectedDate)}.json`;
          const response = await fetch(path || `./data/${encodeURIComponent(this.lang)}/search/${encodeURIComponent(this.selectedDate)}.json`);
          const index = response.ok ? await response.json() : { items: [] };
          this.searchResults = window.EDSearch
            ? window.EDSearch.query(index, term, this.level, 20)
            : [];
        } else {
          const response = await fetch(
            `./${API_SEGMENT}/search?q=${encodeURIComponent(term)}&day=${encodeURIComponent(this.selectedDate)}` +
            `&level=${encodeURIComponent(this.level)}&lang=${encodeURIComponent(this.lang)}`,
          );
          const payload = response.ok ? await response.json() : { results: [] };
          this.searchResults = Array.isArray(payload.results) ? payload.results : [];
        }
      } catch (err) {
        this.error = String(err.message || err);
      } finally {
        this.searching = false;
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
