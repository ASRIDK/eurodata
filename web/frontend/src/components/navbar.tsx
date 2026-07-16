"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";

import { cn } from "@/lib/utils";

const LINKS = [
  { href: "/", label: "Home" },
  { href: "/explore", label: "Explore" },
  { href: "/ranking", label: "Ranking" },
  { href: "/correlations", label: "Correlations" },
  { href: "/events", label: "Events" },
  { href: "/chat", label: "AI Chat" },
];

export function Navbar() {
  const pathname = usePathname();
  const isHome = pathname === "/";
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    if (!isHome) return;
    const onScroll = () => setScrolled(window.scrollY > 100);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [isHome]);

  // Home hosts the full-viewport globe hero: the navbar floats transparent
  // over it and turns solid once the user scrolls. Other routes keep the
  // sticky, always-solid bar (they have content directly beneath it).
  return (
    <header
      className={cn(
        isHome
          ? "fixed inset-x-0 top-0 z-50 transition-colors duration-300"
          : "sticky top-0 z-20",
        !isHome || scrolled
          ? "border-b border-black/10 bg-white/80 backdrop-blur dark:border-white/10 dark:bg-black/60"
          : "border-b border-transparent bg-transparent",
      )}
    >
      <nav className="mx-auto flex h-14 max-w-5xl items-center gap-1 px-4">
        <Link href="/" className="mr-4 font-semibold tracking-tight">
          European Data
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
          European data
        </span>
      </nav>
    </header>
  );
}
