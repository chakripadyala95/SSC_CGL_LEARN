// Server-side calls to the FastAPI backend (api/main.py).
const API_URL = process.env.API_URL ?? "http://localhost:8000";

export type Section = "QUANT" | "REASONING";

export type Mock = {
  id: string;
  paper_id: string;
  section: Section;
  timer_sec: number;
  status: "DRAFT" | "PUBLISHED";
};

export async function getMocks(): Promise<Mock[]> {
  const res = await fetch(`${API_URL}/mocks`, { cache: "no-store" });
  if (!res.ok) throw new Error(`API ${res.status} on /mocks`);
  return res.json();
}
