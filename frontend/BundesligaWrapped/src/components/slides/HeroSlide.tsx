/**
 * HeroSlide — Slide 1: The opening identity card.
 *
 * Shows the club name, hero stat with counting animation, headline, and subtext.
 * Animated fade-in on entry.
 */

import React, { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
} from 'react-native-reanimated';
import { WrappedSlide } from '../../types/wrapped';
import { AnimatedStat } from '../AnimatedStat';
import { FADE_IN_CONFIG } from '../../utils/animations';
import { getTextColor } from '../../utils/colors';

interface HeroSlideProps {
  slide: WrappedSlide;
}

export function HeroSlide({ slide }: HeroSlideProps) {
  const opacity = useSharedValue(0);
  const translateY = useSharedValue(20);
  const textColor = getTextColor(slide.club_color_hex);

  useEffect(() => {
    opacity.value = withTiming(1, FADE_IN_CONFIG);
    translateY.value = withTiming(0, FADE_IN_CONFIG);
  }, []);

  const animatedStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
    transform: [{ translateY: translateY.value }],
  }));

  const statTarget = parseInt(slide.stat_value, 10) || 0;

  return (
    <View style={styles.container}>
      <Animated.View style={[styles.content, animatedStyle]}>
        <Text style={[styles.headline, { color: textColor }]}>
          {slide.headline}
        </Text>

        <AnimatedStat
          target={statTarget}
          label={slide.stat_label}
          color={textColor}
        />

        <Text style={[styles.subtext, { color: textColor }]}>
          {slide.subtext}
        </Text>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 32,
  },
  content: {
    alignItems: 'center',
  },
  headline: {
    fontSize: 28,
    fontWeight: '800',
    textAlign: 'center',
    marginBottom: 32,
  },
  subtext: {
    fontSize: 16,
    fontWeight: '400',
    textAlign: 'center',
    opacity: 0.85,
    marginTop: 24,
    lineHeight: 24,
  },
});
