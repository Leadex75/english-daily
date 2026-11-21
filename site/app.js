const API_SEGMENT = 'ap' + 'i';

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
    theme: 'light',
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

    async init() {
      const goal = document.querySelector('meta[name="eds-goal"]');
      this.weeklyGoal = Number(goal && goal.getAttribute('content')) || 5;
      this.theme = localStorage.getItem('english-daily:theme') ||
        (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      document.documentElement.dataset.theme = this.theme;
      if (this.mode === 'static' && 'serviceWorker' in navigator) {
        navigator.serviceWorker.register('./sw.js').catch(() => {});
      }
      try {
        if (this.mode === 'static') {
          const languagesResponse = await fetch('./data/languages.json');
          const languagesPayload = languagesResponse.ok ? await languagesResponse.json() : {};
          this.languages = Array.isArray(languagesPayload.languages) ? languagesPayload.languages : ['en'];
          this.lang = normalizeLanguage(
            requestedLanguage() || localStorage.getItem('english-daily:lang') || languagesPayload.default,
            this.languages,
          );
          const response = await fetch(`./data/${encodeURIComponent(this.lang)}/index.json`);
          if (!response.ok) throw new Error('Could not load index');
          const index = await response.json();
          this.days = Array.isArray(index.days) ? index.days : [];
          this.counts = index.counts || {};
        } else {
          const languagesResponse = await fetch(`./${API_SEGMENT}/languages`);
          const languagesPayload = languagesResponse.ok ? await languagesResponse.json() : {};
          this.languages = Array.isArray(languagesPayload.languages) ? languagesPayload.languages : ['en'];
          this.lang = normalizeLanguage(
            requestedLanguage() || localStorage.getItem('english-daily:lang') || languagesPayload.default,
            this.languages,
          );
          const response = await fetch(`./${API_SEGMENT}/days?lang=${encodeURIComponent(this.lang)}`);
          if (!response.ok) throw new Error('Could not load dates');
          this.days = await response.json();
          const today = new Date().toISOString().slice(0, 10);
          if (!this.days.includes(today)) this.days.unshift(today);
        }
        localStorage.setItem('english-daily:lang', this.lang);
        this.selectedDate = this.days[0] || new Date().toISOString().slice(0, 10);
        if (this.selectedDate) await this.loadDay();
      } catch (err) {
        this.error = String(err.message || err);
      }
      this.observeReading();
    },

    observeReading() {
      if (typeof IntersectionObserver === 'undefined' || !this.$refs.readSentinel) return;
      this.observer = new IntersectionObserver((entries) => {
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
      this.theme = this.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = this.theme;
      localStorage.setItem('english-daily:theme', this.theme);
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

    isDone(item, kind) {
      if (!item) return false;
      return localStorage.getItem(`english-daily:${kind}:${item.id}`) === '1';
    },
    isRead(item) { return this.isDone(item, 'read'); },
    isListened(item) { return this.isDone(item, 'listened'); },
    markDone(item, kind) {
      if (!item) return;
      localStorage.setItem(`english-daily:${kind}:${item.id}`, '1');
      localStorage.setItem(`english-daily:done-date:${kind}:${item.id}`, this.selectedDate);
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
      const key = this.phraseKey(item);
      return Boolean(key && localStorage.getItem(`english-daily:phrase:${key}`));
    },
    toggleLearned(item) {
      const key = this.phraseKey(item);
      if (!key) return;
      const prefix = `english-daily:phrase:${key}`;
      if (localStorage.getItem(prefix)) {
        localStorage.removeItem(prefix);
        return;
      }
      localStorage.setItem(prefix, JSON.stringify({
        key,
        text: item.text || item.expression || '',
        meaning: item.meaning || '',
        meaning_fr: item.meaning_fr || '',
        example: item.example || '',
        type: item.type || item.kind || '',
        learned_at: this.selectedDate,
      }));
    },
    forgetPhrase(key) { localStorage.removeItem(`english-daily:phrase:${key}`); },
    glossary() {
      const result = [];
      for (let i = 0; i < localStorage.length; i += 1) {
        const key = localStorage.key(i);
        if (!key || !key.startsWith('english-daily:phrase:')) continue;
        try {
          result.push(JSON.parse(localStorage.getItem(key)));
        } catch (err) {
          continue;
        }
      }
      return result.sort((a, b) => String(b.learned_at || '').localeCompare(String(a.learned_at || '')));
    },
    phraseDone() {
      const payload = this.phrase();
      if (!payload) return false;
      return this.isLearned(payload.word) && this.isLearned(payload.expression);
    },

    ankiItem(item) {
      if (!item) return null;
      const front = item.text || item.expression || '';
      const meaning = [item.meaning_fr, item.meaning].filter(Boolean).join(' — ');
      const back = [meaning, item.example].filter(Boolean).join('<br>');
      return { front, back };
    },
    exportAnki(items) {
      const cards = (items || []).map((item) => this.ankiItem(item)).filter(Boolean);
      if (cards.length && window.AnkiExport) window.AnkiExport.download(cards, `english-daily-${this.selectedDate}.txt`);
    },
    exportAllAnki() {
      const cards = this.glossary().map((item) => this.ankiItem(item)).filter(Boolean);
      if (cards.length && window.AnkiExport) window.AnkiExport.download(cards, 'english-daily-glossary.txt');
    },

    allItems() {
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
        if (payload.phrase) items.push(payload.phrase.word, payload.phrase.expression);
      }
      return items;
    },
    todayTotal() { return 48; },
    todayCount() {
      let count = 0;
      for (const item of this.allItems()) {
        if (item.key) {
          if (this.isLearned(item)) count += 1;
        } else if (this.itemDone(item)) {
          count += 1;
        }
      }
      return count;
    },
    todayPercent() {
      return Math.min(100, Math.round((this.todayCount() / this.todayTotal()) * 100));
    },
    weekDates() {
      const cutoff = new Date();
      cutoff.setHours(0, 0, 0, 0);
      cutoff.setDate(cutoff.getDate() - 6);
      const dates = new Set();
      for (let i = 0; i < localStorage.length; i += 1) {
        const key = localStorage.key(i) || '';
        if (key.startsWith('english-daily:done-date:')) dates.add(localStorage.getItem(key));
        if (key.startsWith('english-daily:phrase:')) {
          try {
            const entry = JSON.parse(localStorage.getItem(key));
            if (entry && entry.learned_at) dates.add(entry.learned_at);
          } catch (err) {
            continue;
          }
        }
      }
      return [...dates].filter((date) => date && new Date(date) >= cutoff);
    },
    weekCount() { return this.weekDates().length; },
    weekPercent() {
      return Math.min(100, Math.round((this.weekCount() / this.weeklyGoal) * 100));
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
      this.speed = speed;
      if (this.$refs.audio) this.$refs.audio.playbackRate = speed;
    }
  };
}
