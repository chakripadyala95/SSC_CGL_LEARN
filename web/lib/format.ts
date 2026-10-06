export function shiftLabel(paperId: string) {
  const [date, slot] = paperId.split("_");
  return `${date} · ${slot.slice(0, 2)}:${slot.slice(2)}`;
}

export function questionLabel(row: { paper_id: string; section: string; q_no: number }) {
  return `${shiftLabel(row.paper_id)} · ${row.section === "QUANT" ? "Quant" : "Reasoning"} Q${row.q_no}`;
}

const STATUS: Record<string, string> = {
  KEY_CONFIRMED_CODE: "Verified (code check)",
  KEY_CONFIRMED_DUAL: "Verified (two solvers)",
  KEY_CONFIRMED_REVIEW: "Verified (human review)",
  KEY_DISPUTED: "Disputed",
  EXTRACTION_REVIEW: "In review",
  UNVERIFIED: "Unverified",
  REJECTED: "Rejected",
};

export const statusLabel = (s: string) => STATUS[s] ?? s;
export const isVerified = (s: string) => s.startsWith("KEY_CONFIRMED");

export function formulaHref(f: { id: string; topic_slug: string }) {
  return `/formulas/${f.topic_slug}#${f.id.split(".")[1]}`;
}
