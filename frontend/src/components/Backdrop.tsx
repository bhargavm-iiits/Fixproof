import { useEffect, useRef } from "react";

/**
 * The background is the pipeline.
 *
 * Points travel away from the viewer down a tunnel of nine gates. Most are
 * stopped at one of the first few and flash out; roughly one in eight survives
 * the whole way and arrives lit. That is the actual shape of the data this
 * project produces, not an abstract particle field.
 *
 * Hand-written perspective projection rather than a 3D library: this is a
 * background, and it is not worth tripling the bundle for. It holds 60fps, it
 * stops when the tab is hidden, and `prefers-reduced-motion` gets one still
 * frame instead of motion.
 */

const GATES = 9;
const NEAR = 70;
const FAR = 1340;
const FOCAL = 470;
const GATE_HALF = 250;
/** The tunnel converges right of centre, clear of the left-aligned text column. */
const VANISH_X = 0.68;
const VANISH_Y = 0.46;
const SURVIVAL = 0.12;
const MAX_POINTS = 90;

type Point = {
  angle: number;
  radius: number;
  z: number;
  speed: number;
  stopAt: number;
  flash: number;
  spent: boolean;
};

function gateZ(index: number) {
  return 220 + (index * (FAR - 380)) / (GATES - 1);
}

/** Most rejections happen in the first few gates, so most points stop there. */
function pickFate(): number {
  if (Math.random() < SURVIVAL) return -1;
  const weights = [3, 7, 9, 4, 3, 2, 2, 1, 1];
  const total = weights.reduce((sum, weight) => sum + weight, 0);
  let roll = Math.random() * total;
  for (let index = 0; index < weights.length; index += 1) {
    roll -= weights[index];
    if (roll <= 0) return index;
  }
  return weights.length - 1;
}

function spawn(atStart: boolean): Point {
  return {
    angle: Math.random() * Math.PI * 2,
    radius: 26 + Math.random() * GATE_HALF * 0.82,
    z: atStart ? NEAR + Math.random() * (FAR - NEAR) : NEAR,
    speed: 62 + Math.random() * 88,
    stopAt: pickFate(),
    flash: 0,
    spent: false,
  };
}

export function Backdrop() {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    const context = canvas?.getContext("2d");
    if (!canvas || !context) return;

    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let width = 0;
    let height = 0;
    let centreX = 0;
    let centreY = 0;
    let roll = 0;
    let pointerX = 0;
    let pointerY = 0;
    let driftX = 0;
    let driftY = 0;
    let opacity = -1;
    let frame = 0;
    let last = performance.now();

    const points: Point[] = [];

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      width = window.innerWidth;
      height = window.innerHeight;
      canvas.width = Math.floor(width * ratio);
      canvas.height = Math.floor(height * ratio);
      canvas.style.width = `${width}px`;
      canvas.style.height = `${height}px`;
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      centreX = width * VANISH_X;
      centreY = height * VANISH_Y;

      const wanted = Math.min(MAX_POINTS, Math.round((width * height) / 22000));
      while (points.length < wanted) points.push(spawn(true));
      points.length = Math.min(points.length, wanted);
    };

    const onPointer = (event: PointerEvent) => {
      pointerX = (event.clientX / window.innerWidth - 0.5) * 2;
      pointerY = (event.clientY / window.innerHeight - 0.5) * 2;
    };

    const project = (x: number, y: number, z: number) => {
      const scale = FOCAL / z;
      return {
        x: centreX + driftX + x * scale,
        y: centreY + driftY + y * scale,
        scale,
      };
    };

    const draw = (elapsed: number) => {
      context.clearRect(0, 0, width, height);
      roll += elapsed * 0.045;

      // Full strength behind the hero, then mostly out of the way. A fixed
      // canvas cannot know where the text is, so it yields as soon as reading
      // starts rather than competing with it. Only written when it actually
      // moves, so an unscrolled page is not invalidating style every frame.
      const scrolled = window.scrollY / (window.innerHeight * 0.85);
      const wanted = Math.max(0.16, 1 - scrolled * 0.84);
      if (Math.abs(wanted - opacity) > 0.005) {
        opacity = wanted;
        canvas.style.opacity = String(wanted);
      }

      // Ease the vanishing point toward the pointer. Small on purpose: this is
      // behind text that has to stay readable.
      driftX += (pointerX * 26 - driftX) * 0.04;
      driftY += (pointerY * 18 - driftY) * 0.04;

      const cos = Math.cos(roll);
      const sin = Math.sin(roll);

      // The tunnel: nine gates receding to a vanishing point.
      for (let index = 0; index < GATES; index += 1) {
        const z = gateZ(index);
        const half = GATE_HALF;
        const corners = [
          [-half, -half],
          [half, -half],
          [half, half],
          [-half, half],
        ].map(([x, y]) => project(x * cos - y * sin, x * sin + y * cos, z));

        const fade = 1 - index / GATES;
        context.beginPath();
        context.moveTo(corners[0].x, corners[0].y);
        for (let corner = 1; corner < corners.length; corner += 1) {
          context.lineTo(corners[corner].x, corners[corner].y);
        }
        context.closePath();
        context.lineWidth = index === 2 ? 1.4 : 1;
        // The third gate is the one that catches the cheating, so it is the one
        // that carries a tint. Alphas stay low enough that a 1px line crossing a
        // glyph cannot pull body text under its contrast floor.
        context.strokeStyle =
          index === 2
            ? `rgba(255, 122, 107, ${0.26 * fade + 0.05})`
            : `rgba(207, 242, 72, ${0.17 * fade + 0.035})`;
        context.stroke();
      }

      // Points, far ones first so nearer ones sit on top.
      const ordered = [...points].sort((a, b) => b.z - a.z);
      for (const point of ordered) {
        const x = Math.cos(point.angle + roll * 0.4) * point.radius;
        const y = Math.sin(point.angle + roll * 0.4) * point.radius;
        const { x: sx, y: sy, scale } = project(x, y, point.z);

        const depth = 1 - (point.z - NEAR) / (FAR - NEAR);
        // Points closest to the camera would otherwise be huge, bright blobs
        // sitting on top of the copy, so they fade in as they enter and their
        // radius is capped.
        const entering = Math.min(1, (point.z - NEAR) / 150);
        const size = Math.min(3.6, Math.max(0.5, scale * 1.5));

        if (point.spent) {
          context.fillStyle = `rgba(255, 122, 107, ${point.flash * 0.45 * entering})`;
          context.beginPath();
          context.arc(sx, sy, Math.min(7, size * (1 + (1 - point.flash) * 2.2)), 0, Math.PI * 2);
          context.fill();
        } else if (point.stopAt === -1 && point.z > gateZ(GATES - 1)) {
          const alpha = Math.min(1, (point.z - gateZ(GATES - 1)) / 90) * 0.8;
          context.fillStyle = `rgba(207, 242, 72, ${alpha})`;
          context.beginPath();
          context.arc(sx, sy, size * 1.7, 0, Math.PI * 2);
          context.fill();
        } else {
          context.fillStyle = `rgba(244, 244, 242, ${(0.12 + depth * 0.34) * entering})`;
          context.beginPath();
          context.arc(sx, sy, size, 0, Math.PI * 2);
          context.fill();
        }
      }
    };

    const step = (now: number) => {
      const elapsed = Math.min((now - last) / 1000, 0.05);
      last = now;

      for (let index = 0; index < points.length; index += 1) {
        const point = points[index];
        if (point.spent) {
          point.flash -= elapsed * 1.9;
          point.z += point.speed * elapsed * 0.25;
          if (point.flash <= 0) points[index] = spawn(false);
          continue;
        }

        point.z += point.speed * elapsed;

        if (point.stopAt >= 0 && point.z >= gateZ(point.stopAt)) {
          point.spent = true;
          point.flash = 1;
        } else if (point.z > FAR) {
          points[index] = spawn(false);
        }
      }

      draw(elapsed);
      frame = window.requestAnimationFrame(step);
    };

    const start = () => {
      if (frame) return;
      last = performance.now();
      frame = window.requestAnimationFrame(step);
    };

    const stop = () => {
      if (!frame) return;
      window.cancelAnimationFrame(frame);
      frame = 0;
    };

    const onVisibility = () => (document.hidden ? stop() : start());

    resize();
    window.addEventListener("resize", resize);

    if (still) {
      draw(0);
      return () => window.removeEventListener("resize", resize);
    }

    window.addEventListener("pointermove", onPointer, { passive: true });
    document.addEventListener("visibilitychange", onVisibility);
    start();

    return () => {
      stop();
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onPointer);
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, []);

  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 z-0"
    />
  );
}
