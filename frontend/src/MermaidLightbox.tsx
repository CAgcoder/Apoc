import { useEffect, useRef, useState } from "react";

export function MermaidLightbox({ svg, onClose }: { svg: string; onClose: () => void }) {
  const [scale, setScale] = useState(1);
  const [pos, setPos] = useState({ x: 0, y: 0 });
  const drag = useRef<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const zoom = (delta: number) => setScale((value) => Math.min(4, Math.max(0.45, value + delta)));

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/75 p-6"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Diagram preview"
    >
      <div
        className="relative h-[82dvh] w-[86vw] overflow-hidden rounded-lg border border-white/10 bg-[#0d1117]"
        onClick={(event) => event.stopPropagation()}
        onWheel={(event) => {
          event.preventDefault();
          zoom(event.deltaY > 0 ? -0.12 : 0.12);
        }}
        onMouseDown={(event) => {
          drag.current = { x: event.clientX - pos.x, y: event.clientY - pos.y };
        }}
        onMouseMove={(event) => {
          if (drag.current) setPos({ x: event.clientX - drag.current.x, y: event.clientY - drag.current.y });
        }}
        onMouseUp={() => {
          drag.current = null;
        }}
        onMouseLeave={() => {
          drag.current = null;
        }}
      >
        <div className="absolute right-3 top-3 z-10 flex items-center gap-1 rounded-md border border-white/10 bg-[#161b22] p-1">
          <button
            type="button"
            aria-label="Zoom out"
            onClick={() => zoom(-0.2)}
            className="size-7 rounded text-sm text-white/70 hover:bg-white/10 hover:text-white"
          >
            -
          </button>
          <button
            type="button"
            aria-label="Zoom in"
            onClick={() => zoom(0.2)}
            className="size-7 rounded text-sm text-white/70 hover:bg-white/10 hover:text-white"
          >
            +
          </button>
          <button
            type="button"
            onClick={onClose}
            className="rounded px-2 py-1 text-xs text-white/70 hover:bg-white/10 hover:text-white"
          >
            Close
          </button>
        </div>
        <div
          className="flex h-full w-full cursor-grab items-center justify-center active:cursor-grabbing [&_svg]:h-auto [&_svg]:w-auto [&_svg]:max-w-none"
          style={{ transform: `translate(${pos.x}px, ${pos.y}px) scale(${scale})` }}
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      </div>
    </div>
  );
}
