/**
 * Shared motion tokens for AQI Sentinel.
 * Calm springs by default — interruptible, not bouncy.
 */
import type { Transition } from 'motion/react';

/** Default calm spring — use for buttons, cards, sheets. */
export const calmSpring: Transition = {
  type: 'spring',
  stiffness: 420,
  damping: 32,
  mass: 0.85,
};

/** Slightly softer for larger surfaces (panels, sheets). */
export const softSpring: Transition = {
  type: 'spring',
  stiffness: 320,
  damping: 34,
  mass: 1,
};

/** Instant press feedback scale. */
export const pressScale = 0.97;
export const hoverScale = 1.015;

/** Reduced-motion: disable spring transforms. */
export function useMotionSafe(): boolean {
  if (typeof window === 'undefined') return true;
  return !window.matchMedia('(prefers-reduced-motion: reduce)').matches;
}

export const fadeInUp = {
  initial: { opacity: 0, y: 10 },
  animate: { opacity: 1, y: 0 },
  exit: { opacity: 0, y: 6 },
  transition: calmSpring,
};
