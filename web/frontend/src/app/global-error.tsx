"use client";

import { useEffect } from "react";

// Catches errors thrown by the root layout itself (e.g. the navbar), which
// error.tsx cannot — it must render its own <html>/<body> since the layout
// that would normally provide them is what failed.
export default function GlobalError({
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
    <html lang="en">
      <body className="flex min-h-screen flex-col items-center justify-center gap-4 bg-white px-4 text-center font-sans text-black dark:bg-black dark:text-white">
        <h1 className="text-xl font-semibold tracking-tight">
          Something went wrong
        </h1>
        <p className="max-w-[95%] rounded-xl border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-black/70 dark:text-white/70">
          {error.message || "An unexpected error occurred."}
        </p>
        <button
          type="button"
          onClick={reset}
          className="rounded-full border border-black/15 px-3.5 py-1.5 text-sm text-black/70 transition-colors hover:bg-black/5 dark:border-white/20 dark:text-white/70 dark:hover:bg-white/10"
        >
          Try again
        </button>
      </body>
    </html>
  );
}
