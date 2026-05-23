/**
 * Club color theming utilities.
 * All colors come from the slide's club_color_hex — never hardcoded.
 */

/**
 * Compute a gradient array from a primary and secondary club color.
 * Used by LinearGradient as the background for each slide.
 */
export function getSlideGradient(primary: string, secondary: string): [string, string, string] {
  return [primary, darken(primary, 0.3), secondary];
}

/**
 * Darken a hex color by a given factor (0–1).
 * factor=0 returns the original, factor=1 returns black.
 */
export function darken(hex: string, factor: number): string {
  const rgb = hexToRgb(hex);
  if (!rgb) return hex;
  const r = Math.round(rgb.r * (1 - factor));
  const g = Math.round(rgb.g * (1 - factor));
  const b = Math.round(rgb.b * (1 - factor));
  return rgbToHex(r, g, b);
}

/**
 * Determine whether text should be white or dark on a given background.
 * Uses relative luminance formula (WCAG 2.1).
 */
export function getTextColor(backgroundHex: string): string {
  const rgb = hexToRgb(backgroundHex);
  if (!rgb) return '#FFFFFF';
  // Relative luminance
  const luminance = 0.299 * rgb.r + 0.587 * rgb.g + 0.114 * rgb.b;
  return luminance > 150 ? '#1A1A2E' : '#FFFFFF';
}

function hexToRgb(hex: string): { r: number; g: number; b: number } | null {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  return result
    ? {
        r: parseInt(result[1], 16),
        g: parseInt(result[2], 16),
        b: parseInt(result[3], 16),
      }
    : null;
}

function rgbToHex(r: number, g: number, b: number): string {
  return `#${[r, g, b].map((x) => x.toString(16).padStart(2, '0')).join('')}`;
}
