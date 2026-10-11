import Link from "next/link";
import { getFormulas, getIndex, getTree, type IndexFilters, type TopicNode } from "@/lib/api";
import { formulaHref, isVerified, questionLabel, statusLabel } from "@/lib/format";

export const dynamic = "force-dynamic";

const PAGE = 50;
const KEYS = ["section", "topic", "subtopic", "question_type", "difficulty", "formula", "status", "q"] as const;

function href(filters: IndexFilters, change: Partial<IndexFilters>) {
  const next = { ...filters, offset: undefined, ...change };
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(next)) if (v) qs.set(k, v);
  return `/questions${qs.size ? `?${qs}` : ""}`;
}

function Tree({ tree, filters }: { tree: TopicNode[]; filters: IndexFilters }) {
  return (
    <nav aria-label="Topics" className="text-sm">
      {(["QUANT", "REASONING"] as const).map((section) => (
        <div key={section} className="mb-4">
          <h2 className="mb-1 font-medium">{section === "QUANT" ? "Quant" : "Reasoning"}</h2>
          <p className="mb-2 text-xs text-zinc-500">Count · per shift</p>
          {tree
            .filter((t) => t.section === section)
            .map((t) => (
              <details key={t.topic} open={filters.topic === t.topic} className="mb-1">
                <summary className="cursor-pointer">
                  <Link href={href({}, { topic: t.topic })} className="hover:underline">
                    {t.topic}
                  </Link>{" "}
                  <span className="tabular-nums text-zinc-500">
                    {t.count} · {t.per_shift}
                  </span>
                </summary>
                <ul className="ml-4 mt-1 space-y-1">
                  {t.subtopics.map((s) => (
                    <li key={s.name}>
                      <Link href={href({}, { topic: t.topic, subtopic: s.name })} className="hover:underline">
                        {s.name}
                      </Link>{" "}
                      <span className="tabular-nums text-zinc-500">
                        {s.count} · {s.per_shift}
                      </span>
                      <ul className="ml-3 text-xs text-zinc-600 dark:text-zinc-400">
                        {s.question_types.map((qt) => (
                          <li key={qt.name}>
                            <Link
                              href={href({}, { topic: t.topic, subtopic: s.name, question_type: qt.name })}
                              className="hover:underline"
                            >
                              {qt.name}
                            </Link>{" "}
                            <span className="tabular-nums">{qt.count}</span>
                          </li>
                        ))}
                      </ul>
                    </li>
                  ))}
                </ul>
              </details>
            ))}
        </div>
      ))}
    </nav>
  );
}

const field = "rounded border border-zinc-300 bg-transparent px-2 py-1 text-sm dark:border-zinc-700";

export default async function QuestionIndex({ searchParams }: { searchParams: Promise<Record<string, string>> }) {
  const sp = await searchParams;
  const filters: IndexFilters = Object.fromEntries(KEYS.filter((k) => sp[k]).map((k) => [k, sp[k]]));
  const offset = Number(sp.offset ?? 0) || 0;
  const [tree, formulas, page] = await Promise.all([
    getTree(),
    getFormulas(),
    getIndex({ ...filters, offset: String(offset) }),
  ]);
  const topics = [...new Set(tree.map((t) => t.topic))].sort();
  const byTopic = new Map<string, typeof formulas>();
  for (const f of formulas) byTopic.set(f.topic, [...(byTopic.get(f.topic) ?? []), f]);

  return (
    <>
      <h1 className="text-2xl font-semibold">Question index</h1>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
        All 1,500 questions from the 30 shifts of 2024, by topic, subtopic and question type.
      </p>
      <div className="mt-6 grid gap-8 md:grid-cols-[16rem_1fr]">
        <aside className="md:max-h-[80vh] md:overflow-y-auto">
          <Tree tree={tree} filters={filters} />
        </aside>
        <section>
          <form className="flex flex-wrap gap-2" action="/questions">
            <input name="q" defaultValue={filters.q} placeholder="Search question text" className={`${field} w-56`} />
            <select name="section" defaultValue={filters.section ?? ""} className={field} aria-label="Section">
              <option value="">Both sections</option>
              <option value="QUANT">Quant</option>
              <option value="REASONING">Reasoning</option>
            </select>
            <select name="topic" defaultValue={filters.topic ?? ""} className={field} aria-label="Topic">
              <option value="">Any topic</option>
              {topics.map((t) => (
                <option key={t}>{t}</option>
              ))}
            </select>
            <select name="difficulty" defaultValue={filters.difficulty ?? ""} className={field} aria-label="Difficulty">
              <option value="">Any difficulty</option>
              {[1, 2, 3, 4, 5].map((d) => (
                <option key={d} value={d}>
                  Difficulty {d}
                </option>
              ))}
            </select>
            <select name="formula" defaultValue={filters.formula ?? ""} className={`${field} max-w-56`} aria-label="Formula">
              <option value="">Any formula or method</option>
              {[...byTopic].map(([topic, fs]) => (
                <optgroup key={topic} label={topic}>
                  {fs.map((f) => (
                    <option key={f.id} value={f.id}>
                      {f.name} ({f.question_count})
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <select name="status" defaultValue={filters.status ?? ""} className={field} aria-label="Verification status">
              <option value="">Any status</option>
              <option value="CONFIRMED">Verified</option>
              <option value="KEY_CONFIRMED_CODE">Verified (code check)</option>
              <option value="KEY_CONFIRMED_DUAL">Verified (two solvers)</option>
              <option value="KEY_CONFIRMED_REVIEW">Verified (human review)</option>
              <option value="REJECTED">Rejected</option>
            </select>
            {filters.subtopic && <input type="hidden" name="subtopic" value={filters.subtopic} />}
            {filters.question_type && <input type="hidden" name="question_type" value={filters.question_type} />}
            <button className="rounded bg-zinc-900 px-3 py-1 text-sm text-white dark:bg-zinc-100 dark:text-zinc-900">
              Filter
            </button>
          </form>
          <p className="mt-3 text-sm text-zinc-600 dark:text-zinc-400">
            {page.total} questions
            {filters.subtopic && <> · {filters.subtopic}</>}
            {filters.question_type && <> · {filters.question_type}</>}
            {Object.keys(filters).length > 0 && (
              <>
                {" · "}
                <Link href="/questions" className="underline">
                  clear filters
                </Link>
              </>
            )}
          </p>
          <ul className="mt-2 divide-y divide-zinc-200 dark:divide-zinc-800">
            {page.rows.map((r) => (
              <li key={r.id} className="py-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2 text-xs text-zinc-500">
                  <span className="tabular-nums">{questionLabel(r)}</span>
                  <span>
                    Difficulty {r.difficulty} · ~{r.expected_time_sec}s ·{" "}
                    <span className={isVerified(r.key_status) ? "text-emerald-700 dark:text-emerald-400" : ""}>
                      {statusLabel(r.key_status)}
                    </span>
                  </span>
                </div>
                <p className="mt-1 line-clamp-2 text-sm">
                  {r.stem_text || <span className="italic text-zinc-500">Question is an image (see crop)</span>}
                </p>
                <p className="mt-1 text-xs text-zinc-600 dark:text-zinc-400">
                  {r.topic} › {r.subtopic} › {r.question_type}
                  {r.duplicate_of && <> · repeat of an earlier shift</>}
                </p>
                <div className="mt-1 flex flex-wrap gap-x-3 gap-y-1 text-xs">
                  {isVerified(r.key_status) && (
                    <Link href={`/questions/${r.id}`} className="font-medium underline">
                      Solution
                    </Link>
                  )}
                  {r.crop_url && (
                    <a href={r.crop_url} className="underline" target="_blank" rel="noreferrer">
                      Source crop
                    </a>
                  )}
                  {r.formulas.map((f, i) => (
                    <Link key={f.id} href={formulaHref(f)} className="text-sky-700 hover:underline dark:text-sky-400">
                      {i === 0 ? "★ " : ""}
                      {f.name}
                    </Link>
                  ))}
                </div>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex justify-between text-sm">
            {offset > 0 ? (
              <Link href={href(filters, { offset: String(Math.max(0, offset - PAGE)) })} className="underline">
                Previous
              </Link>
            ) : (
              <span />
            )}
            {offset + PAGE < page.total && (
              <Link href={href(filters, { offset: String(offset + PAGE) })} className="underline">
                Next
              </Link>
            )}
          </div>
        </section>
      </div>
    </>
  );
}
