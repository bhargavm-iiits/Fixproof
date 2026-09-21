import { useEffect, useRef } from "react";
import { createTarget, destroyTarget, link, type Target } from "../lib/gl";
import {
  COMPOSITE_FRAG,
  FEEDBACK_FRAG,
  FULLSCREEN_VERT,
  PARTICLE_FRAG,
  PARTICLE_VERT,
  TUNNEL_FRAG,
} from "../lib/shaders";

/**
 * The background is the pipeline, rendered on the GPU.
 *
 * Four passes per frame into an offscreen target:
 *
 *   1. the previous frame, faded and pushed outward  — the trails
 *   2. sixteen gate shells, solved analytically      — the tunnel
 *   3. additive point sprites                        — the candidates
 *   4. composite to screen with tone mapping,
 *      chromatic aberration, vignette and grain      — the lens
 *
 * Most points are stopped at one of the first few gates and flash out; roughly
 * one in eight reaches the container at the end and arrives lit. That weighting
 * is the real rejection distribution, not an arbitrary particle field.
 *
 * Raw WebGL2 rather than a library: the whole thing is a few kilobytes, and a
 * background has no business being the largest dependency in the bundle.
 */

const PARTICLES = 260;
const RENDER_SCALE = 0.62;
/** Hard ceiling on offscreen pixels. Sixteen shell intersections per pixel is
 *  cheap at 600k and ruinous at 2M, and a retina display would ask for the
 *  latter. The result is a soft glow being upscaled, so nobody can tell. */
const PIXEL_BUDGET = 620_000;
const VANISH_X = 0.74;
const VANISH_Y = 0.54;
/** Steady state is input * 1/(1 - fade), so this number sets the exposure
 *  budget every shader above has to live inside. */
const TRAIL_FADE = 0.82;
const TRAIL_ZOOM = 1.006;
const SURVIVAL = 0.12;

function buildParticles() {
  const phase = new Float32Array(PARTICLES);
  const angle = new Float32Array(PARTICLES);
  const radius = new Float32Array(PARTICLES);
  const speed = new Float32Array(PARTICLES);
  const stop = new Float32Array(PARTICLES);

  for (let index = 0; index < PARTICLES; index += 1) {
    phase[index] = Math.random();
    angle[index] = Math.random() * Math.PI * 2;
    radius[index] = 0.05 + Math.random() * 0.5;
    speed[index] = 0.032 + Math.random() * 0.055;
    // Stops cluster toward the early gates, the way real rejections do.
    stop[index] =
      Math.random() < SURVIVAL ? 2 : 0.04 + Math.pow(Math.random(), 2.2) * 0.62;
  }
  return { phase, angle, radius, speed, stop };
}

export function Backdrop() {
  const ref = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;

    const gl = canvas.getContext("webgl2", {
      alpha: false,
      antialias: false,
      depth: false,
      stencil: false,
      powerPreference: "high-performance",
    });

    if (!gl) {
      canvas.style.display = "none";
      return;
    }

    const floatTargets = Boolean(gl.getExtension("EXT_color_buffer_float"));
    const still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let feedback: WebGLProgram;
    let tunnel: WebGLProgram;
    let particles: WebGLProgram;
    let composite: WebGLProgram;
    try {
      feedback = link(gl, FULLSCREEN_VERT, FEEDBACK_FRAG);
      tunnel = link(gl, FULLSCREEN_VERT, TUNNEL_FRAG);
      particles = link(gl, PARTICLE_VERT, PARTICLE_FRAG);
      composite = link(gl, FULLSCREEN_VERT, COMPOSITE_FRAG);
    } catch {
      canvas.style.display = "none";
      return;
    }

    // ---------------------------------------------------------------- geometry

    const quadBuffer = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, quadBuffer);
    gl.bufferData(
      gl.ARRAY_BUFFER,
      new Float32Array([-1, -1, 3, -1, -1, 3]),
      gl.STATIC_DRAW,
    );

    const quadVao = gl.createVertexArray();
    gl.bindVertexArray(quadVao);
    gl.bindBuffer(gl.ARRAY_BUFFER, quadBuffer);
    for (const program of [feedback, tunnel, composite]) {
      const location = gl.getAttribLocation(program, "aPos");
      if (location >= 0) {
        gl.enableVertexAttribArray(location);
        gl.vertexAttribPointer(location, 2, gl.FLOAT, false, 0, 0);
      }
    }

    const data = buildParticles();
    const particleVao = gl.createVertexArray();
    const particleBuffers: WebGLBuffer[] = [];
    gl.bindVertexArray(particleVao);
    for (const [name, values] of [
      ["aPhase", data.phase],
      ["aAngle", data.angle],
      ["aRadius", data.radius],
      ["aSpeed", data.speed],
      ["aStop", data.stop],
    ] as const) {
      const buffer = gl.createBuffer();
      if (!buffer) continue;
      particleBuffers.push(buffer);
      gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
      gl.bufferData(gl.ARRAY_BUFFER, values, gl.STATIC_DRAW);
      const location = gl.getAttribLocation(particles, name);
      if (location >= 0) {
        gl.enableVertexAttribArray(location);
        gl.vertexAttribPointer(location, 1, gl.FLOAT, false, 0, 0);
      }
    }
    gl.bindVertexArray(null);

    // --------------------------------------------------------------- uniforms

    const uniform = (program: WebGLProgram, name: string) =>
      gl.getUniformLocation(program, name);

    const u = {
      feedbackPrev: uniform(feedback, "uPrev"),
      feedbackVanish: uniform(feedback, "uVanish"),
      feedbackFade: uniform(feedback, "uFade"),
      feedbackZoom: uniform(feedback, "uZoom"),

      tunnelVanish: uniform(tunnel, "uVanish"),
      tunnelDrift: uniform(tunnel, "uDrift"),
      tunnelTime: uniform(tunnel, "uTime"),
      tunnelAspect: uniform(tunnel, "uAspect"),

      pointTime: uniform(particles, "uTime"),
      pointVanish: uniform(particles, "uVanish"),
      pointDrift: uniform(particles, "uDrift"),
      pointAspect: uniform(particles, "uAspect"),
      pointScale: uniform(particles, "uPixelScale"),

      compositeScene: uniform(composite, "uScene"),
      compositeVanish: uniform(composite, "uVanish"),
      compositeTime: uniform(composite, "uTime"),
      compositeExposure: uniform(composite, "uExposure"),
    };

    // ----------------------------------------------------------------- state

    let front: Target | null = null;
    let back: Target | null = null;
    let cssWidth = 0;
    let cssHeight = 0;
    let aspect = 1;
    let pixelScale = 20;
    let pointerX = 0;
    let pointerY = 0;
    let driftX = 0;
    let driftY = 0;
    let opacity = -1;
    let frame = 0;
    let start = performance.now();
    let lost = false;

    const resize = () => {
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      cssWidth = window.innerWidth;
      cssHeight = window.innerHeight;
      canvas.style.width = `${cssWidth}px`;
      canvas.style.height = `${cssHeight}px`;
      canvas.width = Math.max(1, Math.floor(cssWidth * ratio));
      canvas.height = Math.max(1, Math.floor(cssHeight * ratio));
      aspect = cssWidth / Math.max(1, cssHeight);

      let wide = canvas.width * RENDER_SCALE;
      let tall = canvas.height * RENDER_SCALE;
      const over = (wide * tall) / PIXEL_BUDGET;
      if (over > 1) {
        const shrink = Math.sqrt(over);
        wide /= shrink;
        tall /= shrink;
      }
      const targetWidth = Math.max(2, Math.floor(wide));
      const targetHeight = Math.max(2, Math.floor(tall));
      pixelScale = targetHeight * 0.03;

      if (front) destroyTarget(gl, front);
      if (back) destroyTarget(gl, back);
      front = createTarget(gl, targetWidth, targetHeight, floatTargets);
      back = createTarget(gl, targetWidth, targetHeight, floatTargets);

      for (const target of [front, back]) {
        gl.bindFramebuffer(gl.FRAMEBUFFER, target.framebuffer);
        gl.clearColor(0, 0, 0, 1);
        gl.clear(gl.COLOR_BUFFER_BIT);
      }
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    };

    const render = (now: number) => {
      if (lost || !front || !back) return;
      const time = (now - start) / 1000;

      driftX += (pointerX * 0.018 - driftX) * 0.045;
      driftY += (pointerY * 0.012 - driftY) * 0.045;

      // 1 + 2 + 3 — build this frame in the offscreen target.
      gl.bindFramebuffer(gl.FRAMEBUFFER, back.framebuffer);
      gl.viewport(0, 0, back.width, back.height);
      gl.disable(gl.BLEND);

      gl.useProgram(feedback);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, front.texture);
      gl.uniform1i(u.feedbackPrev, 0);
      gl.uniform2f(u.feedbackVanish, VANISH_X, VANISH_Y);
      gl.uniform1f(u.feedbackFade, still ? 0 : TRAIL_FADE);
      gl.uniform1f(u.feedbackZoom, TRAIL_ZOOM);
      gl.bindVertexArray(quadVao);
      gl.drawArrays(gl.TRIANGLES, 0, 3);

      gl.enable(gl.BLEND);
      gl.blendFunc(gl.ONE, gl.ONE);

      gl.useProgram(tunnel);
      gl.uniform2f(u.tunnelVanish, VANISH_X, VANISH_Y);
      gl.uniform2f(u.tunnelDrift, driftX, driftY);
      gl.uniform1f(u.tunnelTime, time);
      gl.uniform1f(u.tunnelAspect, aspect);
      gl.drawArrays(gl.TRIANGLES, 0, 3);

      gl.useProgram(particles);
      gl.uniform1f(u.pointTime, time);
      gl.uniform2f(u.pointVanish, VANISH_X, VANISH_Y);
      gl.uniform2f(u.pointDrift, driftX, driftY);
      gl.uniform1f(u.pointAspect, aspect);
      gl.uniform1f(u.pointScale, pixelScale);
      gl.bindVertexArray(particleVao);
      gl.drawArrays(gl.POINTS, 0, PARTICLES);

      // 4 — through the lens, to the screen.
      gl.disable(gl.BLEND);
      gl.bindFramebuffer(gl.FRAMEBUFFER, null);
      gl.viewport(0, 0, canvas.width, canvas.height);
      gl.useProgram(composite);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, back.texture);
      gl.uniform1i(u.compositeScene, 0);
      gl.uniform2f(u.compositeVanish, VANISH_X, VANISH_Y);
      gl.uniform1f(u.compositeTime, time);
      gl.uniform1f(u.compositeExposure, 1.0);
      gl.bindVertexArray(quadVao);
      gl.drawArrays(gl.TRIANGLES, 0, 3);
      gl.bindVertexArray(null);

      const swap = front;
      front = back;
      back = swap;

      // Full strength behind the hero, then out of the reader's way. A fixed
      // canvas cannot know where the text is, so it yields the moment there is
      // something to read.
      const scrolled = window.scrollY / (window.innerHeight * 0.85);
      const wanted = Math.max(0.18, 1 - scrolled * 0.82);
      if (Math.abs(wanted - opacity) > 0.005) {
        opacity = wanted;
        canvas.style.opacity = String(wanted);
      }
    };

    const loop = (now: number) => {
      render(now);
      frame = window.requestAnimationFrame(loop);
    };

    const play = () => {
      if (frame || lost || still) return;
      frame = window.requestAnimationFrame(loop);
    };
    const pause = () => {
      if (!frame) return;
      window.cancelAnimationFrame(frame);
      frame = 0;
    };

    const onPointer = (event: PointerEvent) => {
      pointerX = (event.clientX / window.innerWidth - 0.5) * 2;
      pointerY = -(event.clientY / window.innerHeight - 0.5) * 2;
    };
    const onVisibility = () => (document.hidden ? pause() : play());
    const onLost = (event: Event) => {
      event.preventDefault();
      lost = true;
      pause();
    };
    const onRestored = () => {
      lost = false;
      start = performance.now();
      resize();
      play();
    };

    resize();
    window.addEventListener("resize", resize);
    canvas.addEventListener("webglcontextlost", onLost);
    canvas.addEventListener("webglcontextrestored", onRestored);

    if (still) {
      // One frame, held. Reduced motion means no motion, not slow motion.
      render(performance.now());
      render(performance.now());
    } else {
      window.addEventListener("pointermove", onPointer, { passive: true });
      document.addEventListener("visibilitychange", onVisibility);
      play();
    }

    return () => {
      pause();
      window.removeEventListener("resize", resize);
      window.removeEventListener("pointermove", onPointer);
      document.removeEventListener("visibilitychange", onVisibility);
      canvas.removeEventListener("webglcontextlost", onLost);
      canvas.removeEventListener("webglcontextrestored", onRestored);
      if (front) destroyTarget(gl, front);
      if (back) destroyTarget(gl, back);
      for (const buffer of particleBuffers) gl.deleteBuffer(buffer);
      if (quadBuffer) gl.deleteBuffer(quadBuffer);
      if (quadVao) gl.deleteVertexArray(quadVao);
      if (particleVao) gl.deleteVertexArray(particleVao);
      for (const program of [feedback, tunnel, particles, composite]) {
        gl.deleteProgram(program);
      }
    };
  }, []);

  return <canvas ref={ref} aria-hidden="true" className="pointer-events-none fixed inset-0 z-0" />;
}
