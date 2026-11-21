(function () {
  function escapeField(value) {
    return String(value == null ? '' : value)
      .replace(/\r\n/g, '<br>')
      .replace(/\n/g, '<br>')
      .replace(/\t/g, ' ')
      .trim();
  }

  function toTsv(cards) {
    return cards.map(function (card) {
      return escapeField(card.front) + '\t' + escapeField(card.back);
    }).join('\n');
  }

  function download(cards, filename) {
    if (!cards || !cards.length) return;
    var text = '\ufeff#separator:tab\n#html:true\n' + toTsv(cards) + '\n';
    var blob = new Blob([text], { type: 'text/plain;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var link = document.createElement('a');
    link.href = url;
    link.download = filename || 'english-daily-anki.txt';
    document.body.appendChild(link);
    link.click();
    link.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function copy(cards) {
    if (!navigator.clipboard || !cards || !cards.length) return Promise.resolve(false);
    return navigator.clipboard.writeText(toTsv(cards)).then(function () { return true; }, function () { return false; });
  }

  function available() {
    return Boolean(window.AnkiExport && typeof window.AnkiExport.download === 'function');
  }

  function select(items, isLearned, toCard) {
    return (Array.isArray(items) ? items : []).filter(function (item) {
      return typeof isLearned !== 'function' || isLearned(item);
    }).map(function (item) {
      return typeof toCard === 'function' ? toCard(item) : item;
    }).filter(Boolean);
  }

  function status(item, isLearned, isAvailable) {
    if (!isAvailable) return 'Anki export unavailable offline';
    if (typeof isLearned === 'function' && !isLearned(item)) return 'Mark learned before exporting to Anki';
    return 'Ready for Anki';
  }

  window.AnkiExport = { toTsv: toTsv, download: download, copy: copy, available: available, select: select, status: status };
}());
