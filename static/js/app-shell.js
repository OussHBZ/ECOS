/* Presentation-only behavior shared by ECOS and KardioX. */
(() => {
  'use strict';
  const sidebar = document.querySelector('.app-sidebar');
  const workspace = document.querySelector('.app-workspace');
  const trigger = document.querySelector('[data-menu-open]');
  const backdrop = document.querySelector('[data-menu-backdrop]');
  const mobile = window.matchMedia('(max-width: 900px)');
  const focusable = root => [...root.querySelectorAll('a[href],button,input,select,textarea,[tabindex]')]
    .filter(el => !el.disabled && el.tabIndex >= 0 && el.getClientRects().length && !el.closest('[inert]'));
  let menuOpen = false;
  function closeMenu(restore = true) {
    if (!sidebar) return;
    const wasOpen = menuOpen;
    menuOpen = false;
    document.body.classList.remove('menu-open');
    trigger.setAttribute('aria-expanded', 'false');
    backdrop.hidden = true;
    workspace.inert = false;
    sidebar.inert = mobile.matches;
    if (restore && wasOpen) trigger.focus();
  }
  trigger?.addEventListener('click', () => {
    menuOpen = true;
    document.body.classList.add('menu-open');
    sidebar.inert = false;
    workspace.inert = true;
    backdrop.hidden = false;
    trigger.setAttribute('aria-expanded', 'true');
    sidebar.querySelector('[data-menu-close]').focus();
  });
  document.querySelector('[data-menu-close]')?.addEventListener('click', () => closeMenu());
  backdrop?.addEventListener('click', () => closeMenu());
  mobile.addEventListener('change', () => closeMenu(false));
  if (sidebar) sidebar.inert = mobile.matches;

  const context = document.querySelector('[data-page-context]');
  function updateContext() {
    const heading = [...document.querySelectorAll('#main-content h1,#main-content h2')]
      .find(el => el.getClientRects().length);
    if (context && heading && context.textContent !== heading.textContent.trim()) {
      context.textContent = heading.textContent.trim();
    }
    document.querySelectorAll('[data-app-tab]').forEach(button => {
      const active = document.getElementById(button.dataset.appTab)?.classList.contains('active');
      button.classList.toggle('active', !!active);
      if (active) button.setAttribute('aria-current', 'page');
      else button.removeAttribute('aria-current');
    });
  }
  function activeRoute() {
    if (!sidebar) return;
    const links = [...sidebar.querySelectorAll('a.app-nav-link')];
    const exact = links.find(a => a.pathname === location.pathname && a.hash === location.hash);
    if (exact) links.forEach(a => {
      a.classList.toggle('active', a === exact);
      if (a === exact) a.setAttribute('aria-current','page'); else a.removeAttribute('aria-current');
    });
  }
  window.addEventListener('hashchange', activeRoute);
  sidebar?.addEventListener('click', event => {
    if (event.target.closest('.app-nav-link')) {
      closeMenu();
      updateContext();
    }
  });

  // Existing screens generate dialogs dynamically. Keep their close handlers and data intact.
  let activeModal = null;
  let modalReturnFocus = null;
  let previousFocus = document.activeElement;
  const modalSelector = '.modal,#zoom-image-viewer,dialog.app-dialog';
  const closeSelector = '.close-modal,.close-button,[data-dialog-close],.ziv-close';
  const dirtyDialogs = new WeakSet();
  document.addEventListener('focusin', event => {
    if (!activeModal && !event.target.closest(modalSelector)) previousFocus = event.target;
    if (activeModal && !activeModal.contains(event.target) && activeModal.getClientRects().length) {
      (focusable(activeModal)[0] || activeModal).focus();
    }
  });
  const dirtyDialog = event => {
    const modal = event.target.closest(modalSelector);
    if (modal) dirtyDialogs.add(modal);
  };
  document.addEventListener('input', dirtyDialog);
  document.addEventListener('change', dirtyDialog);
  function allowDismiss(modal) {
    return !dirtyDialogs.has(modal) || window.confirm('Fermer cette fenêtre et abandonner les modifications non enregistrées ?');
  }
  document.addEventListener('click', event => {
    const modal = event.target.closest(modalSelector);
    if (!modal) return;
    const control = event.target.closest('button,span,a');
    const dismiss = (event.target === modal && modal.tagName !== 'DIALOG') || event.target.closest(closeSelector) ||
      (control && /^(Annuler|Fermer)$/.test(control.textContent.trim()));
    if (dismiss && !allowDismiss(modal)) {
      event.preventDefault(); event.stopImmediatePropagation();
    }
  }, true);
  function syncModal() {
    const visible = [...document.querySelectorAll(modalSelector)].filter(el =>
      !el.classList.contains('hidden') && getComputedStyle(el).display !== 'none' && el.getClientRects().length);
    const next = visible.at(-1) || null;
    if (next === activeModal) return;
    const previous = activeModal;
    activeModal = next;
    document.body.classList.toggle('dialog-open', !!next);
    if (previous && !visible.includes(previous)) dirtyDialogs.delete(previous);
    if (next) {
      if (!previous) modalReturnFocus = previousFocus;
      next.setAttribute('role','dialog');
      next.setAttribute('aria-modal','true');
      if (!next.getAttribute('aria-label') && !next.getAttribute('aria-labelledby')) {
        next.setAttribute('aria-label', next.querySelector('h1,h2,h3')?.textContent.trim() || 'Fenêtre de dialogue');
      }
      next.tabIndex = -1;
      (focusable(next)[0] || next).focus();
    } else if (previous) {
      previous.removeAttribute('aria-modal');
      if (modalReturnFocus?.isConnected && modalReturnFocus.getClientRects().length) modalReturnFocus.focus();
      modalReturnFocus = null;
    }
  }
  document.addEventListener('keydown', event => {
    const trap = activeModal || (menuOpen ? sidebar : null);
    if (!trap) return;
    if (event.key === 'Escape') {
      if (activeModal) activeModal.querySelector(closeSelector)?.click();
      else closeMenu();
      event.preventDefault();
    }
    if (event.key === 'Tab') {
      const nodes = focusable(trap), first = nodes[0], last = nodes.at(-1);
      if (!first) { event.preventDefault(); trap.focus(); return; }
      if (event.shiftKey && (document.activeElement === first || !trap.contains(document.activeElement))) {
        event.preventDefault(); last.focus();
      } else if (!event.shiftKey && (document.activeElement === last || !trap.contains(document.activeElement))) {
        event.preventDefault(); first.focus();
      }
    }
  });

  let nextLabel = 0;
  const editor = document.querySelector('[data-kine-case-form]');
  const dirtyStatus = document.querySelector('[data-editor-dirty]');
  const markDirty = () => {
    if (dirtyStatus) dirtyStatus.textContent = 'Modifications non enregistrées. Enregistrez le brouillon avant de publier.';
  };
  editor?.addEventListener('input', markDirty);
  editor?.addEventListener('change', markDirty);
  // Collapse only on initial mobile entry. The original toggle keeps the iframe,
  // conversation and draft mounted, and the user's subsequent choice is retained.
  document.addEventListener('DOMContentLoaded', () => {
    const recordToggle = document.querySelector('[data-record-toggle]');
    if (mobile.matches && recordToggle?.getAttribute('aria-expanded') === 'true') recordToggle.click();
  });
  function enhance(root) {
    // Structure legacy panels once, retaining the original nodes and their events.
    root.querySelectorAll('.modal-content').forEach(panel => {
      if (panel.querySelector(':scope > .app-dialog-header')) return;
      const close = panel.querySelector('.close-modal,.close-button');
      const title = panel.querySelector('h2,h3');
      if (!close && !title) return;
      const header = document.createElement('div'); header.className = 'app-dialog-header';
      const body = document.createElement('div'); body.className = 'app-dialog-body';
      if (title) header.append(title);
      if (close) header.append(close);
      while (panel.firstChild) body.append(panel.firstChild);
      panel.append(header, body);
      // Standalone footer actions can remain visible while the body scrolls.
      const actions = body.querySelector(':scope > .form-actions');
      if (actions) { actions.classList.add('app-dialog-actions'); panel.append(actions); }
    });
    root.querySelectorAll('dialog.app-dialog').forEach(dialog => {
      if (dialog.dataset.enhancedDialog) return;
      dialog.dataset.enhancedDialog = 'true';
      dialog.addEventListener('cancel', event => {
        event.preventDefault(); dialog.querySelector('[data-dialog-close]')?.click();
      });
      dialog.addEventListener('close', syncModal);
    });
    // Associate existing visible labels with their fields, including repeated rows.
    root.querySelectorAll('label:not([for])').forEach(label => {
      if (label.querySelector('input,select,textarea')) return;
      const field = label.nextElementSibling;
      if (field?.matches('input,select,textarea')) {
        if (!field.id) field.id = 'app-field-' + (++nextLabel);
        label.htmlFor = field.id;
      }
    });
    root.querySelectorAll('input:not([type=hidden]),select,textarea').forEach(field => {
      if (field.labels?.length || field.hasAttribute('aria-label') || field.hasAttribute('aria-labelledby')) return;
      const label = field.getAttribute('placeholder') || field.getAttribute('title');
      if (label) field.setAttribute('aria-label',label);
    });
    root.querySelectorAll('table').forEach(table => {
      table.querySelectorAll('thead th').forEach(th => { if (!th.scope) th.scope = 'col'; });
      table.querySelectorAll('td').forEach(cell => {
        if (cell.querySelectorAll(':scope > button').length > 1) {
          const actions = document.createElement('div'); actions.className = 'table-actions';
          while (cell.firstChild) actions.append(cell.firstChild);
          cell.append(actions);
        }
        if (/^\d{2}\/\d{2}\/\d{4}(?:\s+\d{2}:\d{2})?$/.test(cell.textContent.trim())) cell.classList.add('table-date');
      });
      if (!table.closest('.kine-table-wrap,.table-container,.app-table-scroll')) {
        const wrapper = document.createElement('div');
        wrapper.className = 'app-table-scroll';
        table.before(wrapper); wrapper.append(table);
      }
    });
    root.querySelectorAll('.kine-table-wrap,.table-container,.app-table-scroll').forEach(wrapper => {
      if (!wrapper.hasAttribute('tabindex')) wrapper.tabIndex = 0;
      if (!wrapper.hasAttribute('aria-label')) wrapper.setAttribute('aria-label','Tableau — défilement horizontal si nécessaire');
      wrapper.setAttribute('role','region');
    });
    root.querySelectorAll('.close-modal,.close-button').forEach(close => {
      if (!close.matches('button')) {
        close.setAttribute('role','button'); close.tabIndex = 0;
        if (!close.dataset.keyboardClose) {
          close.dataset.keyboardClose = 'true';
          close.addEventListener('keydown', event => {
            if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); close.click(); }
          });
        }
      }
      if (/^[×✕✖x]$/.test(close.textContent.trim())) close.textContent = 'Fermer';
    });
  }
  let pending = false;
  const observer = new MutationObserver(mutations => {
    if (!mutations.some(m => m.type === 'childList' || (m.type === 'attributes' && m.target.matches(modalSelector + ',[class$="tab-content"],.student-tab-content,.teacher-tab-content,.admin-tab-content')))) return;
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      enhance(document); syncModal(); updateContext();
    });
  });
  enhance(document); updateContext(); activeRoute(); syncModal();
  observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['class','style','open']});
})();
