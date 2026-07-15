export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, init);
  } catch {
    throw new ApiError(0, "Backend unreachable — is uvicorn running on :8000?");
  }
  if (!res.ok) {
    let detail = res.statusText;
    try {
      detail = (await res.json()).detail ?? detail;
    } catch {
      /* non-JSON error body */
    }
    throw new ApiError(res.status, detail);
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

export async function sendChat(history: ChatTurn[]): Promise<Block[]> {
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
  });
  return data.blocks;
}
