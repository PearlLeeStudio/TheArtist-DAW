import type { CSSProperties, ReactNode } from 'react';

interface ScreenProps {
  /** The screen's lines. Highlight text with style={{ color: 'var(--led-on)' }}. */
  children: ReactNode;
  /** Tiny header line, e.g. 'HARMONY'. */
  label?: string;
  className?: string;
  style?: CSSProperties;
}

/**
 * LCD-style screen, dark glass in both themes: 11px device type on 14px
 * lines, no wrapping. Natural height = 12px padding + 14px header (with a
 * label) + 14px per line; give it a fixed height from the pane's budget —
 * what does not fit is clipped, never scrolled.
 */
export default function Screen({ children, label, className, style }: ScreenProps) {
  return (
    <div
      role={label ? 'group' : undefined}
      aria-label={label}
      className={`te-screen min-w-0 overflow-hidden whitespace-nowrap${className ? ` ${className}` : ''}`}
      style={{ flexShrink: 0, padding: '6px 8px', fontSize: 11, lineHeight: '14px', ...style }}
    >
      {label && (
        <div
          aria-hidden
          className="flex items-center uppercase"
          style={{
            height: 12,
            marginBottom: 2,
            gap: 6,
            fontSize: 9,
            lineHeight: '12px',
            letterSpacing: '0.1em',
            color: 'var(--screen-text-dim)',
          }}
        >
          <span className="shrink-0">{label}</span>
          <span className="flex-1" style={{ height: 1, background: 'currentColor', opacity: 0.3 }} />
        </div>
      )}
      {children}
    </div>
  );
}
