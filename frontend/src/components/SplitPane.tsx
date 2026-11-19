import { useEffect, useRef, useState, type CSSProperties, type ReactNode } from 'react';

const STORAGE_KEY = 'llm-studio.split';

function readRatio(fallback: number) {
  try {
    const v = Number(localStorage.getItem(STORAGE_KEY));
    return v > 0.15 && v < 0.85 ? v : fallback;
  } catch {
    return fallback;
  }
}

/** Dos paneles lado a lado con un divisor arrastrable (doble clic = restablecer). */
export function SplitPane({ left, right, initial = 0.36 }: { left: ReactNode; right: ReactNode; initial?: number }) {
  const [ratio, setRatio] = useState(() => readRatio(initial));
  const [dragging, setDragging] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(ratio));
    } catch {
      /* almacenamiento no disponible */
    }
  }, [ratio]);

  useEffect(() => {
    if (!dragging) return;
    const move = (e: PointerEvent) => {
      const box = ref.current?.getBoundingClientRect();
      if (!box) return;
      setRatio(Math.min(0.7, Math.max(0.22, (e.clientX - box.left) / box.width)));
    };
    const up = () => setDragging(false);
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
    return () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
  }, [dragging]);

  return (
    <div className={`split ${dragging ? 'dragging' : ''}`} ref={ref} style={{ '--split': `${ratio * 100}%` } as CSSProperties}>
      <div className="split-left">{left}</div>
      <div
        className="split-divider"
        role="separator"
        aria-orientation="vertical"
        aria-valuenow={Math.round(ratio * 100)}
        tabIndex={0}
        onPointerDown={(e) => {
          e.preventDefault();
          setDragging(true);
        }}
        onDoubleClick={() => setRatio(initial)}
        onKeyDown={(e) => {
          if (e.key === 'ArrowLeft') setRatio((r) => Math.max(0.22, r - 0.02));
          if (e.key === 'ArrowRight') setRatio((r) => Math.min(0.7, r + 0.02));
        }}
      />
      <div className="split-right">{right}</div>
    </div>
  );
}
