import { useHealth } from "../lib/health";
import { Reveal, Tag } from "../components/Section";

export function Hero() {
  const { data } = useHealth();
  const dockerReady = Boolean(data?.docker_reachable && data?.image_present);

  return (
    <header className="relative px-6 pt-10 pb-20 sm:px-12 sm:pt-14 sm:pb-28">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <div className="flex flex-wrap items-center justify-between gap-4">
            <span className="font-mono text-[11px] tracking-[0.2em] text-muted uppercase">
              fixproof
            </span>
            <div className="flex flex-wrap items-center gap-2">
              <Tag tone={dockerReady ? "acid" : "reject"}>
                <span
                  className={`h-1.5 w-1.5 rounded-full ${dockerReady ? "bg-acid" : "bg-reject"}`}
                />
                {dockerReady ? "verifier ready" : "verifier unavailable"}
              </Tag>
              {data && <Tag>{data.model_mode} mode</Tag>}
              {data && <Tag>config {data.config_hash.slice(0, 8)}</Tag>}
            </div>
          </div>
        </Reveal>

        <Reveal delay={90}>
          <h1
            className="mt-20 font-display font-semibold tracking-tight text-bone sm:mt-28"
            style={{ fontSize: "clamp(2.8rem, 9.4vw, 9rem)", lineHeight: 0.92, letterSpacing: "-0.05em" }}
          >
            Repair a defect.
            <br />
            <span className="text-muted">Prove</span> the repair.
          </h1>
        </Reveal>

        <div className="mt-14 flex flex-col gap-12 lg:flex-row lg:items-end lg:justify-between">
          <Reveal delay={160}>
            <p className="max-w-xl text-base leading-relaxed text-muted sm:text-lg">
              A patch is a hypothesis until something runs it. fixproof pushes every candidate
              through nine static gates, then executes the survivors against the target&rsquo;s own
              test suite inside a container with no network, a read&#8209;only image and a
              host&#8209;enforced kill.
            </p>
          </Reveal>
          <Reveal delay={220}>
            <a
              href="#live"
              className="group inline-flex h-14 items-center gap-4 border-b border-bone pb-1 font-display text-2xl font-medium tracking-tight text-bone sm:text-3xl"
            >
              run one
              <span className="transition-transform duration-300 group-hover:translate-y-1">
                &darr;
              </span>
            </a>
          </Reveal>
        </div>

        <Reveal delay={280}>
          <div className="mt-20 grid grid-cols-2 gap-px border border-line bg-line sm:grid-cols-4">
            {[
              ["24", "seeded defects"],
              ["9", "static gates"],
              ["1", "container that decides"],
              ["333", "tests per verification"],
            ].map(([value, label]) => (
              <div key={label} className="bg-ink px-5 py-7">
                <div className="font-display text-3xl font-semibold tracking-tight sm:text-4xl">
                  {value}
                </div>
                <div className="mt-2 text-xs leading-snug text-muted">{label}</div>
              </div>
            ))}
          </div>
        </Reveal>
      </div>
    </header>
  );
}
