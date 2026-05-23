/**
 * ShareSlide — Slide 7: Share your Wrapped.
 *
 * Shows the generated social caption, a share button, and a restart button.
 * Fade-in animation on entry.
 */

import React, { useEffect } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withTiming,
  withDelay,
} from 'react-native-reanimated';
import { WrappedSlide } from '../../types/wrapped';
import { ShareButton } from '../ShareButton';
import { FADE_IN_CONFIG } from '../../utils/animations';
import { getTextColor } from '../../utils/colors';

interface ShareSlideProps {
  slide: WrappedSlide;
  /** Callback to restart the Wrapped experience from slide 1 */
  onRestart: () => void;
}

export function ShareSlide({ slide, onRestart }: ShareSlideProps) {
  const opacity = useSharedValue(0);
  const buttonOpacity = useSharedValue(0);
  const textColor = getTextColor(slide.club_color_hex);

  useEffect(() => {
    opacity.value = withTiming(1, FADE_IN_CONFIG);
    buttonOpacity.value = withDelay(600, withTiming(1, { duration: 500 }));
  }, []);

  const contentStyle = useAnimatedStyle(() => ({
    opacity: opacity.value,
  }));

  const buttonStyle = useAnimatedStyle(() => ({
    opacity: buttonOpacity.value,
  }));

  return (
    <View style={styles.container}>
      <Animated.View style={[styles.content, contentStyle]}>
        <Text style={[styles.headline, { color: textColor }]}>
          {slide.headline}
        </Text>

        <View style={styles.captionBox}>
          <Text style={[styles.caption, { color: textColor }]}>
            {slide.subtext}
          </Text>
        </View>
      </Animated.View>

      <Animated.View style={[styles.actions, buttonStyle]}>
        <ShareButton caption={slide.subtext} color={textColor} />

        <Pressable
          style={styles.restartButton}
          onPress={onRestart}
          accessibilityRole="button"
          accessibilityLabel="Watch again"
        >
          <Text style={[styles.restartText, { color: textColor }]}>
            ↺ Watch Again
          </Text>
        </Pressable>
      </Animated.View>
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 32,
    paddingVertical: 60,
  },
  content: {
    alignItems: 'center',
    flex: 1,
    justifyContent: 'center',
  },
  headline: {
    fontSize: 24,
    fontWeight: '800',
    textAlign: 'center',
    marginBottom: 32,
  },
  captionBox: {
    backgroundColor: 'rgba(255, 255, 255, 0.1)',
    borderRadius: 16,
    padding: 20,
    width: '100%',
  },
  caption: {
    fontSize: 16,
    fontWeight: '400',
    textAlign: 'center',
    lineHeight: 24,
  },
  actions: {
    alignItems: 'center',
    width: '100%',
  },
  restartButton: {
    marginTop: 16,
    padding: 12,
  },
  restartText: {
    fontSize: 14,
    fontWeight: '600',
    opacity: 0.7,
  },
});
