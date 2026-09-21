import { useHealth } from "../lib/health";
import { Reveal } from "../components/Section";

export function Footer() {
  const { data } = useHealth();

  return (
    <footer className="border-t border-line px-6 py-16 sm:px-12 sm:py-20">
      <div className="mx-auto max-w-6xl">
        <Reveal>
          <div className="flex flex-col gap-12 lg:flex-row lg:items-end lg:justify-between">
            <div>
              <p
                className="font-display font-semibold tracking-tight text-bone"
                style={{ fontSize: "clamp(1.9rem, 5vw, 3.4rem)", lineHeight: 1.02 }}
              >
                The proof is a container
                <br />
                exit code.
              </p>
              <p className="mt-5 max-w-md text-sm leading-relaxed text-muted">
                Not a score, not a confidence, not a model&rsquo;s opinion about its own patch.
              </p>
            </div>

            <nav className="flex flex-col gap-3">
              {[
                ["API reference", "/docs"],
                ["OpenAPI schema", "/openapi.json"],
                ["Stage machine", "/graph"],
                ["Latest report", "/reports/latest"],
              ].map(([label, href]) => (
                <a
                  key={href}
                  href={href}
                  className="group inline-flex items-center gap-3 font-display text-lg tracking-tight text-muted transition-colors hover:text-acid"
                >
                  <span className="transition-transform duration-300 group-hover:translate-x-1">
                    &rarr;
                  </span>
                  {label}
                </a>
              ))}
            </nav>
          </div>
        </Reveal>

        <hr className="rule my-12" />

        <div className="flex flex-wrap items-center justify-between gap-4 font-mono text-[11px] text-muted">
          <span>fixproof</span>
          <span>
            {data
              ? `${data.model_mode} · config ${data.config_hash.slice(0, 12)} · schema v${data.schema_version}`
              : "—"}
          </span>
        </div>
      </div>
    </footer>
  );
}
