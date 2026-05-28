export default function Footer() {
    return (
      <footer className="border-t border-[#d0daea] mt-16 py-8 text-center text-sm text-[#7a8fa8]">
        <p>WARroom © {new Date().getFullYear()} — MLB Analytics Platform</p>
        <p className="mt-1">Data sourced from MLB Stats API & Baseball Savant</p>
      </footer>
    );
  }