import React, { useMemo, useState } from 'react';
import { detectBrowser } from '../../utils/teslaSetup';
import { BrowserDiagram } from './help/BrowserDiagram';
import { BROWSER_HELP, HELP_TABS, type HelpTab } from './help/helpContent';
import { resolveHelpVisual, screenshotFor } from './help/helpVisual';

interface TeslaSignInHelpProps {
  userAgent?: string;
  /** Overrides the configured diagram/screenshot choice (tests, previews) */
  visual?: 'diagram' | 'screenshot';
  screenshots?: Record<string, string>;
}

/** Browser-specific steps for copying the tesla:// result out of the developer tools. */
export const TeslaSignInHelp: React.FC<TeslaSignInHelpProps> = ({ userAgent, visual, screenshots }) => {
  const detected = useMemo(
    () => detectBrowser(userAgent ?? (typeof navigator !== 'undefined' ? navigator.userAgent : '')),
    [userAgent],
  );
  const [selected, setSelected] = useState<HelpTab>(detected === 'other' ? 'chromium' : detected);
  const mode = visual ?? resolveHelpVisual();
  const help = BROWSER_HELP[selected];
  const screenshot = mode === 'screenshot' ? screenshotFor(selected, screenshots) : null;

  return (
    <div className="space-y-3">
      {detected === 'other' && (
        <p className="text-sm text-yellow-800 bg-yellow-50 border border-yellow-200 rounded-md p-3">
          Phones and tablets cannot show the developer tools needed here. Use a computer, or sign in with
          tokens from pypowerwall instead.
        </p>
      )}
      <div role="tablist" aria-label="Browser" className="flex flex-wrap gap-2">
        {HELP_TABS.map((tab) => (
          <button
            key={tab}
            type="button"
            role="tab"
            id={`tesla-help-tab-${tab}`}
            aria-selected={selected === tab}
            aria-controls="tesla-help-panel"
            onClick={() => setSelected(tab)}
            className={`px-3 py-1.5 rounded-md text-sm border ${
              selected === tab
                ? 'bg-blue-600 text-white border-blue-600'
                : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'
            }`}
          >
            {BROWSER_HELP[tab].label}
          </button>
        ))}
      </div>
      <div
        role="tabpanel"
        id="tesla-help-panel"
        aria-labelledby={`tesla-help-tab-${selected}`}
        className="grid gap-4 md:grid-cols-2"
      >
        <div className="space-y-2">
          <ol className="list-decimal ml-5 space-y-1 text-sm text-gray-800 select-text">
            {help.steps.map((step) => (
              <li key={step}>{step}</li>
            ))}
          </ol>
          <p className="text-xs text-gray-600">{help.fallback}</p>
        </div>
        <div>
          {screenshot ? (
            <img
              src={screenshot}
              alt={`${help.label}: the developer tools Console with the tesla://auth/callback line to copy`}
              className="w-full max-w-lg rounded-md border border-gray-200"
            />
          ) : (
            <BrowserDiagram browser={selected} label={help.label} />
          )}
        </div>
      </div>
    </div>
  );
};

export default TeslaSignInHelp;
