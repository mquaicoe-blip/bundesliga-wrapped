/**
 * useSlideTimer — auto-advances slides every SLIDE_DURATION_MS.
 *
 * Returns the current slide index and control functions.
 * Pauses when the user manually navigates (resumes on next auto-advance).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { SLIDE_DURATION_MS } from '../utils/animations';

interface SlideTimerResult {
  /** Current active slide index (0-based) */
  currentIndex: number;
  /** Go to next slide (wraps to 0 at end) */
  next: () => void;
  /** Go to previous slide (stops at 0) */
  prev: () => void;
  /** Jump to a specific slide index */
  goTo: (index: number) => void;
  /** Whether the timer is running */
  isPlaying: boolean;
  /** Pause auto-advance */
  pause: () => void;
  /** Resume auto-advance */
  resume: () => void;
}

/**
 * Auto-advance timer for the Wrapped slide experience.
 *
 * @param totalSlides - Total number of slides
 * @param autoPlay - Whether to start auto-advancing immediately
 * @returns Control object with index and navigation functions
 */
export function useSlideTimer(totalSlides: number, autoPlay = true): SlideTimerResult {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(autoPlay);
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const next = useCallback(() => {
    setCurrentIndex((prev) => {
      if (prev >= totalSlides - 1) {
        // Stop at the last slide (share slide) — don't loop
        setIsPlaying(false);
        return prev;
      }
      return prev + 1;
    });
  }, [totalSlides]);

  const prev = useCallback(() => {
    setCurrentIndex((prev) => Math.max(0, prev - 1));
  }, []);

  const goTo = useCallback((index: number) => {
    setCurrentIndex(Math.max(0, Math.min(index, totalSlides - 1)));
  }, [totalSlides]);

  const pause = useCallback(() => setIsPlaying(false), []);
  const resume = useCallback(() => setIsPlaying(true), []);

  // Auto-advance timer
  useEffect(() => {
    if (isPlaying && totalSlides > 0) {
      timerRef.current = setInterval(next, SLIDE_DURATION_MS);
    }

    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
    };
  }, [isPlaying, next, totalSlides]);

  // Reset timer when user manually navigates
  useEffect(() => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
    if (isPlaying && totalSlides > 0) {
      timerRef.current = setInterval(next, SLIDE_DURATION_MS);
    }
  }, [currentIndex, isPlaying, next, totalSlides]);

  return { currentIndex, next, prev, goTo, isPlaying, pause, resume };
}
