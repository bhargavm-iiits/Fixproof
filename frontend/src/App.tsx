import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "./api";
import { useHealth } from "./lib/health";
import { useActiveSection } from "./lib/motion";
import { Loader } from "./components/Loader";
import { Cursor } from "./components/Cursor";
import { Hero } from "./sections/Hero";
import { Gates } from "./sections/Gates";
import { Stages } from "./sections/Stages";
import { Live } from "./sections/Live";
import { Evidence } from "./sections/Evidence";
import { Limits } from "./sections/Limits";
import { Footer } from "./sections/Footer";

const SECTIONS = [
  { id: "gates", index: "01", label: "Gates" },
  { id: "stages", index: "02", label: "Run" },
  { id: "live", index: "03", label: "Try it" },
  { id: "evidence", index: "04", label: "Evidence" },
  { id: "limits", index: "05", label: "Limits" },
];

const SECTION_IDS = SECTIONS.map((section) => section.id);

function SideNav() {
  const active = useActiveSection(SECTION_IDS);
  return (
    <nav className="pointer-events-none fixed top-1/2 left-6 z-40 hidden -translate-y-1/2 flex-col gap-3 xl:flex">
      {SECTIONS.map((section) => {
        const current = active === section.id;
        return (
          <a
            key={section.id}
            href={`#${section.id}`}
            className={`pointer-events-auto flex items-center gap-3 font-mono text-[10px] tracking-[0.18em] uppercase transition-colors ${
              current ? "text-acid" : "text-muted/50 hover:text-muted"
            }`}
          >
            <span className={`h-px transition-all ${current ? "w-7 bg-acid" : "w-3 bg-muted/40"}`} />
            {section.label}
          </a>
        );
      })}
    </nav>
  );
}

function DemoBanner() {
  const { data } = useHealth();
  if (!data || data.mutations_enabled) return null;
  return (
    <div className="border-b border-reject/40 bg-reject/10 px-6 py-2.5 text-center text-sm text-reject">
      Read&#8209;only demonstration. Runs shown here were recorded in advance; the controls that
      would start one are not rendered, and the server refuses them with a 403 regardless.
    </div>
  );
}

export default function App() {
  const [entered, setEntered] = useState(false);

  const health = useHealth();
  const defects = useQuery({ queryKey: ["defects", "dev"], queryFn: () => api.defects("dev") });

  const settled = [health.isSuccess || health.isError, defects.isSuccess || defects.isError];
  const ready = settled.filter(Boolean).length / settled.length;
  const failed = health.isError;

  useEffect(() => {
    document.body.style.overflow = entered ? "" : "hidden";
    return () => {
      document.body.style.overflow = "";
    };
  }, [entered]);

  return (
    <div className="grain min-h-full">
      <Cursor />
      {!entered && <Loader ready={ready} failed={failed} onEnter={() => setEntered(true)} />}
      <DemoBanner />
      <SideNav />
      <div
        style={{
          opacity: entered ? 1 : 0,
          transition: "opacity .8s cubic-bezier(.22,1,.36,1) .1s",
        }}
      >
        <Hero />
        <Gates />
        <Stages />
        <Live />
        <Evidence />
        <Limits />
        <Footer />
      </div>
    </div>
  );
}
