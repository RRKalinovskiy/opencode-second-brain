#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Второй мозг: минимальный контекст, поиск и обслуживание brain/.

Только стандартная библиотека. Запуск из корня workspace:
    py -3 brain/brain.py brief
    py -3 brain/brain.py pack "задача"
    py -3 brain/brain.py search "термин"
    py -3 brain/brain.py note "..."
    py -3 brain/brain.py lint
    py -3 brain/brain.py stats
"""

from __future__ import annotations

import argparse
import datetime as dt
import math
import re
import sys
from pathlib import Path

BRAIN = Path(__file__).resolve().parent
ROOT = BRAIN.parent

STOP = {
    "а", "без", "более", "бы", "был", "была", "были", "было", "быть", "в", "вам",
    "вас", "весь", "во", "вот", "все", "всё", "всего", "вы", "где", "да", "даже",
    "для", "до", "его", "ее", "её", "если", "есть", "еще", "ещё", "же", "за", "здесь",
    "и", "из", "или", "им", "их", "к", "как", "какая", "какие", "какой", "когда",
    "который", "которая", "которые", "которых", "кто", "ли", "мне", "может", "можно",
    "мы", "на", "над", "надо", "наиболее", "не", "него", "нее", "нее", "нет", "ни",
    "них", "но", "ну", "о", "об", "однако", "он", "она", "они", "оно", "от", "по",
    "под", "при", "с", "со", "так", "также", "там", "те", "тем", "то", "того", "тоже",
    "той", "только", "том", "ты", "у", "уже", "хотя", "чего", "чей", "чем", "что",
    "чтобы", "чье", "эта", "эти", "это", "этот", "я",
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are",
    "be", "by", "from", "as", "at", "it", "this", "that", "these", "those", "use",
    "when", "what", "how", "why", "where", "which", "who", "not", "no", "do", "does",
}

# Группы синонимов для локального «семантического» расширения запроса.
# Элементы — основы/префиксы, чтобы не зависеть от окончаний.
SYNONYM_GROUPS = (
    ("провер", "тест", "test", "кейс", "case", "check"),
    ("автотест", "pytest"),
    ("фич", "feature", "flag"),
    ("документ", "doc", "document"),
    ("генератор", "gen", "generator"),
    ("ошиб", "error", "bug", "баг"),
    ("настрой", "config", "конфиг", "setting"),
    ("сесс", "session"),
    ("поиск", "search"),
    ("плагин", "plugin"),
    ("итог", "result", "summary"),
)

TOKEN_RE = re.compile(r"[0-9A-Za-zА-Яа-яЁё_]+")
PART_RE = re.compile(r"[A-ZА-ЯЁ]+(?![a-zа-яё])|[A-ZА-ЯЁ]?[a-zа-яё0-9]+|[0-9]+")


def setup_stdout() -> None:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:
                pass


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    end = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end = i
            break
    if end is None:
        return {}, text
    meta: dict[str, str] = {}
    for line in lines[1:end]:
        if ":" in line:
            key, value = line.split(":", 1)
            meta[key.strip().lower()] = value.strip().strip('"').strip("'")
    return meta, "\n".join(lines[end + 1:]).lstrip("\n")


def meta_tags(meta: dict[str, str]) -> list[str]:
    raw = meta.get("tags", "")
    return [t.strip().lower() for t in re.split(r"[,\[\]]", raw) if t.strip()]


def tokenize(text: str) -> list[str]:
    """Слова + разбиение camelCase/snake_case; ё → е, без стоп-слов."""
    result: list[str] = []
    for raw in TOKEN_RE.findall(text):
        for piece in re.split(r"_+", raw):
            for part in PART_RE.findall(piece):
                token = part.lower().replace("ё", "е")
                if len(token) < 2 or token in STOP:
                    continue
                result.append(token)
    return result


def prefix_for(term: str) -> str:
    """Короткий префикс для русской морфологии: проверка/проверки → прове."""
    term = term.lower().replace("ё", "е")
    if term.isascii():
        return term[: min(5, max(3, len(term)))]
    if term and term[-1] in "аеёиоуыэюяй":
        return term[: min(5, max(3, len(term) - 2))]
    return term[: min(5, max(3, len(term)))]


def term_freq(tokens: list[str], term: str) -> int:
    prefix = prefix_for(term)
    return sum(1 for token in tokens if token.startswith(prefix))


def idf_for(docs: list[list[str]], terms: list[str]) -> dict[str, float]:
    count = len(docs)
    result: dict[str, float] = {}
    for term in terms:
        df = sum(1 for doc in docs if term_freq(doc, term))
        result[term] = math.log((count + 1) / (df + 1)) + 1.0
    return result


def bm25_score(tokens: list[str], terms: list[str], idf: dict[str, float], avgdl: float) -> float:
    if not tokens:
        return 0.0
    score = 0.0
    length = len(tokens)
    for term in terms:
        freq = term_freq(tokens, term)
        if not freq:
            continue
        denominator = freq + 1.5 * (0.25 + 0.75 * length / max(avgdl, 1.0))
        score += idf.get(term, 1.0) * freq * 2.5 / denominator
    return score


def query_terms(query: str) -> list[str]:
    result: list[str] = []
    for token in tokenize(query):
        if len(token) < 3 and not (token.isascii() and len(token) >= 2):
            continue
        if token not in result:
            result.append(token)

    for group in SYNONYM_GROUPS:
        matched = any(
            token.startswith(prefix_for(member)) or member.startswith(prefix_for(token))
            for token in result
            for member in group
        )
        if not matched:
            continue
        for member in group:
            if member not in result:
                result.append(member)

    # Одинаковый префикс (проверка/провер) не должен считаться дважды.
    unique: list[str] = []
    seen: set[str] = set()
    for term in result:
        prefix = prefix_for(term)
        if prefix in seen:
            continue
        seen.add(prefix)
        unique.append(term)
    return unique


def term_variants(term: str) -> set[str]:
    """Простые усечения для русской морфологии: проверку -> проверк/провер."""
    out = {term}
    for cut in (1, 2, 3):
        if len(term) - cut >= 4:
            out.add(term[: len(term) - cut])
    return out


def count_term(text: str, term: str) -> int:
    return max(text.count(variant) for variant in term_variants(term))


def has_term(text: str, term: str) -> bool:
    return any(variant in text for variant in term_variants(term))


def score_file(path: Path, meta: dict[str, str], body: str, terms: list[str]) -> int:
    path_l = rel(path).lower()
    title_l = (meta.get("title", "") + " " + meta.get("summary", "")).lower()
    tags_l = " ".join(meta_tags(meta))
    heads_l = "\n".join(line for line in body.splitlines() if line.startswith("#")).lower()
    body_l = body.lower()
    score = 0
    for term in terms:
        score += 6 * count_term(path_l, term)
        score += 5 * count_term(title_l, term)
        score += 4 * count_term(tags_l, term)
        score += 4 * count_term(heads_l, term)
        score += min(6, count_term(body_l, term))
    return score


def markdown_files() -> list[Path]:
    result = []
    for path in sorted(BRAIN.rglob("*.md")):
        parts = path.relative_to(BRAIN).parts
        if any(part.startswith(".") for part in parts):
            continue
        result.append(path)
    return result


def split_sections(body: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    title = ""
    buf: list[str] = []
    for line in body.splitlines():
        if re.match(r"^#{1,4}\s+", line):
            if title or buf:
                result.append((title or "(начало)", "\n".join(buf).strip()))
            title = line.strip()
            buf = []
        else:
            buf.append(line)
    if title or buf:
        result.append((title or "(начало)", "\n".join(buf).strip()))
    return result


def excerpt(text: str, terms: list[str], limit: int) -> str:
    text = text.strip()
    if not text:
        return ""
    if len(text) <= limit:
        return text
    lines = text.splitlines()
    hits = [i for i, line in enumerate(lines) if any(has_term(line.lower(), t) for t in terms)]
    if not hits:
        max_lines = max(6, limit // 80)
        return "\n".join(lines[:max_lines]) + "\n…"
    keep: set[int] = set()
    for hit in hits[:2]:
        for j in range(max(0, hit - 2), min(len(lines), hit + 3)):
            keep.add(j)
    out: list[str] = []
    prev = -2
    for i in sorted(keep):
        if i > prev + 1:
            out.append("…")
        out.append(lines[i])
        prev = i
    joined = "\n".join(out)
    return joined[:limit] + ("\n…" if len(joined) > limit else "")


def cmd_brief(args: argparse.Namespace) -> int:
    chunks: list[str] = ["# Brief"]
    state = BRAIN / "STATE.md"
    if state.exists():
        _, body = parse_front_matter(read_text(state))
        chunks.append("## STATE.md\n" + body[: args.budget // 2])
    sessions_dir = BRAIN / "sessions"
    if sessions_dir.exists():
        sessions = sorted(sessions_dir.glob("*.md"))
        if sessions:
            _, body = parse_front_matter(read_text(sessions[-1]))
            tail = "\n".join(body.splitlines()[-40:])
            chunks.append(f"## Последняя сессия: {rel(sessions[-1])}\n{tail}")
    index = BRAIN / "INDEX.md"
    if index.exists():
        _, body = parse_front_matter(read_text(index))
        heads = [line for line in body.splitlines() if line.startswith("## ") or line.startswith("### ")]
        chunks.append("## Карта\n" + "\n".join(heads[:30]))
    text = "\n\n".join(chunks)
    print(text[: args.budget])
    return 0


def cmd_pack(args: argparse.Namespace) -> int:
    terms = query_terms(args.task)
    if not terms:
        print("Не удалось выделить термины. Запусти `py -3 brain/brain.py brief`.")
        return 2

    glossary_terms = {"термин", "термины", "глоссарий", "значение", "означает", "расшифровка"}
    files: list[tuple[Path, dict[str, str], str]] = []
    sections_by_file: dict[Path, list[tuple[str, str, list[str]]]] = {}

    for path in markdown_files():
        parts = path.relative_to(BRAIN).parts
        if parts and parts[0] == "templates":
            continue
        if path.name == "inbox.md":
            continue
        meta, body = parse_front_matter(read_text(path))
        files.append((path, meta, body))
        sections_by_file[path] = [
            (title, text, tokenize(f"{title}\n{text}"))
            for title, text in split_sections(body)
        ]

    all_section_tokens = [
        tokens
        for sections in sections_by_file.values()
        for _, _, tokens in sections
    ]
    idf = idf_for(all_section_tokens, terms)
    avgdl = sum(len(tokens) for tokens in all_section_tokens) / max(1, len(all_section_tokens))

    ranked: list[tuple[float, Path, dict[str, str], str, list[tuple[float, str, str]]]] = []
    for path, meta, body in files:
        scored_sections: list[tuple[float, str, str]] = []
        for title, text, tokens in sections_by_file[path]:
            title_clean = title.lstrip("#").strip().lower()
            if title_clean in {"ссылки", "ссылки:"} and not any(
                t in {"ссылка", "ссылки", "link", "links"} for t in terms
            ):
                continue
            section_score = bm25_score(tokens, terms, idf, avgdl)
            heading_tokens = tokenize(title)
            section_score += 0.5 * sum(
                idf.get(term, 0.0) for term in terms if term_freq(heading_tokens, term)
            )
            if section_score:
                scored_sections.append((section_score, title, text))
        scored_sections.sort(key=lambda item: (-item[0], item[1]))

        file_score = sum(item[0] for item in scored_sections[:3])
        for label, weight in (
            (rel(path), 6.0),
            (f"{meta.get('title', '')} {meta.get('summary', '')}", 5.0),
            (" ".join(meta_tags(meta)), 4.0),
        ):
            label_tokens = tokenize(label)
            for term in terms:
                freq = term_freq(label_tokens, term)
                if freq:
                    file_score += weight * idf.get(term, 1.0) * min(2, freq)

        # Старый substring-поиск спасает короткие/точные совпадения.
        file_score += 0.05 * min(score_file(path, meta, body, terms), 100)

        parts = path.relative_to(BRAIN).parts
        if path.name == "GLOSSARY.md" and not any(t in glossary_terms for t in terms):
            file_score *= 0.25
        if parts and parts[0] == "sessions":
            file_score *= 0.5
        if path.name in {"INDEX.md", "PROJECT.md"}:
            file_score *= 0.5
        if file_score > 0:
            ranked.append((file_score, path, meta, body, scored_sections))

    ranked.sort(key=lambda item: (-item[0], rel(item[1])))
    if not ranked:
        print("Ничего не найдено. Запусти `py -3 brain/brain.py brief` и `search`.")
        return 0

    budget = args.budget
    out = [f"# Контекст: {args.task}", f"Бюджет: {budget} символов (~{budget // 3} токенов)", ""]
    used = sum(len(line) + 1 for line in out)
    shown = 0

    for score, path, meta, body, scored_sections in ranked[: args.files]:
        if used >= budget:
            break
        shown += 1
        summary = meta.get("summary", "").strip()
        chunk = [f"## {shown}. {rel(path)}  [score {score:.1f}]"]
        if summary:
            chunk.append(f"> {summary}")

        remaining = budget - used
        per_section = max(400, min(2500, remaining // 2))
        if scored_sections:
            for _, title, text in scored_sections[:2]:
                piece = excerpt(text, terms, per_section)
                if piece:
                    chunk.append(title)
                    chunk.append(piece)
                    chunk.append("")
        else:
            chunk.append(excerpt(body, terms, per_section))
            chunk.append("")

        text = "\n".join(chunk)
        if used + len(text) > budget:
            text = text[: max(0, budget - used)] + "\n…"
        out.append(text)
        used += len(text) + 1

    out.append(
        f"---\nПоказано файлов: {shown}. Если факта нет — `search`, затем точечный `read` с offset/limit."
    )
    print("\n".join(out))
    return 0


def heading_before(lines: list[str], index: int) -> str:
    for i in range(index, -1, -1):
        if re.match(r"^#{1,4}\s+", lines[i]):
            return lines[i].strip()
    return ""


def cmd_search(args: argparse.Namespace) -> int:
    terms = query_terms(args.query)
    if not terms:
        print("Пустой запрос.")
        return 2

    query_norm = " ".join(tokenize(args.query))
    files: list[tuple[Path, dict[str, str], str, list[str]]] = []
    for path in markdown_files():
        meta, body = parse_front_matter(read_text(path))
        tokens = tokenize(
            " ".join(
                [
                    rel(path),
                    meta.get("title", ""),
                    meta.get("summary", ""),
                    " ".join(meta_tags(meta)),
                    body,
                ]
            )
        )
        files.append((path, meta, body, tokens))

    idf = idf_for([item[3] for item in files], terms)
    avgdl = sum(len(item[3]) for item in files) / max(1, len(files))

    hits: list[tuple[float, float, Path, int, str, str]] = []
    for path, meta, body, tokens in files:
        file_score = max(
            bm25_score(tokens, terms, idf, avgdl),
            0.2 * score_file(path, meta, body, terms),
        )
        name_l = path.name.lower()
        lines = body.splitlines()
        for i, line in enumerate(lines):
            line_tokens = tokenize(line)
            line_score = 0.0
            for term in terms:
                freq = term_freq(line_tokens, term)
                if freq:
                    line_score += idf.get(term, 1.0) * min(3, freq)

            if query_norm and query_norm in " ".join(line_tokens):
                line_score += 2.0

            heading = heading_before(lines, i)
            if heading:
                heading_tokens = tokenize(heading)
                line_score += 0.3 * sum(
                    idf.get(term, 0.0) for term in terms if term_freq(heading_tokens, term)
                )

            # Fallback: точные подстроки для коротких терминов и кода.
            legacy = sum(min(3, count_term(line.lower(), term)) for term in terms)
            line_score = max(line_score, float(legacy))
            if not line_score:
                continue
            if any(has_term(name_l, term) for term in terms):
                line_score += 0.5
            hits.append((line_score, file_score, path, i + 1, line.strip(), heading))

    hits.sort(key=lambda item: (-item[0], -item[1], rel(item[2]), item[3]))

    seen: set[tuple[str, str]] = set()
    out = [f"# Поиск: {args.query}", ""]
    shown = 0
    for line_score, file_score, path, line_no, line, heading in hits:
        key = (rel(path), heading)
        if key in seen:
            continue
        seen.add(key)
        shown += 1
        out.append(f"## {shown}. {rel(path)}:{line_no}  [score {line_score:.1f}]")
        if heading:
            out.append(heading)
        out.append(line[:500])
        out.append("")
        if shown >= args.limit:
            break
    if not shown:
        out.append("Ничего не найдено. Проверь формулировку или добавь знание в `brain/inbox.md`.")
    print("\n".join(out))
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    inbox = BRAIN / "inbox.md"
    stamp = dt.datetime.now().strftime("%Y-%m-%d %H:%M")
    if not inbox.exists():
        inbox.write_text(
            "---\ntitle: Inbox\nsummary: Неклассифицированные заметки.\ntags: [inbox]\n"
            f"updated: {dt.date.today().isoformat()}\n---\n\n# Inbox\n\n",
            encoding="utf-8",
        )
    with inbox.open("a", encoding="utf-8") as fh:
        fh.write(f"- {stamp} — {args.text.strip()}\n")
    print(f"Записано в {rel(inbox)}")
    return 0


def cmd_new_session(args: argparse.Namespace) -> int:
    today = dt.date.today().isoformat()
    sessions = BRAIN / "sessions"
    sessions.mkdir(parents=True, exist_ok=True)
    path = sessions / f"{today}.md"
    if path.exists():
        print(f"Уже существует: {rel(path)}")
        return 0
    path.write_text(
        f"---\ntitle: Сессия {today}\nsummary: Журнал работ за {today}.\n"
        f"tags: [session]\nupdated: {today}\n---\n\n# {today}\n\n"
        "## Задача\n\n## Сделано\n\n## Найдено\n\n## Решения\n\n## Следующие шаги\n",
        encoding="utf-8",
    )
    print(f"Создано: {rel(path)}")
    return 0


def cmd_lint(args: argparse.Namespace) -> int:
    errors: list[str] = []
    warnings: list[str] = []
    today = dt.date.today()

    index_path = BRAIN / "INDEX.md"
    index_text = read_text(index_path) if index_path.exists() else ""

    for path in markdown_files():
        text = read_text(path)
        meta, body = parse_front_matter(text)
        size = len(text.encode("utf-8"))
        if size > 50_000:
            warnings.append(f"{rel(path)}: {size} байт — разбей файл или вынеси детали в отдельный.")
        if not meta:
            warnings.append(f"{rel(path)}: нет frontmatter (title/summary/tags/updated).")
        for target in re.findall(r"\[[^\]]*\]\(([^)]+)\)", body):
            target = target.strip()
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            clean = target.split("#", 1)[0].strip()
            if not clean:
                continue
            resolved = (path.parent / clean).resolve()
            if not resolved.exists():
                errors.append(f"{rel(path)}: битая ссылка -> {target}")
        for line in body.splitlines():
            if re.search(r"(?i)(password|passwd|пароль|token|api[_-]?key)\s*[:=]\s*\S{4,}", line):
                if not re.search(r"(?i)(не\s+хранить|не\s+писать|placeholder|example|xxx)", line):
                    warnings.append(f"{rel(path)}: похоже на секрет в строке: {line[:80]}")

    areas = sorted((BRAIN / "areas").glob("*.md")) if (BRAIN / "areas").exists() else []
    for area in areas:
        if rel(area) not in index_text and area.name not in index_text:
            warnings.append(f"{rel(area)}: не упомянут в INDEX.md")

    state = BRAIN / "STATE.md"
    if state.exists():
        age = (today - dt.date.fromtimestamp(state.stat().st_mtime)).days
        if age > 45:
            warnings.append(f"STATE.md не обновлялся {age} дней — проверь актуальность.")

    print("# Lint")
    if errors:
        print("\n## Ошибки")
        for item in errors:
            print(f"- {item}")
    if warnings:
        print("\n## Предупреждения")
        for item in warnings:
            print(f"- {item}")
    if not errors and not warnings:
        print("OK: битых ссылок и проблем не найдено.")
    print(f"\nФайлов Markdown: {len(markdown_files())}")
    return 1 if errors else 0


def cmd_stats(args: argparse.Namespace) -> int:
    rows: list[tuple[str, int, int]] = []
    for path in markdown_files():
        text = read_text(path)
        size = len(text.encode("utf-8"))
        rows.append((rel(path), size, len(text) // 3))
    rows.sort(key=lambda item: -item[1])
    print("# Размер второго мозга")
    print(f"{'Файл':<52} {'Байт':>7} {'~токенов':>9}")
    print("-" * 72)
    for name, size, tokens in rows:
        print(f"{name:<52} {size:>7} {tokens:>9}")
    print("-" * 72)
    print(f"{'ИТОГО':<52} {sum(r[1] for r in rows):>7} {sum(r[2] for r in rows):>9}")
    print("\nОценка токенов: len(text)//3; для русского реальное значение может быть выше.")
    agents = ROOT / "AGENTS.md"
    if agents.exists():
        text = read_text(agents)
        print(f"\nAGENTS.md (загружается всегда): {len(text.encode('utf-8'))} байт, ~{len(text) // 3} токенов")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="brain.py",
        description="Второй мозг workspace: минимальный контекст, поиск, заметки, проверка.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    brief = sub.add_parser("brief", help="Короткая сводка: STATE + последняя сессия + карта.")
    brief.add_argument("--budget", type=int, default=5000, help="Лимит вывода в символах.")
    brief.set_defaults(func=cmd_brief)

    pack = sub.add_parser("pack", help="Собрать контекст под задачу в пределах бюджета.")
    pack.add_argument("task", help="Формулировка задачи.")
    pack.add_argument("--budget", type=int, default=7000, help="Лимит вывода в символах.")
    pack.add_argument("--files", type=int, default=4, help="Максимум файлов.")
    pack.set_defaults(func=cmd_pack)

    search = sub.add_parser("search", help="Найти термин в brain/.")
    search.add_argument("query", help="Что искать.")
    search.add_argument("--limit", type=int, default=10, help="Максимум результатов.")
    search.set_defaults(func=cmd_search)

    note = sub.add_parser("note", help="Быстро записать заметку в inbox.md.")
    note.add_argument("text", help="Текст заметки.")
    note.set_defaults(func=cmd_note)

    new_session = sub.add_parser("new-session", help="Создать журнал на сегодня.")
    new_session.set_defaults(func=cmd_new_session)

    lint = sub.add_parser("lint", help="Проверить ссылки, размеры и frontmatter.")
    lint.set_defaults(func=cmd_lint)

    stats = sub.add_parser("stats", help="Показать размеры файлов brain/.")
    stats.set_defaults(func=cmd_stats)

    return parser


def main() -> int:
    setup_stdout()
    parser = build_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
