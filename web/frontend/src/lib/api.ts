export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  /** Present when the server sent a `Retry-After` header on a 429. */
  retryAfterSeconds?: number;
  constructor(status: number, message: string, retryAfterSeconds?: number) {
    super(message);
    this.status = status;
    this.retryAfterSeconds = retryAfterSeconds;
  }
}

export async function api<T>(
  path: string,
  init?: RequestInit & { timeoutMs?: number },
): Promise<T> {
  const { timeoutMs, signal: externalSignal, ...rest } = init ?? {};
  // One controller drives the fetch; both an optional timeout and an
  // optional caller-supplied signal (e.g. a Cancel button) can abort it.
  const controller = new AbortController();
  const timer = timeoutMs ? setTimeout(() => controller.abort(), timeoutMs) : null;
  const onExternalAbort = () => controller.abort();
  if (externalSignal?.aborted) controller.abort();
  externalSignal?.addEventListener("abort", onExternalAbort);

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { ...rest, signal: controller.signal });
  } catch {
    if (controller.signal.aborted) {
      throw new ApiError(
        0,
        externalSignal?.aborted ? "Request cancelled." : "Request timed out.",
      );
    }
    throw new ApiError(0, "Backend unreachable — is uvicorn running on :8000?");
  } finally {
    if (timer) clearTimeout(timer);
    externalSignal?.removeEventListener("abort", onExternalAbort);
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    const retryAfterHeader = res.headers.get("retry-after");
    const retryAfterSeconds = retryAfterHeader ? Number(retryAfterHeader) : undefined;
    if (res.status === 429 && detail === res.statusText) {
      detail = "Too many requests — please slow down.";
    }
    throw new ApiError(res.status, detail, retryAfterSeconds);
  }
  return res.json();
}

export type Row = Record<string, string | number | boolean | null>;

export type ChartSpec = {
  kind: "line" | "bar" | "area" | "scatter" | "pie";
  unit: string | null;
  title?: string | null;
  series: {
    name: string;
    points: { x: number | string; y: number | null }[];
    dashed?: boolean;
    color?: string;
    band?: { x: number | string; lo: number; hi: number }[];
  }[];
  /** Curated events to draw as vertical markers on a time-series chart. */
  events?: { x: number | string; label: string; url?: string | null }[];
};

export type SourceItem = {
  label: string;
  url?: string | null;
  is_proxy?: boolean;
  proxy_note?: string | null;
};

export type Block =
  | { type: "text"; text: string }
  | { type: "chart"; spec: ChartSpec }
  | { type: "table"; columns: string[]; rows: (string | number | boolean | null)[][] }
  | { type: "sources"; items: SourceItem[] }
  | { type: "warning"; text: string }
  | { type: "follow_ups"; items: string[] };

export type ChatTurn =
  | { role: "user"; text: string }
  | { role: "assistant"; blocks: Block[] }
  | { role: "assistant"; error: string };

export async function sendChat(
  history: ChatTurn[],
  opts?: { signal?: AbortSignal },
): Promise<Block[]> {
  const messages = history
    .map((t) =>
      t.role === "user"
        ? { role: "user", content: t.text }
        : "blocks" in t
          ? {
              role: "assistant",
              content:
                t.blocks
                  .filter((b): b is Extract<Block, { type: "text" }> => b.type === "text")
                  .map((b) => b.text)
                  .join("\n\n") || "(shown as chart/table)",
            }
          : null,
    )
    .filter((m): m is { role: string; content: string } => m !== null);
  const data = await api<{ blocks: Block[] }>("/api/chat", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ messages }),
    signal: opts?.signal,
    // The AI analyst can take a while (multi-turn tool-calling loop with its
    // own retries) but a genuinely hung backend shouldn't strand the user.
    timeoutMs: 60_000,
  });
  return data.blocks;
}
