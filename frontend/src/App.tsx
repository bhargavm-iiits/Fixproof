import { NavLink, Outlet } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, type Health } from "./api";
import { Badge } from "./components/ui";

const TABS = [
  { to: "/", label: "Defects", end: true },
  { to: "/runs", label: "Runs", end: false },
  { to: "/reports", label: "Quality", end: false },
  { to: "/about", label: "Limits", end: false },
];

export function useHealth() {
  return useQuery<Health>({
    queryKey: ["health"],
    queryFn: api.health,
    refetchInterval: 15_000,
  });
}

function HealthBadge() {
  const { data, isError } = useHealth();
  if (isError) return <Badge tone="fail">API unreachable</Badge>;
  if (!data) return <Badge tone="muted">checking…</Badge>;
  const dockerReady = data.docker_reachable && data.image_present;
  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="health">
      <Badge tone={dockerReady ? "pass" : "fail"} title={data.image}>
        {dockerReady ? "verifier ready" : "verifier unavailable"}
      </Badge>
      <Badge tone={data.model_mode === "gemini" ? "info" : "warn"}>
        {data.model_mode === "gemini" ? `model: ${data.model_name}` : `${data.model_mode} mode`}
      </Badge>
      <Badge tone="muted" title="The hash of every setting that changes what the system decides">
        config {data.config_hash.slice(0, 8)}
      </Badge>
    </div>
  );
}

function DemoBanner() {
  const { data } = useHealth();
  if (!data || data.mutations_enabled) return null;
  return (
    <div
      data-testid="demo-banner"
      className="border-b border-warn/40 bg-warn/10 px-6 py-2 text-center text-sm text-warn"
    >
      Read-only demonstration. Runs shown here were recorded in advance; starting one is disabled
      server-side and the button is not rendered.
    </div>
  );
}

export default function App() {
  return (
    <div className="min-h-full">
      <DemoBanner />
      <header className="border-b border-edge bg-panel/60 backdropblur">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-8 gap-y-3 px-6 py-4">
          <div>
            <h1 className="text-lg font-bold tracking-tight">
              fix<span className="text-accent">proof</span>
            </h1>
            <p className="text-[11px] text-muted">
              No fix is claimed without proof, and the proof is a container exit code.
            </p>
          </div>
          <nav className="flex gap-1">
            {TABS.map((tab) => (
              <NavLink
                key={tab.to}
                to={tab.to}
                end={tab.end}
                className={({ isActive }) =>
                  `rounded-lg px-3 py-1.5 text-sm transition ${
                    isActive ? "bg-accent/15 text-accent" : "text-muted hover:text-slate-200"
                  }`
                }
              >
                {tab.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto">
            <HealthBadge />
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Outlet />
      </main>
      <footer className="mx-auto max-w-6xl px-6 pb-10 text-[11px] text-muted">
        A synthetic target application with seeded defects. See{" "}
        <NavLink to="/about" className="text-accent underline">
          Limits
        </NavLink>{" "}
        before reading anything into these numbers.
      </footer>
    </div>
  );
}
