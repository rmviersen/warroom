export type WARroomLogoProps = {
  size?: "hero" | "navbar" | "small";
  theme?: "dark" | "light";
};

const VIEW_W = 320;
const VIEW_H = 64;

const WIDTH_PX: Record<NonNullable<WARroomLogoProps["size"]>, number> = {
  small: 128,
  navbar: 200,
  hero: 360,
};

/** Diamond center and half-diagonal (corner distance from center). All mark geometry derives from this so it scales with the viewBox. */
const CX = 29;
const CY = 32;
const R = 22.5;
const TICK_LEN = 5.5;
const STROKE_DIAMOND = 2;
const STROKE_TICK = 1.35;
const DOT_R = 3.15;

/**
 * Inline WARroom wordmark: rotated-square diamond with corner ticks + “WAR” (red) + “room” (theme-colored).
 */
export function WARroomLogo({
  size = "navbar",
  theme = "dark",
}: WARroomLogoProps) {
  const w = WIDTH_PX[size];
  const h = (w * VIEW_H) / VIEW_W;

  const top = { x: CX, y: CY - R };
  const right = { x: CX + R, y: CY };
  const bottom = { x: CX, y: CY + R };
  const left = { x: CX - R, y: CY };

  const fillInner = "#e63333";
  const fillInnerOpacity = theme === "dark" ? 0.14 : 0.22;

  const diamondPts = `${top.x},${top.y} ${right.x},${right.y} ${bottom.x},${bottom.y} ${left.x},${left.y}`;

  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
      width={w}
      height={h}
      role="img"
      aria-label="WARroom"
      className="inline-block align-middle select-none"
    >
      <title>WARroom</title>
      <g strokeLinecap="round" strokeLinejoin="round">
        <polygon
          points={diamondPts}
          fill={fillInner}
          fillOpacity={fillInnerOpacity}
          stroke="#e63333"
          strokeWidth={STROKE_DIAMOND}
        />
        {/* Corner tick marks (outward from each vertex) */}
        <path
          d={`M ${top.x} ${top.y} L ${top.x} ${top.y - TICK_LEN} M ${right.x} ${right.y} L ${right.x + TICK_LEN} ${right.y} M ${bottom.x} ${bottom.y} L ${bottom.x} ${bottom.y + TICK_LEN} M ${left.x} ${left.y} L ${left.x - TICK_LEN} ${left.y}`}
          fill="none"
          stroke="#e63333"
          strokeWidth={STROKE_TICK}
        />
        <circle cx={CX} cy={CY} r={DOT_R} fill="#e63333" />
      </g>
      <text
        x={64}
        y={44}
        fontFamily="Georgia, 'Times New Roman', serif"
        fontSize={34}
        fontWeight="700"
        fill="#e63333"
        letterSpacing="-0.02em"
      >
        WAR
      </text>
      <text
        x={152}
        y={44}
        fontFamily="Georgia, 'Times New Roman', serif"
        fontSize={34}
        fontWeight="400"
        fill={theme === "dark" ? "#ffffff" : "#111111"}
        letterSpacing="-0.02em"
      >
        room
      </text>
    </svg>
  );
}
