/**
 * ProgressBar — story-style progress dots at the top of the screen.
 *
 * Shows N segments. The active segment fills over SLIDE_DURATION_MS.
 * Completed segments are fully white, upcoming are white at 40% opacity.
 */

import React, { useEffect } from 'react';
import { StyleSheet, View } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  Easing,
} from 'react-native-reanimated';
import { SLIDE_DURATION_MS } from '../utils/animations';

interface ProgressBarProps {
  /** Total number of slides */
  total: number;
  /** Currently active slide index (0-based) */
  current: number;
}

export function ProgressBar({ total, current }: ProgressBarProps) {
  return (
    <View style={styles.container}>
      {Array.from({ length: total }, (_, i) => (
        <ProgressSegment key={i} index={i} current={current} />
      ))}
    </View>
  );
}

interface SegmentProps {
  index: number;
  current: number;
}

function ProgressSegment({ index, current }: SegmentProps) {
  const fillWidth = useSharedValue(0);

  useEffect(() => {
    if (index === current) {
      // Active: animate fill from 0 to 100%
      fillWidth.value = 0;
      fillWidth.value = withTiming(1, {
        duration: SLIDE_DURATION_MS,
        easing: Easing.linear,
      });
    } else if (index < current) {
      // Completed: fully filled
      fillWidth.value = 1;
    } else {
      // Upcoming: empty
      fillWidth.value = 0;
    }
  }, [current, index]);

  const fillStyle = useAnimatedStyle(() => ({
    width: `${fillWidth.value * 100}%`,
  }));

  return (
    <View style={styles.segment}>
      <Animated.View style={[styles.fill, fillStyle]} />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    paddingHorizontal: 8,
    paddingTop: 12,
    gap: 4,
  },
  segment: {
    flex: 1,
    height: 3,
    borderRadius: 1.5,
    backgroundColor: 'rgba(255, 255, 255, 0.3)',
    overflow: 'hidden',
  },
  fill: {
    height: '100%',
    backgroundColor: '#FFFFFF',
    borderRadius: 1.5,
  },
});
