// DOM layer. Selection bar, popover, hydration rendering, structure-card repair,
// progress observer. Depends on window.BIData being loaded first.
(() => {
  const D = window.BIData;
  const CATEGORIES = [
    { key: 'vocab',     label: '词汇',       dot: 'v', color: '#3a7bb5' },
    { key: 'grammar',   label: '语法',       dot: 'g', color: '#b8924a' },
    { key: 'structure', label: '句子结构',   dot: 's', color: '#7a8a4e' },
  ];
  const KIND_CLASS = { vocab: 'vocab', grammar: 'gram', structure: 'structure' };
  const KIND_LABEL = { vocab: '词汇', grammar: '语法', structure: '句子结构' };

  function mdToHtml(md) {
    let s = escapeHtml(md);
    s = s.replace(/\*\*([^\*]+)\*\*/g, '<strong>$1</strong>');
    s = s.replace(/(^|[^\*])\*([^\*\n]+)\*(?!\*)/g, '$1<em>$2</em>');
    s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
    const paras = s.split(/\n{2,}/).map(p => `<p class="ann-line">${p.replace(/\n/g,'<br>')}</p>`);
    return paras.join('');
  }

  function escapeHtml(s) {
    return String(s).replace(/[&<>"']/g, c => ({
      '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
    }[c]));
  }

  function repairStructureCards() {
    document.querySelectorAll('.card-hdr.structure').forEach(hdr => {
      const card = hdr.closest('.card');
      if (!card) return;
      if (card.querySelector(':scope > .card-body')) return;
      const body = document.createElement('div');
      body.className = 'card-body';
      let n = hdr.nextSibling;
      while (n) { const next = n.nextSibling; body.appendChild(n); n = next; }
      card.appendChild(body);
    });
  }

  function renderSavedNote(note) {
    const para = document.getElementById(note.paraId);
    if (!para) return;
    const kindCls = KIND_CLASS[note.category] || note.category;
    const label = KIND_LABEL[note.category] || note.category;
    const card = document.createElement('div');
    card.className = 'card open bi-ai-card';
    card.innerHTML = `
      <div class="card-hdr ${kindCls}" onclick="(function(h){h.closest('.card').classList.toggle('open')})(this)">
        <span class="cat-badge">${label}</span>
        <span class="card-term">${escapeHtml(note.selectedText)}</span>
        <span class="card-toggle">▼</span>
      </div>
      <div class="card-body">${mdToHtml(note.responseMarkdown)}</div>
    `;
    para.appendChild(card);
  }

  // ─── Selection bar + popover ─────────────────────────────────────
  let currentBar = null, currentPop = null;
  function teardown() {
    if (currentBar) { currentBar.remove(); currentBar = null; }
    if (currentPop) { currentPop.remove(); currentPop = null; }
  }

  document.addEventListener('mouseup', (e) => {
    if (!D.me) return;
    if (currentPop && currentPop.contains(e.target)) return;
    if (currentBar && currentBar.contains(e.target)) return;
    setTimeout(() => handleSelection(e), 0);
  });
  document.addEventListener('keydown', (e) => { if (e.key === 'Escape') teardown(); });
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
    if (findParaSection(range.endContainer) !== para) return;
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
      btn.onclick = (ev) => { ev.stopPropagation(); bar.remove(); currentBar = null; openPopover(rect, para, text, c); };
      bar.appendChild(btn);
    });
    document.body.appendChild(bar);
    currentBar = bar;
  }

  function openPopover(rect, para, text, cat) {
    const isAdmin = !!(D.me && D.me.is_admin);
    const pop = document.createElement('div');
    pop.className = 'bi-pop';
    pop.style.top  = (window.scrollY + rect.bottom + 8) + 'px';
    pop.style.left = (window.scrollX + rect.left) + 'px';
    const scopeRow = isAdmin
      ? `<div class="bi-pop-scope">
           <label><input type="radio" name="bi-scope" value="private" checked> 保存到个人</label>
           <label><input type="radio" name="bi-scope" value="public"> 发布到所有读者</label>
         </div>`
      : '';
    pop.innerHTML = `
      <div class="bi-pop-hdr">
        <span><span class="cat" style="color:${cat.color}">${cat.label}</span> · DeepSeek</span>
        <span>${para.id}</span>
      </div>
      <div class="bi-pop-sel">"${escapeHtml(text)}"</div>
      <div class="bi-pop-body"></div>
      ${scopeRow}
      <div class="bi-pop-foot">
        <button class="bi-close">关闭</button>
        <button class="bi-save primary" disabled>保存</button>
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

    D.streamQuery(cat.key, text, paraText,
      (tok) => { raw += tok; streamEl.innerHTML = mdToHtml(raw); },
      () => { cursorEl.remove(); saveBtn.disabled = false; saveBtn.dataset.raw = raw; },
      (err) => { bodyEl.innerHTML = `<div class="bi-pop-err">出错：${escapeHtml(err)}</div>`; }
    );

    closeBtn.onclick = teardown;
    saveBtn.onclick = async () => {
      saveBtn.disabled = true;
      const note = {
        paraId: para.id, category: cat.key,
        selectedText: text, responseMarkdown: saveBtn.dataset.raw || streamEl.innerText,
      };
      try {
        const scope = isAdmin
          ? (pop.querySelector('input[name="bi-scope"]:checked')?.value || 'private')
          : 'private';
        if (scope === 'public') await D.savePublicNote(note);
        else await D.saveUserNote(note);
        renderSavedNote(note);
        teardown();
      } catch (e) {
        alert('保存失败: ' + e.message);
        saveBtn.disabled = false;
      }
    };
  }

  // ─── Reading-progress observer ───────────────────────────────────
  function setupProgressObserver() {
    if (!D.me) return;
    let lastSent = null;
    let timer = null;
    const send = (paraId) => {
      const m = paraId.match(/^ch(\d+)s(\d+)$/);
      if (!m) return;
      const ch = parseInt(m[1], 10), sec = parseInt(m[2], 10);
      const key = `${ch}.${sec}`;
      if (key === lastSent) return;
      lastSent = key;
      D.postProgress(ch, sec);
    };
    const obs = new IntersectionObserver((entries) => {
      const visible = entries.filter(e => e.isIntersecting && e.intersectionRatio > 0.5);
      if (!visible.length) return;
      const para = visible[0].target;
      clearTimeout(timer);
      timer = setTimeout(() => send(para.id), 1500);
    }, { threshold: [0.5] });
    document.querySelectorAll('.para-section[id]').forEach(p => obs.observe(p));
  }

  // ─── Boot ────────────────────────────────────────────────────────
  async function boot() {
    repairStructureCards();
    await D.fetchMe();
    const [pub, mine] = await Promise.all([
      D.fetchPublicNotes(),
      D.fetchUserNotes(),
    ]);
    pub.forEach(renderSavedNote);
    mine.forEach(renderSavedNote);
    setupProgressObserver();
  }

  document.addEventListener('DOMContentLoaded', boot);
})();
