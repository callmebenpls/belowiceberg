# Prototype Shipping — Plan A (Frontend Polish) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish all reader-facing pages of the live BelowIceberg site (home / books catalog / library / reader) to match the prototype, shipping incrementally with no architecture changes.

**Architecture:** Static HTML files served by nginx (`/var/www/belowiceberg/`) with `/api/*` reverse-proxied to FastAPI on `127.0.0.1:8001`. Login state is detected via `GET /api/me` (returns 200 + user JSON, or 401). The site already has working auth, library, and progress APIs — this plan only touches frontend and adds one small backend endpoint for the upcoming-books list.

**Tech Stack:** Static HTML + vanilla JS + Lora/Playfair/Noto Serif SC fonts. CSS uses design tokens from `belowiceberg-website-v2.html` (gold #b8942e, ink #1a1a15, hairline borders). FastAPI on the server side for the one new endpoint.

**Spec:** `docs/superpowers/specs/2026-05-25-prototype-shipping-design.md`

**Scope of this plan:** Ships 1–4 only (home tweaks, books catalog, library redesign, reader navbar). Ships 5–6 (admin dashboard + admin editor) require a separate plan because they introduce a new admin subsystem with backend work (book CRUD, EPUB parsing, annotation job runner).

---

## File Structure

**Modified files:**

- `belowiceberg-website-v2.html` (home) — Ship 1: nav login state + hero CTA hrefs + 查看完整书库 link
- `library/index.html` — Ship 3: full content rewrite
- `library/styles.css` — Ship 3: new card grid + tabs CSS
- `gatsby-teaching-edition.html` — Ship 4: replace navbar markup + CSS
- `server/app/main.py` — Ship 3 (only if want-to-read endpoint added)

**New files:**

- `books/index.html` — Ship 2: full catalog page (search + filter + grid)
- `books/styles.css` — Ship 2: catalog styles (reuses tokens from website-v2.html)
- `server/app/routes/catalog.py` — Ship 3: `/api/want-to-read` endpoint (small, optional — see decision in Task 7)
- `server/tests/test_catalog.py` — Ship 3: tests for /api/want-to-read (if added)

**Unchanged files (already correct):**

- `login/index.html`, `settings/index.html` — user confirmed live versions are good
- All `server/app/*` modules except `main.py` and one new `routes/catalog.py`
- All migrations (`server/migrations/`)

**Deployment:** Each ship deploys by syncing changed files to `/var/www/belowiceberg/` on the server (`66.135.16.106`). The server's nginx config already serves `try_files $uri $uri/ =404;` for the root, so new directories (`/books/`) are picked up automatically without nginx changes. For backend changes, restart the systemd unit:

```bash
ssh root@66.135.16.106 'systemctl restart belowiceberg-api.service'
```

---

# SHIP 1 — Home Page Tweaks

Four targeted edits to `belowiceberg-website-v2.html` (1181 lines). No structural changes — just nav additions, button href swaps, and one new link.

---

### Task 1: Home — nav login state (guest + logged-in)

**Files:**
- Modify: `belowiceberg-website-v2.html:108-122` (`.nav-cta` CSS) and `:735-750` (nav HTML)

**Context:** The current nav has `[logo] [4 links] [开始阅读 CTA]`. We add (a) a 登录 outlined pill for guests sitting between links and CTA, and (b) when logged in, swap CTA for "我的书房" link + user chip. Detection uses `GET /api/me` (returns 200 with `{id, email, display_name, …}` or 401).

- [ ] **Step 1: Add CSS for the new nav elements**

Insert immediately after the existing `.nav-cta:hover { opacity: 0.85; }` rule (around line 122):

```css
/* Login state (added Ship 1) */
.nav-login {
  font-family: 'Noto Serif SC', serif;
  font-size: 0.82rem;
  color: var(--text2);
  text-decoration: none;
  padding: 0.35rem 0.9rem;
  border-radius: 4px;
  border: 0.5px solid var(--border);
  transition: color 0.18s, border-color 0.18s;
}
.nav-login:hover { color: var(--gold); border-color: var(--gold); }

.nav-shelf {
  font-family: 'Noto Serif SC', serif;
  font-size: 0.82rem;
  color: var(--text2);
  text-decoration: none;
  padding: 0.3rem 0.7rem;
  border-radius: 4px;
  transition: color 0.18s, background 0.18s;
}
.nav-shelf:hover { color: var(--gold); background: var(--gold-pale); }

.nav-user-chip {
  display: flex; align-items: center; gap: 0.4rem;
  padding: 0.2rem 0.7rem 0.2rem 0.3rem;
  border: 0.5px solid var(--border);
  border-radius: 999px;
  background: var(--bg);
  cursor: pointer; text-decoration: none;
  transition: border-color 0.18s;
}
.nav-user-chip:hover { border-color: var(--gold); }
.nav-user-chip .av {
  width: 22px; height: 22px; border-radius: 50%;
  background: var(--gold); color: #fff;
  display: flex; align-items: center; justify-content: center;
  font-family: 'Playfair Display', serif;
  font-size: 0.72rem; font-weight: 700;
}
.nav-user-chip .uname {
  font-family: 'Noto Serif SC', serif;
  font-size: 0.78rem; color: var(--text2);
}
.nav-user-chip .caret { font-size: 0.6rem; color: var(--text3); }
```

- [ ] **Step 2: Update the nav HTML — add guest and logged-in variants, both hidden by default**

Replace lines 734-750 (the `<nav class="nav">…</nav>` block) with:

```html
<!-- ══ NAV ══════════════════════════════════════════════════════════════ -->
<nav class="nav">
  <a href="#top" class="nav-logo">
    <div class="nav-seal"><span>B社</span></div>
    <div class="nav-brand">
      <span class="nav-brand-en">BelowIceberg</span>
      <span class="nav-brand-zh">B社</span>
    </div>
  </a>
  <ul class="nav-links">
    <li><a href="#method">方法论</a></li>
    <li><a href="#books">书目</a></li>
    <li><a href="#sample">试读</a></li>
    <li><a href="#about">关于B社</a></li>
  </ul>
  <!-- Guest state (visible by default; hidden when logged in) -->
  <a href="/login/?next=/" class="nav-login" id="nav-guest-login" hidden>登录</a>
  <a href="#books" class="nav-cta" id="nav-guest-cta" hidden>开始阅读</a>
  <!-- Logged-in state (hidden by default; shown when /api/me succeeds) -->
  <a href="/library/" class="nav-shelf" id="nav-user-shelf" hidden>我的书房</a>
  <a href="/settings/" class="nav-user-chip" id="nav-user-chip" hidden>
    <div class="av" id="nav-user-av">B</div>
    <span class="uname" id="nav-user-name">读者</span>
    <span class="caret">▾</span>
  </a>
</nav>
```

Both states start `hidden`; the script in Step 3 reveals the correct one once `/api/me` returns.

- [ ] **Step 3: Add the login-state detection script**

Find the existing `<script>` block at the bottom of the file (begins ~line 1151 with `// Smooth scroll`). Append a new script element BEFORE the existing one (so it runs first):

```html
<script>
(async () => {
  try {
    const r = await fetch('/api/me', { credentials: 'same-origin' });
    if (r.ok) {
      const u = await r.json();
      document.getElementById('nav-user-shelf').hidden = false;
      const chip = document.getElementById('nav-user-chip');
      chip.hidden = false;
      const name = u.display_name || u.email || '读者';
      document.getElementById('nav-user-name').textContent = name;
      const initial = (name.charCodeAt(0) < 128 ? name[0] : 'B').toUpperCase();
      document.getElementById('nav-user-av').textContent = initial;
      return;
    }
  } catch (_) { /* network error → fall through to guest */ }
  // Guest fallback
  document.getElementById('nav-guest-login').hidden = false;
  document.getElementById('nav-guest-cta').hidden = false;
})();
</script>
```

- [ ] **Step 4: Manual verification — guest state**

In a fresh incognito window (no cookies), load `http://66.135.16.106/`. Expected:
- Nav shows `[B社 logo] [方法论 书目 试读 关于B社] [登录] [开始阅读]`
- The 登录 button is outlined, 开始阅读 is gold filled
- No flash of "我的书房" or user chip

- [ ] **Step 5: Manual verification — logged-in state**

Log in at `/login/` as `admin@gmail.com / admin123`, then navigate back to `/`. Expected:
- Nav shows `[B社 logo] [方法论 书目 试读 关于B社] [我的书房] [(A) admin ▾]`
- Avatar shows letter "A" (first char of "admin")
- 登录 and 开始阅读 are NOT visible
- Hover on user chip → border turns gold

- [ ] **Step 6: Commit**

```bash
cd /Users/ben/Downloads/belowiceberg
git add belowiceberg-website-v2.html
git commit -m "feat(home): nav shows login state — 登录 (guest) / 我的书房 + user chip (logged in)"
```

---

### Task 2: Home — hero CTA hrefs change

**Files:**
- Modify: `belowiceberg-website-v2.html:767-770`

**Context:** Hero currently has two buttons that scroll to `#sample` and `#books` anchors. Change to route to the actual reader page and the new full catalog page.

- [ ] **Step 1: Update the hero buttons**

In `belowiceberg-website-v2.html`, find:

```html
    <div class="hero-buttons">
      <a href="#sample" class="btn-primary">免费试读</a>
      <a href="#books" class="btn-secondary">浏览全部书目</a>
    </div>
```

Replace with:

```html
    <div class="hero-buttons">
      <a href="/gatsby" class="btn-primary">免费试读</a>
      <a href="/books/" class="btn-secondary">浏览全部书目</a>
    </div>
```

(Trailing slash on `/books/` matches the existing pattern for `/library/`, `/settings/`, etc.)

- [ ] **Step 2: Manual verification**

Reload `/`. Click 免费试读 → must navigate to `/gatsby` (the Great Gatsby reader page, NOT a same-page scroll). Click 浏览全部书目 → must navigate to `/books/`. Currently `/books/` returns 404 — that's expected; Ship 2 creates the page.

Note: the existing smooth-scroll script (`document.querySelectorAll('a[href^="#"]')` in the trailing script block) only intercepts hrefs starting with `#`, so our new `/gatsby` and `/books/` hrefs trigger normal navigation correctly.

- [ ] **Step 3: Commit**

```bash
cd /Users/ben/Downloads/belowiceberg
git add belowiceberg-website-v2.html
git commit -m "feat(home): hero CTAs route to /gatsby and /books/ (was in-page scroll)"
```

---

### Task 3: Home — add "查看完整书库 →" link in Books section

**Files:**
- Modify: `belowiceberg-website-v2.html` (CSS near line 506; HTML near line 968)

**Context:** After the existing 4-book grid inside `<section class="section" id="books">`, add a centered outlined link to the new full catalog page.

- [ ] **Step 1: Add CSS**

Insert after the existing `.b-soon` rule (around line 508):

```css
/* "View full catalog" CTA — added Ship 1 */
.books-cta {
  text-align: center;
  margin-top: 3rem;
}
.books-cta a {
  display: inline-block;
  font-family: 'Noto Serif SC', serif;
  font-size: 0.9rem;
  color: var(--text);
  background: transparent;
  border: 0.5px solid var(--border);
  padding: 0.7rem 2rem;
  border-radius: 4px;
  text-decoration: none;
  transition: border-color 0.2s, background 0.2s, color 0.2s;
}
.books-cta a:hover {
  border-color: var(--gold);
  background: var(--gold-pale);
  color: var(--gold);
}
```

- [ ] **Step 2: Add the link inside the books section**

Find the closing `</div>` of `<div class="books-grid">` (around line 969). Insert the new block immediately AFTER that closing div and BEFORE the `</section>` of `#books`:

```html
        <div class="books-cta">
          <a href="/books/">查看完整书库 →</a>
        </div>
      </div>  <!-- /.books-grid (unchanged) -->
```

The exact insertion point: the file currently has:

```html
            </div>  <!-- /.book-meta-badges of the 4th book -->
          </div>  <!-- /.book-card of the 4th book -->

        </div>  <!-- closes .books-grid -->
      </section>
```

Change to:

```html
            </div>  <!-- /.book-meta-badges of the 4th book -->
          </div>  <!-- /.book-card of the 4th book -->

        </div>  <!-- closes .books-grid -->

        <div class="books-cta">
          <a href="/books/">查看完整书库 →</a>
        </div>
      </section>
```

- [ ] **Step 3: Manual verification**

Reload `/`, scroll to the "现有书目 · Current Titles" section. After the 4 book cards, expect the centered outlined button "查看完整书库 →". On hover: border gold, background gold-pale, text gold. Click → navigates to `/books/` (404 until Ship 2).

- [ ] **Step 4: Commit**

```bash
cd /Users/ben/Downloads/belowiceberg
git add belowiceberg-website-v2.html
git commit -m "feat(home): add 查看完整书库 link at end of books section"
```

---

### Task 4: Ship 1 — deploy to production

**Files:** none changed; this is a deploy step.

- [ ] **Step 1: Sync the modified file to the server**

```bash
cd /Users/ben/Downloads/belowiceberg
rsync -avz belowiceberg-website-v2.html root@66.135.16.106:/var/www/belowiceberg/index.html
```

Note: `index.html` is what nginx serves at `/` because of the `index index.html;` directive. The repo file is named `belowiceberg-website-v2.html` but on the server it lives as `index.html`. Verify with:

```bash
ssh root@66.135.16.106 'ls -la /var/www/belowiceberg/index.html'
```

If the file is actually a symlink to a different repo file, follow the existing convention instead.

- [ ] **Step 2: Smoke test live site**

```bash
curl -s http://66.135.16.106/ | grep -c "查看完整书库"
# Expected: 1

curl -s http://66.135.16.106/ | grep -c 'href="/gatsby" class="btn-primary"'
# Expected: 1
```

- [ ] **Step 3: Browser smoke test**

Open `http://66.135.16.106/` in a real browser. Run through verifications from Tasks 1–3 in production (guest state, logged-in state, button navigation, 查看完整书库 link).

- [ ] **Step 4: Commit a deploy marker**

```bash
cd /Users/ben/Downloads/belowiceberg
git commit --allow-empty -m "deploy: ship 1 — home page tweaks live on 66.135.16.106"
```

---

# SHIP 2 — Books Catalog Page

A brand-new self-contained static page at `/books/`. Search, filter (全部/已上线/即将推出), grid of all 4 books with the same cover styling as the homepage.

---

### Task 5: Create `books/index.html`

**Files:**
- Create: `books/index.html`
- Create: `books/styles.css`

**Context:** The homepage has 4 book cards in `<section id="books">`. We copy that markup pattern into a standalone page, add a search input and filter buttons, and bind small vanilla-JS filter logic. The page must include the same nav as the homepage (with login state) so users stay anchored.

- [ ] **Step 1: Create `books/styles.css`**

```css
/* /books/ catalog — reuses tokens from belowiceberg-website-v2.html */
:root {
  --bg:#fafaf7;--bg2:#f2efe7;--bg3:#e8e4d8;--bg4:#ded9cb;
  --gold:#b8942e;--gold-dim:rgba(184,148,46,0.4);
  --gold-pale:rgba(184,148,46,0.08);
  --text:#2d2a20;--text2:#6b5e3e;--text3:#a89870;--ink:#1a1a15;
  --vocab:#3a7bb5;--gram:#3a8b5e;
  --border:rgba(184,148,46,0.25);--r:8px;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{
  background:var(--bg);color:var(--text);
  font-family:'Lora','Noto Serif SC',Georgia,serif;line-height:1.8;
}

/* Nav — duplicate of homepage nav styling */
.nav{
  position:fixed;top:0;left:0;right:0;z-index:200;height:52px;
  background:rgba(250,250,247,0.94);backdrop-filter:blur(12px);
  border-bottom:0.5px solid var(--border);
  display:flex;align-items:center;padding:0 2.5rem;gap:1.5rem;
}
.nav-logo{display:flex;align-items:center;gap:0.75rem;text-decoration:none;}
.nav-seal{width:34px;height:34px;border:1px solid var(--gold);transform:rotate(45deg);display:flex;align-items:center;justify-content:center;}
.nav-seal span{font-family:'Noto Serif SC',serif;font-size:11px;color:var(--gold);transform:rotate(-45deg);}
.nav-brand{display:flex;flex-direction:column;line-height:1.1;}
.nav-brand-en{font-family:'Playfair Display',serif;font-size:0.95rem;font-weight:700;color:var(--ink);}
.nav-brand-zh{font-family:'Noto Serif SC',serif;font-size:0.62rem;color:var(--gold);letter-spacing:0.2em;}
.nav-links{display:flex;gap:0.25rem;list-style:none;margin-left:auto;}
.nav-links a{font-family:'Noto Serif SC',serif;font-size:0.82rem;color:var(--text2);text-decoration:none;padding:0.3rem 0.8rem;border-radius:4px;}
.nav-links a:hover,.nav-links a.active{color:var(--gold);background:var(--gold-pale);}
.nav-login,.nav-cta,.nav-shelf{font-family:'Noto Serif SC',serif;font-size:0.82rem;text-decoration:none;padding:0.35rem 0.9rem;border-radius:4px;}
.nav-login{color:var(--text2);border:0.5px solid var(--border);}
.nav-login:hover{color:var(--gold);border-color:var(--gold);}
.nav-cta{background:var(--gold);color:var(--bg);border:none;}
.nav-shelf{color:var(--text2);}
.nav-shelf:hover{color:var(--gold);background:var(--gold-pale);}
.nav-user-chip{display:flex;align-items:center;gap:0.4rem;padding:0.2rem 0.7rem 0.2rem 0.3rem;border:0.5px solid var(--border);border-radius:999px;background:var(--bg);text-decoration:none;}
.nav-user-chip:hover{border-color:var(--gold);}
.nav-user-chip .av{width:22px;height:22px;border-radius:50%;background:var(--gold);color:#fff;display:flex;align-items:center;justify-content:center;font-family:'Playfair Display',serif;font-size:0.72rem;font-weight:700;}
.nav-user-chip .uname{font-family:'Noto Serif SC',serif;font-size:0.78rem;color:var(--text2);}
.nav-user-chip .caret{font-size:0.6rem;color:var(--text3);}

/* Page */
.catalog{max-width:1100px;margin:0 auto;padding:88px 2rem 5rem;}
.catalog-header{text-align:center;margin-bottom:2.5rem;}
.catalog-tag{font-family:'JetBrains Mono',monospace;font-size:0.7rem;letter-spacing:0.3em;color:var(--gold);margin-bottom:0.6rem;text-transform:uppercase;}
.catalog-h1{font-family:'Playfair Display',serif;font-size:2rem;color:var(--ink);margin-bottom:0.4rem;}
.catalog-sub{font-family:'Noto Serif SC',serif;font-size:0.95rem;color:var(--text2);}

/* Search */
.catalog-search-wrap{max-width:480px;margin:0 auto 1.5rem;position:relative;}
.catalog-search{
  width:100%;font-family:'Lora',serif;font-size:0.95rem;
  padding:0.7rem 1rem 0.7rem 2.8rem;
  border:0.5px solid var(--border);border-radius:var(--r);
  background:var(--bg);color:var(--text);outline:none;
  transition:border-color 0.15s;
}
.catalog-search:focus{border-color:var(--gold);}
.catalog-search-icon{position:absolute;left:0.9rem;top:50%;transform:translateY(-50%);width:18px;height:18px;color:var(--text3);}

/* Filter tabs */
.catalog-filters{display:flex;gap:0.5rem;justify-content:center;margin-bottom:2.5rem;flex-wrap:wrap;}
.catalog-filter{
  font-family:'Noto Serif SC',serif;font-size:0.85rem;
  padding:0.45rem 1rem;border:0.5px solid var(--border);
  border-radius:var(--r);background:var(--bg);color:var(--text2);cursor:pointer;
  transition:all 0.15s;
}
.catalog-filter:hover{border-color:var(--gold);color:var(--gold);}
.catalog-filter.active{background:var(--gold);color:var(--bg);border-color:var(--gold);}

/* Book grid — same look as homepage but in its own context */
.catalog-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:2rem;}
.book-card{display:flex;flex-direction:column;text-decoration:none;cursor:pointer;transition:transform 0.25s;}
.book-card:hover{transform:translateY(-5px);}
.book-card.soon{cursor:default;opacity:0.85;}
.book-cover{aspect-ratio:2/3;border-radius:var(--r);overflow:hidden;position:relative;margin-bottom:1rem;border:0.5px solid var(--border);box-shadow:-3px 3px 0 var(--gold-dim),0 12px 40px rgba(44,36,20,0.15);display:flex;flex-direction:column;align-items:center;justify-content:center;padding:1.4rem;text-align:center;}
.bc-title-en{font-family:'Playfair Display',serif;font-size:0.95rem;font-weight:700;color:var(--ink);line-height:1.3;margin-bottom:0.3rem;}
.bc-title-zh{font-family:'Noto Serif SC',serif;font-size:0.82rem;color:var(--gold);margin-bottom:0.4rem;}
.bc-author{font-family:'Lora',serif;font-size:0.68rem;font-style:italic;color:var(--text2);}
.bc-label{position:absolute;bottom:0.6rem;left:0;right:0;text-align:center;font-family:'JetBrains Mono',monospace;font-size:0.55rem;letter-spacing:0.18em;text-transform:uppercase;color:var(--text3);}
.bc-gatsby{background:linear-gradient(150deg,#f5f0e0 0%,#ede5c8 60%,#e0d8b8 100%);}
.bc-henry{background:linear-gradient(150deg,#f0f0e8 0%,#e8e8d8 60%,#d8d8c0 100%);}
.bc-sun{background:linear-gradient(150deg,#f5ede0 0%,#edd8c0 60%,#e0c8a8 100%);}
.bc-falcon{background:linear-gradient(150deg,#e8f0ee 0%,#d0e8e0 60%,#b8d8cc 100%);}

.book-meta-en{font-family:'Lora',serif;font-size:0.9rem;font-weight:500;color:var(--text);margin-bottom:0.15rem;}
.book-meta-zh{font-family:'Noto Serif SC',serif;font-size:0.82rem;color:var(--gold);margin-bottom:0.5rem;}
.book-meta-badges{display:flex;gap:0.4rem;flex-wrap:wrap;}
.badge{font-family:'JetBrains Mono',monospace;font-size:0.58rem;letter-spacing:0.08em;padding:0.15rem 0.5rem;border-radius:3px;text-transform:uppercase;}
.b-level{background:var(--gold-pale);color:var(--text2);border:0.5px solid var(--border);}
.b-avail{background:rgba(58,139,94,0.1);color:var(--gram);border:0.5px solid rgba(58,139,94,0.3);}
.b-soon{background:var(--bg3);color:var(--text3);border:0.5px solid var(--bg4);}

/* Empty state */
.catalog-empty{text-align:center;padding:4rem 0;color:var(--text3);display:none;}
.catalog-empty p{font-family:'Noto Serif SC',serif;}

@media (max-width:640px){
  .nav{padding:0 1rem;}
  .nav-links{display:none;}
  .catalog-grid{grid-template-columns:repeat(2,1fr);gap:1.2rem;}
}
@media (max-width:400px){
  .catalog-grid{grid-template-columns:1fr;}
}
```

- [ ] **Step 2: Create `books/index.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>书库 · BelowIceberg · B社</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Lora:ital,wght@0,400;0,500;1,400&family=Noto+Serif+SC:wght@300;400;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
</head>
<body>

<nav class="nav">
  <a href="/" class="nav-logo">
    <div class="nav-seal"><span>B社</span></div>
    <div class="nav-brand">
      <span class="nav-brand-en">BelowIceberg</span>
      <span class="nav-brand-zh">B社</span>
    </div>
  </a>
  <ul class="nav-links">
    <li><a href="/#method">方法论</a></li>
    <li><a href="/books/" class="active">书目</a></li>
    <li><a href="/#sample">试读</a></li>
    <li><a href="/#about">关于B社</a></li>
  </ul>
  <a href="/login/?next=/books/" class="nav-login" id="nav-guest-login" hidden>登录</a>
  <a href="/gatsby" class="nav-cta" id="nav-guest-cta" hidden>开始阅读</a>
  <a href="/library/" class="nav-shelf" id="nav-user-shelf" hidden>我的书房</a>
  <a href="/settings/" class="nav-user-chip" id="nav-user-chip" hidden>
    <div class="av" id="nav-user-av">B</div>
    <span class="uname" id="nav-user-name">读者</span>
    <span class="caret">▾</span>
  </a>
</nav>

<main class="catalog">
  <header class="catalog-header">
    <div class="catalog-tag">COLLECTION · 全部书库</div>
    <h1 class="catalog-h1">经典文学精读</h1>
    <p class="catalog-sub">精选英文文学经典，逐段六维深度分析</p>
  </header>

  <div class="catalog-search-wrap">
    <svg class="catalog-search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35"/></svg>
    <input id="catalog-search" class="catalog-search" type="text" placeholder="搜索书名、作者...">
  </div>

  <div class="catalog-filters">
    <button class="catalog-filter active" data-status="all">全部</button>
    <button class="catalog-filter" data-status="live">已上线</button>
    <button class="catalog-filter" data-status="soon">即将推出</button>
  </div>

  <div id="catalog-grid" class="catalog-grid">
    <a href="/gatsby" class="book-card" data-status="live" data-search="the great gatsby f scott fitzgerald 盖茨比 菲茨杰拉德">
      <div class="book-cover bc-gatsby">
        <span class="bc-title-en">The Great<br>Gatsby</span>
        <span class="bc-title-zh">了不起的盖茨比</span>
        <span class="bc-author">F. Scott Fitzgerald</span>
        <span class="bc-label">BelowIceberg · B社</span>
      </div>
      <div class="book-meta-en">The Great Gatsby</div>
      <div class="book-meta-zh">了不起的盖茨比</div>
      <div class="book-meta-badges">
        <span class="badge b-level">B2–C1</span>
        <span class="badge b-avail">已上架</span>
      </div>
    </a>
    <div class="book-card soon" data-status="soon" data-search="o henry short stories 欧亨利 麦琪的礼物 最后一片叶子">
      <div class="book-cover bc-henry">
        <span class="bc-title-en">O. Henry<br>Short Stories</span>
        <span class="bc-title-zh">欧·亨利短篇精选</span>
        <span class="bc-author">O. Henry</span>
        <span class="bc-label">BelowIceberg · B社</span>
      </div>
      <div class="book-meta-en">O. Henry — Short Stories</div>
      <div class="book-meta-zh">欧·亨利短篇精选</div>
      <div class="book-meta-badges">
        <span class="badge b-level">B1–B2</span>
        <span class="badge b-soon">即将上架</span>
      </div>
    </div>
    <div class="book-card soon" data-status="soon" data-search="the sun also rises ernest hemingway 太阳照常升起 海明威">
      <div class="book-cover bc-sun">
        <span class="bc-title-en">The Sun Also<br>Rises</span>
        <span class="bc-title-zh">太阳照常升起</span>
        <span class="bc-author">Ernest Hemingway</span>
        <span class="bc-label">BelowIceberg · B社</span>
      </div>
      <div class="book-meta-en">The Sun Also Rises</div>
      <div class="book-meta-zh">太阳照常升起</div>
      <div class="book-meta-badges">
        <span class="badge b-level">B2–C1</span>
        <span class="badge b-soon">即将上架</span>
      </div>
    </div>
    <div class="book-card soon" data-status="soon" data-search="the maltese falcon dashiell hammett 马耳他之鹰 哈米特">
      <div class="book-cover bc-falcon">
        <span class="bc-title-en">The Maltese<br>Falcon</span>
        <span class="bc-title-zh">马耳他之鹰</span>
        <span class="bc-author">Dashiell Hammett</span>
        <span class="bc-label">BelowIceberg · B社</span>
      </div>
      <div class="book-meta-en">The Maltese Falcon</div>
      <div class="book-meta-zh">马耳他之鹰</div>
      <div class="book-meta-badges">
        <span class="badge b-level">B2</span>
        <span class="badge b-soon">即将上架</span>
      </div>
    </div>
  </div>

  <div id="catalog-empty" class="catalog-empty">
    <p>没有找到匹配的书籍</p>
    <p style="font-size:0.85rem;margin-top:0.5rem">试试其他关键词？</p>
  </div>
</main>

<script>
// Login state — same pattern as homepage
(async () => {
  try {
    const r = await fetch('/api/me', { credentials: 'same-origin' });
    if (r.ok) {
      const u = await r.json();
      document.getElementById('nav-user-shelf').hidden = false;
      const chip = document.getElementById('nav-user-chip');
      chip.hidden = false;
      const name = u.display_name || u.email || '读者';
      document.getElementById('nav-user-name').textContent = name;
      const initial = (name.charCodeAt(0) < 128 ? name[0] : 'B').toUpperCase();
      document.getElementById('nav-user-av').textContent = initial;
      return;
    }
  } catch (_) {}
  document.getElementById('nav-guest-login').hidden = false;
  document.getElementById('nav-guest-cta').hidden = false;
})();

// Filter + search
const searchInput = document.getElementById('catalog-search');
const filterButtons = document.querySelectorAll('.catalog-filter');
const cards = document.querySelectorAll('.book-card');
const empty = document.getElementById('catalog-empty');
let activeStatus = 'all';

function applyFilters() {
  const q = searchInput.value.trim().toLowerCase();
  let visible = 0;
  cards.forEach(c => {
    const status = c.dataset.status;
    const haystack = c.dataset.search.toLowerCase();
    const statusOk = activeStatus === 'all' || status === activeStatus;
    const searchOk = !q || haystack.includes(q);
    const show = statusOk && searchOk;
    c.style.display = show ? '' : 'none';
    if (show) visible++;
  });
  empty.style.display = visible === 0 ? 'block' : 'none';
}

searchInput.addEventListener('input', applyFilters);
filterButtons.forEach(btn => {
  btn.addEventListener('click', () => {
    filterButtons.forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    activeStatus = btn.dataset.status;
    applyFilters();
  });
});

// Soft toast for 即将上架 cards (no destination)
cards.forEach(c => {
  if (c.dataset.status === 'soon') {
    c.addEventListener('click', e => {
      e.preventDefault();
      const t = document.createElement('div');
      t.textContent = '此书精读版正在制作中';
      t.style.cssText = 'position:fixed;bottom:2rem;left:50%;transform:translateX(-50%);background:#1a1a15;color:#b8942e;padding:0.6rem 1.2rem;border-radius:4px;font-family:Noto Serif SC,serif;font-size:0.85rem;z-index:300';
      document.body.appendChild(t);
      setTimeout(() => t.remove(), 2400);
    });
  }
});
</script>
</body>
</html>
```

- [ ] **Step 3: Local smoke test (open the file directly)**

```bash
cd /Users/ben/Downloads/belowiceberg
open books/index.html
```

In the browser:
- Page renders with 4 book covers and the header "经典文学精读"
- Search box: type "gat" → only Gatsby visible; clear → all 4 show
- Click "已上线" filter → only Gatsby; click "即将推出" → other 3; click "全部" → all 4
- Combined: type "hemingway" with "已上线" active → empty state appears
- Login state will fail to fetch `/api/me` (local file://); guest CTAs show

- [ ] **Step 4: Commit**

```bash
cd /Users/ben/Downloads/belowiceberg
git add books/
git commit -m "feat(books): new /books/ catalog page with search and live/soon filter"
```

---

### Task 6: Ship 2 — deploy catalog to production

**Files:** none changed.

- [ ] **Step 1: Sync the new directory**

```bash
cd /Users/ben/Downloads/belowiceberg
rsync -avz books/ root@66.135.16.106:/var/www/belowiceberg/books/
```

- [ ] **Step 2: Verify nginx serves the page**

```bash
curl -sI http://66.135.16.106/books/ | head -1
# Expected: HTTP/1.1 200 OK

curl -s http://66.135.16.106/books/ | grep -c "经典文学精读"
# Expected: 1
```

If you get 404, check that `books/index.html` exists with the right permissions:

```bash
ssh root@66.135.16.106 'ls -la /var/www/belowiceberg/books/'
```

The nginx `location / { try_files $uri $uri/ =404; }` directive serves `books/index.html` automatically — no nginx changes needed.

- [ ] **Step 3: Live browser test**

Open `http://66.135.16.106/books/`. Run through the filter/search tests from Task 5 Step 3 — but now logged in (so user chip should appear in nav). Also click 查看完整书库 from the homepage and confirm it lands here.

- [ ] **Step 4: Commit deploy marker**

```bash
cd /Users/ben/Downloads/belowiceberg
git commit --allow-empty -m "deploy: ship 2 — /books/ catalog page live on 66.135.16.106"
```

---

# SHIP 3 — Library Page Redesign

Rewrite the `/library/` page from the current continue-reading-card + stats + tiny book list layout to the new design: 3 tabs (正在阅读 / 想读 / 已读完), uniform 3:4 cover-card grid with per-card progress overlays, and a "Want to Read" section listing upcoming books.

The library page already calls `/api/library` and gets back `{current, books_in_progress, stats, all_my_notes}`. The new design uses `books_in_progress` for the 正在阅读 tab and ignores `stats`/`all_my_notes` (we're dropping those sections per the spec).

For the 想读 tab, the simplest source is a small hardcoded array baked into the page (YAGNI — no admin tooling yet to manage it). This matches the data already shown on the homepage's "现有书目" section.

---

### Task 7: Decide want-to-read source — hardcoded list

**Files:** none. This is a design decision step, locked here so later tasks don't have to revisit it.

**Decision:** Hardcode the want-to-read list inline in `library/index.html` as a JS array. Same titles as the homepage's 现有书目 grid: O. Henry / Sun Also Rises / Maltese Falcon. When admin tooling lands in Plan B, swap to `/api/books?status=draft`.

Rationale:
- No new backend endpoint needed for Plan A.
- The list is small (3 entries) and rarely changes.
- Hard-coding it avoids coupling the library page to admin-state that doesn't exist yet.

No code changes in this step; the decision is encoded directly in Task 8.

- [ ] **Step 1: Note the decision in commit**

No file change — proceed to Task 8.

---

### Task 8: Library — rewrite the page

**Files:**
- Modify: `library/index.html` (full replacement, currently 92 lines)
- Modify: `library/styles.css` (full replacement)

**Context:** The existing page has a working `/api/library` fetch and a logout button — we preserve the API call and the redirect-to-login-on-401 behavior. Everything else (content rendering, layout, styling) is replaced.

- [ ] **Step 1: Replace `library/styles.css`**

```css
:root {
  --bg:#fafaf7;--bg2:#f2efe7;--bg3:#e8e4d8;--bg4:#ded9cb;
  --gold:#b8942e;--gold-dim:rgba(184,148,46,0.4);
  --gold-pale:rgba(184,148,46,0.08);
  --text:#2d2a20;--text2:#6b5e3e;--text3:#a89870;--ink:#1a1a15;
  --border:rgba(184,148,46,0.25);--r:8px;
}
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
body{background:var(--bg);color:var(--text);font-family:'Lora','Noto Serif SC',Georgia,serif;line-height:1.8;}

/* Nav — same pattern as books page */
.nav{
  position:fixed;top:0;left:0;right:0;z-index:200;height:52px;
  background:rgba(250,250,247,0.94);backdrop-filter:blur(12px);
  border-bottom:0.5px solid var(--border);
  display:flex;align-items:center;padding:0 2.5rem;gap:1.5rem;
}
.nav-logo{display:flex;align-items:center;gap:0.75rem;text-decoration:none;}
.nav-seal{width:34px;height:34px;border:1px solid var(--gold);transform:rotate(45deg);display:flex;align-items:center;justify-content:center;}
.nav-seal span{font-family:'Noto Serif SC',serif;font-size:11px;color:var(--gold);transform:rotate(-45deg);}
.nav-brand{display:flex;flex-direction:column;line-height:1.1;}
.nav-brand-en{font-family:'Playfair Display',serif;font-size:0.95rem;font-weight:700;color:var(--ink);}
.nav-brand-zh{font-family:'Noto Serif SC',serif;font-size:0.62rem;color:var(--gold);letter-spacing:0.2em;}
.nav-links{display:flex;gap:0.25rem;list-style:none;margin-left:auto;}
.nav-links a{font-family:'Noto Serif SC',serif;font-size:0.82rem;color:var(--text2);text-decoration:none;padding:0.3rem 0.8rem;border-radius:4px;}
.nav-links a:hover,.nav-links a.active{color:var(--gold);background:var(--gold-pale);}
.nav-user-chip{display:flex;align-items:center;gap:0.4rem;padding:0.2rem 0.7rem 0.2rem 0.3rem;border:0.5px solid var(--border);border-radius:999px;background:var(--bg);text-decoration:none;}
.nav-user-chip:hover{border-color:var(--gold);}
.nav-user-chip .av{width:22px;height:22px;border-radius:50%;background:var(--gold);color:#fff;display:flex;align-items:center;justify-content:center;font-family:'Playfair Display',serif;font-size:0.72rem;font-weight:700;}
.nav-user-chip .uname{font-family:'Noto Serif SC',serif;font-size:0.78rem;color:var(--text2);}
.nav-user-chip .caret{font-size:0.6rem;color:var(--text3);}

/* Page */
.lib{max-width:1100px;margin:0 auto;padding:88px 2rem 5rem;}

/* Tabs */
.lib-tabs{display:flex;gap:0;margin-bottom:2.5rem;}
.lib-tab{
  font-family:'Noto Serif SC',serif;font-size:0.88rem;
  padding:0.55rem 1.3rem;border:1px solid var(--border);
  cursor:pointer;background:var(--bg);color:var(--text3);
  transition:all 0.15s;
}
.lib-tab:first-child{border-radius:var(--r) 0 0 var(--r);}
.lib-tab:last-child{border-radius:0 var(--r) var(--r) 0;}
.lib-tab:not(:first-child){border-left:none;}
.lib-tab.active{background:var(--gold);color:var(--bg);border-color:var(--gold);}
.lib-tab .count{font-size:0.75rem;margin-left:0.35rem;opacity:0.7;}

/* Section header (eyebrow + optional title + optional count) */
.lib-section-header{
  display:flex;justify-content:space-between;align-items:baseline;
  margin-bottom:1.2rem;padding-bottom:0.8rem;
  border-bottom:1px solid var(--border);
}
.lib-eyebrow{font-family:'JetBrains Mono',monospace;font-size:0.7rem;letter-spacing:0.2em;color:var(--gold);}
.lib-section-title{font-family:'Noto Serif SC',serif;font-size:1rem;color:var(--ink);margin-left:1rem;}
.lib-section-count{font-family:'JetBrains Mono',monospace;font-size:0.72rem;color:var(--gold);}

/* Book grid */
.lib-grid{
  display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));
  gap:1.5rem;margin-bottom:3rem;
}
.lib-card{cursor:pointer;text-decoration:none;color:inherit;transition:transform 0.18s;}
.lib-card:hover{transform:translateY(-3px);}
.lib-cover{
  width:100%;aspect-ratio:3/4;border-radius:var(--r);
  overflow:hidden;position:relative;
  border:0.5px solid var(--border);
}
.lib-cover-inner{
  width:100%;height:100%;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  padding:1.5rem 1rem;text-align:center;
}
.lib-cover-inner .ct{font-family:'Playfair Display',serif;font-size:1.05rem;font-weight:700;color:var(--ink);line-height:1.3;margin-bottom:0.4rem;}
.lib-cover-inner .cz{font-family:'Noto Serif SC',serif;font-size:0.78rem;color:var(--gold);}

/* Progress overlay at bottom of reading cards */
.lib-progress{
  position:absolute;bottom:0;left:0;right:0;
  background:rgba(255,255,255,0.88);backdrop-filter:blur(6px);
  padding:0.6rem 0.8rem;
}
.lib-progress .pos{font-family:'Noto Serif SC',serif;font-size:0.68rem;color:var(--text2);margin-bottom:0.3rem;}
.lib-bar{height:3px;background:var(--bg3);border-radius:2px;overflow:hidden;}
.lib-bar-fill{height:100%;background:var(--gold);border-radius:2px;}
.lib-row{display:flex;justify-content:space-between;margin-top:0.2rem;}
.lib-row span{font-family:'JetBrains Mono',monospace;font-size:0.58rem;color:var(--text3);}

/* Soon badge for want-to-read cards */
.lib-soon-badge{
  position:absolute;bottom:0.8rem;left:50%;transform:translateX(-50%);
  font-family:'JetBrains Mono',monospace;font-size:0.62rem;
  color:var(--text3);letter-spacing:0.05em;
}

/* Card meta below */
.lib-meta{padding:0.6rem 0.15rem 0;}
.lib-meta .mt{font-family:'Playfair Display',serif;font-size:0.85rem;color:var(--ink);line-height:1.3;}
.lib-meta .ms{font-size:0.72rem;color:var(--text3);line-height:1.4;}

/* Empty state */
.lib-empty{text-align:center;padding:3rem 1rem;color:var(--text3);}
.lib-empty a{color:var(--gold);}

/* Loading */
.lib-loading{text-align:center;padding:5rem 2rem;color:var(--text3);font-family:'Noto Serif SC',serif;}

@media (max-width:640px){
  .nav{padding:0 1rem;}
  .nav-links{display:none;}
  .lib-grid{grid-template-columns:repeat(2,1fr);gap:1rem;}
  .lib-tab{font-size:0.8rem;padding:0.45rem 0.9rem;}
}
```

- [ ] **Step 2: Replace `library/index.html`**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>我的书房 · BelowIceberg · B社</title>
<link href="https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,700;1,400&family=Lora:ital,wght@0,400;0,500;1,400&family=Noto+Serif+SC:wght@300;400;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<link rel="stylesheet" href="styles.css">
</head>
<body>

<nav class="nav">
  <a href="/" class="nav-logo">
    <div class="nav-seal"><span>B社</span></div>
    <div class="nav-brand">
      <span class="nav-brand-en">BelowIceberg</span>
      <span class="nav-brand-zh">B社</span>
    </div>
  </a>
  <ul class="nav-links">
    <li><a href="/#method">方法论</a></li>
    <li><a href="/books/">书目</a></li>
    <li><a href="/library/" class="active">我的书房</a></li>
    <li><a href="/#about">关于B社</a></li>
  </ul>
  <a href="/settings/" class="nav-user-chip" id="nav-user-chip" hidden>
    <div class="av" id="nav-user-av">B</div>
    <span class="uname" id="nav-user-name">读者</span>
    <span class="caret">▾</span>
  </a>
</nav>

<main class="lib">
  <div id="lib-loading" class="lib-loading">加载中…</div>
  <div id="lib-root" hidden>
    <div class="lib-tabs">
      <div class="lib-tab active" data-tab="reading">正在阅读<span class="count" id="cnt-reading">0</span></div>
      <div class="lib-tab" data-tab="want">想读<span class="count" id="cnt-want">0</span></div>
      <div class="lib-tab" data-tab="done">已读完<span class="count" id="cnt-done">0</span></div>
    </div>

    <!-- Reading tab -->
    <div class="lib-tab-panel" data-panel="reading">
      <div class="lib-section-header">
        <span class="lib-eyebrow">CURRENTLY READING · 正在阅读</span>
      </div>
      <div id="reading-grid" class="lib-grid"></div>
      <div id="reading-empty" class="lib-empty" hidden>
        <p>你还没有开始阅读。</p>
        <p style="margin-top:0.5rem"><a href="/gatsby">从《了不起的盖茨比》开始 →</a></p>
      </div>
    </div>

    <!-- Want-to-read tab -->
    <div class="lib-tab-panel" data-panel="want" hidden>
      <div class="lib-section-header">
        <div><span class="lib-eyebrow">WANT TO READ · 想读</span><span class="lib-section-title">B社系列下一批书目</span></div>
        <span class="lib-section-count" id="want-count-label">3 部即将上架</span>
      </div>
      <div id="want-grid" class="lib-grid"></div>
    </div>

    <!-- Done tab -->
    <div class="lib-tab-panel" data-panel="done" hidden>
      <div class="lib-section-header">
        <span class="lib-eyebrow">FINISHED · 已读完</span>
      </div>
      <div class="lib-empty">
        <p>你还没有完成任何书目。</p>
      </div>
    </div>
  </div>
</main>

<script>
// Book metadata — slug → display info + cover class. Mirrors the homepage 现有书目 data.
const BOOK_META = {
  'gatsby': {
    title_en: 'The Great Gatsby',
    title_zh: '了不起的盖茨比',
    author: 'F. Scott Fitzgerald',
    cover_class: 'bc-gatsby',
    gradient: 'linear-gradient(155deg,#f0e8d5,#e2d8c0)',
    chapters: 9
  }
};

// Want-to-read — hardcoded for Plan A (Task 7 decision). Plan B replaces with /api/books?status=draft.
const WANT_TO_READ = [
  { title_en: 'O. Henry Short Stories', title_zh: '欧·亨利短篇精选', author: 'O. Henry',
    gradient: 'linear-gradient(155deg,#f5f0e8,#ede6d6)' },
  { title_en: 'The Sun Also Rises', title_zh: '太阳照常升起', author: 'Ernest Hemingway',
    gradient: 'linear-gradient(155deg,#f5e8d8,#eddcc8)' },
  { title_en: 'The Maltese Falcon', title_zh: '马耳他之鹰', author: 'Dashiell Hammett',
    gradient: 'linear-gradient(155deg,#e0eee8,#d0e2da)' }
];

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, c => ({ '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;' }[c]));
}

function meta(slug) {
  return BOOK_META[slug] || { title_en: slug, title_zh: slug, author: '', gradient: 'linear-gradient(155deg,#e8e4d8,#d4cdb4)', chapters: 1 };
}

function readingCardHtml(book) {
  const m = meta(book.book_slug);
  const totalSections = m.chapters * 10; // rough estimate; replaced when real chapter metadata lands
  const doneSections = Math.max(1, (book.chapter - 1) * 10 + book.section);
  const pct = Math.min(100, Math.round(100 * doneSections / Math.max(1, totalSections)));
  return `
    <a class="lib-card" href="/${escapeHtml(book.book_slug)}#ch${book.chapter}s${book.section}">
      <div class="lib-cover" style="background:${m.gradient}">
        <div class="lib-cover-inner">
          <div class="ct">${escapeHtml(m.title_en)}</div>
          <div class="cz">${escapeHtml(m.title_zh)}</div>
        </div>
        <div class="lib-progress">
          <div class="pos">第 ${book.chapter} 章 · 第 ${book.section} 节</div>
          <div class="lib-bar"><div class="lib-bar-fill" style="width:${pct}%"></div></div>
          <div class="lib-row"><span>Ch.${book.chapter} · ${book.section}/10</span><span>${pct}%</span></div>
        </div>
      </div>
      <div class="lib-meta">
        <div class="mt">${escapeHtml(m.title_en)}</div>
        <div class="ms">${escapeHtml(m.title_zh)} · ${escapeHtml(m.author)}</div>
      </div>
    </a>`;
}

function wantCardHtml(b) {
  return `
    <div class="lib-card">
      <div class="lib-cover" style="background:${b.gradient}">
        <div class="lib-cover-inner">
          <div class="ct">${escapeHtml(b.title_en)}</div>
          <div class="cz">${escapeHtml(b.title_zh)}</div>
        </div>
        <div class="lib-soon-badge">即将上架</div>
      </div>
      <div class="lib-meta">
        <div class="mt">${escapeHtml(b.title_en)}</div>
        <div class="ms">${escapeHtml(b.title_zh)} · ${escapeHtml(b.author)}</div>
      </div>
    </div>`;
}

function renderReading(books) {
  const grid = document.getElementById('reading-grid');
  const empty = document.getElementById('reading-empty');
  document.getElementById('cnt-reading').textContent = books.length;
  if (books.length === 0) { grid.innerHTML = ''; empty.hidden = false; return; }
  empty.hidden = true;
  grid.innerHTML = books.map(readingCardHtml).join('');
}

function renderWant(items) {
  document.getElementById('cnt-want').textContent = items.length;
  document.getElementById('want-count-label').textContent = `${items.length} 部即将上架`;
  document.getElementById('want-grid').innerHTML = items.map(wantCardHtml).join('');
}

function setUserChip(u) {
  const chip = document.getElementById('nav-user-chip');
  chip.hidden = false;
  const name = u.display_name || u.email || '读者';
  document.getElementById('nav-user-name').textContent = name;
  const initial = (name.charCodeAt(0) < 128 ? name[0] : 'B').toUpperCase();
  document.getElementById('nav-user-av').textContent = initial;
}

function wireTabs() {
  const tabs = document.querySelectorAll('.lib-tab');
  const panels = document.querySelectorAll('.lib-tab-panel');
  tabs.forEach(t => {
    t.addEventListener('click', () => {
      tabs.forEach(x => x.classList.remove('active'));
      t.classList.add('active');
      const which = t.dataset.tab;
      panels.forEach(p => { p.hidden = p.dataset.panel !== which; });
    });
  });
}

(async () => {
  // Fetch library data; redirect to login if not authed
  const r = await fetch('/api/library', { credentials: 'same-origin' });
  if (r.status === 401) { location.href = '/login/?next=/library/'; return; }
  if (!r.ok) {
    document.getElementById('lib-loading').textContent = '加载失败，请刷新';
    return;
  }
  const data = await r.json();

  // Also fetch /api/me for the nav chip (we already know user is logged in)
  try {
    const me = await fetch('/api/me', { credentials: 'same-origin' });
    if (me.ok) setUserChip(await me.json());
  } catch (_) {}

  document.getElementById('lib-loading').remove();
  document.getElementById('lib-root').hidden = false;

  renderReading(data.books_in_progress || []);
  renderWant(WANT_TO_READ);
  wireTabs();
})();
</script>
</body>
</html>
```

- [ ] **Step 3: Local smoke test**

Run the server locally if convenient, or open the file with credentials disabled to verify it shows the loading state:

```bash
cd /Users/ben/Downloads/belowiceberg
open library/index.html
```

It will redirect to `/login/?next=/library/` because `/api/library` fails with file://; that's expected. Real testing happens in Task 9 on the live server.

- [ ] **Step 4: Commit**

```bash
cd /Users/ben/Downloads/belowiceberg
git add library/
git commit -m "feat(library): redesign — 3 tabs, uniform cover-card grid, hardcoded want-to-read list"
```

---

### Task 9: Ship 3 — deploy library to production

**Files:** none changed.

- [ ] **Step 1: Sync library dir**

```bash
cd /Users/ben/Downloads/belowiceberg
rsync -avz library/ root@66.135.16.106:/var/www/belowiceberg/library/
```

- [ ] **Step 2: Smoke test — guest**

In incognito, navigate to `http://66.135.16.106/library/`. Expected: redirect to `/login/?next=/library/`.

- [ ] **Step 3: Smoke test — logged in**

Log in as `admin@gmail.com / admin123`. Navigate to `/library/`. Expected:
- 3 tabs across top: 正在阅读 (count matches the number of books with progress; should be ≥1 if admin has read), 想读 3, 已读完 0
- 正在阅读 tab active by default; if admin has Gatsby progress, see a Gatsby cover card with overlay showing "第 N 章 · 第 M 节" and a gold progress bar
- Click 想读 → 3 cover cards (O. Henry / Sun Also Rises / Maltese Falcon) with "即将上架" badge
- Click 已读完 → empty state "你还没有完成任何书目"
- User chip in nav (top right) shows "(A) admin"

If 正在阅读 is empty for the admin user, first visit `/gatsby` and scroll to trigger a progress update, then return to `/library/`.

- [ ] **Step 4: Mobile smoke (per project memory: "minimal + always responsive")**

Resize browser to 375px (iPhone width). Verify:
- Nav links hide (replaced by chip alone)
- Tabs wrap or remain inline (font shrinks)
- Grid switches to 2 columns

- [ ] **Step 5: Commit deploy marker**

```bash
cd /Users/ben/Downloads/belowiceberg
git commit --allow-empty -m "deploy: ship 3 — library redesign live on 66.135.16.106"
```

---

# SHIP 4 — Reader Navbar Polish

The `/gatsby` reader (file: `gatsby-teaching-edition.html`, 11420 lines) has a navbar near the top. Replace it with the 3-zone layout from the prototype: left = back + brand, center = chapter tabs (existing), right = 我的书房 + user chip / 登录.

The reader is a large file. Find the navbar by class — almost certainly `.reader-navbar` or similar. The change is purely the navbar markup + a small CSS addition; the rest of the reader (cover, chapters, annotations) is untouched.

---

### Task 10: Reader — rebuild navbar (CSS + HTML + login state)

**Files:**
- Modify: `gatsby-teaching-edition.html` (CSS at lines 170-204, HTML at lines 444-456, add script before existing scripts)

**Context (locked from discovery):** The reader navbar uses class `.navbar` (not `.reader-navbar`). The current CSS is at lines 170–204 and the HTML at lines 444–456. The existing markup has only brand + chapter tab list — no 书库/书架 buttons exist yet (so no rename needed; we're adding the back/shelf/login pieces from scratch). The chapter tab `<li><a href="#chN">Ch.N</a></li>` entries (9 chapters) must be preserved exactly.

- [ ] **Step 1: Replace the entire `.navbar` CSS block (lines 170–204)**

Replace lines 170–204 of `gatsby-teaching-edition.html` (the `/* ── NAV BAR ── */` section through the `.navbar-links a:hover` rule) with:

```css
/* ── NAV BAR — 3-zone grid (Ship 4) ────────────────────────── */
.navbar{
  position:sticky;top:0;z-index:100;
  background:rgba(250,250,247,0.92);
  backdrop-filter:blur(12px);
  border-bottom:0.5px solid var(--border);
  display:grid;
  grid-template-columns:1fr auto 1fr;
  align-items:center;gap:1.5rem;
  padding:0.6rem 1.5rem;
}
.nav-left{display:flex;align-items:center;gap:1rem;justify-self:start;}
.nav-center{justify-self:center;min-width:0;}
.nav-right{display:flex;align-items:center;gap:0.6rem;justify-self:end;}
.nav-back{
  font-family:'Noto Serif SC',serif;font-size:0.8rem;
  color:var(--text3);cursor:pointer;text-decoration:none;
  display:inline-flex;align-items:center;gap:0.3rem;
  padding:0.3rem 0.6rem 0.3rem 0;
}
.nav-back:hover{color:var(--gold);}
.navbar-brand{
  font-family:'Playfair Display',serif;font-size:0.85rem;
  color:var(--gold);letter-spacing:0.1em;
  white-space:nowrap;text-decoration:none;
}
.navbar-links{
  display:flex;gap:0.5rem;list-style:none;
  overflow-x:auto;scrollbar-width:none;
}
.navbar-links::-webkit-scrollbar{display:none;}
.navbar-links li{margin:0;}
.navbar-links a{
  font-family:'Noto Serif SC',serif;font-size:0.72rem;
  color:var(--text2);text-decoration:none;
  white-space:nowrap;padding:0.2rem 0.4rem;border-radius:4px;
  transition:color 0.15s,background 0.15s;
}
.navbar-links a:hover{color:var(--gold);background:var(--gold-pale);}
.navbar-links a.active-tab{color:var(--gold);border-bottom:1.5px solid var(--gold);}
.nav-left{display:flex;align-items:center;gap:1rem;justify-self:start;}
.nav-center{justify-self:center;}
.nav-right{display:flex;align-items:center;gap:0.6rem;justify-self:end;}
.nav-back{
  font-family:'Noto Serif SC',serif;font-size:0.8rem;
  color:var(--text3);cursor:pointer;text-decoration:none;
  display:inline-flex;align-items:center;gap:0.3rem;
  padding:0.3rem 0.6rem 0.3rem 0;
}
.nav-back:hover{color:var(--gold);}
.navbar-brand{font-family:'Playfair Display',serif;font-size:0.95rem;color:var(--ink);font-weight:700;text-decoration:none;}
.navbar-links{display:flex;gap:0;list-style:none;}
.navbar-links li{margin:0;}
.navbar-links a{
  font-family:'JetBrains Mono',monospace;font-size:0.78rem;
  padding:0.4rem 0.8rem;color:var(--text2);cursor:pointer;text-decoration:none;
}
.navbar-links a.active-tab{color:var(--gold);border-bottom:1.5px solid var(--gold);}
.shelf-link{
  font-family:'Noto Serif SC',serif;font-size:0.78rem;
  color:var(--text2);cursor:pointer;padding:0.3rem 0.6rem;border-radius:4px;text-decoration:none;
}
.shelf-link:hover{color:var(--gold);background:var(--gold-pale);}
.nav-user-chip{
  display:flex;align-items:center;gap:0.4rem;
  padding:0.2rem 0.7rem 0.2rem 0.3rem;
  border:0.5px solid var(--border);border-radius:999px;
  background:var(--bg);text-decoration:none;
}
.nav-user-chip:hover{border-color:var(--gold);}
.nav-user-chip .av{
  width:20px;height:20px;border-radius:50%;background:var(--gold);color:#fff;
  display:flex;align-items:center;justify-content:center;
  font-family:'Playfair Display',serif;font-size:0.68rem;font-weight:700;
}
.nav-user-chip .uname{font-family:'Noto Serif SC',serif;font-size:0.74rem;color:var(--text2);}
.nav-user-chip .caret{font-size:0.55rem;color:var(--text3);}
.login-pill{
  font-family:'Noto Serif SC',serif;font-size:0.78rem;
  padding:0.3rem 0.85rem;border-radius:4px;
  background:var(--gold);color:var(--bg);border:none;cursor:pointer;text-decoration:none;
}
.login-pill:hover{opacity:0.85;}

@media (max-width:640px){
  .navbar{grid-template-columns:auto 1fr auto;gap:0.6rem;padding:0.5rem 0.8rem;}
  .navbar-brand{display:none;}
  .nav-back{padding:0.3rem 0.3rem 0.3rem 0;}
}
```

- [ ] **Step 2: Replace the navbar HTML block (lines 444–456)**

Replace lines 444–456 entirely (the existing `<nav class="navbar">…</nav>` block) with:

```html
<!-- ══ NAVBAR ══════════════════════════════════════════════════════════════ -->
<nav class="navbar">
  <div class="nav-left">
    <a href="/books/" class="nav-back">← 书库</a>
    <a href="/" class="navbar-brand">BelowIceberg</a>
  </div>
  <div class="nav-center">
    <ul class="navbar-links">
      <li><a href="#ch1">Ch.1</a></li>
      <li><a href="#ch2">Ch.2</a></li>
      <li><a href="#ch3">Ch.3</a></li>
      <li><a href="#ch4">Ch.4</a></li>
      <li><a href="#ch5">Ch.5</a></li>
      <li><a href="#ch6">Ch.6</a></li>
      <li><a href="#ch7">Ch.7</a></li>
      <li><a href="#ch8">Ch.8</a></li>
      <li><a href="#ch9">Ch.9</a></li>
    </ul>
  </div>
  <div class="nav-right">
    <!-- Logged-in -->
    <a href="/library/" class="shelf-link" id="reader-shelf-link" hidden>我的书房</a>
    <a href="/settings/" class="nav-user-chip" id="reader-user-chip" hidden>
      <div class="av" id="reader-user-av">B</div>
      <span class="uname" id="reader-user-name">读者</span>
      <span class="caret">▾</span>
    </a>
    <!-- Logged-out -->
    <a href="/login/?next=/gatsby" class="login-pill" id="reader-login-pill" hidden>登录</a>
  </div>
</nav>
```

The 9 chapter `<li>` entries match the original markup exactly (verified from the file's current contents).

- [ ] **Step 3: Add the login-detection script**

Find an existing `<script>` block near the end of the file. Insert this script BEFORE the existing scripts (so it runs early):

```html
<script>
(async () => {
  try {
    const r = await fetch('/api/me', { credentials: 'same-origin' });
    if (r.ok) {
      const u = await r.json();
      document.getElementById('reader-shelf-link').hidden = false;
      const chip = document.getElementById('reader-user-chip');
      chip.hidden = false;
      const name = u.display_name || u.email || '读者';
      document.getElementById('reader-user-name').textContent = name;
      const initial = (name.charCodeAt(0) < 128 ? name[0] : 'B').toUpperCase();
      document.getElementById('reader-user-av').textContent = initial;
      return;
    }
  } catch (_) {}
  document.getElementById('reader-login-pill').hidden = false;
})();
</script>
```

- [ ] **Step 4: Verify no stale "书架" references remain**

```bash
cd /Users/ben/Downloads/belowiceberg
grep -n "书架" gatsby-teaching-edition.html
```

Expected: no matches (the existing file does not contain "书架" — discovery confirmed). If any appear, change them to "我的书房".

- [ ] **Step 5: Commit**

```bash
cd /Users/ben/Downloads/belowiceberg
git add gatsby-teaching-edition.html
git commit -m "feat(reader): 3-zone navbar with login state; rename 书架 → 我的书房"
```

---

### Task 11: Ship 4 — deploy reader to production

**Files:** none changed.

- [ ] **Step 1: Sync the reader file**

The nginx config has `location = /gatsby { try_files /gatsby.html =404; }` — so on the server the file is named `gatsby.html`, not `gatsby-teaching-edition.html`:

```bash
cd /Users/ben/Downloads/belowiceberg
rsync -avz gatsby-teaching-edition.html root@66.135.16.106:/var/www/belowiceberg/gatsby.html
```

(If the live server uses a different filename, mirror whatever's there.)

- [ ] **Step 2: Smoke test — guest**

In incognito, open `http://66.135.16.106/gatsby`. Expected:
- Navbar shows: `← 书库` + `BelowIceberg` (left) · chapter tabs (center) · gold "登录" pill (right)
- No 我的书房 or user chip visible
- Click 登录 → goes to `/login/?next=/gatsby`; after login, returns to `/gatsby`

- [ ] **Step 3: Smoke test — logged in**

Log in. Navigate to `/gatsby`. Expected:
- Navbar right zone now shows `我的书房` + user chip (avatar A + display name + ▾)
- No 登录 button
- Click 我的书房 → /library/
- Click user chip → /settings/

- [ ] **Step 4: Smoke test — chapter tabs still work**

Click each chapter tab. Verify the navigation behaviour is unchanged from before this ship (this is critical — the chapter tab logic was reused, not rewritten).

- [ ] **Step 5: Mobile smoke**

Resize to 375px. The 3-zone grid collapses to single column. Brand and back link stay readable; chapter tabs wrap; right zone moves below or remains visible.

- [ ] **Step 6: Commit deploy marker**

```bash
cd /Users/ben/Downloads/belowiceberg
git commit --allow-empty -m "deploy: ship 4 — reader navbar polish live on 66.135.16.106"
```

---

# WRAP-UP

### Task 12: Push everything to GitHub

**Files:** none changed.

- [ ] **Step 1: Push all commits**

```bash
cd /Users/ben/Downloads/belowiceberg
git push origin main
```

- [ ] **Step 2: Confirm clean tree**

```bash
git status
# Expected: "nothing to commit, working tree clean"
```

---

### Task 13: Manual end-to-end walkthrough of the polished site

**Files:** none. This is a holistic browser test of all 4 shipped pages.

- [ ] **Step 1: As guest**

In incognito, run this user flow:
1. Open `/` — nav shows 登录 + 开始阅读 (✓ Ship 1)
2. Click 浏览全部书目 → lands on `/books/` (✓ Ship 1 + 2)
3. On `/books/`, type "gat" in search → only Gatsby visible (✓ Ship 2)
4. Click Gatsby card → lands on `/gatsby`; navbar right shows 登录 pill (✓ Ship 4)
5. Click 登录 → `/login/?next=/gatsby`

- [ ] **Step 2: As logged-in user**

Continue from Step 1 (or start fresh, then log in):
1. Log in as `admin@gmail.com / admin123`
2. Land back on `/gatsby` (because of `?next=`); navbar right now shows 我的书房 + user chip
3. Click 我的书房 → `/library/`; sees 3 tabs, reading grid, want-to-read tab works
4. Navigate to `/` via brand click; home nav shows 我的书房 + user chip
5. From home, click 查看完整书库 → `/books/`; nav still shows logged-in state

If any step shows a wrong state, debug before declaring the plan complete.

---

## Self-Review Checklist (run after writing)

This was reviewed by the plan author. Spec coverage confirmed:

- ✅ Home — nav login state (1a) → Task 1
- ✅ Home — hero CTA targets (1b) → Task 2
- ✅ Home — 查看完整书库 link (1c) → Task 3
- ✅ Books catalog (`/books/`) → Tasks 5–6
- ✅ Library redesign (`/library/`) → Tasks 7–9
- ✅ Reader navbar polish + rename → Tasks 10–11
- ✅ Login / Settings — no change (per spec) → no tasks needed
- ⏭️ Admin dashboard + editor → separate Plan B (out of scope here, called out at top)

Mobile responsiveness checks are embedded in each deploy task (Tasks 4, 6, 9, 11).
