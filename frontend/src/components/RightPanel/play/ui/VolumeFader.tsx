import type { KeyboardEvent } from 'react';
import './VolumeFader.css';

interface VolumeFaderProps {
  label: string;
  value: number;
  defaultValue: number;
  onChange: (value: number) => void;
}

const bounded = (value: number): number => Math.min(100, Math.max(0, Math.round(value)));

/** Native vertical range behavior with a quiet, recessed hardware face. */
export default function VolumeFader({ label, value, defaultValue, onChange }: VolumeFaderProps) {
  const current = bounded(value);

  const handleKeyDown = (event: KeyboardEvent<HTMLInputElement>) => {
    let next: number;
    if (event.key === 'ArrowUp') next = current + 1;
    else if (event.key === 'ArrowDown') next = current - 1;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = 100;
    else return;
    event.preventDefault();
    onChange(bounded(next));
  };

  return (
    <label className="te-volume-fader">
      <span className="te-volume-fader-travel">
        <input
          type="range"
          className="te-volume-fader-input"
          min={0}
          max={100}
          step={1}
          value={current}
          aria-label={`${label} volume`}
          aria-orientation="vertical"
          aria-valuenow={current}
          onChange={(event) => onChange(bounded(Number(event.currentTarget.value)))}
          onKeyDown={handleKeyDown}
          onDoubleClick={() => onChange(bounded(defaultValue))}
        />
        <span className="te-volume-fader-groove" aria-hidden="true" />
        <span
          className="te-volume-fader-thumb"
          aria-hidden="true"
          style={{ bottom: `${current}%`, transform: `translateY(${current}%)` }}
        />
      </span>
      <span className="te-volume-fader-label">{label}</span>
    </label>
  );
}
