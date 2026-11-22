window.EDShortcuts = (() => {
  const TYPING = ['INPUT', 'TEXTAREA', 'SELECT'];
  const BINDINGS = [
    { key: 'j', action: 'previousDay', labelKey: 'shortcuts.previousDay' },
    { key: 'k', action: 'nextDay', labelKey: 'shortcuts.nextDay' },
    { key: '1', action: 'tabNews', labelKey: 'shortcuts.tabNews' },
    { key: '2', action: 'tabCulture', labelKey: 'shortcuts.tabCulture' },
    { key: '3', action: 'tabHistory', labelKey: 'shortcuts.tabHistory' },
    { key: '4', action: 'tabPhrase', labelKey: 'shortcuts.tabPhrase' },
    { key: '5', action: 'tabArchive', labelKey: 'shortcuts.tabArchive' },
    { key: 'r', action: 'readingMode', labelKey: 'control.reading' },
    { key: 'a', action: 'annotation', labelKey: 'shortcuts.annotation' },
    { key: 's', action: 'quiz', labelKey: 'shortcuts.checkQuiz' },
    { key: '?', action: 'help', labelKey: 'shortcuts.open' },
  ];

  function isTyping(target) {
    const element = target || {};
    return TYPING.includes(String(element.tagName || '').toUpperCase()) || Boolean(element.isContentEditable);
  }

  function parse(event) {
    const input = event || {};
    if (input.ctrlKey || input.metaKey || input.altKey || isTyping(input.target)) return '';
    const key = String(input.key || '');
    return BINDINGS.some((binding) => binding.key === key) ? key : '';
  }

  function bindingFor(event) {
    const key = parse(event);
    return BINDINGS.find((binding) => binding.key === key) || null;
  }

  function dispatch(event, actions, target) {
    const binding = bindingFor(event);
    if (!binding) return '';
    const handler = actions && typeof actions[binding.action] === 'function' ? actions[binding.action] : null;
    if (!handler) return '';
    handler.call(target || null, event);
    return binding.action;
  }

  return { TYPING, BINDINGS, isTyping, parse, bindingFor, dispatch };
})();
