"use client";

import Link from "next/link";
import { useEffect } from "react";

export default function Error({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error(error);
  }, [error]);

  return (
    <main className="mx-auto flex w-full max-w-lg flex-1 flex-col items-center justify-center gap-4 px-4 text-center">
      <h1 className="text-xl font-semibold tracking-tight">
        Something went wrong
      </h1>
      <p className="max-w-[95%] rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-black/70 dark:text-white/70">
        {error.message || "An unexpected error occurred while rendering this page."}
      </p>
      <div className="flex gap-2">
        <button
          type="button"
          onClick={reset}
          className="rounded-full border border-black/15 px-3.5 py-1.5 text-sm text-black/70 transition-colors hover:bg-black/5 dark:border-white/20 dark:text-white/70 dark:hover:bg-white/10"
        >
          Try again
        </button>
        <Link
          href="/"
          className="rounded-full border border-black/15 px-3.5 py-1.5 text-sm text-black/70 transition-colors hover:bg-black/5 dark:border-white/20 dark:text-white/70 dark:hover:bg-white/10"
        >
          Back to home
        </Link>
      </div>
    </main>
  );
}
