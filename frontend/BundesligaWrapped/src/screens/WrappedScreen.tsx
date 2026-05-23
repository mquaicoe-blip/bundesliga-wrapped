/**
 * WrappedScreen — main screen that orchestrates the full Wrapped experience.
 *
 * Fetches data, shows loading state, then renders the SlideContainer
 * with auto-advancing timer and tap/swipe navigation.
 * StatusBar is hidden for immersive full-screen experience.
 */

import React from 'react';
import { StatusBar } from 'expo-status-bar';
import { View, StyleSheet } from 'react-native';
import { useWrappedData } from '../hooks/useWrappedData';
import { useSlideTimer } from '../hooks/useSlideTimer';
import { SlideContainer } from '../components/SlideContainer';
import { LoadingScreen } from './LoadingScreen';

interface WrappedScreenProps {
  /** DFL-CLU-* identifier */
  clubId?: string;
  /** User hash string */
  userId?: string;
}

export function WrappedScreen({
  clubId = 'DFL-CLU-00000G',
  userId = 'demo-user-001',
}: WrappedScreenProps) {
  const { slides, loading, error } = useWrappedData(clubId, userId);
  const { currentIndex, next, prev, goTo } = useSlideTimer(slides.length, !loading);

  if (loading || error) {
    return (
      <>
        <StatusBar hidden />
        <LoadingScreen error={error} />
      </>
    );
  }

  return (
    <View style={styles.container}>
      <StatusBar hidden />
      <SlideContainer
        slides={slides}
        currentIndex={currentIndex}
        onNext={next}
        onPrev={prev}
        onGoTo={goTo}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: '#1A1A2E',
  },
});
