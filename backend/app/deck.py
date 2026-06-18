"""Editable single-file HTML deck assembler.

Aligned with the vendored ``frontend-slides-editable`` skill
(``apoc/skills/frontend-slides-editable``): each slide is a ``.slide`` that fills
the frame with ``overflow:hidden`` and ``clamp()``-based sizing from the skill's
canonical ``viewport-base.css`` — so content can never cram or overlap (the model
is instructed to split overflowing content into more slides instead).

The generator emits ``{theme_css, slides[]}`` (content only); this module wraps
them with the viewport base, a presenter runtime (one slide at a time, keyboard
nav), and an **edit mode** gated to the architect (contenteditable + save back +
clean export).
"""

from __future__ import annotations

import re
from pathlib import Path

# Inject `active` into the first slide's class list, whatever extra tokens it
# carries (the model may emit `class="slide title"`). Replaces a fragile literal
# string match that silently failed — and left a blank frame — on such slides.
_FIRST_SLIDE_CLASS_RE = re.compile(
    r"""(<section\b[^>]*\bclass\s*=\s*["'])([^"']*\bslide\b[^"']*)(["'])""",
    re.IGNORECASE,
)


def _activate_first_slide(deck_html: str) -> str:
    def repl(m: "re.Match[str]") -> str:
        classes = m.group(2)
        if re.search(r"\bactive\b", classes):
            return m.group(0)
        return f"{m.group(1)}{classes} active{m.group(3)}"

    return _FIRST_SLIDE_CLASS_RE.sub(repl, deck_html, count=1)

_SKILL_VIEWPORT = (
    Path(__file__).resolve().parents[2] / "skills" / "frontend-slides-editable" / "viewport-base.css"
)


def _viewport_base_css() -> str:
    try:
        return _SKILL_VIEWPORT.read_text(encoding="utf-8")
    except OSError:
        # Minimal fallback if the vendored skill file is missing.
        return (
            ":root{--title-size:clamp(1.5rem,5vw,4rem);--h2-size:clamp(1.25rem,3.5vw,2.5rem);"
            "--h3-size:clamp(1rem,2.5vw,1.75rem);--body-size:clamp(.8rem,1.6vw,1.15rem);"
            "--slide-padding:clamp(1rem,4vw,4rem);--content-gap:clamp(.5rem,2vw,2rem);}"
            ".slide{width:100vw;height:100vh;overflow:hidden;display:flex;flex-direction:column;position:relative;}"
            ".slide-content{flex:1;display:flex;flex-direction:column;justify-content:center;max-height:100%;"
            "overflow:hidden;padding:var(--slide-padding);}"
        )


# Presenter overrides — layered AFTER viewport-base so single-slide nav and the
# stage geometry win (with !important) over the skill's scroll-deck defaults.
PRESENTER_CSS = """
:root { --apoc-bar-h: 48px; }
* { box-sizing: border-box; }
html, body { margin: 0; height: 100%; overflow: hidden; scroll-snap-type: none;
  background: #07080c; color: #e9e9ef;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }
#apoc-stage { position: absolute; inset: 0 0 var(--apoc-bar-h) 0; overflow: hidden; background: #07080c; }
.slide { position: absolute !important; inset: 0 !important; width: 100% !important; height: 100% !important;
  display: none !important; animation: apoc-in .45s ease both; }
.slide.active { display: flex !important; }
/* Safety net: if nothing is marked active (e.g. the runtime failed to load),
   still show the first slide instead of a blank black frame. */
#apoc-stage:not(:has(.slide.active)) > .slide:first-child { display: flex !important; }
/* DELIBERATE DEVIATION from frontend-slides-editable's NON-NEGOTIABLE
   "no scrolling within slides, ever" rule. The deck uses runtime-growing
   <details> drill-downs, which can push content past a fixed frame; rather than
   clip the revealed text out of reach, we let .slide-content scroll and fall
   back to top-alignment on overflow (`safe`). Chosen knowingly over the skill's
   "split into more slides" approach. */
.slide-content { overflow-y: auto !important; overflow-x: hidden !important;
  justify-content: safe center !important;
  /* Give the content a DEFINITE cross-axis size. Themes routinely center it with
     `.slide-content{margin:0 auto;max-width:Npx}`, but in the flex-column `.slide`
     those `auto` side margins suppress the default stretch, collapsing the content
     to its shrink-to-fit width. The grid inside then sees a too-narrow track and
     `auto-fit minmax()` drops to a single column — cards stack and overflow.
     width:100% restores a real width (still capped by the theme's max-width, still
     centred by the auto margins). */
  width: 100% !important; }
@keyframes apoc-in { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .slide { animation: none; } }
/* CSS-only click-to-reveal used by generated slides for interactivity */
.slide details { margin: .3em 0; }
.slide details > summary { cursor: pointer; list-style: none; }
.slide details > summary::-webkit-details-marker { display: none; }
.slide details.card,
.slide .diagram-box details { cursor: pointer; }
.slide .diagram-box details > summary,
.slide details.card > summary {
  display: flex; flex-direction: column; align-items: center; justify-content: center;
  width: 100%; gap: .15em;
}
/* CLOSED: the summary fills the box so its label sits vertically centred and
   every closed card in a row is the same height. */
.slide .diagram-box details:not([open]) > summary,
.slide details.card:not([open]) > summary { min-height: 100%; }
/* OPEN: the summary must collapse to its label height — otherwise `min-height:100%`
   makes it claim the whole <details> box and the revealed paragraph is pushed
   *outside* the box border (the "text escapes the ticket / overlaps neighbours"
   bug). Top-align the label so the detail flows directly beneath it, inside. */
.slide .diagram-box details[open] > summary,
.slide details.card[open] > summary { min-height: 0; justify-content: flex-start; }
body.apoc-editing .slide details,
body.apoc-editing .slide details > summary { cursor: text; }
body.apoc-editing .slide [contenteditable="true"] {
  outline: 1px dashed rgba(79, 124, 255, .55); outline-offset: 3px; border-radius: 4px;
}
.slide .diagram {
  display: flex !important; flex-direction: column !important; align-items: center !important;
  justify-content: center !important; gap: clamp(.55rem, 1.1vw, .9rem) !important;
}
.slide .diagram-row {
  display: flex !important; align-items: stretch !important; justify-content: center !important;
  flex-wrap: nowrap !important; gap: clamp(.55rem, 1vw, .85rem) !important;
}
.slide .diagram > .connector {
  display: flex !important; align-items: center !important; justify-content: center !important;
  min-height: 1.65rem !important; width: 100% !important; padding: 0 !important; line-height: 1 !important;
}
.slide .diagram-row > .connector {
  display: flex !important; align-items: center !important; justify-content: center !important;
  width: 2.25rem !important; min-width: 2.25rem !important; padding: 0 !important; line-height: 1 !important;
}
.slide .diagram-box {
  display: flex !important; align-items: stretch !important; justify-content: center !important;
  min-width: clamp(8rem, 14vw, 16rem) !important; min-height: 4.25rem !important;
  /* Pin the box to the clamp width so opening a <details> only grows it
     vertically — without a max-width the revealed paragraph balloons the box
     sideways, and `flex-wrap: nowrap` then shoves the rightmost box off-slide
     (the horizontal twin of the row-height bug fixed below). */
  max-width: clamp(8rem, 14vw, 16rem) !important;
}
.slide .diagram-box details { width: 100%; }
/* Flex children default to `min-width: auto`, which refuses to shrink below
   their content; force wrapping so revealed text reflows inside the pinned box. */
.slide .diagram-box details,
.slide .diagram-box details > summary > * { min-width: 0; overflow-wrap: anywhere; }
/* Tile heights — equalise when CLOSED, grow-one when OPEN.
   Default: let rows/grids stretch their cells (align-items:stretch) so every
   CLOSED tile in a line shares the tallest's height — fixes the "tickets are
   different sizes" raggedness when labels wrap to different line counts.
   When a drill-down <details> opens, flip ONLY that container to top-alignment
   so the opened card grows on its own and its row-mates keep their height
   instead of ballooning to match (the "other tags in the row expand too" bug).
   Applies to all decks regardless of the generated theme CSS. */
.slide .grid:has(details[open]) > *,
.slide .diagram-row:has(details[open]) > * { align-self: start !important; }
.slide .diagram-row:has(details[open]) { align-items: start !important; }
#apoc-bar { position: absolute; left: 0; right: 0; bottom: 0; height: var(--apoc-bar-h);
  display: flex; align-items: center; gap: 10px; padding: 0 14px;
  background: #11131a; border-top: 1px solid #262a36; z-index: 50; }
#apoc-bar button { background: #21252f; color: #e9e9ef; border: 1px solid #333949; border-radius: 8px;
  padding: 6px 12px; font-size: 13px; cursor: pointer; }
#apoc-bar button:hover { background: #2b303c; }
#apoc-bar button.primary { background: #4f7cff; border-color: #4f7cff; color: #fff; }
#apoc-counter { font-size: 13px; color: #9aa0b0; min-width: 64px; text-align: center; }
#apoc-dots { display: flex; gap: 6px; }
#apoc-dots i { width: 7px; height: 7px; border-radius: 50%; background: #333949; cursor: pointer; }
#apoc-dots i.on { background: #4f7cff; }
#apoc-spacer { flex: 1; }
#apoc-status { font-size: 12px; color: #7de29a; }
body.apoc-editing .slide.active { outline: 2px dashed #4f7cff; outline-offset: -4px; }
"""

RUNTIME_JS = """
const API_BASE = "__API_BASE__", POC_ID = "__POC_ID__", EDITABLE = __EDITABLE__;
const stage = document.getElementById('apoc-stage');
const slides = Array.from(stage.querySelectorAll('.slide'));
const dotsBox = document.getElementById('apoc-dots');
let idx = 0, editing = false;
const EDITABLE_TEXT_SELECTOR = 'h1,h2,h3,h4,p,li,td,th,figcaption,summary,.attribution';

slides.forEach((_, i) => {
  const d = document.createElement('i');
  d.onclick = () => show(i);
  dotsBox.appendChild(d);
});

function show(i) {
  if (!slides.length) return;
  idx = Math.max(0, Math.min(i, slides.length - 1));
  slides.forEach((s, n) => s.classList.toggle('active', n === idx));
  Array.from(dotsBox.children).forEach((d, n) => d.classList.toggle('on', n === idx));
  document.getElementById('apoc-counter').textContent = (idx + 1) + ' / ' + slides.length;
}
function setStatus(t) { document.getElementById('apoc-status').textContent = t || ''; }

document.addEventListener('keydown', (e) => {
  if (editing || /^(INPUT|TEXTAREA)$/.test(document.activeElement.tagName)) return;
  if (e.key === 'ArrowRight' || e.key === 'PageDown' || e.key === ' ') { e.preventDefault(); show(idx + 1); }
  if (e.key === 'ArrowLeft' || e.key === 'PageUp') { e.preventDefault(); show(idx - 1); }
});

stage.addEventListener('click', (e) => {
  const target = e.target;
  if (!(target instanceof Element)) return;
  const summary = target.closest('summary');
  if (editing && summary) {
    e.preventDefault();
    e.stopPropagation();
    summary.focus();
    return;
  }
  if (editing) return;
  if (target.closest('a,button,input,textarea,select')) return;
  const details = target.closest('.slide details');
  if (!details || summary) return;
  e.preventDefault();
  details.open = !details.open;
});

function setEditing(on) {
  editing = on;
  document.body.classList.toggle('apoc-editing', on);
  slides.forEach((s) => {
    const t = s.querySelector('.slide-content') || s;
    t.setAttribute('contenteditable', 'false');
    s.querySelectorAll(EDITABLE_TEXT_SELECTOR).forEach((el) => {
      el.setAttribute('contenteditable', on ? 'true' : 'false');
    });
  });
  document.getElementById('apoc-edit').textContent = on ? 'Editing…' : 'Edit';
  document.getElementById('apoc-save').style.display = on ? '' : 'none';
}

// Serialize a slide without transient runtime state (active class, contenteditable
// flags, toggled <details open>) so saved HTML re-renders cleanly on reload.
function cleanSlideHtml(s) {
  const c = s.cloneNode(true);
  c.classList.remove('active');
  if (c.hasAttribute('contenteditable')) c.removeAttribute('contenteditable');
  c.querySelectorAll('[contenteditable]').forEach((el) => el.removeAttribute('contenteditable'));
  c.querySelectorAll('details[open]').forEach((d) => d.removeAttribute('open'));
  return c.outerHTML;
}

async function save() {
  setStatus('Saving…');
  const html = slides.map((s) => cleanSlideHtml(s)).join('\\n');
  try {
    const r = await fetch(API_BASE + '/api/pocs/' + POC_ID + '/deck', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'X-Apoc-Role': 'architect' },
      body: JSON.stringify({ deck_html: html }),
    });
    if (!r.ok) throw new Error(await r.text());
    setStatus('Saved'); setTimeout(() => setStatus(''), 1500);
  } catch (err) { setStatus('Save failed'); console.error(err); }
}

function exportHtml() {
  const clone = document.documentElement.cloneNode(true);
  clone.querySelector('#apoc-bar')?.remove();
  clone.querySelector('#apoc-runtime')?.remove();
  clone.querySelectorAll('.slide').forEach((s, n) => {
    (s.querySelector('.slide-content') || s).setAttribute('contenteditable', 'false');
    s.classList.toggle('active', n === 0);
  });
  const blob = new Blob(['<!doctype html>\\n' + clone.outerHTML], { type: 'text/html' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob); a.download = 'apoc-poc.html'; a.click();
}

document.getElementById('apoc-prev').onclick = () => show(idx - 1);
document.getElementById('apoc-next').onclick = () => show(idx + 1);
document.getElementById('apoc-export').onclick = exportHtml;
if (EDITABLE) {
  document.getElementById('apoc-edit').onclick = () => setEditing(!editing);
  document.getElementById('apoc-save').onclick = save;
} else {
  document.getElementById('apoc-edit').remove();
  document.getElementById('apoc-save').remove();
}
show(0);
"""


def _controls() -> str:
    return (
        '<div id="apoc-bar">'
        '<button id="apoc-prev">‹</button>'
        '<button id="apoc-next">›</button>'
        '<span id="apoc-counter">1 / 1</span>'
        '<div id="apoc-dots"></div>'
        '<span id="apoc-spacer"></span>'
        '<span id="apoc-status"></span>'
        '<button id="apoc-edit">Edit</button>'
        '<button id="apoc-save" class="primary" style="display:none">Save</button>'
        '<button id="apoc-export">Export</button>'
        "</div>"
    )


def assemble_deck(*, deck_html: str, deck_css: str, poc_id: str, api_base: str, editable: bool) -> str:
    runtime = (
        RUNTIME_JS.replace("__API_BASE__", api_base)
        .replace("__POC_ID__", poc_id)
        .replace("__EDITABLE__", "true" if editable else "false")
    )
    # Pre-activate the first slide so the deck renders even before the runtime
    # JS executes (defends against any script hiccup leaving a blank frame).
    deck_html = _activate_first_slide(deck_html)
    return (
        '<!doctype html>\n<html lang="en"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1">'
        f"<style>{_viewport_base_css()}</style>"
        f"<style>{PRESENTER_CSS}</style>"
        f"<style>{deck_css}</style></head><body>"
        f'<div id="apoc-stage">{deck_html}</div>'
        f"{_controls()}"
        f'<script id="apoc-runtime">{runtime}</script>'
        "</body></html>"
    )
