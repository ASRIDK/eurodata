"use client";

import { useEffect, useRef, useState } from "react";

import { AssistantBlocks } from "@/components/assistant-blocks";
import { AIInput } from "@/components/ui/ai-input";
import { ApiError, sendChat, type ChatTurn } from "@/lib/api";

const EXAMPLES = [
  "Compare unemployment in France, Germany and Italy",
  "How did inflation change around the 2021 energy crisis?",
  "Rank EU countries by GDP per capita",
  "Is internet adoption correlated with GDP per capita?",
];

export default function Chat() {
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const cancelledRef = useRef(false);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns, loading]);

  // Abort an in-flight request if the user navigates away mid-answer.
  useEffect(() => () => controllerRef.current?.abort(), []);

  const send = async (text: string) => {
    if (loading) return;
    const history: ChatTurn[] = [...turns, { role: "user", text }];
    setTurns(history);
    setLoading(true);
    cancelledRef.current = false;
    const controller = new AbortController();
    controllerRef.current = controller;
    try {
      const blocks = await sendChat(history, { signal: controller.signal });
      setTurns([...history, { role: "assistant", blocks }]);
    } catch (e) {
      if (!cancelledRef.current) {
        const message =
          e instanceof ApiError && e.status === 429
            ? `Rate limited — try again in ${e.retryAfterSeconds ?? 30}s.`
            : e instanceof Error
              ? e.message
              : String(e);
        setTurns([...history, { role: "assistant", error: message }]);
      }
    } finally {
      controllerRef.current = null;
      setLoading(false);
    }
  };

  const cancel = () => {
    cancelledRef.current = true;
    controllerRef.current?.abort();
  };

  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-4">
      <div className="flex-1 overflow-y-auto py-6">
        {turns.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center gap-6 text-center">
            <div>
              <h1 className="text-2xl font-semibold tracking-tight">
                European Data AI analyst
              </h1>
              <p className="mt-1 text-sm text-black/50 dark:text-white/50">
                Answers from official European statistics — with charts,
                sources and caveats.
              </p>
            </div>
            <div className="flex max-w-xl flex-wrap justify-center gap-2">
              {EXAMPLES.map((ex) => (
                <button
                  key={ex}
                  type="button"
                  onClick={() => send(ex)}
                  className="rounded-full border border-black/15 px-3.5 py-1.5 text-sm text-black/70 transition-colors hover:bg-black/5 dark:border-white/20 dark:text-white/70 dark:hover:bg-white/10"
                >
                  {ex}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-6">
            {turns.map((turn, i) =>
              turn.role === "user" ? (
                <div key={i} className="flex justify-end">
                  <div className="max-w-[85%] whitespace-pre-wrap rounded-3xl bg-black/5 px-5 py-3 dark:bg-white/10">
                    {turn.text}
                  </div>
                </div>
              ) : "error" in turn ? (
                <div
                  key={i}
                  className="max-w-[95%] rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm"
                >
                  {turn.error}
                </div>
              ) : (
                <div key={i} className="max-w-[95%]">
                  <AssistantBlocks blocks={turn.blocks} onFollowUp={send} />
                </div>
              ),
            )}
            {loading ? (
              <div className="flex items-center gap-1.5 pl-1 text-black/40 dark:text-white/40">
                <Dot delay="0ms" />
                <Dot delay="150ms" />
                <Dot delay="300ms" />
                <span className="ml-2 text-xs">consulting the dataset…</span>
                <button
                  type="button"
                  onClick={cancel}
                  className="ml-2 text-xs underline underline-offset-2 hover:text-black/70 dark:hover:text-white/70"
                >
                  Cancel
                </button>
              </div>
            ) : null}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      <div className="sticky bottom-0 bg-gradient-to-t from-white via-white to-transparent pb-2 dark:from-black dark:via-black">
        <AIInput disabled={loading} onSubmit={send} />
      </div>
    </main>
  );
}

function Dot({ delay }: { delay: string }) {
  return (
    <span
      className="h-1.5 w-1.5 animate-bounce rounded-full bg-current"
      style={{ animationDelay: delay }}
    />
  );
}
