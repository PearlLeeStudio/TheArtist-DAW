import { useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';

interface Props {
  x: number;
  y: number;
  onChoose: (tool: 'generate' | 'reharmonize') => void;
  onClose: () => void;
}

/** Navigation only: opening a tool never starts a model call or changes chords. */
export default function ScoreContextMenu({ x, y, onChoose, onClose }: Props) {
  const menu = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const element = menu.current;
    const buttons = [...element?.querySelectorAll<HTMLButtonElement>('button') ?? []];
    buttons[0]?.focus();
    const dismissOutside = (event: PointerEvent) => {
      if (!element?.contains(event.target as Node)) onClose();
    };
    const keyboard = (event: KeyboardEvent) => {
      if (event.key === 'Escape' || event.key === 'Tab') {
        if (event.key === 'Escape') event.preventDefault();
        onClose();
      } else if (['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) {
        event.preventDefault();
        const current = buttons.indexOf(document.activeElement as HTMLButtonElement);
        const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1
          : (current + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length;
        buttons[next]?.focus();
      }
    };
    window.addEventListener('pointerdown', dismissOutside);
    window.addEventListener('keydown', keyboard);
    window.addEventListener('scroll', onClose, true);
    window.addEventListener('resize', onClose);
    return () => {
      window.removeEventListener('pointerdown', dismissOutside);
      window.removeEventListener('keydown', keyboard);
      window.removeEventListener('scroll', onClose, true);
      window.removeEventListener('resize', onClose);
    };
  }, [onClose]);

  return createPortal(<div ref={menu} role="menu" aria-label="Selected passage" className="fixed p-1 rounded-md shadow-xl"
    onContextMenu={event => event.preventDefault()}
    style={{ left: Math.max(8, Math.min(x, window.innerWidth - 188)),
      top: Math.max(8, Math.min(y, window.innerHeight - 100)), width: 180, maxWidth: 'calc(100vw - 16px)',
      zIndex: 100, background: 'var(--bg-surface)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}>
    {(['generate', 'reharmonize'] as const).map(tool => <button key={tool} role="menuitem"
      onClick={() => onChoose(tool)} className="block w-full text-left px-3 py-2 text-sm rounded btn-hover focus-visible:outline-2"
      style={{ outlineColor: 'var(--brand-yellow)' }}>
      {tool === 'generate' ? 'Generate' : 'Reharmonize'}
    </button>)}
  </div>, document.body);
}
