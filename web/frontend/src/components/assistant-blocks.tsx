"use client";

import { AlertTriangle, ExternalLink } from "lucide-react";

import { BlockChart } from "@/components/block-chart";
import { DataTable } from "@/components/data-table";
import type { Block } from "@/lib/api";

export function AssistantBlocks({
  blocks,
  onFollowUp,
}: {
  blocks: Block[];
  onFollowUp?: (prompt: string) => void;
}) {
  return (
    <div className="space-y-3">
      {blocks.map((block, i) => {
        switch (block.type) {
          case "text":
            return (
              <p key={i} className="whitespace-pre-wrap leading-relaxed">
                {block.text}
              </p>
            );
          case "chart":
            return <BlockChart key={i} spec={block.spec} />;
          case "table":
            return <DataTable key={i} columns={block.columns} rows={block.rows} />;
          case "sources":
            return (
              <div key={i} className="flex flex-wrap gap-1.5">
                {block.items.map((item, j) => {
                  const chip = (
                    <span
                      className="inline-flex items-center gap-1 rounded-full border border-black/10 bg-black/[.03] px-2.5 py-0.5 text-xs text-black/70 dark:border-white/15 dark:bg-white/[.06] dark:text-white/70"
                      title={item.proxy_note ?? undefined}
                    >
                      {item.label}
                      {item.is_proxy ? <span className="font-medium text-amber-600 dark:text-amber-400">proxy</span> : null}
                      {item.url ? <ExternalLink className="h-3 w-3" /> : null}
                    </span>
                  );
                  return item.url ? (
                    <a key={j} href={item.url} target="_blank" rel="noreferrer">
                      {chip}
                    </a>
                  ) : (
                    <span key={j}>{chip}</span>
                  );
                })}
              </div>
            );
          case "warning":
            return (
              <div
                key={i}
                className="flex items-start gap-2 rounded-xl border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-amber-800 dark:text-amber-200"
              >
                <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
                {block.text}
              </div>
            );
          case "follow_ups":
            return onFollowUp && block.items.length ? (
              <div key={i} className="flex flex-wrap gap-1.5 pt-1">
                {block.items.map((p) => (
                  <button
                    key={p}
                    type="button"
                    onClick={() => onFollowUp(p)}
                    className="rounded-full border border-black/15 px-3 py-1 text-xs text-black/70 transition-colors hover:bg-black/5 dark:border-white/20 dark:text-white/70 dark:hover:bg-white/10"
                  >
                    {p}
                  </button>
                ))}
              </div>
            ) : null;
          default:
            return null;
        }
      })}
    </div>
  );
}
