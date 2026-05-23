/**
 * TopPlayerSlide — Slide 3: Player Bond.
 *
 * Shows the user's top player with their key stat and a fun fact.
 * Slides up from the bottom on entry.
 */

import React, { useEffect } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
} from 'react-native-reanimated';
import { WrappedSlide } from '../../types/wrapped';
import { AnimatedStat } from '../AnimatedStat';
import { SLIDE_UP_CONFIG } from '../../utils/animations';
import { getTextColor } from '../../utils/colors';

interface TopPlayerSlideProps {
  slide: WrappedSlide;
}

export function TopPlayerSlide({ slide }: TopPlayerSlideProps) {
  const translateY = useSharedValue(60);
  const opacity = useSharedValue(0);
  const textColor = getTextColor(slide.club_color_hex);

  useEffect(() => {
    translateY.value = withTiming(0, SLIDE_UP_CONFIG);
    opacity.value = withTiming(1, { duration: 600 });
  }, []);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: translateY.value }],
    opacity: opacity.value,
  }));

  const statTarget = parseInt(slide.stat_value, 10) || 0;

  return (
    <View style={styles.container}>
      <Animated.View style={[styles.content, animatedStyle]}>
        {/* Player media (video thumbnail or placeholder) */}
        {slide.media_url ? (
          <Image
            source={{ uri: slide.media_url }}
            style={styles.playerImage}
            resizeMode="cover"
            accessibilityLabel={`${slide.headline} highlight`}
          />
        ) : (
          <View style={[styles.playerImage, styles.placeholder]} />
        )}

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
    width: '100%',
  },
  playerImage: {
    width: 120,
    height: 120,
    borderRadius: 60,
    marginBottom: 24,
  },
  placeholder: {
    backgroundColor: 'rgba(255, 255, 255, 0.15)',
  },
  headline: {
    fontSize: 32,
    fontWeight: '900',
    textAlign: 'center',
    marginBottom: 16,
  },
  subtext: {
    fontSize: 15,
    fontWeight: '400',
    textAlign: 'center',
    opacity: 0.8,
    marginTop: 16,
    lineHeight: 22,
  },
});
