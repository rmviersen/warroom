"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAVY = "#1e3a6b";
const GOLD = "#c9a84c";

function pathnameMatchesHref(pathname: string, href: string): boolean {
  if (href === "/teams") return pathname.startsWith("/teams");
  if (href === "/players") return pathname.startsWith("/players");
  if (href === "/leaderboards/batting")
    return pathname.startsWith("/leaderboards");
  if (href === "/statcast") return pathname.startsWith("/statcast");
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
            <NavItem href="/leaderboards/batting" label="Leaderboards" />
            <NavItem href="/statcast" label="Statcast" />
          </div>
        </div>
      </div>
    </nav>
  );
}
