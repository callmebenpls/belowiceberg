import asyncio
import json
import hashlib
from app.deepseek import call_once, DeepSeekError
from app import books as bk

_job_lock = asyncio.Lock()

DEFAULT_PROMPTS = {
    "vocab": "Identify vocabulary worth teaching: unusual words, literary diction, words used in unexpected ways. For each, write a 2-3 sentence explanation in the target language.",
    "grammar": "Identify grammatical structures worth teaching: tenses, passive voice, complex clauses. Explain the structure and why it matters here.",
    "syntax": "Identify syntactic patterns worth teaching: sentence length, inversion, parallelism, fragmentation. Explain the effect.",
    "lit": "Identify literary devices: metaphor, simile, irony, foreshadowing, allusion. Explain the device and its effect.",
    "cult": "Identify cultural references: historical events, geography, social customs, period details. Explain what a non-Western reader needs to know.",
    "style": "Identify stylistic choices: register, tone, rhythm, word choice. Explain what they reveal about the narrator or characters.",
}


def compute_prompt_hash(system_prompt: str) -> str:
    return hashlib.sha256(system_prompt.encode()).hexdigest()[:16]


def build_system_prompt(dimensions: list[str], prompts: dict[str, str],
                        depth: str, language: str,
                        extra: str | None) -> str:
    depth_desc = {
        "light": "brief (1-2 items max per dimension)",
        "standard": "thorough (2-4 items per dimension)",
        "deep": "exhaustive (all notable items)",
    }[depth]
    lang_desc = {
        "zh": "Chinese (中文)",
        "en": "English",
        "bilingual": "both Chinese and English (bilingual)",
    }[language]

    dim_section = "\n".join(
        f"[{d.upper()}] {prompts.get(d, DEFAULT_PROMPTS.get(d, ''))}"
        for d in dimensions
    )
    extra_section = f"\nExtra instructions: {extra}" if extra else ""
    return (
        "You are an expert literary annotator for Chinese readers learning English literature.\n"
        f"Analysis depth: {depth_desc}.\n"
        f"Explanation language: {lang_desc}.\n\n"
        "Dimensions to annotate:\n"
        f"{dim_section}"
        f"{extra_section}\n\n"
        "Return ONLY valid JSON with keys matching the dimension names. "
        "Each value is an array of objects with 'term' (string) and 'body_markdown' (string). "
        "Omit dimensions with no findings. "
        'Example: {"vocab": [{"term": "verdant", "body_markdown": "Means ..."}], "grammar": []}'
    )


async def _pre_pass_filter(paragraphs: list[dict]) -> list[int]:
    """Returns list of paragraph IDs worth annotating."""
    para_list = "\n".join(
        f'[{p["id"]}] {p["text_en"][:200]}' for p in paragraphs
    )
    system = (
        "You are filtering paragraphs in a literary text. "
        "Return a JSON array of paragraph IDs worth annotating for language learning. "
        "Skip: dialog tags ('he said', 'she asked'), single-word lines, "
        "repeated phrases, chapter headings, very short fragments under 10 words."
    )
    user = f"Paragraphs:\n{para_list}\n\nReturn JSON array of IDs to annotate."
    raw = await call_once(system, user)
    try:
        ids = json.loads(raw)
        if isinstance(ids, list):
            return [int(i) for i in ids]
    except (json.JSONDecodeError, ValueError):
        pass
    # Fallback: annotate all
    return [p["id"] for p in paragraphs]


async def run_job(job_id: int, queue: asyncio.Queue) -> None:
    """Background coroutine. Runs the full annotation job and pushes SSE events to queue."""
    async with _job_lock:
        from app.db import get_conn
        get_conn().execute(
            "UPDATE annotation_jobs SET status='running', started_at=datetime('now') WHERE id=?",
            (job_id,)
        )

        try:
            job = bk.get_job(job_id)
            scope_chapter_nums = json.loads(job["scope_json"])
            dimensions = [d.strip() for d in job["dimensions_csv"].split(",") if d.strip()]
            prompts = json.loads(job["prompts_json"])
            system_prompt = build_system_prompt(
                dimensions, prompts, job["depth"], job["language"],
                job.get("extra_instructions")
            )
            prompt_hash = job["prompt_version_hash"]

            all_chapters = bk.get_chapters_for_book(job["book_id"])
            chapters_in_scope = [ch for ch in all_chapters
                                  if ch["chapter_num"] in scope_chapter_nums]

            all_paras = bk.get_paragraphs_for_book(job["book_id"])
            paras_by_chapter: dict[int, list[dict]] = {}
            for p in all_paras:
                paras_by_chapter.setdefault(p["chapter_id"], []).append(p)

            total = sum(len(paras_by_chapter.get(ch["id"], [])) for ch in chapters_in_scope)
            done = 0
            bk.update_job(job_id, progress_total=total)
            await queue.put({"type": "progress", "done": 0, "total": total})

            for ch in chapters_in_scope:
                ch_paras = paras_by_chapter.get(ch["id"], [])
                if not ch_paras:
                    continue

                worth_ids = set(await _pre_pass_filter(ch_paras))

                for para in ch_paras:
                    done += 1
                    if para["id"] not in worth_ids:
                        bk.update_job(job_id, progress_done=done)
                        await queue.put({"type": "progress", "done": done, "total": total})
                        continue

                    raw = await call_once(system_prompt, f'Paragraph: "{para["text_en"]}"')
                    try:
                        result = json.loads(raw)
                    except json.JSONDecodeError:
                        bk.update_job(job_id, progress_done=done)
                        await queue.put({"type": "progress", "done": done, "total": total})
                        continue

                    for dim, items in result.items():
                        if not isinstance(items, list):
                            continue
                        for item in items:
                            if not isinstance(item, dict):
                                continue
                            term = item.get("term", "")
                            body = item.get("body_markdown", "")
                            if not term or not body:
                                continue
                            bk.upsert_annotation(para["id"], dim, term, body, prompt_hash)
                            await queue.put({
                                "type": "annotation",
                                "paragraph_id": para["id"],
                                "dimension": dim,
                                "term": term,
                                "body_markdown": body,
                            })

                    bk.update_job(job_id, progress_done=done)
                    await queue.put({"type": "progress", "done": done, "total": total})

            bk.update_job(job_id, status="done", progress_done=done)
            get_conn().execute(
                "UPDATE annotation_jobs SET completed_at=datetime('now') WHERE id=?", (job_id,)
            )
            await queue.put({"type": "done", "job_id": job_id})

        except DeepSeekError as e:
            bk.update_job(job_id, status="error", error_message=str(e)[:500])
            await queue.put({"type": "error", "message": str(e)[:200]})
        except Exception as e:
            bk.update_job(job_id, status="error", error_message=str(e)[:500])
            await queue.put({"type": "error", "message": str(e)[:200]})
