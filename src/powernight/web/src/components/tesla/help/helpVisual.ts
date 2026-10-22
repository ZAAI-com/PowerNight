import type { HelpTab } from './helpContent';

export type HelpVisualMode = 'diagram' | 'screenshot';

/**
 * Which illustration the sign-in help shows. Both are kept so the choice can
 * be made later: change this default, or set localStorage
 * "powernight_help_visual" to "screenshot" or "diagram" to compare them in
 * the running app. Browsers without a screenshot fall back to the diagram.
 */
export const TESLA_HELP_VISUAL: HelpVisualMode = 'diagram';

export const HELP_VISUAL_STORAGE_KEY = 'powernight_help_visual';

export function resolveHelpVisual(): HelpVisualMode {
  try {
    const override = window.localStorage.getItem(HELP_VISUAL_STORAGE_KEY);
    if (override === 'diagram' || override === 'screenshot') return override;
  } catch {
    // Storage unavailable: use the default
  }
  return TESLA_HELP_VISUAL;
}

// Screenshots are optional files named <browser>-<panel>.png, for example
// chromium-console.png. Missing files simply fall back to the diagram, and
// Vite fingerprints the ones that exist into /assets.
const screenshotFiles = import.meta.glob('../../../assets/tesla-help/*.png', {
  eager: true,
  import: 'default',
}) as Record<string, string>;

export function screenshotFor(browser: HelpTab, files: Record<string, string> = screenshotFiles): string | null {
  const match = Object.entries(files).find(([path]) => path.endsWith(`/${browser}-console.png`));
  return match ? match[1] : null;
}
