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
  { href: "/revisions", label: "Revisions" },
  { href: "/events", label: "Events" },
  { href: "/chat", label: "AI Chat" },
];

export function Navbar() {
  const pathname = usePathname();
  const isHome = pathname === "/";
  const [scrolled, setScrolled] = useState(false);
  // Storing the route the menu was opened on (rather than a bare boolean)
  // closes it on any navigation — including browser back/forward, which an
  // onClick handler never sees — without an effect that setStates on render.
  const [openPath, setOpenPath] = useState<string | null>(null);
  const menuOpen = openPath === pathname;
  const closeMenu = () => setOpenPath(null);

  useEffect(() => {
    if (!isHome) return;
    const onScroll = () => setScrolled(window.scrollY > 100);
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [isHome]);

  // Escape closes the menu; click-away is handled by the backdrop below.
  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpenPath(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  const solid = !isHome || scrolled || menuOpen;

  // Home hosts the full-viewport globe hero: the navbar floats transparent
  // over it and turns solid once the user scrolls. Other routes keep the
  // sticky, always-solid bar (they have content directly beneath it).
  return (
    <header
      className={cn(
        isHome
          ? "fixed inset-x-0 top-0 z-50 transition-colors duration-300"
          : "sticky top-0 z-20",
        solid
          ? "border-b border-black/10 bg-white/80 backdrop-blur dark:border-white/10 dark:bg-black/60"
          // Unscrolled on home the bar sits over the globe's dot matrix, which
          // rendered the links unreadable. A top-down scrim, deeper than the
          // bar itself so it fades out below the links, keeps them legible
          // without reintroducing a hard edge over the hero. (An open menu
          // takes the solid branch above, so this never applies to it.)
          : "border-b border-transparent bg-gradient-to-b from-white via-white/80 to-transparent pb-12 dark:from-black dark:via-black/75",
      )}
    >
      <nav className="mx-auto flex h-14 max-w-5xl items-center gap-1 px-4">
        <Link
          href="/"
          className="mr-2 font-semibold tracking-tight whitespace-nowrap sm:mr-4"
        >
          European Data
        </Link>

        {/* Desktop: inline links (scroll horizontally if ever too wide). */}
        <div className="hidden min-w-0 flex-1 items-center gap-1 overflow-x-auto md:flex">
          {LINKS.map((l) => (
            <NavLink key={l.href} href={l.href} active={pathname === l.href}>
              {l.label}
            </NavLink>
          ))}
        </div>

        {/* Mobile: seven links do not fit a phone — they overflowed the
            viewport and the last of them were unreachable. Collapse to a
            hamburger toggling a dropdown sheet below md. */}
        <button
          type="button"
          onClick={() => setOpenPath(menuOpen ? null : pathname)}
          aria-expanded={menuOpen}
          aria-controls="mobile-nav"
          aria-label={menuOpen ? "Close navigation menu" : "Open navigation menu"}
          className="ml-auto inline-flex h-9 w-9 items-center justify-center rounded-lg hover:bg-black/5 md:hidden dark:hover:bg-white/10"
        >
          {menuOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
        </button>
      </nav>

      {menuOpen ? (
        <>
          {/* Click-away backdrop (below the panel, above the page). */}
          <button
            type="button"
            aria-hidden="true"
            tabIndex={-1}
            onClick={closeMenu}
            className="fixed inset-0 top-14 z-10 md:hidden"
          />
          <div
            id="mobile-nav"
            className="relative z-20 border-t border-black/10 bg-white/95 px-4 py-2 backdrop-blur md:hidden dark:border-white/10 dark:bg-black/80"
          >
            <div className="flex flex-col gap-1">
              {LINKS.map((l) => (
                <NavLink
                  key={l.href}
                  href={l.href}
                  active={pathname === l.href}
                  block
                  onNavigate={closeMenu}
                >
                  {l.label}
                </NavLink>
              ))}
            </div>
          </div>
        </>
      ) : null}
    </header>
  );
}

function NavLink({
  href,
  active,
  block,
  onNavigate,
  children,
}: {
  href: string;
  active: boolean;
  block?: boolean;
  onNavigate?: () => void;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      onClick={onNavigate}
      aria-current={active ? "page" : undefined}
      className={cn(
        "rounded-lg px-3 py-1.5 text-sm whitespace-nowrap transition-colors",
        block && "w-full",
        active
          ? "bg-black/10 font-medium dark:bg-white/15"
          : "text-black/60 hover:bg-black/5 dark:text-white/60 dark:hover:bg-white/10",
      )}
    >
      {children}
    </Link>
  );
}
