export default function TeamsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <div className="relative left-1/2 w-[min(100rem,calc(100vw-2rem))] max-w-none -translate-x-1/2 sm:w-[min(100rem,calc(100vw-3rem))] lg:w-[min(100rem,calc(100vw-4rem))]">
      {children}
    </div>
  );
}
