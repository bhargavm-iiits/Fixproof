import { useHealth } from "../lib/health";

export function Footer() {
  const { data } = useHealth();

  return (
    <footer className="border-t border-line px-6 py-14 sm:px-10">
      <div className="mx-auto max-w-4xl">
        <p className="max-w-xl font-display text-2xl font-semibold tracking-tight">
          A fix is a claim. A passing test suite in a sealed box is evidence.
        </p>

        <nav aria-label="Technical details" className="mt-8 flex flex-wrap gap-x-8 gap-y-2">
          {[
            ["Browse the API", "/docs"],
            ["Raw schema", "/openapi.json"],
            ["Latest results", "/reports/latest"],
          ].map(([label, href]) => (
            <a key={href} href={href} className="text-[15px] text-body underline hover:text-acid">
              {label}
            </a>
          ))}
        </nav>

        <p className="mt-10 border-t border-line pt-6 text-[13px] text-muted">
          {data
            ? `Running in ${data.model_mode} mode. Sandbox ${data.docker_reachable ? "available" : "unavailable"}.`
            : "Checking status…"}
        </p>
      </div>
    </footer>
  );
}
