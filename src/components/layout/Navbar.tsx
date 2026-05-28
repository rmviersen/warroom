"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";

const NAVY = "#1e3a6b";
const GOLD = "#c9a84c";

function pathnameMatchesHref(pathname: string, href: string): boolean {
  if (href === "/teams") return pathname.startsWith("/teams");
  if (href === "/players") return pathname.startsWith("/players");
  if (href === "/statcast") return pathname.startsWith("/statcast");
  if (href === "/status") return pathname.startsWith("/status");
  return pathname === href;
}

function NavItem({ href, label }: { href: string; label: string }) {
  const pathname = usePathname();
  const active = pathnameMatchesHref(pathname, href);

  return (
    <Link
      href={href}
      className={
        active
          ? "text-[#ffffff] underline decoration-2 decoration-[#c9a84c] underline-offset-4 transition-colors"
          : "text-[#a8bdd8] hover:text-[#ffffff] transition-colors"
      }
    >
      {label}
    </Link>
  );
}

function LeaderboardsDropdown() {
  const pathname = usePathname();
  const sectionActive = pathname.startsWith("/leaderboards");
  const [menuOpen, setMenuOpen] = useState(false);

  const triggerBase = "text-sm font-medium transition-colors";

  const triggerCls = sectionActive
    ? `${triggerBase} text-[#ffffff] underline decoration-2 decoration-[#c9a84c] underline-offset-4`
    : `${triggerBase} text-[#a8bdd8] hover:text-[#ffffff]`;

  const subCls = (prefix: string) => {
    const active = pathname.startsWith(prefix);
    return active
      ? "block px-3 py-2 text-sm text-[#ffffff] bg-white/10 font-medium underline decoration-[#c9a84c] decoration-2 underline-offset-2 transition-colors"
      : "block px-3 py-2 text-sm text-[#a8bdd8] hover:text-[#ffffff] hover:bg-white/10 transition-colors";
  };

  return (
    <div
      className="relative"
      onMouseEnter={() => setMenuOpen(true)}
      onMouseLeave={() => setMenuOpen(false)}
    >
      <span className={triggerCls}>Leaderboards</span>
      {menuOpen ? (
        <div className="absolute left-0 top-full z-50 pt-1 min-w-[11rem]">
          <div
            className="rounded-md border border-white/20 py-1 shadow-lg"
            style={{ backgroundColor: NAVY }}
          >
            <Link href="/leaderboards/batting" className={subCls("/leaderboards/batting")}>
              Batting
            </Link>
            <Link href="/leaderboards/baserunning" className={subCls("/leaderboards/baserunning")}>
              Baserunning
            </Link>
            <Link href="/leaderboards/pitching" className={subCls("/leaderboards/pitching")}>
              Pitching
            </Link>
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default function Navbar() {
  return (
    <nav
      className="sticky top-0 z-50 border-b border-white/15 backdrop-blur-sm"
      style={{ backgroundColor: NAVY }}
    >
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link
            href="/"
            className="flex items-center font-black tracking-tight text-xl"
          >
            <span style={{ color: GOLD }}>WAR</span>
            <span className="text-white">room</span>
          </Link>
          <div className="flex items-center gap-6 text-sm font-medium">
            <NavItem href="/teams" label="Teams" />
            <NavItem href="/players" label="Players" />
            <LeaderboardsDropdown />
            <NavItem href="/statcast" label="Statcast" />
            <NavItem href="/status" label="Status" />
          </div>
        </div>
      </div>
    </nav>
  );
}
