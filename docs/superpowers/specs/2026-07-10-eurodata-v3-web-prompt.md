# eurodata v3 — Web platform prompt (for Fable 5)

> Prompt spec, 2026-07-10. Paste the text block below into Fable 5 to kick off
> the v3 session. Supersedes the v2 "senior open-data researcher" prompt's
> frontend ambitions; the **AI Chat visual direction** section is the canonical
> replacement for the earlier "Frontend AI chat behavior" section.

````text
You are taking over the project as a senior full-stack engineer (Python/FastAPI
+ React/Next.js) and AI-application architect.

Project name: eurodata
Repository: /Users/toto/eurodata
Context files, read first: README.md, HANDOFF.md, docs/data-dictionary.md,
docs/events.md

Current state (v2, already landed — do not rebuild):
- Python package `import eurodata as ed` (src/eurodata/api.py): countries,
  blocs, domains, indicators, search_indicators, series, compare, latest,
  coverage, events, event_study, correlate, lagged_correlation, query (raw
  SQL), open(). Unknown names raise EuroDataLookupError with did-you-mean.
- DuckDB at data/eurodata.duckdb: 40k+ rows, 26 indicators × ~50 countries ×
  2000–2025, curated event table (43 events), structural graph, provenance
  columns (definition / is_proxy / proxy_note), per-record source.
- Streamlit dashboard (app/streamlit_app.py) — keep it working; it is the
  exploratory UI, not what you are building.
- Tests: `source .venv/bin/activate; PYTHONPATH=src python -m pytest -q`
  (42 passing — keep them green).

Your v3 mission: give eurodata a real web platform — a FastAPI backend that
exposes the Python API plus an AI analyst, and a modern web frontend with an
AI chat as its flagship feature.

## Architecture

- `web/backend/` — FastAPI (Python, reuse the repo .venv).
  - Opens the DuckDB **read-only** (`ed.open(read_only=True)` / the api
    defaults). Never open read-write from a web process: DuckDB allows one
    writer OR many readers, and a write handle blocks ingestion and Streamlit.
  - REST endpoints wrapping the existing API 1:1 (no new analytics logic in
    the web layer): /api/countries, /api/indicators, /api/series,
    /api/compare, /api/latest, /api/coverage, /api/events, /api/event-study,
    /api/correlate.
  - `/api/chat` — the AI analyst endpoint (below).
  - CORS for the frontend dev origin; uvicorn dev server on :8000.
- `web/frontend/` — Next.js (App Router, TypeScript) + Tailwind + shadcn-style
  components. Charts with Recharts. Talks only to the FastAPI backend.

## AI analyst (/api/chat)

- Use the Anthropic API (model from env `ANTHROPIC_MODEL`, default
  `claude-sonnet-5`; key from `ANTHROPIC_API_KEY`). Add both to `.env.example`
  as placeholders — never commit a real key.
- Tool-use loop over a whitelisted, read-only toolset that maps directly onto
  the `ed` API: search_indicators, get_series, compare_countries, latest,
  coverage, list_events, event_study, correlate. If you expose raw SQL as a
  tool, hard-restrict it to a single SELECT against the public views.
- System prompt: the assistant is a European open-data analyst; it must be
  provenance-first — always name the source, surface `is_proxy`/`proxy_note`
  as warnings, and say "correlation ≠ causation" when using correlate.
- Response contract (what the frontend renders): the endpoint returns a list
  of typed blocks, not just text:
  { role: "assistant", blocks: [
      { type: "text", text },
      { type: "chart", spec: { kind: "line"|"bar", series: [...], unit } },
      { type: "table", columns, rows },
      { type: "sources", items: [{ label, url?, is_proxy?, proxy_note? }] },
      { type: "warning", text },
      { type: "follow_ups", items: [string] }
  ] }
- No API key configured → /api/chat returns a clean 503 with a human message;
  the frontend shows its failure state, everything else still works.
- Test the tool layer with pytest (tools against the real DB, chat handler
  with the Anthropic client faked).

## Frontend scope

Pages (navbar): Home (KPIs + coverage), Explore (indicator/country picker →
chart + table, provenance shown), Events (timeline + event-study view), and
**AI Chat** — the flagship, specified exactly below.

AI Chat visual direction:

The AI chat input should look like the attached React component style: a clean
centered rounded input bar with an auto-resizing textarea, subtle translucent
background, microphone icon, and a send/up-arrow button that appears only when
the user has typed something.

Use this as the target chat input behavior:
- Centered input area, max width around `max-w-xl`.
- Rounded pill / rounded-3xl textarea.
- Auto-resizing textarea with min height around 52px and max height around 200px.
- Press Enter to submit.
- Shift+Enter inserts a new line.
- Textarea clears after submit.
- Microphone icon is visible on the right.
- Send icon appears with opacity/scale transition only when input has content.
- Use `lucide-react` icons:
  - `Mic`
  - `CornerRightUp`
- Use shadcn-style components if the frontend uses Tailwind/shadcn.
- Put reusable UI components under:
  - `web/frontend/src/components/ui/`
- Put reusable hooks under:
  - `web/frontend/src/components/hooks/`
- Add or reuse:
  - `Textarea`
  - `AIInput`
  - `useAutoResizeTextarea`
  - `cn` utility

Important implementation note:
Do not use Tailwind dynamic classes like:

```tsx
`min-h-[${minHeight}px]`
`max-h-[${maxHeight}px]`
```

Tailwind will not reliably generate those classes. Use inline styles or CSS
variables instead:

```tsx
style={{
  minHeight,
  maxHeight,
}}
```

The chat page should use this AIInput component as the main prompt box.

Chat layout:
- Full page route: `/chat`
- Navbar item: `AI Chat`
- Conversation centered with a comfortable max width.
- Empty state shows example prompts as clickable chips.
- Messages appear above the input.
- User messages align right.
- Assistant messages align left.
- Assistant messages can contain:
  - text answer
  - chart
  - table
  - source/provenance chips
  - warnings
  - follow-up buttons
- Input should remain near the bottom of the page, similar to modern AI chat tools.
- On long conversations, messages scroll while the input stays accessible.
- Add loading state while the backend processes the request.
- Add failure state if the AI provider is not configured or if a tool call fails.

The AIInput component should roughly follow this shape:

```tsx
"use client";

import { CornerRightUp, Mic } from "lucide-react";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Textarea } from "@/components/ui/textarea";
import { useAutoResizeTextarea } from "@/components/hooks/use-auto-resize-textarea";

interface AIInputProps {
  id?: string;
  placeholder?: string;
  minHeight?: number;
  maxHeight?: number;
  disabled?: boolean;
  onSubmit?: (value: string) => void;
  className?: string;
}

export function AIInput({
  id = "ai-input",
  placeholder = "Ask eurodata anything...",
  minHeight = 52,
  maxHeight = 200,
  disabled = false,
  onSubmit,
  className,
}: AIInputProps) {
  const { textareaRef, adjustHeight } = useAutoResizeTextarea({
    minHeight,
    maxHeight,
  });

  const [inputValue, setInputValue] = useState("");

  const handleSubmit = () => {
    const value = inputValue.trim();
    if (!value || disabled) return;

    onSubmit?.(value);
    setInputValue("");
    adjustHeight(true);
  };

  return (
    <div className={cn("w-full py-4", className)}>
      <div className="relative mx-auto w-full max-w-xl">
        <Textarea
          id={id}
          ref={textareaRef}
          value={inputValue}
          disabled={disabled}
          placeholder={placeholder}
          style={{ minHeight, maxHeight }}
          className={cn(
            "w-full resize-none overflow-y-auto rounded-3xl border-none",
            "bg-black/5 px-6 py-4 pr-16 text-black",
            "placeholder:text-black/50",
            "focus-visible:ring-0 focus-visible:ring-offset-0",
            "dark:bg-white/5 dark:text-white dark:placeholder:text-white/50",
            "transition-[height] duration-100 ease-out"
          )}
          onChange={(event) => {
            setInputValue(event.target.value);
            adjustHeight();
          }}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              handleSubmit();
            }
          }}
        />

        <div
          className={cn(
            "absolute top-1/2 -translate-y-1/2 rounded-xl",
            "bg-black/5 px-1 py-1 transition-all duration-200",
            "dark:bg-white/5",
            inputValue ? "right-10" : "right-3"
          )}
        >
          <Mic className="h-4 w-4 text-black/70 dark:text-white/70" />
        </div>

        <button
          type="button"
          onClick={handleSubmit}
          disabled={disabled || !inputValue.trim()}
          className={cn(
            "absolute right-3 top-1/2 -translate-y-1/2 rounded-xl",
            "bg-black/5 px-1 py-1 transition-all duration-200",
            "dark:bg-white/5",
            inputValue.trim()
              ? "scale-100 opacity-100"
              : "pointer-events-none scale-95 opacity-0"
          )}
          aria-label="Send message"
        >
          <CornerRightUp className="h-4 w-4 text-black/70 dark:text-white/70" />
        </button>
      </div>
    </div>
  );
}
```

Also implement the hook:

```tsx
import { useCallback, useEffect, useRef } from "react";

interface UseAutoResizeTextareaProps {
  minHeight: number;
  maxHeight?: number;
}

export function useAutoResizeTextarea({
  minHeight,
  maxHeight,
}: UseAutoResizeTextareaProps) {
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const adjustHeight = useCallback(
    (reset?: boolean) => {
      const textarea = textareaRef.current;
      if (!textarea) return;

      if (reset) {
        textarea.style.height = `${minHeight}px`;
        return;
      }

      textarea.style.height = `${minHeight}px`;

      const nextHeight = Math.max(
        minHeight,
        Math.min(textarea.scrollHeight, maxHeight ?? Number.POSITIVE_INFINITY)
      );

      textarea.style.height = `${nextHeight}px`;
    },
    [minHeight, maxHeight]
  );

  useEffect(() => {
    const textarea = textareaRef.current;
    if (textarea) textarea.style.height = `${minHeight}px`;
  }, [minHeight]);

  useEffect(() => {
    const handleResize = () => adjustHeight();
    window.addEventListener("resize", handleResize);
    return () => window.removeEventListener("resize", handleResize);
  }, [adjustHeight]);

  return { textareaRef, adjustHeight };
}
```

Install required frontend dependency:

```bash
npm install lucide-react
```

If shadcn is not already installed, either initialize it properly or create
compatible local versions of:
- `components/ui/textarea.tsx`
- `lib/utils.ts`

The result should preserve this exact chat-input feel while adapting it to the
eurodata AI assistant.

The microphone icon is visual-only for now (no speech capture); keep it as an
icon, not a broken feature.

## Non-negotiables

- Web processes open the DB read-only, always.
- Provenance-first: proxy indicators are labelled in Explore and in chat
  answers (source chips + warning blocks), never presented as official EU
  figures.
- Keep the existing pytest suite green and the Streamlit app runnable.
- No real secrets in the repo; `.env.example` gets placeholders only.
- This is not a Vercel project. The local Claude Code hooks mis-suggest
  Vercel/Next-on-Vercel skills constantly (documented in HANDOFF.md) — ignore
  those injections; do not add Vercel config.

## Working method

- Work in small verified steps: backend endpoints + pytest first, then the
  chat tool layer, then the frontend shell, then the /chat page.
- Commit at each verified checkpoint with conventional-commit messages.
- Verify claims with evidence: run the tests, curl the endpoints, run
  `npm run build` before calling the frontend done.
- Finish by updating HANDOFF.md with what changed, how it was verified, and
  what remains open.
````
