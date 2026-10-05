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

async function get<T>(path: string, params: Record<string, string | number | undefined> = {}): Promise<T> {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) if (v !== undefined && v !== "") qs.set(k, String(v));
  const url = `${API_URL}${path}${qs.size ? `?${qs}` : ""}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new ApiError(res.status, `API ${res.status} on ${path}`);
  return res.json();
}

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

export type TopicNode = {
  section: Section;
  topic: string;
  slug: string;
  count: number;
  per_shift: number;
  subtopics: {
    name: string;
    count: number;
    per_shift: number;
    question_types: { name: string; count: number }[];
  }[];
};

export type FormulaRef = { id: string; name: string; topic_slug: string };

export type IndexRow = {
  id: number;
  paper_id: string;
  section: Section;
  q_no: number;
  stem_text: string;
  topic: string;
  subtopic: string;
  question_type: string;
  difficulty: number;
  expected_time_sec: number;
  has_visual: boolean;
  key_status: string;
  duplicate_of: number | null;
  formulas: FormulaRef[];
  crop_url: string | null;
};

export type IndexFilters = {
  section?: string;
  topic?: string;
  subtopic?: string;
  question_type?: string;
  difficulty?: string;
  formula?: string;
  status?: string;
  q?: string;
  offset?: string;
};

export type Formula = FormulaRef & {
  section: Section;
  topic: string;
  subtopic: string;
  statement: string;
  shortcut: string | null;
  verification_status: string;
  question_count: number;
};

export type LibraryEntry = {
  conditions: string[];
  derivation: string[];
  common_traps: string[];
  related_ids: string[];
  worked_example: { question_key: string; answer: string; steps: string[] } | null;
  diagram: { alt_text: string } | null;
};

export type StudyQuestion = {
  id: number;
  paper_id: string;
  section: Section;
  q_no: number;
  stem_text: string;
  stem_text_complete: boolean;
  stem_image_url: string | null;
  options: { label: string; text: string; image_url: string | null }[];
  answer: string;
  key_status: string;
  crop_url: string | null;
  tag: {
    topic: string;
    subtopic: string;
    question_type: string;
    shortcut_used: string;
    difficulty: number;
    expected_time_sec: number;
    duplicate_of_id: number | null;
  } | null;
  formulas: FormulaRef[];
  working: string[];
};

export const getTree = (section?: string) => get<TopicNode[]>("/index/tree", { section });
export const getIndex = (f: IndexFilters) => get<{ total: number; rows: IndexRow[] }>("/index/questions", f);
export const getFormulas = (topic_slug?: string) => get<Formula[]>("/formulas", { topic_slug });
export const getFormula = (id: string) =>
  get<Formula & { entry: LibraryEntry; question_ids: number[] }>(`/formulas/${encodeURIComponent(id)}`);
export const getStudyQuestion = (id: string) => get<StudyQuestion>(`/study/questions/${id}`);
