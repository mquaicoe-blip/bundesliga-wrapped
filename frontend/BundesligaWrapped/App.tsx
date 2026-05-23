/**
 * App.tsx — Entry point for Bundesliga Wrapped.
 *
 * Renders the WrappedScreen with gesture handler provider.
 */

import React from 'react';
import { GestureHandlerRootView } from 'react-native-gesture-handler';
import { StyleSheet } from 'react-native';
import { WrappedScreen } from './src/screens/WrappedScreen';

export default function App() {
  return (
    <GestureHandlerRootView style={styles.root}>
      <WrappedScreen />
    </GestureHandlerRootView>
  );
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
  },
});
