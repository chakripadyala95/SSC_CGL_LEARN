import Link from "next/link";
import { notFound } from "next/navigation";
import { getFormula, getFormulas } from "@/lib/api";
import { formulaHref } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function FormulaTopic({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const list = await getFormulas(slug);
  if (list.length === 0) notFound();
  const entries = await Promise.all(list.map((f) => getFormula(f.id)));
  const names = new Map((await getFormulas()).map((f) => [f.id, f]));
  return (
    <>
      <p className="text-sm text-zinc-500">
        <Link href="/questions" className="underline">
          Question index
        </Link>
      </p>
      <h1 className="mt-1 text-2xl font-semibold">{list[0].topic}: formulas and methods</h1>
      {entries.map((f) => (
        <section key={f.id} id={f.id.split(".")[1]} className="mt-8 scroll-mt-4">
          <h2 className="font-medium">{f.name}</h2>
          <p className="text-xs text-zinc-500">
            {f.subtopic} · {f.question_count ? `used in ${f.question_count} questions` : "not yet seen in papers"}
            {f.verification_status !== "PASSED" && " · awaiting review"}
          </p>
          <pre className="mt-2 overflow-x-auto rounded bg-zinc-50 p-2 text-sm dark:bg-zinc-900">{f.statement}</pre>
          {f.shortcut && <p className="mt-2 text-sm">Shortcut: {f.shortcut}</p>}
          {f.entry.conditions.length > 0 && (
            <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">When: {f.entry.conditions.join("; ")}</p>
          )}
          <details className="mt-2 text-sm">
            <summary className="cursor-pointer">Derivation and traps</summary>
            <ol className="mt-1 list-decimal pl-5">
              {f.entry.derivation.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ol>
            <ul className="mt-2 list-disc pl-5 text-zinc-600 dark:text-zinc-400">
              {f.entry.common_traps.map((s, i) => (
                <li key={i}>{s}</li>
              ))}
            </ul>
          </details>
          {f.question_ids.length > 0 && (
            <p className="mt-2 text-sm">
              <Link href={`/questions?formula=${encodeURIComponent(f.id)}`} className="underline">
                See the {f.question_count} questions
              </Link>
            </p>
          )}
          {f.entry.related_ids.length > 0 && (
            <p className="mt-1 text-xs">
              Related:{" "}
              {f.entry.related_ids
                .filter((id) => names.has(id))
                .map((id, i) => (
                  <span key={id}>
                    {i > 0 && ", "}
                    <Link href={formulaHref(names.get(id)!)} className="text-sky-700 hover:underline dark:text-sky-400">
                      {names.get(id)!.name}
                    </Link>
                  </span>
                ))}
            </p>
          )}
        </section>
      ))}
    </>
  );
}
