import { getMocks, type Mock, type Section } from "@/lib/api";

export const dynamic = "force-dynamic";

const SECTIONS: { key: Section; name: string }[] = [
  { key: "QUANT", name: "Quantitative Aptitude" },
  { key: "REASONING", name: "General Intelligence & Reasoning" },
];

function shiftLabel(paperId: string) {
  const [date, slot] = paperId.split("_");
  return `${date} · ${slot.slice(0, 2)}:${slot.slice(2)}`;
}

function MockRow({ mock }: { mock: Mock }) {
  const published = mock.status === "PUBLISHED";
  return (
    <li className="flex items-center justify-between py-2">
      <span className="tabular-nums">{shiftLabel(mock.paper_id)}</span>
      <span
        className={
          published
            ? "rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-800 dark:bg-emerald-900 dark:text-emerald-100"
            : "rounded bg-zinc-100 px-2 py-0.5 text-xs text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300"
        }
      >
        {published ? "Ready" : "Answers being verified"}
      </span>
    </li>
  );
}

export default async function Home() {
  const mocks = await getMocks();
  return (
    <>
      <h1 className="text-2xl font-semibold">SSC CGL Tier-1 section mocks</h1>
      <p className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
        25 questions each, from the 2024 shifts. A mock opens once all 25 answers are verified.
      </p>
      <div className="mt-8 grid gap-8 md:grid-cols-2">
        {SECTIONS.map(({ key, name }) => {
          const rows = mocks.filter((m) => m.section === key);
          const ready = rows.filter((m) => m.status === "PUBLISHED").length;
          return (
            <section key={key}>
              <h2 className="font-medium">{name}</h2>
              <p className="text-sm text-zinc-600 dark:text-zinc-400">
                {ready} of {rows.length} ready
              </p>
              <ul className="mt-2 divide-y divide-zinc-200 dark:divide-zinc-800">
                {rows.map((m) => (
                  <MockRow key={m.id} mock={m} />
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    </>
  );
}
