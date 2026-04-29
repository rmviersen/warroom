import Link from "next/link";

export default function Navbar() {
  return (
    <nav className="border-b border-gray-800 bg-gray-950/80 backdrop-blur-sm sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <Link href="/" className="flex items-center gap-2">
            <span className="text-red-500 font-black text-2xl tracking-tight">WAR</span>
            <span className="text-white font-black text-2xl tracking-tight">room</span>
          </Link>
          <div className="flex items-center gap-6 text-sm font-medium text-gray-400">
            <Link href="/teams" className="hover:text-white transition-colors">Teams</Link>
            <Link href="/players" className="hover:text-white transition-colors">Players</Link>
            <Link href="/statcast" className="hover:text-white transition-colors">Statcast</Link>
          </div>
        </div>
      </div>
    </nav>
  );
}
