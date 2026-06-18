type Status = "open" | "accepted" | "closed";

const BADGE: Record<Status, string> = {
  open: "bg-white/10 text-white/60",
  accepted: "bg-emerald-500/15 text-emerald-300",
  closed: "bg-white/5 text-white/40",
};

// Per-status architect actions: label -> next status.
const ACTIONS: Record<Status, [string, Status][]> = {
  open: [["Accept", "accepted"], ["Close", "closed"]],
  accepted: [["Unaccept", "open"], ["Close", "closed"]],
  closed: [["Reopen", "open"]],
};

export function CommentStatus({
  status,
  canCurate,
  onChange,
}: {
  status: Status;
  canCurate: boolean;
  onChange: (next: Status) => void;
}) {
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`rounded-full px-2 py-0.5 text-[11px] ${BADGE[status]}`}>{status}</span>
      {canCurate &&
        ACTIONS[status].map(([label, next]) => (
          <button
            key={label}
            type="button"
            onClick={() => onChange(next)}
            className="rounded border border-white/15 px-1.5 py-0.5 text-[11px] text-white/70 hover:bg-white/5 hover:text-white"
          >
            {label}
          </button>
        ))}
    </span>
  );
}
