"use client";

import { Menu, X } from "lucide-react";
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
  // Storing the route the menu was opened on (rather than a bare boolean)
  // closes it on any navigation — including browser back/forward — without an
  // effect that would setState during render.
  const [openPath, setOpenPath] = useState<string | null>(null);
  const menuOpen = openPath === pathname;
  const closeMenu = () => setOpenPath(null);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenPath(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

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
          // Unscrolled on home the bar sits over the globe's dot matrix, which
          // rendered the links unreadable. A top-down scrim, deeper than the
          // bar itself so it fades out below the links, keeps them legible
          // without reintroducing a hard edge over the hero.
          : cn(
              "border-b border-transparent bg-gradient-to-b from-white via-white/80 to-transparent dark:from-black dark:via-black/75",
              // The extra depth is what fades the scrim out below the links;
              // with the mobile menu open its solid panel provides the
              // backdrop instead, and the padding would just add dead space.
              !menuOpen && "pb-12",
            ),
      )}
    >
      <nav className="mx-auto flex h-14 max-w-5xl items-center gap-1 px-4">
        <Link href="/" className="mr-4 font-semibold tracking-tight whitespace-nowrap">
          European Data
        </Link>
        {/* Six links do not fit a phone: they overflowed the viewport and the
            last of them were unreachable. Collapse to a menu below md. */}
        <div className="hidden items-center gap-1 md:flex">
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
        </div>
        <span className="ml-auto hidden text-xs text-black/40 sm:block dark:text-white/40">
          European data
        </span>
        <button
          type="button"
          aria-expanded={menuOpen}
          aria-controls="mobile-nav"
          aria-label={menuOpen ? "Close menu" : "Open menu"}
          onClick={() => setOpenPath(menuOpen ? null : pathname)}
          className="ml-auto rounded-lg p-2 text-black/70 hover:bg-black/5 md:hidden dark:text-white/70 dark:hover:bg-white/10"
        >
          {menuOpen ? <X className="size-5" /> : <Menu className="size-5" />}
        </button>
      </nav>
      {menuOpen && (
        <div
          id="mobile-nav"
          className="border-t border-black/10 bg-white px-4 pb-3 md:hidden dark:border-white/10 dark:bg-black"
        >
          {LINKS.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={closeMenu}
              className={cn(
                "block rounded-lg px-3 py-2.5 text-sm transition-colors",
                pathname === l.href
                  ? "bg-black/10 font-medium dark:bg-white/15"
                  : "text-black/70 hover:bg-black/5 dark:text-white/70 dark:hover:bg-white/10",
              )}
            >
              {l.label}
            </Link>
          ))}
        </div>
      )}
    </header>
  );
}
