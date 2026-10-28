import type { CSSProperties } from 'react';

interface StepCell {
  /** 0 = off; 0..1 = on at that brightness (ghost notes dim but visible). */
  level: number;
  /** Alternate articulation, shown in a lighter green. */
  alt?: boolean;
}

interface StepRowProps {
  cells: StepCell[];
  /** Index of the cell playing now; null or out of range = none. */
  playhead?: number | null;
  /** e.g. 'K', 'HARM', 'BASS' — shown in a fixed-width column on the left. */
  label?: string;
  /** Whole row muted (e.g. bass off). */
  dim?: boolean;
  /** Extra gap every n cells (default 4; 0 = none). */
  group?: number;
  /** LED cell height in px; the recessed frame adds six pixels. */
  height?: number;
  labelSize?: number;
}

/** Fits a four-letter label in 9px device type. */
const LABEL_WIDTH = 26;
const LABEL_GAP = 4;
const CELL_GAP = 2;
/** Added to CELL_GAP at each group boundary. */
const GROUP_GAP = 3;

function cellStyle(cell: StepCell, here: boolean, groupStart: boolean, radius: number): CSSProperties {
  const style: CSSProperties = {
    flex: '1 1 0',
    minWidth: 0,
    borderRadius: radius,
    marginLeft: groupStart ? GROUP_GAP : undefined,
  };
  const level = Math.min(1, Math.max(0, cell.level || 0));
  if (level === 0) {
    style.background = here
      ? 'linear-gradient(180deg, #405935, #24341e)'
      : 'linear-gradient(180deg, #20271d, #141a12)';
    style.boxShadow = here ? 'inset 0 0 0 1px #b5ff7d, 0 0 4px #76ef48' : 'inset 0 1px 1px #080c07';
    return style;
  }
  const color = cell.alt ? '#c8ff67' : '#8bff4c';
  // The playing step flashes at full brightness whatever its level.
  style.background = here || level >= 1
    ? color
    : `color-mix(in srgb, ${color} ${Math.round(25 + 75 * level)}%, #172211)`;
  style.boxShadow = here
    ? `inset 0 1px 0 #e4ffd2, 0 0 0 1px #d6ffbc, 0 0 6px ${color}`
    : 'inset 0 1px 0 #d1ffa566, inset 0 -1px 0 #27571a';
  return style;
}

/** Horizontal green LEDs in a black recessed meter, with the live beat marked. */
export default function StepRow({ cells, playhead = null, label, dim = false, group = 4, height = 10, labelSize = 9 }: StepRowProps) {
  const radius = Math.min(2, height / 4);
  const onSteps = cells.flatMap((cell, i) => (cell.level > 0 ? [i + 1] : []));
  const name = `${label ? `${label}: ` : ''}${onSteps.length > 0 ? `steps ${onSteps.join(' ')}` : 'no steps'}${dim ? ', muted' : ''}`;

  return (
    <div
      role="img"
      aria-label={name}
      className="flex w-full min-w-0 items-center"
      style={{
        height: height + 6,
        opacity: dim ? 0.35 : 1,
        filter: dim ? 'saturate(0.4)' : undefined,
        transition: 'opacity 0.15s ease',
      }}
    >
      {label !== undefined && (
        <span
          className="shrink-0 truncate uppercase"
          style={{
            width: labelSize > 9 ? 34 : LABEL_WIDTH,
            marginRight: LABEL_GAP,
            fontFamily: 'var(--font-device)',
            fontSize: labelSize,
            lineHeight: 1,
            letterSpacing: '0.06em',
            color: 'var(--key-text-dim)',
          }}
        >
          {label}
        </span>
      )}
      <div className="te-step-meter flex min-w-0 flex-1 self-stretch" style={{ gap: CELL_GAP }}>
        {cells.map((cell, i) => (
          <span
            key={i}
            style={cellStyle(cell, i === playhead, group > 0 && i > 0 && i % group === 0, radius)}
          />
        ))}
      </div>
    </div>
  );
}
