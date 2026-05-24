// static/annotate.js
(() => {
  const BOOK_SLUG = (location.pathname.replace(/^\/+|\/+$/g, '').split('/')[0] || 'index')
                      .replace(/\.html$/, '');
  const CATEGORIES = [
    { key: 'vocab',     label: '词汇',       dot: 'v', color: '#3a7bb5' },
    { key: 'grammar',   label: '语法',       dot: 'g', color: '#b8924a' },
    { key: 'structure', label: '句子结构',   dot: 's', color: '#7a8a4e' },
  ];

  // ─── Repairs: wrap structure-card flow lines in a .card-body so
  // the existing .card.open .card-body { display: block } toggle works.
  function repairStructureCards() {
    document.querySelectorAll('.card-hdr.structure').forEach(hdr => {
      const card = hdr.closest('.card');
      if (!card) return;
      if (card.querySelector(':scope > .card-body')) return; // already wrapped
      const body = document.createElement('div');
      body.className = 'card-body';
      let n = hdr.nextSibling;
      while (n) {
        const next = n.nextSibling;
        body.appendChild(n);
        n = next;
      }
      card.appendChild(body);
    });
  }

  // ─── Hydration: load saved notes on page load ───────────────────
  async function hydrate() {
    try {
      const r = await fetch(`/api/notes/${BOOK_SLUG}`);
      if (!r.ok) return;
      const notes = await r.json();
      notes.forEach(renderSavedNote);
    } catch (_) { /* ignore */ }
  }

  // map our internal category keys -> the page's CSS card-hdr modifier
  const KIND_CLASS = { vocab: 'vocab', grammar: 'gram', structure: 'structure' };
  const KIND_LABEL = { vocab: '词汇', grammar: '语法', structure: '句子结构' };

  // Minimal markdown -> HTML for streamed LLM responses.
  // Supports: **bold**, *italic*, `code`, paragraph breaks on \n\n, single \n -> <br>.
  function mdToHtml(md) {
    let s = escapeHtml(md);
    s = s.replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^\*])\*([^\*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    const paras = s.split(/\n{2,}/).map(p => `<p class="ann-line">${p.replace(/\n/g,'<br>')}</p>`);
    return paras.join('');
  }

  function renderSavedNote(note) {
    const para = document.getElementById(note.paraId);
    if (!para) {
      console.warn('bi: paraId not found', note.paraId);
      return;
    }
    // Insert a NEW full card matching the page's existing card pattern.
    const kindCls = KIND_CLASS[note.category] || note.category;
    const label = KIND_LABEL[note.category] || note.category;
    const card = document.createElement('div');
    card.className = 'card open bi-ai-card';
    card.innerHTML = `
      <div class="card-hdr ${kindCls}" onclick="(function(h){h.closest('.card').classList.toggle('open')})(this)">
        <span class="cat-badge">${label}</span>
        <span class="card-term">${escapeHtml(note.selectedText)} <span class="bi-ai-badge">AI</span></span>
        <span class="card-toggle">▼</span>
      </div>
      <div class="card-body">${mdToHtml(note.responseMarkdown)}</div>
    `;
    para.appendChild(card);
  }

  // ─── Admin gate ─────────────────────────────────────────────────
  let isAdmin = false;
  async function checkAdmin() {
    try {
      const r = await fetch('/admin', { credentials: 'same-origin' });
      isAdmin = r.ok;
    } catch (_) { isAdmin = false; }
  }

  // ─── Selection bar ──────────────────────────────────────────────
  let currentBar = null;
  let currentPop = null;

  function teardown() {
    if (currentBar) { currentBar.remove(); currentBar = null; }
    if (currentPop) { currentPop.remove(); currentPop = null; }
  }

  document.addEventListener('mouseup', (e) => {
    if (!isAdmin) return;
    if (currentPop && currentPop.contains(e.target)) return;
    if (currentBar && currentBar.contains(e.target)) return;
    setTimeout(() => handleSelection(e), 0);
  });

  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') teardown();
  });

  document.addEventListener('mousedown', (e) => {
    if (currentPop && currentPop.contains(e.target)) return;
    if (currentBar && currentBar.contains(e.target)) return;
    teardown();
  });

  function handleSelection(e) {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) return;
    const text = sel.toString().trim();
    if (!text) return;
    const range = sel.getRangeAt(0);
    const para = findParaSection(range.startContainer);
    if (!para) return;
    if (findParaSection(range.endContainer) !== para) return;  // single para only
    teardown();
    showBar(range.getBoundingClientRect(), para, text);
  }

  function findParaSection(node) {
    while (node && node.nodeType !== 1) node = node.parentNode;
    return node ? node.closest('.para-section') : null;
  }

  function showBar(rect, para, text) {
    const bar = document.createElement('div');
    bar.className = 'bi-sel-bar';
    bar.style.top  = (window.scrollY + rect.top - 42) + 'px';
    bar.style.left = (window.scrollX + rect.left) + 'px';
    CATEGORIES.forEach(c => {
      const btn = document.createElement('button');
      btn.innerHTML = `<span class="dot ${c.dot}"></span>${c.label}`;
      btn.onclick = (ev) => {
        ev.stopPropagation();
        bar.remove(); currentBar = null;
        openPopover(rect, para, text, c);
      };
      bar.appendChild(btn);
    });
    document.body.appendChild(bar);
    currentBar = bar;
  }

  // ─── Popover + streaming ────────────────────────────────────────
  function openPopover(rect, para, text, cat) {
    const pop = document.createElement('div');
    pop.className = 'bi-pop';
    pop.style.top  = (window.scrollY + rect.bottom + 8) + 'px';
    pop.style.left = (window.scrollX + rect.left) + 'px';
    pop.innerHTML = `
      <div class="bi-pop-hdr">
        <span><span class="cat" style="color:${cat.color}">${cat.label}</span> · DeepSeek</span>
        <span>${para.id}</span>
      </div>
      <div class="bi-pop-sel">"${escapeHtml(text)}"</div>
      <div class="bi-pop-body"></div>
      <div class="bi-pop-foot">
        <button class="bi-close">关闭</button>
        <button class="bi-save primary" disabled>保存到卡片</button>
      </div>
    `;
    document.body.appendChild(pop);
    currentPop = pop;
    const bodyEl  = pop.querySelector('.bi-pop-body');
    const saveBtn = pop.querySelector('.bi-save');
    const closeBtn = pop.querySelector('.bi-close');

    bodyEl.innerHTML = '<div class="bi-stream"></div><span class="bi-cursor"></span>';
    const streamEl = bodyEl.querySelector('.bi-stream');
    const cursorEl = bodyEl.querySelector('.bi-cursor');
    let raw = '';

    const paraText = (para.querySelector('.original') || para).innerText.trim();

    streamQuery(cat.key, text, paraText,
      (tok) => { raw += tok; streamEl.innerHTML = mdToHtml(raw); },
      () => { cursorEl.remove(); saveBtn.disabled = false; saveBtn.dataset.raw = raw; },
      (err) => { bodyEl.innerHTML = `<div class="bi-pop-err">出错：${escapeHtml(err)}</div>`; }
    );

    closeBtn.onclick = teardown;
    saveBtn.onclick = async () => {
      saveBtn.disabled = true;
      const note = {
        paraId: para.id,
        category: cat.key,
        selectedText: text,
        responseMarkdown: saveBtn.dataset.raw || streamEl.innerText,
      };
      try {
        const r = await fetch(`/api/notes/${BOOK_SLUG}`, {
          method: 'POST',
          credentials: 'same-origin',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(note),
        });
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        renderSavedNote(note);
        teardown();
      } catch (e) {
        alert('保存失败: ' + e.message);
        saveBtn.disabled = false;
      }
    };
  }

  async function streamQuery(category, selectedText, paraContext, onToken, onDone, onError) {
    try {
      const r = await fetch('/api/query', {
        method: 'POST',
        credentials: 'same-origin',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ category, selectedText, paraContext }),
      });
      if (!r.ok) { onError(`HTTP ${r.status}`); return; }
      const reader = r.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const events = buf.split('\n\n');
        buf = events.pop();
        for (const ev of events) {
          for (const line of ev.split('\n')) {
            if (line.startsWith('data: ')) {
              const data = line.slice(6);
              if (data === '[DONE]') { onDone(); return; }
              onToken(data.replace(/\\n/g, '\n'));
            } else if (line.startsWith('event: error')) {
              // next line will be data:
            }
          }
        }
      }
      onDone();
    } catch (e) {
      onError(e.message);
    }
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }

  // ─── Boot ───────────────────────────────────────────────────────
  document.addEventListener('DOMContentLoaded', async () => {
    repairStructureCards();
    await Promise.all([hydrate(), checkAdmin()]);
  });
})();
