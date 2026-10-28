import { useEffect, useEffectEvent, useRef, useState } from 'react';
import type { KeyboardEvent as ReactKeyboardEvent, PointerEvent as ReactPointerEvent } from 'react';

interface KnobProps {
  label: string;
  value: number;
  min: number;
  max: number;
  /** Snap grid (from min) and arrow-key increment; default (max - min) / 100. */
  step?: number;
  /** Double-click resets to this. */
  defaultValue?: number;
  onChange: (v: number) => void;
  format?: (v: number) => string;
  /** Knob diameter in px (default 34). The whole control is size + 24 px tall. */
  size?: number;
}

/** Vertical drag distance for the full range; Shift drags five times finer. */
const DRAG_RANGE_PX = 150;
const FINE_FACTOR = 0.2;
/** Wheel: one step once this much scroll has built up, at most one per interval. */
const WHEEL_MIN_PX = 4;
const WHEEL_INTERVAL_MS = 45;
/** The arc runs 270° clockwise from 7:30 to 4:30 (0° = 12 o'clock). */
const START_DEG = -135;
const SWEEP_DEG = 270;
/** Set on <html> while dragging (index.css): no text selection, ns-resize cursor. */
const DRAG_CLASS = 'te-knob-drag';
const TEXT_LINE = 11;

interface Drag {
  pointerId: number;
  lastY: number;
  /** Unsnapped value the drag has reached. */
  raw: number;
  /** Last value sent to onChange. */
  emitted: number;
}

function decimalsOf(n: number): number {
  const [mantissa, exponent] = String(n).split('e');
  const places = mantissa.split('.')[1]?.length ?? 0;
  return Math.max(0, places - Number(exponent ?? 0));
}

function clamp(v: number, min: number, max: number): number {
  return Math.min(max, Math.max(min, v));
}

/** Clamp to [min, max] and snap to the step grid that starts at min. */
function snap(v: number, min: number, max: number, step: number): number {
  const stepped = min + Math.round((clamp(v, min, max) - min) / step) * step;
  const places = Math.min(10, Math.max(decimalsOf(step), decimalsOf(min)));
  return Number(Math.min(max, stepped).toFixed(places));
}

/** Point at `deg` (0° = 12 o'clock, clockwise) on a circle of radius r around (c, c). */
function polar(c: number, r: number, deg: number): [number, number] {
  const rad = (deg * Math.PI) / 180;
  return [c + r * Math.sin(rad), c - r * Math.cos(rad)];
}

function arcPath(c: number, r: number, from: number, to: number): string {
  const [x0, y0] = polar(c, r, from);
  const [x1, y1] = polar(c, r, to);
  const large = to - from > 180 ? 1 : 0;
  return `M ${x0.toFixed(2)} ${y0.toFixed(2)} A ${r} ${r} 0 ${large} 1 ${x1.toFixed(2)} ${y1.toFixed(2)}`;
}

/**
 * Round knob with a 270° value arc; label and value under it. Drag up to
 * increase (pointer capture, ~150px for the full range, Shift = fine),
 * scroll, or use the keyboard (Arrows = step, PageUp/PageDown = 10 steps,
 * Home/End). Double-click resets to defaultValue. Fills its column's
 * width; size + 24 px tall.
 */
export default function Knob({ label, value, min, max, step, defaultValue, onChange, format, size = 34 }: KnobProps) {
  const stepSize = step !== undefined && step > 0 ? step : (max - min) / 100 || 1;
  const rootRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<Drag | null>(null);
  const wheelRef = useRef({ acc: 0, at: -Infinity });
  const [dragging, setDragging] = useState(false);

  const shown = format ? format(value) : value.toFixed(Math.min(3, decimalsOf(stepSize)));
  const current = Number.isFinite(value) ? clamp(value, min, max) : min;

  /** Send `next`, snapped and clamped, unless it is the value already shown. */
  const commit = (next: number) => {
    const v = snap(next, min, max, stepSize);
    if (v !== value) onChange(v);
  };
  const nudge = (steps: number) => commit(current + steps * stepSize);

  // React's onWheel listener is passive (the page would scroll too), so
  // the wheel is handled by a native listener.
  const onWheel = useEffectEvent((e: WheelEvent) => {
    e.preventDefault();
    const unit = e.deltaMode === 1 ? 16 : e.deltaMode === 2 ? 120 : 1;
    const delta = (e.deltaY !== 0 ? e.deltaY : -e.deltaX) * unit;
    if (delta === 0) return;
    const prev = wheelRef.current;
    const acc = Math.sign(delta) === Math.sign(prev.acc) ? prev.acc + delta : delta;
    if (Math.abs(acc) < WHEEL_MIN_PX || e.timeStamp - prev.at < WHEEL_INTERVAL_MS) {
      wheelRef.current = { acc, at: prev.at };
      return;
    }
    wheelRef.current = { acc: 0, at: e.timeStamp };
    nudge(acc < 0 ? 1 : -1);
  });

  useEffect(() => {
    const el = rootRef.current;
    if (!el) return;
    const handleWheel = (e: WheelEvent) => onWheel(e);
    el.addEventListener('wheel', handleWheel, { passive: false });
    return () => {
      el.removeEventListener('wheel', handleWheel);
      // Unmounted mid-drag: give the page back its cursor and text selection.
      if (dragRef.current) document.documentElement.classList.remove(DRAG_CLASS);
    };
  }, []);

  const onPointerDown = (e: ReactPointerEvent<HTMLDivElement>) => {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { pointerId: e.pointerId, lastY: e.clientY, raw: current, emitted: value };
    document.documentElement.classList.add(DRAG_CLASS);
    setDragging(true);
  };

  const onPointerMove = (e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    const perPx = ((max - min) / DRAG_RANGE_PX) * (e.shiftKey ? FINE_FACTOR : 1);
    const raw = clamp(drag.raw + (drag.lastY - e.clientY) * perPx, min, max);
    const next = snap(raw, min, max, stepSize);
    dragRef.current = { ...drag, lastY: e.clientY, raw, emitted: next };
    if (next !== drag.emitted) onChange(next);
  };

  const endDrag = (e: ReactPointerEvent<HTMLDivElement>) => {
    const drag = dragRef.current;
    if (!drag || drag.pointerId !== e.pointerId) return;
    dragRef.current = null;
    if (e.currentTarget.hasPointerCapture(e.pointerId)) e.currentTarget.releasePointerCapture(e.pointerId);
    document.documentElement.classList.remove(DRAG_CLASS);
    setDragging(false);
  };

  const onKeyDown = (e: ReactKeyboardEvent<HTMLDivElement>) => {
    switch (e.key) {
      case 'ArrowUp':
      case 'ArrowRight':
        nudge(1);
        break;
      case 'ArrowDown':
      case 'ArrowLeft':
        nudge(-1);
        break;
      case 'PageUp':
        nudge(10);
        break;
      case 'PageDown':
        nudge(-10);
        break;
      case 'Home':
        commit(min);
        break;
      case 'End':
        commit(max);
        break;
      default:
        return;
    }
    e.preventDefault();
  };

  const onDoubleClick = () => {
    if (defaultValue !== undefined) commit(defaultValue);
  };

  // Geometry in px: track ring, cap inside it, pointer line on the cap.
  const c = size / 2;
  const stroke = Math.max(2, Math.round(size * 0.18) / 2);
  const arcR = c - stroke / 2 - 0.5;
  const capR = arcR - stroke / 2 - 2.5;
  const t = max > min ? (current - min) / (max - min) : 0;
  const angle = START_DEG + SWEEP_DEG * t;
  const valueArc = t > 0 ? arcPath(c, arcR, START_DEG, angle) : null;
  const [px0, py0] = polar(c, capR * 0.3, angle);
  const [px1, py1] = polar(c, capR * 0.85, angle);

  return (
    <div
      ref={rootRef}
      role="slider"
      tabIndex={0}
      aria-label={label}
      aria-valuemin={min}
      aria-valuemax={max}
      aria-valuenow={value}
      aria-valuetext={shown}
      title={`${label}: drag up or down (Shift = fine), scroll or use the arrow keys${defaultValue !== undefined ? '; double-click resets' : ''}`}
      data-dragging={dragging ? '' : undefined}
      className="te-knob flex w-full min-w-0 flex-col items-center"
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endDrag}
      onPointerCancel={endDrag}
      onLostPointerCapture={endDrag}
      onKeyDown={onKeyDown}
      onDoubleClick={onDoubleClick}
    >
      <svg
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
        aria-hidden
        className="block shrink-0"
        style={{ overflow: 'visible' }}
      >
        <path
          d={arcPath(c, arcR, START_DEG, START_DEG + SWEEP_DEG)}
          fill="none"
          strokeWidth={stroke}
          strokeLinecap="round"
          style={{ stroke: 'var(--led-off)' }}
        />
        {valueArc && (
          <>
            <path
              d={valueArc}
              fill="none"
              strokeWidth={stroke + 1.5}
              strokeLinecap="round"
              style={{ stroke: 'var(--led-edge)' }}
            />
            <path
              d={valueArc}
              fill="none"
              strokeWidth={stroke}
              strokeLinecap="round"
              style={{ stroke: 'var(--led-on)' }}
            />
          </>
        )}
        <circle cx={c} cy={c + 1.25} r={capR} style={{ fill: 'var(--key-edge)' }} />
        <circle className="te-knob-cap" cx={c} cy={c} r={capR - 0.5} strokeWidth={1} />
        <line
          x1={px0}
          y1={py0}
          x2={px1}
          y2={py1}
          strokeWidth={Math.max(1.5, size * 0.05)}
          strokeLinecap="round"
          style={{ stroke: 'var(--key-text)' }}
        />
      </svg>
      <span
        className="block w-full truncate text-center uppercase"
        style={{
          marginTop: 2,
          fontSize: 9,
          lineHeight: `${TEXT_LINE}px`,
          letterSpacing: '0.06em',
          color: 'var(--key-text-dim)',
        }}
      >
        {label}
      </span>
      <span
        className="block w-full truncate text-center"
        style={{
          fontSize: 9,
          lineHeight: `${TEXT_LINE}px`,
          color: dragging ? 'var(--key-text-active)' : 'var(--key-text)',
        }}
      >
        {shown}
      </span>
    </div>
  );
}
