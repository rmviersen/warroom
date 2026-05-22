/** Ordinal suffix for whole numbers (1st…13th exceptions). Exported for callers/tests. */
export function getOrdinal(n: number): string {
  const k = Math.round(n);
  const v = Math.abs(k) % 100;
  if (v >= 11 && v <= 13) {
    return `${k}th`;
  }
  switch (Math.abs(k) % 10) {
    case 1:
      return `${k}st`;
    case 2:
      return `${k}nd`;
    case 3:
      return `${k}rd`;
    default:
      return `${k}th`;
  }
}

function fillColorClasses(percentile: number, isWarroomMetric?: boolean): string {
  if (percentile >= 80 && isWarroomMetric) return "bg-[#b8922a]";
  if (percentile >= 80) return "bg-[#1e3a6b]";
  if (percentile >= 50) return "bg-[#1e3a6b]/60";
  return "bg-[#7a8fa8]";
}

function percentileTextClasses(
  percentile: number,
  isWarroomMetric: boolean | undefined,
  qualifies: boolean,
): string {
  if (!qualifies) return "text-[#7a8fa8]";
  if (percentile >= 80 && isWarroomMetric) return "text-[#b8922a]";
  if (percentile >= 80) return "text-[#1e3a6b]";
  if (percentile >= 50) return "text-[#1e3a6b]/60";
  return "text-[#7a8fa8]";
}

export interface PercentileBarProps {
  label: string;
  rawDisplay: string;
  percentile: number | null;
  qualifies: boolean;
  isWarroomMetric?: boolean;
}

export default function PercentileBar({
  label,
  rawDisplay,
  percentile,
  qualifies,
  isWarroomMetric,
}: PercentileBarProps) {
  const p =
    percentile == null ? null : Math.min(100, Math.max(0, percentile));
  const fillCls = p == null ? "" : fillColorClasses(p, isWarroomMetric);
  const textCls =
    p == null
      ? "text-[#7a8fa8]"
      : percentileTextClasses(p, isWarroomMetric, qualifies);

  return (
    <div className="flex w-full max-w-full items-center gap-2">
      <div className="w-[40%] min-w-0 shrink-0">
        <div
          className={`text-xs font-medium ${
            isWarroomMetric ? "text-[#b8922a]" : "text-[#7a8fa8]"
          }`}
        >
          {label}
        </div>
        <div className="text-[10px] font-mono tabular-nums text-[#1e3050]">
          {rawDisplay}
        </div>
      </div>

      <div className="w-[45%] min-w-0 shrink-0 self-center px-1">
        <div
          className={[
            "relative box-border h-[6px] w-full rounded-[3px] bg-[#f0f4f9]",
            !qualifies
              ? "border-[1.5px] border-dashed border-[#d0daea]"
              : "",
          ]
            .filter(Boolean)
            .join(" ")}
        >
          {p != null ? (
            <div
              className={[
                "absolute inset-y-0 left-0 rounded-[3px]",
                fillCls,
                qualifies ? "" : "opacity-50",
              ]
                .filter(Boolean)
                .join(" ")}
              style={{ width: `${p}%` }}
              aria-hidden
            />
          ) : null}
        </div>
      </div>

      <div
        className={[
          "w-[15%] min-w-0 shrink-0 text-right font-mono text-xs tabular-nums",
          textCls,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        {p == null
          ? "—"
          : `${getOrdinal(Math.round(p))}${qualifies ? "" : "*"}`}
      </div>
    </div>
  );
}
