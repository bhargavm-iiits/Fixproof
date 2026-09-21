import { useHealth } from "./lib/health";
import { Backdrop } from "./components/Backdrop";
import { Hero } from "./sections/Hero";
import { HowItWorks } from "./sections/HowItWorks";
import { TheCatch } from "./sections/TheCatch";
import { Live } from "./sections/Live";
import { Results } from "./sections/Results";
import { Limits } from "./sections/Limits";
import { Footer } from "./sections/Footer";

function ReadOnlyNotice() {
  const { data } = useHealth();
  if (!data || data.mutations_enabled) return null;
  return (
    <div className="border-b border-line bg-raised px-6 py-3 text-center text-[15px] text-body">
      This is a read-only copy. You can read everything, but starting a new run is turned off.
    </div>
  );
}

export default function App() {
  return (
    <>
      <a href="#try" className="skip-link">
        Skip to the interactive demo
      </a>
      <Backdrop />
      <div className="relative z-10">
        <ReadOnlyNotice />
        <main id="main">
          <Hero />
          <HowItWorks />
          <TheCatch />
          <Live />
          <Results />
          <Limits />
        </main>
        <Footer />
      </div>
    </>
  );
}
