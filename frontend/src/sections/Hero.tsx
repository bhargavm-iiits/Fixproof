import { useHealth } from "../lib/health";
import { Reveal } from "../components/Section";

export function Hero() {
  const { data } = useHealth();
  const ready = Boolean(data?.docker_reachable && data?.image_present);

  return (
    <header className="px-6 pt-8 pb-16 sm:px-10 sm:pt-12 sm:pb-24">
      <div className="mx-auto max-w-4xl">
        <Reveal>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <span className="font-display text-lg font-semibold tracking-tight">
              fix<span className="text-acid">proof</span>
            </span>
            <span className="flex items-center gap-2 text-[13px] text-muted">
              <span
                className={`h-2 w-2 rounded-full ${ready ? "bg-acid" : "bg-reject"}`}
                aria-hidden="true"
              />
              {ready ? "Ready to run" : "Sandbox unavailable"}
            </span>
          </div>
        </Reveal>

        <Reveal delay={60}>
          <h1
            className="mt-16 font-display font-semibold tracking-tight text-bone sm:mt-24"
            style={{ fontSize: "clamp(2.4rem, 6.6vw, 4.6rem)", lineHeight: 1.03, letterSpacing: "-0.035em" }}
          >
            An AI says it fixed the bug.
            <br />
            <span className="text-muted">Did it?</span>
          </h1>
        </Reveal>

        <Reveal delay={120}>
          <p className="mt-8 max-w-2xl text-lg text-body">
            fixproof takes a program with a known bug, asks an AI to repair it, and then checks the
            answer the only way that counts &mdash; by actually running the program&rsquo;s tests
            inside a locked box with no internet access.
          </p>
          <p className="mt-4 max-w-2xl text-lg text-body">
            If the tests don&rsquo;t pass, it isn&rsquo;t a fix. It doesn&rsquo;t matter how
            confident the AI sounded.
          </p>
        </Reveal>

        <Reveal delay={180}>
          <div className="mt-10 flex flex-wrap gap-3">
            <a
              href="#try"
              className="inline-flex h-12 items-center rounded-lg bg-acid px-6 font-medium text-ink transition hover:brightness-110"
            >
              Try it yourself
            </a>
            <a
              href="#how"
              className="inline-flex h-12 items-center rounded-lg border border-line px-6 text-bone transition hover:border-bone/40"
            >
              How it works
            </a>
          </div>
        </Reveal>

        <Reveal delay={240}>
          <dl className="mt-16 grid grid-cols-2 gap-6 border-t border-line pt-8 sm:grid-cols-4">
            {[
              ["24", "bugs to try"],
              ["9", "checks before testing"],
              ["333", "tests run every time"],
              ["0", "cheats let through"],
            ].map(([value, label]) => (
              <div key={label}>
                <dt className="sr-only">{label}</dt>
                <dd>
                  <span className="block font-display text-3xl font-semibold tracking-tight">
                    {value}
                  </span>
                  <span className="mt-1 block text-[14px] text-muted">{label}</span>
                </dd>
              </div>
            ))}
          </dl>
        </Reveal>
      </div>
    </header>
  );
}
