# OpenCode Second Brain

Переносимый навык «второй мозг» для OpenCode: файловая база знаний в `brain/`, локальный поиск и сборка контекста без внешнего сервиса и без вызовов LLM.

Навык помогает агенту:
- не перечитывать проект целиком перед каждой задачей;
- находить уже проверенные факты и решения;
- сохранять итоги сессии и handoff;
- держать контекст в пределах заданного бюджета.

## Состав

```
.opencode/
  commands/              # /brain, /brain-search, /brain-save
  plugins/second-brain/  # автожурнал сессий
  skills/second-brain/   # SKILL.md
brain/
  brain.py               # CLI: brief, pack, search, note, new-session, lint, stats
  INDEX.md               # карта базы знаний
  STATE.md               # текущий фокус и handoff
  PROJECT.md             # карта проекта
  GLOSSARY.md            # термины
  DECISIONS.md           # решения
  inbox.md               # неклассифицированные заметки
  areas/                 # области знаний
  sessions/              # ручные журналы
  sessions/auto/         # автожурнал плагина
  playbooks/work.md      # протокол работы
  templates/             # шаблоны
AGENTS.example.md        # пример правил для корневого AGENTS.md
```

## Установка

1. Скопируйте `.opencode/`, `brain/` и `AGENTS.example.md` в корень проекта.
2. Переименуйте `AGENTS.example.md` в `AGENTS.md` или добавьте его правила в существующий `AGENTS.md`.
3. Заполните `brain/PROJECT.md`, `brain/GLOSSARY.md` и `brain/STATE.md` под свой проект.
4. Перезагрузите OpenCode: `opencode reload`.
5. Проверьте:
   ```bash
   py -3 brain/brain.py brief
   py -3 brain/brain.py lint
   ```

На Linux/macOS вместо `py -3` используйте `python3`.

## Быстрый старт

```bash
py -3 brain/brain.py pack "задача"    # контекст под задачу, ≤ 7000 символов
py -3 brain/brain.py brief            # STATE + последняя сессия + карта
py -3 brain/brain.py search "термин"  # BM25 + префиксы + синонимы
py -3 brain/brain.py note "мысль"     # быстро в inbox.md
py -3 brain/brain.py new-session      # журнал на сегодня
py -3 brain/brain.py lint             # ссылки, размеры, frontmatter
py -3 brain/brain.py stats            # размеры файлов
```

Команды OpenCode:

- `/brain <задача>` — собрать контекст.
- `/brain-search <термин>` — найти знание.
- `/brain-save` — сохранить итоги сессии.

## Автожурнал

Плагин `.opencode/plugins/second-brain` слушает завершение хода и пишет последний запрос и последний текст ассистента в `brain/sessions/auto/YYYY-MM-DD.md`.

- LLM не вызывается, токены не расходуются.
- Типовые секреты редактируются, текст обрезается.
- Это черновик: tool calls и детали не сохраняются.
- Плагин активен только там, где есть `brain/brain.py`.

Чтобы автожурнал версионировался, удалите строку `brain/sessions/auto/*.md` из `.gitignore`.

## Требования

- Python 3.10+ (используется только стандартная библиотека).
- OpenCode с поддержкой локальных плагинов; проверено на OpenCode V2.
- `brain.py` должен лежать в `<проект>/brain/brain.py`.

## Границы

В репозитории нет знаний конкретного проекта: `STATE.md`, `DECISIONS.md`, `areas/` и `sessions/` — пустые стартовые файлы. Заполняйте их фактами своего проекта и не храните секреты.
