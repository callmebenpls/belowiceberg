// API + state layer. Exposes window.BIData with all fetch logic.
(() => {
  const BOOK_SLUG = (location.pathname.replace(/^\/+|\/+$/g, '').split('/')[0] || 'index')
                      .replace(/\.html$/, '');

  let _me = null;  // {id, display_name, is_admin, ...} or null

  async function fetchMe() {
    try {
      const r = await fetch('/api/me', { credentials: 'same-origin' });
      _me = r.ok ? await r.json() : null;
    } catch (_) { _me = null; }
    return _me;
  }

  async function fetchPublicNotes() {
    try {
      const r = await fetch(`/api/notes/${BOOK_SLUG}`);
      return r.ok ? await r.json() : [];
    } catch (_) { return []; }
  }

  async function fetchUserNotes() {
    if (!_me) return [];
    try {
      const r = await fetch(`/api/user-notes/${BOOK_SLUG}`, { credentials: 'same-origin' });
      return r.ok ? await r.json() : [];
    } catch (_) { return []; }
  }

  async function savePublicNote(note) {
    const r = await fetch(`/api/notes/${BOOK_SLUG}`, {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(note),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
  }

  async function saveUserNote(note) {
    const r = await fetch(`/api/user-notes/${BOOK_SLUG}`, {
      method: 'POST', credentials: 'same-origin',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(note),
    });
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
  }

  async function postProgress(chapter, section) {
    if (!_me) return;
    try {
      await fetch('/api/progress', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({book_slug: BOOK_SLUG, chapter, section}),
      });
    } catch (_) { /* silent */ }
  }

  async function streamQuery(category, selectedText, paraContext, onToken, onDone, onError) {
    try {
      const r = await fetch('/api/query', {
        method: 'POST', credentials: 'same-origin',
        headers: {'Content-Type': 'application/json'},
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
            }
          }
        }
      }
      onDone();
    } catch (e) { onError(e.message); }
  }

  window.BIData = {
    BOOK_SLUG,
    get me() { return _me; },
    fetchMe, fetchPublicNotes, fetchUserNotes,
    savePublicNote, saveUserNote, postProgress, streamQuery,
  };
})();
