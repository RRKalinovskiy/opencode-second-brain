import { Plugin } from "@opencode/plugin"
import { access, appendFile, mkdir, writeFile } from "node:fs/promises"
import { join } from "node:path"
import { autoHeader, formatEntry, localStamp } from "./format.mjs"

function normalize(path: string | undefined) {
  return String(path ?? "").replace(/\\/g, "/").replace(/\/+$/, "").toLowerCase()
}

export default Plugin.define({
  id: "second-brain",
  async setup(ctx) {
    const root = ctx.location?.directory
    if (!root) return

    // Only projects that actually have the second brain.
    try {
      await access(join(root, "brain", "brain.py"))
    } catch {
      return
    }

    const controller = new AbortController()
    const prompts = new Map<string, string>()
    const replies = new Map<string, { messageID: string; text: string }>()
    let queue: Promise<void> = Promise.resolve()

    const promptHook = await ctx.session.hook("prompt", (event) => {
      const text = event?.prompt?.text
      if (typeof text === "string" && text.trim()) {
        prompts.set(String(event.sessionID), text)
      }
    })

    const writeEntry = (sessionID: string, prompt: string, reply: string) => {
      queue = queue
        .catch(() => undefined)
        .then(async () => {
          const { day, time } = localStamp()
          const dir = join(root, "brain", "sessions", "auto")
          const file = join(dir, `${day}.md`)
          await mkdir(dir, { recursive: true })
          try {
            await access(file)
          } catch {
            await writeFile(file, autoHeader(day), "utf8")
          }
          await appendFile(file, formatEntry({ time, sessionID, prompt, reply }), "utf8")
        })
        .catch((error) => {
          console.error("[second-brain] failed to write session note:", error)
        })
      return queue
    }

    const flush = async (sessionID: string) => {
      const prompt = prompts.get(sessionID)
      if (!prompt) return
      const reply = replies.get(sessionID)?.text ?? ""
      prompts.delete(sessionID)
      replies.delete(sessionID)
      await writeEntry(sessionID, prompt, reply)
    }

    void (async () => {
      try {
        for await (const event of ctx.event.subscribe({ signal: controller.signal })) {
          const location = (event as any).location?.directory
          if (location && normalize(location) !== normalize(root)) continue

          if (event.type === "session.text.ended") {
            const data = (event as any).data
            if (!data?.sessionID || typeof data.text !== "string") continue
            const sessionID = String(data.sessionID)
            const messageID = String(data.assistantMessageID ?? "")
            const previous = replies.get(sessionID)
            if (previous && previous.messageID === messageID) previous.text += `\n${data.text}`
            else replies.set(sessionID, { messageID, text: data.text })
            continue
          }

          if (event.type === "session.execution.succeeded") {
            const data = (event as any).data
            if (data?.sessionID) await flush(String(data.sessionID))
            continue
          }

          if (event.type === "session.idle") {
            const data = (event as any).data
            if (data?.sessionID) await flush(String(data.sessionID))
          }
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          console.error("[second-brain] event stream failed:", error)
        }
      }
    })()

    return async () => {
      controller.abort()
      await promptHook.dispose()
      await queue.catch(() => undefined)
    }
  },
})
