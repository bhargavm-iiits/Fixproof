import { useEffect, useRef } from "react";

/** A soft follower that widens over anything clickable. The real cursor stays. */
export function Cursor() {
  const ref = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const node = ref.current;
    if (!node) return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;

    let raf = 0;
    let x = window.innerWidth / 2;
    let y = window.innerHeight / 2;
    let targetX = x;
    let targetY = y;

    const onMove = (event: MouseEvent) => {
      targetX = event.clientX;
      targetY = event.clientY;
      node.style.opacity = "1";
      const over = (event.target as HTMLElement | null)?.closest(
        "a,button,[role='button'],input,summary",
      );
      node.style.width = over ? "46px" : "28px";
      node.style.height = over ? "46px" : "28px";
      node.style.margin = over ? "-23px 0 0 -23px" : "-14px 0 0 -14px";
    };
    const onLeave = () => {
      node.style.opacity = "0";
    };

    const tick = () => {
      x += (targetX - x) * 0.18;
      y += (targetY - y) * 0.18;
      node.style.transform = `translate3d(${x}px, ${y}px, 0)`;
      raf = window.requestAnimationFrame(tick);
    };

    window.addEventListener("mousemove", onMove, { passive: true });
    document.addEventListener("mouseleave", onLeave);
    raf = window.requestAnimationFrame(tick);
    return () => {
      window.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseleave", onLeave);
      window.cancelAnimationFrame(raf);
    };
  }, []);

  return <div ref={ref} className="cursor-dot" style={{ opacity: 0 }} aria-hidden="true" />;
}
