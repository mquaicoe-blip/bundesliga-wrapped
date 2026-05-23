/**
 * Reanimated 2 animation presets for Wrapped slides.
 * Each preset returns worklet-compatible config objects.
 */

import { withTiming, withSpring, Easing } from 'react-native-reanimated';

/** Fade-in animation config (used by hero and share slides) */
export const FADE_IN_CONFIG = {
  duration: 800,
  easing: Easing.out(Easing.cubic),
};

/** Slide-up animation config (used by player and moment slides) */
export const SLIDE_UP_CONFIG = {
  duration: 600,
  easing: Easing.out(Easing.back(1.2)),
};

/** Counter animation duration in ms (used by stat counters) */
export const COUNTER_DURATION = 2000;

/** Pulse animation config (used by personal angle slide) */
export const PULSE_CONFIG = {
  damping: 8,
  stiffness: 100,
};

/** Auto-advance timer per slide in ms */
export const SLIDE_DURATION_MS = 6000;

/** Number of slides in the Wrapped experience */
export const TOTAL_SLIDES = 8;
