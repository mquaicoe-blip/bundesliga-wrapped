/**
 * SeasonJourneySlide — Slide 5: Season Arc Narrative.
 *
 * Tells the story of the club's season in 2 sentences.
 * Uses a counter animation for any embedded stat.
 */

import React, { useEffect } from 'react';
import { StyleSheet, Text, View } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withDelay,
} from 'react-native-reanimated';
import { WrappedSlide } from '../../types/wrapped';
import { FADE_IN_CONFIG } from '../../utils/animations';
import { getTextColor } from '../../utils/colors';

interface SeasonJourneySlideProps {
  slide: WrappedSlide;
}

export function SeasonJourneySlide({ slide }: SeasonJourneySlideProps) {
  const headlineOpacity = useSharedValue(0);
  const textOpacity = useSharedValue(0);
  const textColor = getTextColor(slide.club_color_hex);

  useEffect(() => {
    headlineOpacity.value = withTiming(1, FADE_IN_CONFIG);
    textOpacity.value = withDelay(400, withTiming(1, { duration: 800 }));
  }, []);

  const headlineStyle = useAnimatedStyle(() => ({
    opacity: headlineOpacity.value,
  }));

  const textStyle = useAnimatedStyle(() => ({
    opacity: textOpacity.value,
  }));

  return (
    <View style={styles.container}>
      <Animated.View style={headlineStyle}>
        <Text style={[styles.headline, { color: textColor }]}>
          {slide.headline}
        </Text>
      </Animated.View>

      <Animated.View style={textStyle}>
        <Text style={[styles.narrative, { color: textColor }]}>
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
  headline: {
    fontSize: 26,
    fontWeight: '800',
    textAlign: 'center',
    marginBottom: 32,
  },
  narrative: {
    fontSize: 18,
    fontWeight: '400',
    textAlign: 'center',
    lineHeight: 28,
    opacity: 0.9,
  },
});
