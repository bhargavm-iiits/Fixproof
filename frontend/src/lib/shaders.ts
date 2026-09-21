/**
 * The background's shaders.
 *
 * Geometry is solved analytically rather than raymarched: for each of sixteen
 * gate shells the ray is intersected with that shell's plane in closed form and
 * a 2D rounded-rectangle distance is evaluated there. Sixteen cheap iterations
 * instead of sixty-odd marching steps, for the same perspective and a far
 * kinder frame budget on integrated graphics.
 */

const COMMON = `
#define SPACING 1.15
#define FOCAL 1.35
#define ZNEAR 0.55
#define ZFAR 18.0

float hash21(vec2 p) {
  p = fract(p * vec2(123.34, 456.21));
  p += dot(p, p + 45.32);
  return fract(p.x * p.y);
}
`;

export const FULLSCREEN_VERT = `#version 300 es
in vec2 aPos;
out vec2 vUv;
void main() {
  vUv = aPos * 0.5 + 0.5;
  gl_Position = vec4(aPos, 0.0, 1.0);
}
`;

/** Previous frame, faded and pushed outward: the trails, and the sense of travel. */
export const FEEDBACK_FRAG = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 outColor;

uniform sampler2D uPrev;
uniform vec2 uVanish;
uniform float uFade;
uniform float uZoom;

void main() {
  vec2 uv = (vUv - uVanish) / uZoom + uVanish;
  float inside =
    step(0.0, uv.x) * step(uv.x, 1.0) *
    step(0.0, uv.y) * step(uv.y, 1.0);
  outColor = vec4(texture(uPrev, uv).rgb * uFade * inside, 1.0);
}
`;

export const TUNNEL_FRAG = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 outColor;

uniform vec2 uVanish;
uniform vec2 uDrift;
uniform float uTime;
uniform float uAspect;

${COMMON}

#define GATES 16

float roundedRect(vec2 p, vec2 b, float r) {
  vec2 d = abs(p) - b + r;
  return length(max(d, 0.0)) + min(max(d.x, d.y), 0.0) - r;
}

void main() {
  vec2 p = (vUv - uVanish - uDrift) * vec2(uAspect, 1.0);
  vec3 rd = normalize(vec3(p, FOCAL));

  float travel = uTime * 0.5;
  float offset = fract(travel);
  float base = floor(travel);

  vec3 col = vec3(0.0);

  for (int i = 0; i < GATES; i++) {
    float z = (float(i) + 1.0 - offset) * SPACING;
    vec2 hit = rd.xy * (z / rd.z);

    // The tunnel twists with depth, so the shells never read as a flat stack.
    float a = uTime * 0.06 + z * 0.038;
    float c = cos(a), s = sin(a);
    hit = mat2(c, -s, s, c) * hit;

    float d = roundedRect(hit, vec2(0.58), 0.16);

    // A hard filament plus a wide halo. The halo is what reads as volume.
    //
    // These look absurdly small, and have to be: the feedback loop settles at
    // input * 1/(1 - fade), so whatever is emitted here arrives on screen
    // roughly six times over. Emitting at "looks right for one frame" blows the
    // whole image out to white.
    float filament = exp(-abs(d) * 150.0) * 0.075;
    float halo = exp(-abs(d) * 9.0) * 0.016;

    // The absolute gate number, so the tinted shell is always the same gate as
    // it travels toward the camera: the third, the one that catches cheating.
    float gate = mod(base + float(i), 9.0);
    vec3 tint = abs(gate - 2.0) < 0.5
      ? vec3(1.00, 0.42, 0.36)
      : vec3(0.72, 0.93, 0.32);

    float fog = 1.0 / (1.0 + z * z * 0.10);
    float born = smoothstep(0.0, 1.8, z);

    col += tint * (filament + halo) * fog * born;
  }

  // The container waiting at the end of it.
  float r = length(p);
  float pulse = 0.86 + 0.14 * sin(uTime * 1.6);
  col += vec3(0.80, 0.99, 0.42) * exp(-r * 13.0) * 0.075 * pulse;
  col += vec3(0.26, 0.50, 0.24) * exp(-r * 3.2) * 0.013 * pulse;

  // Dither, so an 8-bit target does not band across the halos.
  col += (hash21(gl_FragCoord.xy + fract(uTime)) - 0.5) * 0.004;

  outColor = vec4(col, 1.0);
}
`;

export const PARTICLE_VERT = `#version 300 es
precision highp float;

in float aPhase;
in float aAngle;
in float aRadius;
in float aSpeed;
in float aStop;

uniform float uTime;
uniform vec2 uVanish;
uniform vec2 uDrift;
uniform float uAspect;
uniform float uPixelScale;

out vec3 vColor;
out float vAlpha;

${COMMON}

void main() {
  float t = fract(aPhase + uTime * aSpeed);
  float z = mix(ZNEAR, ZFAR, t);

  float a = aAngle + uTime * 0.06 + z * 0.038;
  vec2 world = vec2(cos(a), sin(a)) * aRadius;

  float scale = FOCAL / z;
  vec2 screen = uVanish + uDrift + (world * scale) / vec2(uAspect, 1.0);
  gl_Position = vec4(screen * 2.0 - 1.0, 0.0, 1.0);

  // aStop above 1 means this one is never stopped: it reaches the container.
  float survivor = step(1.0, aStop);
  float over = t - aStop;
  float stopped = step(0.0, over) * (1.0 - survivor);
  float flash = exp(-max(over, 0.0) * 26.0);
  float arrive = smoothstep(0.82, 1.0, t) * survivor;

  vec3 flying = vec3(0.88, 0.92, 0.86);
  vec3 dying = vec3(1.00, 0.40, 0.34);
  vec3 winner = vec3(0.81, 0.98, 0.28);
  vColor = mix(mix(flying, dying, stopped), winner, arrive);

  float entering = smoothstep(0.0, 0.07, t);
  float leaving = 1.0 - smoothstep(0.90, 1.0, t) * (1.0 - survivor);
  vAlpha = entering * leaving * mix(1.0, flash, stopped) * (0.30 + 0.70 * (1.0 - t));
  vAlpha += arrive * 0.85;

  float swell = 1.0 + stopped * (1.0 - flash) * 3.2 + arrive * 2.2;
  gl_PointSize = clamp(scale * uPixelScale * swell, 1.0, 190.0);
}
`;

export const PARTICLE_FRAG = `#version 300 es
precision highp float;
in vec3 vColor;
in float vAlpha;
out vec4 outColor;

void main() {
  vec2 c = gl_PointCoord - 0.5;
  float d = dot(c, c);
  if (d > 0.25) discard;
  // Scaled for the same reason the tunnel is: this lands in a feedback buffer.
  float fall = exp(-d * 26.0);
  outColor = vec4(vColor * fall * vAlpha * 0.16, 1.0);
}
`;

/** Exposure, filmic tone map, chromatic aberration, vignette, grain. */
export const COMPOSITE_FRAG = `#version 300 es
precision highp float;
in vec2 vUv;
out vec4 outColor;

uniform sampler2D uScene;
uniform vec2 uVanish;
uniform float uTime;
uniform float uExposure;

${COMMON}

vec3 tonemap(vec3 x) {
  return clamp((x * (2.51 * x + 0.03)) / (x * (2.43 * x + 0.59) + 0.14), 0.0, 1.0);
}

void main() {
  vec2 d = vUv - uVanish;
  float r = length(d);

  // Lens dispersion, stronger toward the edges where a real lens disperses most.
  float spread = 0.004 * r * r;
  vec3 col = vec3(
    texture(uScene, vUv - d * spread).r,
    texture(uScene, vUv).g,
    texture(uScene, vUv + d * spread).b
  );

  col = tonemap(col * uExposure);
  col *= 1.0 - smoothstep(0.40, 1.08, r) * 0.88;
  col += (hash21(vUv * 900.0 + fract(uTime) * 77.0) - 0.5) * 0.020;

  outColor = vec4(max(col, 0.0), 1.0);
}
`;
