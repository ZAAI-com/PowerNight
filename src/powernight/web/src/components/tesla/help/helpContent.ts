import type { HelpBrowser } from '../../../utils/teslaSetup';

export type HelpTab = Exclude<HelpBrowser, 'other'>;

export interface BrowserHelp {
  id: HelpTab;
  label: string;
  /** Developer tools panel the result shows up in, for the diagram */
  panel: string;
  steps: string[];
  fallback: string;
}

/*
 * Browsers cannot open tesla:// links, and a web page cannot read another
 * site's tab, so the result has to be copied by hand. Keep this wording in
 * sync with a real sign-in whenever browsers change their developer tools.
 */
export const BROWSER_HELP: Record<HelpTab, BrowserHelp> = {
  chromium: {
    id: 'chromium',
    label: 'Chrome / Edge',
    panel: 'Console',
    steps: [
      'In the Tesla tab, open the developer tools before you sign in: Cmd+Option+J on a Mac, Ctrl+Shift+J on Windows or Linux.',
      'Sign in to Tesla, including any verification code. Afterwards the page stays blank: Tesla sends the result to a tesla:// link that only the Tesla app can open.',
      'In the Console, find the message "Failed to launch \'tesla://auth/callback?code=...\'". Select the whole message and copy it.',
      'Come back to this tab and paste it below. PowerNight picks out the result by itself.',
    ],
    fallback: 'No message? Open the Network tab, select the last request to auth.tesla.com and copy its "location" response header.',
  },
  safari: {
    id: 'safari',
    label: 'Safari',
    panel: 'Console',
    steps: [
      'Turn on the Develop menu once: Safari > Settings > Advanced > "Show features for web developers".',
      'In the Tesla tab, choose Develop > Show JavaScript Console (Cmd+Option+C) before you sign in.',
      'Sign in to Tesla. Safari then says it cannot open the page, because tesla:// links only work in the Tesla app.',
      'In the Console, copy the address that starts with tesla://auth/callback?code= and paste it below.',
    ],
    fallback: 'No address in the Console? In the Network tab, select the last request to auth.tesla.com and copy its "Location" response header.',
  },
  firefox: {
    id: 'firefox',
    label: 'Firefox',
    panel: 'Console',
    steps: [
      'In the Tesla tab, open the Web Console before you sign in: Cmd+Option+K on a Mac, Ctrl+Shift+K on Windows or Linux.',
      'Sign in to Tesla. Firefox may say that it does not know how to open the address.',
      'In the Console, find the message that mentions tesla://auth/callback?code= and copy the whole line.',
      'Paste it below.',
    ],
    fallback: 'No message? Open the Network tab, select the last request to auth.tesla.com and copy its "Location" response header.',
  },
};

export const HELP_TABS: HelpTab[] = ['chromium', 'safari', 'firefox'];
