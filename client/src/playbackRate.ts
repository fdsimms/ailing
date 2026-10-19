// Audio is synthesized once at normal speed; slower playback is the player's rate.
export const MIN_RATE = 0.7;
export const MAX_RATE = 1.0;
export const RATE_STEP = 0.1;

export function clampRate(rate: number): number {
  if (Number.isNaN(rate)) return MAX_RATE;
  const stepped = Math.round(rate / RATE_STEP) * RATE_STEP;
  return Math.min(MAX_RATE, Math.max(MIN_RATE, Number(stepped.toFixed(1))));
}

// The speeds the reader offers, slowest first.
export const RATES = [0.7, 0.8, 0.9, 1.0];
