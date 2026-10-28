import { useId } from 'react';
import './ToggleSwitch.css';

interface ToggleSwitchProps {
  label: string;
  checked: boolean;
  onSelect: () => void;
  title?: string;
  ariaLabel?: string;
  kind?: 'radio' | 'switch';
}

/** One latched choice: a brushed circular mount and a metal lever. The
 *  selected radio points up; choosing it never turns the radio group off. */
export default function ToggleSwitch({ label, checked, onSelect, title, ariaLabel, kind = 'radio' }: ToggleSwitchProps) {
  const id = `toggle-${useId().replaceAll(':', '')}`;
  return (
    <button type="button" role={kind} aria-checked={checked} aria-label={ariaLabel ?? label}
      tabIndex={kind === 'switch' || checked ? 0 : -1} onClick={onSelect} title={title} className="te-toggle">
      <svg className="te-toggle__mechanism" width="34" height="28" viewBox="0 0 44 36" aria-hidden="true" focusable="false">
        <defs>
          <linearGradient id={`${id}-mount`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0" stopColor="#f0eee5" />
            <stop offset=".25" stopColor="#b8b9af" />
            <stop offset=".5" stopColor="#d2cbb5" />
            <stop offset=".74" stopColor="#91948c" />
            <stop offset="1" stopColor="#e1e2d9" />
          </linearGradient>
          <linearGradient id={`${id}-seat`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#61645e" />
            <stop offset=".5" stopColor="#96978c" />
            <stop offset="1" stopColor="#dad9cd" />
          </linearGradient>
          <linearGradient id={`${id}-shaft`} x1="0" y1="0" x2="1" y2="0">
            <stop offset="0" stopColor="#747a79" />
            <stop offset=".2" stopColor="#d5dddc" />
            <stop offset=".43" stopColor="#fafdfb" />
            <stop offset=".68" stopColor="#b9c1bf" />
            <stop offset="1" stopColor="#626b69" />
          </linearGradient>
          <linearGradient id={`${id}-tip`} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#f8fbf8" />
            <stop offset="1" stopColor="#959e99" />
          </linearGradient>
        </defs>
        <g className="te-toggle__mount">
          <ellipse cx="22" cy="26.8" rx="10.6" ry="2.8" fill="#30352f" opacity=".17" />
          <circle cx="22" cy="18" r="10.6" fill={`url(#${id}-mount)`} stroke="#74766c" strokeWidth=".7" />
          <circle cx="22" cy="18" r="8.9" fill="none" stroke="#f5f3e8" strokeWidth=".6" opacity=".8" />
          <circle cx="22" cy="18" r="7.3" fill={`url(#${id}-seat)`} stroke="#737369" strokeWidth=".65" />
          <path d="M13.6 15.3a8.8 8.8 0 0 1 13.8-4.1" fill="none" stroke="#fffef5" strokeWidth=".65" opacity=".65" />
          <path d="M16.5 24.7a8.8 8.8 0 0 0 13-7" fill="none" stroke="#5b6058" strokeWidth=".65" opacity=".5" />
        </g>
        <g className="te-toggle__lever">
          <ellipse cx="23.6" cy="10.5" rx="3.2" ry="8" fill="#30372f" opacity=".12" />
          <rect x="19" y="3.5" width="6" height="15.8" rx="2.8" fill={`url(#${id}-shaft)`} stroke="#707974" strokeWidth=".55" />
          <path d="M20.3 5.7v10.2" fill="none" stroke="#ffffff" strokeWidth=".7" opacity=".65" />
          <ellipse cx="22" cy="3.9" rx="2.85" ry="1.55" fill={`url(#${id}-tip)`} stroke="#8e9891" strokeWidth=".5" />
        </g>
        <circle cx="22" cy="18" r="3.7" fill={`url(#${id}-seat)`} stroke="#666c63" strokeWidth=".55" />
        <path d="M19.2 17.2a3 3 0 0 1 4-2" fill="none" stroke="#f2f4eb" strokeWidth=".7" opacity=".65" />
      </svg>
      <span className="te-toggle__label">{label}</span>
    </button>
  );
}
