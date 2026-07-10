"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/explore", label: "Explore" },
  { href: "/events", label: "Events" },
  { href: "/chat", label: "AI Chat" },
];

export function Navbar() {
  const pathname = usePathname();
  return (
    <header className="sticky top-0 z-20 border-b border-black/10 bg-white/80 backdrop-blur dark:border-white/10 dark:bg-black/60">
      <nav className="mx-auto flex h-14 max-w-5xl items-center gap-1 px-4">
        <Link href="/" className="mr-4 font-semibold tracking-tight">
          eurodata
        </Link>
        {LINKS.map((l) => (
          <Link
            key={l.href}
            href={l.href}
            className={cn(
              "rounded-lg px-3 py-1.5 text-sm transition-colors",
              pathname === l.href
                ? "bg-black/10 font-medium dark:bg-white/15"
                : "text-black/60 hover:bg-black/5 dark:text-white/60 dark:hover:bg-white/10",
            )}
          >
            {l.label}
          </Link>
        ))}
        <span className="ml-auto hidden text-xs text-black/40 sm:block dark:text-white/40">
          European data intelligence
        </span>
      </nav>
    </header>
  );
}
