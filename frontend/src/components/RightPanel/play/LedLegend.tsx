import Led from './ui/Led';

/** A pane grid's spare cell: what the two LED colours mean. 26px tall, like an sm key. */
export default function LedLegend() {
  return (
    <div
      aria-hidden
      className="flex flex-col justify-center gap-[2px] px-[4px] uppercase"
      style={{
        height: 26,
        fontFamily: 'var(--font-device)',
        fontSize: 8,
        lineHeight: '10px',
        letterSpacing: '0.06em',
        color: 'var(--key-text)',
      }}
    >
      <span className="flex items-center gap-[4px]">
        <Led state="on" size={5} />
        <span style={{ opacity: 0.6 }}>on</span>
      </span>
      <span className="flex items-center gap-[4px]">
        <Led state="alt" size={5} />
        <span style={{ opacity: 0.6 }}>auto</span>
      </span>
    </div>
  );
}
