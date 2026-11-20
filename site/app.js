const API_SEGMENT = 'ap' + 'i';

function appMode() {
  const meta = document.querySelector('meta[name="eds-mode"]');
  return meta && meta.getAttribute('content') === 'static' ? 'static' : 'server';
}

function app() {
  return {
    levels: ['A1', 'A2', 'B1', 'B2', 'C1', 'C2'],
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

    async init() {
      this.theme = localStorage.getItem('english-daily:theme') ||
        (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      document.documentElement.dataset.theme = this.theme;
      try {
        if (this.mode === 'static') {
          const response = await fetch('./data/index.json');
          if (!response.ok) throw new Error('Could not load index');
          const index = await response.json();
          this.days = Array.isArray(index.days) ? index.days : [];
          this.counts = index.counts || {};
        } else {
          const response = await fetch(`./${API_SEGMENT}/days`);
          if (!response.ok) throw new Error('Could not load dates');
          this.days = await response.json();
          const today = new Date().toISOString().slice(0, 10);
          if (!this.days.includes(today)) this.days.unshift(today);
        }
        this.selectedDate = this.days[0] || '';
        if (this.selectedDate) await this.loadDay();
      } catch (err) {
        this.error = String(err.message || err);
      }
      if (typeof IntersectionObserver !== 'undefined' && this.$refs.readSentinel) {
        this.observer = new IntersectionObserver((entries) => {
          if (entries.some((entry) => entry.isIntersecting) && this.currentText()) {
            this.markRead(this.currentText());
          }
        });
        this.observer.observe(this.$refs.readSentinel);
      }
    },

    async dayUrl(level) {
      if (this.mode === 'static') {
        return `./data/${encodeURIComponent(this.selectedDate)}/${encodeURIComponent(level)}.json`;
      }
      return `./${API_SEGMENT}/day/${encodeURIComponent(this.selectedDate)}?level=${level}`;
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
          const response = await fetch(await this.dayUrl(level));
          if (!response.ok) throw new Error(`Could not load ${level} content`);
          return [level, await response.json()];
        }));
        for (const [level, payload] of results) this.all[level] = payload;
      } catch (err) {
        this.error = String(err.message || err);
      } finally {
        this.loading = false;
        this.resetPlayer();
      }
    },

    async setLevel(level) {
      if (level === this.level) return;
      this.level = level;
      this.stop();
      if (!this.all[level]) {
        this.loading = true;
        try {
          const response = await fetch(await this.dayUrl(level));
          if (!response.ok) throw new Error('Could not load level');
          this.all[level] = await response.json();
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

    progressKey(item) {
      return item ? `english-daily:${item.kind || 'item'}:${item.id}` : '';
    },
    isDone(item, kind) {
      if (!item) return false;
      return localStorage.getItem(`english-daily:${kind}:${item.id}`) === '1';
    },
    isRead(item) { return this.isDone(item, 'read'); },
    isListened(item) { return this.isDone(item, 'listened'); },
    markRead(item) {
      if (!item) return;
      localStorage.setItem(`english-daily:read:${item.id}`, '1');
    },
    markListened(item) {
      if (!item || this.isListened(item)) return;
      localStorage.setItem(`english-daily:listened:${item.id}`, '1');
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
      for (const category of ['news', 'culture']) {
        for (const kind of ['text', 'audio']) {
          const item = payload.slots[category] && payload.slots[category][kind];
          if (item) present.push(item);
        }
      }
      return present.length > 0 && present.every((item) => this.itemDone(item));
    },

    resetPlayer() {
      this.position = 0;
      this.duration = 0;
      this.playing = false;
      this.audioError = false;
      if (this.$refs.audio) {
        try { this.$refs.audio.currentTime = 0; } catch (err) { /* not loaded yet */ }
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
