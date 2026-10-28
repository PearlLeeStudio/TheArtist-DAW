interface LedProps {
  /** on = yellow, alt = orange, off = grey. */
  state: 'on' | 'off' | 'alt';
  /** Brightness 0..1 (default 1); below 1 the colour mixes toward the off grey. */
  level?: number;
  /** Diameter in px (default 6). */
  size?: number;
  /** Tooltip; also makes the LED an image with this name for screen readers. */
  title?: string;
}

/** Round panel LED. A lit LED glows; every LED has a thin ring so yellow reads on a pale key. */
export default function Led({ state, level = 1, size = 6, title }: LedProps) {
  const amount = Math.min(1, Math.max(0, level));
  const lit = state !== 'off' && amount > 0;
  const color = state === 'alt' ? 'var(--led-alt)' : 'var(--led-on)';

  let background = 'var(--led-off)';
  let boxShadow = 'var(--led-ring)';
  if (lit) {
    background = amount >= 1
      ? color
      : `color-mix(in srgb, ${color} ${Math.round(20 + 80 * amount)}%, var(--led-off))`;
    const glow = Math.max(2, Math.round(size * 0.8));
    boxShadow += `, 0 0 ${glow}px color-mix(in srgb, ${color} ${Math.round(65 * amount)}%, transparent)`;
  }

  return (
    <span
      role={title ? 'img' : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      title={title}
      className="inline-block shrink-0 rounded-full align-middle"
      style={{ width: size, height: size, background, boxShadow }}
    />
  );
}
