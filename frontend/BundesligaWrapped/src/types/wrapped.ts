/**
 * TypeScript interfaces matching the Python WrappedSlide dataclass and related types.
 * These define the contract between the backend pipeline and the React Native frontend.
 */

/** Narrative tone — matches Python Literal["commentator", "analyst", "fan"] */
export type Tone = 'commentator' | 'analyst' | 'fan';

/** Slide type — maps to the 8-slide sequence */
export type SlideType =
  | 'hero'
  | 'fan_dna'
  | 'player_bond'
  | 'goal_of_season'
  | 'match_of_season'
  | 'season_arc'
  | 'personal_angle'
  | 'share';

/** Animation type hint for the slide renderer */
export type AnimationType = 'counter' | 'fade' | 'slide_up' | 'pulse';

/**
 * A single Wrapped slide — the primary data unit consumed by the frontend.
 * Matches the JSON output from backend/pipeline/slide_assembler.py.
 */
export interface WrappedSlide {
  slide_id: string;
  slide_type: SlideType;
  headline: string;
  subtext: string;
  stat_value: string;
  stat_label: string;
  media_url: string;
  media_type: 'image' | 'video_thumbnail' | 'none';
  club_color_hex: string;
  club_color_secondary_hex: string;
  animation_type: AnimationType;
  tone: Tone;
}

/** Response shape from the wrapped.json endpoint */
export type WrappedResponse = WrappedSlide[];

/** Loading state for the useWrappedData hook */
export interface WrappedDataState {
  slides: WrappedSlide[];
  loading: boolean;
  error: string | null;
}
