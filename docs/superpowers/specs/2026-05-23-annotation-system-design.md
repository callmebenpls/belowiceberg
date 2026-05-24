# Annotation System — Design Spec

**Date:** 2026-05-23
**Status:** Approved for planning
**Project:** belowiceberg (Phase 1 of admin authoring tools)

## Problem

The teaching editions on belowiceberg (e.g. `/gatsby`) are static HTML with pre-written paragraph-by-paragraph analysis. While reading, the admin (Ben) still hits words, phrases, or sentences whose analysis is missing or insufficient. Today the only fix is to hand-edit the HTML and redeploy — too slow to do in the flow of reading.

## Goal

Let the logged-in admin select any text inside a `.para-section`, ask DeepSeek to analyze it under one of three categories (词汇 / 语法 / 句子结构), and save the response into the matching subsection of that paragraph's card. The saved note becomes part of the public page for all future readers.

## Non-goals

- Public readers calling the LLM (admin-only in v1)
- Multi-provider LLM choice (DeepSeek only in v1)
- Edit-before-save flow (save the raw LLM response; manual JSON editing for fixes)
- Per-note delete/edit UI in v1 (edit the sidecar JSON file by hand)
- Undo

## Architecture

All on the existing Vultr box (`66.135.16.106`, Debian 12, nginx already serving the site).

Four components:

1. **Annotation script** — a `~6KB` `annotate.js` added via `<script defer>` to each teaching-edition page. Two responsibilities:
   - On load: if an admin session cookie is present, fetch `GET /api/notes/<book-slug>` and inject saved notes into the matching subsections.
   - Listen for `selectionchange` on `.para-section` blocks; render the selection bar and popover.
2. **FastAPI app** — `uvicorn` under systemd, bound to `127.0.0.1:8001`. Four endpoints (see API section).
3. **nginx** — reverse-proxies `/api/*` and `/admin/*` to `127.0.0.1:8001`. Everything else stays static.
4. **JSON sidecar files** — source of truth for saved notes at `/var/www/belowiceberg-data/notes/<book-slug>.json`.

No SQLite, no worker, no job queue. The book HTML stays a static file the admin scp's; saved notes are an overlay loaded at runtime.

### Why JSON sidecar (not in-place HTML edit, not DB)

- **In-place HTML edit** is fragile: regenerating the page wipes notes; concurrent saves can corrupt; diffs are noisy.
- **SQLite + server render** means the page is no longer static, requiring the app to serve every page request. Premature complexity for one admin.
- **JSON sidecar** keeps the published HTML pristine, makes notes versionable/backup-able as a single file, and the read path is one tiny fetch.

## Selection anchor model

Each saved note is anchored by:

```json
{
  "paraId": "para3",
  "category": "vocab" | "grammar" | "structure",
  "selectedText": "advantages",
  "responseMarkdown": "**advantages** /ədˈvæntɪdʒɪz/ — 此处为复数...",
  "createdAt": "2026-05-23T14:22:09Z"
}
```

`paraId` is the existing `id` attribute on each `<section class="para-section">`. `selectedText` is the literal selected string. We do **not** store DOM ranges or character offsets — they would break the moment the original HTML changes by one character. On render, the script appends the note into the para's matching `.card-hdr.<category> + .card-body` block; the `selectedText` is shown as the note header so the reader can see what triggered the annotation.

## API

All endpoints prefixed `/api` (proxied to FastAPI). Auth via signed session cookie set by `/admin/login`.

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/admin/login` | none | Body: `{password}`. Sets `belowiceberg_session` cookie (HttpOnly, Secure, SameSite=Lax). |
| POST | `/admin/logout` | session | Clears cookie. |
| GET  | `/api/notes/<book-slug>` | session | Returns the sidecar JSON. 404 if no notes yet. |
| POST | `/api/notes/<book-slug>` | session | Body: a note object (see above). Appends to sidecar atomically (write to tmp, fsync, rename). |
| POST | `/api/query` | session | Body: `{category, selectedText, paraContext}`. Streams DeepSeek response back as `text/event-stream`. Does NOT save; client decides. |

`paraContext` = the full text of the surrounding `.para-section` original, so DeepSeek has enough context to analyze "advantages" inside the actual sentence.

## DeepSeek prompts

Three system prompts, one per category. Each instructs DeepSeek to:
- Respond in Chinese (Simplified), matching the existing card tone
- Format with the same conventions as existing notes (term bolded, IPA in slashes for vocab, etc.)
- Keep response under ~150 words

Prompts live in `prompts/{vocab,grammar,structure}.txt` and are loaded at app startup. Easy to tune without redeploying code.

## Frontend UX

Per the approved mockup:

1. Admin selects text → floating bar appears above selection (`position: absolute`, dark background, three pill buttons).
2. Click category → bar morphs into popover (380px wide). Header shows category + provider + paraId. Selected text shown italicized. Body streams response with a blinking caret. Footer has 关闭 and 保存到卡片 (disabled until stream completes).
3. Save → POST to `/api/notes/<book>`. On success: client appends the new note into the matching subsection's `.card-body`, marked with a small black `AI` badge, with a fade-in. Popover closes.
4. Esc / outside-click dismisses without saving.

Selection bar is suppressed if: selection is empty, selection crosses paragraph boundaries, or admin session cookie absent.

## Auth

Single password, bcrypt-hashed, stored in `/etc/belowiceberg/admin.env` (mode 600, root-readable). `POST /admin/login` checks password, issues a signed session cookie (itsdangerous, 30-day expiry). Session secret in the same env file. No user table, no password reset flow — if Ben loses the password he edits the env file and restarts the service.

A `/admin` page provides login and a one-line status ("logged in as admin · log out").

## Failure modes

- **DeepSeek timeout / 5xx**: popover shows error message with retry button. Nothing saved.
- **Concurrent save (rare, single admin)**: file write is atomic (tmp + rename). Last write wins on the same paragraph.
- **Sidecar JSON corruption**: app refuses to serve corrupted JSON (500); admin fixes the file by hand. Sidecar is kept in git on the server.
- **Selected text not found in para on render**: log warning, render the note at the top of the matching subsection with a "⚠ anchor stale" marker. Admin can re-anchor by re-saving.

## Deployment changes

- Install Python 3.11 + venv on Vultr; pip install fastapi, uvicorn, httpx, itsdangerous, bcrypt.
- New systemd unit `belowiceberg-api.service` running uvicorn on 127.0.0.1:8001.
- Update nginx config: add `location /api/ { proxy_pass http://127.0.0.1:8001; }` and same for `/admin/`.
- Add `<script defer src="/static/annotate.js"></script>` to each teaching-edition HTML file. Script auto-detects book slug from URL.
- `/etc/belowiceberg/admin.env` with `ADMIN_PASSWORD_HASH`, `SESSION_SECRET`, `DEEPSEEK_API_KEY`.

## Open questions for the implementation plan

- Exact DeepSeek model + endpoint (chat completions vs. their newer API)
- Streaming format mapping from DeepSeek SSE to our SSE
- Whether `annotate.js` is bundled or hand-written (lean toward hand-written, no build step)

---

Spec written and committed. Please review and let me know if you want any changes before I have the writing-plans skill turn this into a step-by-step implementation plan.
