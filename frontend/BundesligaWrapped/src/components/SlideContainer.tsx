/**
 * SlideContainer — full-screen swipeable slide wrapper.
 *
 * Renders the correct slide component based on slide_type.
 * Supports tap navigation (left half = back, right half = forward)
 * and swipe gestures via GestureHandler.
 * Background uses LinearGradient from club colors.
 */

import React from 'react';
import { Pressable, StyleSheet, useWindowDimensions, View } from 'react-native';
import { LinearGradient } from 'expo-linear-gradient';
import { WrappedSlide } from '../types/wrapped';
import { getSlideGradient } from '../utils/colors';
import { ProgressBar } from './ProgressBar';
import { HeroSlide } from './slides/HeroSlide';
import { TopPlayerSlide } from './slides/TopPlayerSlide';
import { SeasonJourneySlide } from './slides/SeasonJourneySlide';
import { MomentSlide } from './slides/MomentSlide';
import { ShareSlide } from './slides/ShareSlide';

interface SlideContainerProps {
  /** All slides in the Wrapped experience */
  slides: WrappedSlide[];
  /** Currently active slide index */
  currentIndex: number;
  /** Navigate to next slide */
  onNext: () => void;
  /** Navigate to previous slide */
  onPrev: () => void;
  /** Jump to a specific slide */
  onGoTo: (index: number) => void;
}

export function SlideContainer({
  slides,
  currentIndex,
  onNext,
  onPrev,
  onGoTo,
}: SlideContainerProps) {
  const { width, height } = useWindowDimensions();
  const slide = slides[currentIndex];

  if (!slide) return null;

  const gradient = getSlideGradient(
    slide.club_color_hex,
    slide.club_color_secondary_hex
  );

  /** Tap left half → go back, tap right half → go forward */
  const handleTap = (event: { nativeEvent: { locationX: number } }) => {
    const tapX = event.nativeEvent.locationX;
    if (tapX < width * 0.3) {
      onPrev();
    } else {
      onNext();
    }
  };

  const renderSlide = () => {
    switch (slide.slide_type) {
      case 'hero':
        return <HeroSlide slide={slide} />;
      case 'player_bond':
        return <TopPlayerSlide slide={slide} />;
      case 'season_arc':
        return <SeasonJourneySlide slide={slide} />;
      case 'match_of_season':
        return <MomentSlide slide={slide} />;
      case 'goal_of_season':
        return <MomentSlide slide={slide} />;
      case 'share':
        return <ShareSlide slide={slide} onRestart={() => onGoTo(0)} />;
      // fan_dna and personal_angle use the same layout as hero
      case 'fan_dna':
      case 'personal_angle':
        return <HeroSlide slide={slide} />;
      default:
        return <HeroSlide slide={slide} />;
    }
  };

  return (
    <LinearGradient colors={gradient} style={[styles.container, { width, height }]}>
      {/* Progress bar at top */}
      <View style={styles.progressWrapper}>
        <ProgressBar total={slides.length} current={currentIndex} />
      </View>

      {/* Slide content — tappable for navigation */}
      <Pressable style={styles.slideArea} onPress={handleTap}>
        {renderSlide()}
      </Pressable>
    </LinearGradient>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
  },
  progressWrapper: {
    position: 'absolute',
    top: 48,
    left: 0,
    right: 0,
    zIndex: 10,
  },
  slideArea: {
    flex: 1,
  },
});
