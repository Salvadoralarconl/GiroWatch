'use strict';
// "This page couldn't load": shown when GiroWatch cannot reach its server or a page fails to load.
(() => {
  const ICON = '<svg viewBox="0 0 24 24" width="48" height="48" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4"/><path d="M12 17h.01"/></svg>';
  function screen() {
    let element = document.getElementById('load-failure');
    if (element) return element;
    element = document.createElement('main');
    element.id = 'load-failure';
    element.setAttribute('role', 'alert');
    element.setAttribute('aria-labelledby', 'load-failure-title');
    element.innerHTML = `<div class="load-failure-box">${ICON}<h1 id="load-failure-title">This page couldn’t load</h1><p>Reload to try again, or go back.</p><div class="load-failure-actions"><button type="button" data-action="reload">Reload</button><button type="button" data-action="back">Back</button></div></div>`;
    element.addEventListener('click', event => {
      const action = event.target.closest('[data-action]')?.dataset.action;
      if (action === 'reload') location.reload();
      if (action === 'back') history.length > 1 ? history.back() : location.assign('/');
    });
    document.body.append(element);
    return element;
  }
  window.showLoadFailure = () => {
    if (document.documentElement.classList.contains('load-failed')) return;
    document.documentElement.classList.add('load-failed');
    screen().querySelector('button').focus();
  };
  // Network failures (server stopped or unreachable), not requests cancelled on purpose.
  window.isUnreachable = error => error instanceof TypeError;
  document.addEventListener('DOMContentLoaded', () => {
    if (document.body.dataset.loadFailure !== undefined) window.showLoadFailure();
  });
  // Keeps a copy of this screen so it can be shown even when the server is down at page load.
  if ('serviceWorker' in navigator && document.currentScript?.dataset.register !== 'false') {
    navigator.serviceWorker.register('/sw.js').catch(() => {});
  }
})();
