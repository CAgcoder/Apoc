import { useMemo, useState } from "react";
import { renderMermaidSVG } from "beautiful-mermaid";
import { MermaidLightbox } from "./MermaidLightbox";

const THEME = {
  bg: "#0d1117",
  fg: "#c9d1d9",
  accent: "#4493f8",
  muted: "#8b949e",
  line: "#30363d",
  border: "#30363d",
  transparent: true,
} as const;

export function Mermaid({ code }: { code: string }) {
  const [open, setOpen] = useState(false);
  const rendered = useMemo(() => {
    try {
      return { svg: renderMermaidSVG(code, THEME), error: "" };
    } catch (error) {
      return { svg: "", error: error instanceof Error ? error.message : String(error) };
    }
  }, [code]);

  if (rendered.error || !rendered.svg) {
    return (
      <div className="my-3 rounded-lg border border-amber-500/30 bg-amber-500/[0.06] p-3">
        <div className="mb-1 text-xs text-amber-300/80">diagram failed to render</div>
        <pre className="overflow-x-auto whitespace-pre-wrap text-xs text-white/60">{code}</pre>
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        className="my-3 block w-full cursor-zoom-in rounded-lg border border-white/10 bg-white/[0.02] p-3 text-left [&_svg]:mx-auto [&_svg]:h-auto [&_svg]:max-w-full"
        title="Click to enlarge"
        onClick={() => setOpen(true)}
        dangerouslySetInnerHTML={{ __html: rendered.svg }}
      />
      {open && <MermaidLightbox svg={rendered.svg} onClose={() => setOpen(false)} />}
    </>
  );
}
