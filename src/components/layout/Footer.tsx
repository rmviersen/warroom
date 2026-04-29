export default function Footer() {
    return (
      <footer className="border-t border-gray-800 mt-16 py-8 text-center text-sm text-gray-600">
        <p>WARroom © {new Date().getFullYear()} — MLB Analytics Platform</p>
        <p className="mt-1">Data sourced from MLB Stats API & Baseball Savant</p>
      </footer>
    );
  }