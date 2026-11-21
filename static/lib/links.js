(function () {
  var LABELS = {
    text: 'Read the full text',
    audio: 'Listen to the original audio'
  };

  function label(kind) {
    return LABELS[kind] || LABELS.text;
  }

  function source(item) {
    return (item && (item.source || item.source_name)) || 'the publisher';
  }

  function hasUrl(item) {
    return Boolean(item && item.url);
  }

  function describe(item, kind) {
    return {
      label: label(kind),
      source: source(item),
      url: hasUrl(item) ? item.url : null
    };
  }

  window.EDLinks = { label: label, source: source, hasUrl: hasUrl, describe: describe };
}());
