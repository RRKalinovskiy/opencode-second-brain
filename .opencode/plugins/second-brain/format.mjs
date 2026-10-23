const PRIVATE_KEY = /-----BEGIN [^-]+ PRIVATE KEY-----[\s\S]*?-----END [^-]+ PRIVATE KEY-----/g
const BEARER = /\b(Bearer)\s+[A-Za-z0-9._~+/=-]{8,}/gi
const URL_CREDENTIALS = /(https?:\/\/)([^/\s:@]+):([^/\s@]+)@/gi
const KNOWN_TOKEN = /\b(sk-[A-Za-z0-9_-]{10,}|ghp_[A-Za-z0-9]{20,}|xox[baprs]-[A-Za-z0-9-]{10,}|AKIA[0-9A-Z]{16})\b/g
const KEY_VALUE = /((?:password|passwd|pwd|пароль|token|api[_-]?key|secret|authorization|credential|session[_-]?key)\s*[:=]\s*)(["']?)([^\s"'`,;)\]]{1,})\2/gi

/** Remove common secret shapes before anything reaches the brain. */
export function redact(value) {
  let text = String(value ?? "")
  text = text.replace(PRIVATE_KEY, "[redacted private key]")
  text = text.replace(BEARER, "$1 [redacted]")
  text = text.replace(URL_CREDENTIALS, "$1[redacted]:[redacted]@")
  text = text.replace(KNOWN_TOKEN, "[redacted]")
  text = text.replace(KEY_VALUE, "$1[redacted]")
  return text
}

/** One compact line suitable for a Markdown bullet. */
export function compact(value, limit) {
  const text = redact(value).replace(/\s+/g, " ").trim()
  if (!text) return "—"
  if (text.length <= limit) return text
  return text.slice(0, Math.max(0, limit - 1)).trimEnd() + "…"
}

export function localStamp(date = new Date()) {
  const pad = (number) => String(number).padStart(2, "0")
  return {
    day: `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`,
    time: `${pad(date.getHours())}:${pad(date.getMinutes())}`,
  }
}

export function autoHeader(day) {
  return `---
title: Автожурнал сессий ${day}
summary: Автоматические записи OpenCode; текст сокращён и очищен от типовых секретов.
tags: [session, auto]
updated: ${day}
---

# Автожурнал ${day}

> Создаётся плагином \`.opencode/plugins/second-brain\` при завершении хода. Это черновик: проверяй и переноси выводы в \`sessions/${day}.md\`.

`
}

export function formatEntry({ time, sessionID, prompt, reply }) {
  const sid = String(sessionID || "unknown").replace(/`/g, "'")
  const request = compact(prompt, 700)
  const result = String(reply ?? "").trim() ? compact(reply, 1400) : "_(нет текстового ответа)_"
  return `## ${time} · \`${sid}\`\n\n- **Запрос:** ${request}\n- **Итог:** ${result}\n\n`
}
