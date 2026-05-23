/**
 * AnimatedStat — counting animation for numeric stats.
 *
 * Counts up from 0 to the target number using Reanimated 2.
 * Triggers on mount (when the slide becomes active).
 *
 * @example
 * <AnimatedStat target={220} label="times you showed up" />
 */

import React, { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedProps,
  withTiming,
  useDerivedValue,
  useAnimatedStyle,
  Easing,
} from 'react-native-reanimated';
import { COUNTER_DURATION } from '../utils/animations';

interface AnimatedStatProps {
  /** Target number to count up to */
  target: number;
  /** Label displayed below the number */
  label: string;
  /** Duration of the count animation in ms */
  duration?: number;
  /** Text color (from club theme) */
  color?: string;
}

const AnimatedText = Animated.createAnimatedComponent(Text);

export function AnimatedStat({
  target,
  label,
  duration = COUNTER_DURATION,
  color = '#FFFFFF',
}: AnimatedStatProps) {
  const progress = useSharedValue(0);

  useEffect(() => {
    progress.value = withTiming(1, {
      duration,
      easing: Easing.out(Easing.cubic),
    });
  }, [target, duration]);

  const displayValue = useDerivedValue(() => {
    return Math.round(progress.value * target).toString();
  });

  const animatedStyle = useAnimatedStyle(() => ({
    opacity: Math.min(progress.value * 2, 1),
    transform: [{ scale: 0.8 + progress.value * 0.2 }],
  }));

  return (
    <View style={styles.container}>
      <Animated.View style={animatedStyle}>
        <AnimatedText style={[styles.number, { color }]}>
          {displayValue.value}
        </AnimatedText>
      </Animated.View>
      <Text style={[styles.label, { color }]}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    alignItems: 'center',
    justifyContent: 'center',
    paddingVertical: 24,
  },
  number: {
    fontSize: 72,
    fontWeight: '900',
    letterSpacing: -2,
  },
  label: {
    fontSize: 18,
    fontWeight: '500',
    marginTop: 8,
    textAlign: 'center',
    opacity: 0.9,
  },
});
