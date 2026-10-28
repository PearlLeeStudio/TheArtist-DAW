import type { CSSProperties, ReactNode } from 'react';
import Led from './Led';

type KeySize = 'sm' | 'md' | 'lg';

interface KeyButtonProps {
  label?: string;
  /** Smaller, dimmer second line under the label. */
  sublabel?: string;
  /** An icon in place of the label (the label then becomes the accessible name). */
  children?: ReactNode;
  /** Latched / selected: pressed look, plus aria-pressed (aria-checked or
   *  aria-selected when `role` is a checkable or selectable role). */
  active?: boolean;
  /** LED dot in the top-right corner (default 'none'). Use 'off' rather than
   *  'none' on keys that sit in a group with lit ones. */
  led?: 'on' | 'off' | 'alt' | 'none';
  onClick?: () => void;
  title?: string;
  ariaLabel?: string;
  disabled?: boolean;
  /** Fixed heights: sm 26px, md 30px (default), lg 36px. */
  size?: KeySize;
  role?: string;
  ariaSelected?: boolean;
  /** For a tab in a roving-tabindex tablist: -1 takes it out of the tab order. */
  tabIndex?: number;
  id?: string;
  ariaControls?: string;
  className?: string;
  style?: CSSProperties;
}

/** Geometry per size (px): key height, label type and line, sublabel line, LED size and inset. */
const SIZES: Record<KeySize, { height: number; font: number; line: number; subLine: number; led: number; ledInset: number }> = {
  sm: { height: 26, font: 9, line: 10, subLine: 9, led: 5, ledInset: 2 },
  md: { height: 30, font: 10, line: 12, subLine: 9, led: 5, ledInset: 3 },
  lg: { height: 36, font: 10, line: 12, subLine: 11, led: 6, ledInset: 4 },
};
/** A lone label sits this much below centre on a key with an LED, so the
 *  corner LED clears the tops of its capitals on narrow keys. */
const LED_LABEL_DROP = 1;
const SUBLABEL_FONT = 8;
/** Side padding inside the 1px border. */
const PAD_X = 3;

const CHECKED_ROLES = new Set(['checkbox', 'radio', 'switch', 'menuitemcheckbox', 'menuitemradio']);
const SELECTED_ROLES = new Set(['tab', 'option', 'gridcell', 'row', 'treeitem']);

/**
 * Square device key: uppercase device type on one line (ellipsis), an
 * optional dim sublabel, an optional corner LED. Fills its grid cell's
 * width; its height is fixed by `size`.
 */
export default function KeyButton({
  label,
  sublabel,
  children,
  active,
  led = 'none',
  onClick,
  title,
  ariaLabel,
  disabled,
  size = 'md',
  role,
  ariaSelected,
  tabIndex,
  id,
  ariaControls,
  className,
  style,
}: KeyButtonProps) {
  const s = SIZES[size];
  // With a sublabel the label line sits level with the LED, so it keeps
  // clear of it — on both sides, to stay centred. Without one it drops a
  // little below the LED instead, keeping its full width.
  const labelInset = led !== 'none' && sublabel !== undefined ? s.led + s.ledInset + 1 - PAD_X : 0;
  const labelDrop = led !== 'none' && sublabel === undefined ? LED_LABEL_DROP : 0;
  const toggle = role === undefined || role === 'button';
  const checkable = role !== undefined && CHECKED_ROLES.has(role);
  const selectable = role !== undefined && SELECTED_ROLES.has(role);

  return (
    <button
      type="button"
      id={id}
      role={role}
      tabIndex={tabIndex}
      aria-controls={ariaControls}
      aria-pressed={toggle ? active : undefined}
      aria-checked={checkable ? Boolean(active) : undefined}
      aria-selected={ariaSelected ?? (selectable ? Boolean(active) : undefined)}
      aria-label={ariaLabel ?? (children !== undefined ? label : undefined)}
      title={title}
      disabled={disabled}
      onClick={onClick}
      data-active={active ? '' : undefined}
      className={`te-key btn-hover relative flex w-full min-w-0 flex-col items-center justify-center uppercase select-none${className ? ` ${className}` : ''}`}
      style={{ height: s.height, paddingInline: PAD_X, fontSize: s.font, ...style }}
    >
      {children ?? (label !== undefined && (
        <span
          className="relative block max-w-full truncate"
          style={{ lineHeight: `${s.line}px`, paddingInline: labelInset || undefined, top: labelDrop || undefined }}
        >
          {label}
        </span>
      ))}
      {sublabel !== undefined && (
        <span
          className="block max-w-full truncate"
          style={{ fontSize: SUBLABEL_FONT, lineHeight: `${s.subLine}px`, color: 'var(--key-text-dim)' }}
        >
          {sublabel}
        </span>
      )}
      {led !== 'none' && (
        <span className="absolute flex" style={{ top: s.ledInset, right: s.ledInset }}>
          <Led state={led} size={s.led} />
        </span>
      )}
    </button>
  );
}
