/**
 * MomentSlide — Slide 4: Match of the Season.
 *
 * Shows the most dramatic match with result, venue, and atmosphere description.
 * Slides up on entry. Can display a highlight video thumbnail if available.
 */

import React, { useEffect } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
} from 'react-native-reanimated';
import { WrappedSlide } from '../../types/wrapped';
import { SLIDE_UP_CONFIG } from '../../utils/animations';
import { getTextColor } from '../../utils/colors';

interface MomentSlideProps {
  slide: WrappedSlide;
}

export function MomentSlide({ slide }: MomentSlideProps) {
  const translateY = useSharedValue(50);
  const opacity = useSharedValue(0);
  const textColor = getTextColor(slide.club_color_hex);

  useEffect(() => {
    translateY.value = withTiming(0, SLIDE_UP_CONFIG);
    opacity.value = withTiming(1, { duration: 700 });
  }, []);

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [{ translateY: translateY.value }],
    opacity: opacity.value,
  }));

  return (
    <View style={styles.container}>
      <Animated.View style={[styles.content, animatedStyle]}>
        {/* Highlight video thumbnail */}
        {slide.media_url ? (
          <Image
            source={{ uri: slide.media_url }}
            style={styles.thumbnail}
            resizeMode="cover"
            accessibilityLabel="Match highlight thumbnail"
          />
        ) : null}

        <Text style={[styles.headline, { color: textColor }]}>
          {slide.headline}
        </Text>

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
  thumbnail: {
    width: '100%',
    height: 180,
    borderRadius: 16,
    marginBottom: 32,
  },
  headline: {
    fontSize: 28,
    fontWeight: '900',
    textAlign: 'center',
    marginBottom: 16,
  },
  subtext: {
    fontSize: 16,
    fontWeight: '400',
    textAlign: 'center',
    opacity: 0.85,
    lineHeight: 24,
  },
});
