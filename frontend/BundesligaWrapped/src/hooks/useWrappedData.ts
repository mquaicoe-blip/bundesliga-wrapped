/**
 * useWrappedData — fetches the wrapped.json payload from the backend.
 *
 * Reads the API base URL from EXPO_PUBLIC_API_URL env var.
 * Falls back to a local mock if the fetch fails.
 */

import { useEffect, useState } from 'react';
import { WrappedDataState, WrappedResponse, WrappedSlide } from '../types/wrapped';

const API_BASE = process.env.EXPO_PUBLIC_API_URL || 'http://localhost:8000';

/**
 * Fetch Wrapped slides for a given club and user.
 *
 * @param clubId - DFL-CLU-* identifier
 * @param userId - User hash string
 * @returns Object with slides array, loading boolean, and error string
 */
export function useWrappedData(clubId: string, userId: string): WrappedDataState {
  const [state, setState] = useState<WrappedDataState>({
    slides: [],
    loading: true,
    error: null,
  });

  useEffect(() => {
    let cancelled = false;

    async function fetchData() {
      try {
        const url = `${API_BASE}/wrapped/${clubId}/${userId}/wrapped.json`;
        const response = await fetch(url);

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data: WrappedResponse = await response.json();

        if (!cancelled) {
          setState({ slides: data, loading: false, error: null });
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : 'Unknown error';
          setState({ slides: [], loading: false, error: message });
        }
      }
    }

    fetchData();

    return () => {
      cancelled = true;
    };
  }, [clubId, userId]);

  return state;
}
