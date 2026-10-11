import Link from "next/link";
import { notFound } from "next/navigation";
import { ApiError, getStudyQuestion } from "@/lib/api";
import { formulaHref, questionLabel, statusLabel } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function StudyQuestion({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const q = await getStudyQuestion(id).catch((e) => {
    if (e instanceof ApiError && (e.status === 404 || e.status === 409)) notFound();
    throw e;
  });
  return (
    <article>
      <p className="text-sm text-zinc-500">
        <Link href="/questions" className="underline">
          Question index
        </Link>{" "}
        · {questionLabel(q)}
      </p>
      {q.tag && (
        <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
          {q.tag.topic} › {q.tag.subtopic} › {q.tag.question_type} · Difficulty {q.tag.difficulty} · ~
          {q.tag.expected_time_sec}s
        </p>
      )}
      {q.stem_text && <p className="mt-4">{q.stem_text}</p>}
      {q.stem_image_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={q.stem_image_url} alt="Question" className="mt-3 max-w-full" />
      )}
      <ol className="mt-4 space-y-1">
        {q.options.map((o) => (
          <li
            key={o.label}
            className={
              o.label === q.answer
                ? "rounded bg-emerald-50 px-2 py-1 font-medium dark:bg-emerald-950"
                : "px-2 py-1"
            }
          >
            {o.label}. {o.text}
            {o.image_url && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={o.image_url} alt={`Option ${o.label}`} className="inline max-h-24" />
            )}
          </li>
        ))}
      </ol>
      <h2 className="mt-6 font-medium">Answer: {q.answer}</h2>
      <p className="text-xs text-zinc-500">{statusLabel(q.key_status)}</p>
      {q.tag && <p className="mt-2 text-sm">Shortcut: {q.tag.shortcut_used}</p>}
      {q.formulas.length > 0 && (
        <>
          <h2 className="mt-6 font-medium">Formulas and methods</h2>
          <ul className="mt-1 text-sm">
            {q.formulas.map((f, i) => (
              <li key={f.id}>
                <Link href={formulaHref(f)} className="text-sky-700 hover:underline dark:text-sky-400">
                  {f.name}
                </Link>
                {i === 0 && <span className="text-zinc-500"> (main step)</span>}
              </li>
            ))}
          </ul>
        </>
      )}
      {q.working.length > 0 && (
        <>
          <h2 className="mt-6 font-medium">Verified working</h2>
          <p className="text-xs text-zinc-500">Step-by-step shortcut-first solutions come in the next phase.</p>
          <ol className="mt-1 list-decimal pl-5 text-sm">
            {q.working.map((s, i) => (
              <li key={i}>{s}</li>
            ))}
          </ol>
        </>
      )}
      {q.crop_url && (
        <>
          <h2 className="mt-6 font-medium">Source</h2>
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={q.crop_url} alt="The question as printed in the official paper" className="mt-1 max-w-full border" />
        </>
      )}
    </article>
  );
}
