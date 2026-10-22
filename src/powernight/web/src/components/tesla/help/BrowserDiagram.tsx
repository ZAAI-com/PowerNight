import React from 'react';
import type { HelpTab } from './helpContent';

interface DiagramStyle {
  devtoolsTabs: string[];
  message: string;
  tabBar: string;
}

const STYLES: Record<HelpTab, DiagramStyle> = {
  chromium: {
    devtoolsTabs: ['Elements', 'Console', 'Network'],
    message: "Failed to launch 'tesla://auth/callback?code=...&state=...'",
    tabBar: '#e5e7eb',
  },
  safari: {
    devtoolsTabs: ['Elements', 'Console', 'Network'],
    message: 'tesla://auth/callback?code=...&state=...',
    tabBar: '#f3f4f6',
  },
  firefox: {
    devtoolsTabs: ['Inspector', 'Console', 'Network'],
    message: 'Prevented navigation to "tesla://auth/callback?code=..."',
    tabBar: '#ddd6fe',
  },
};

interface BrowserDiagramProps {
  browser: HelpTab;
  label: string;
}

/** Schematic of the browser's developer tools with the line to copy highlighted. */
export const BrowserDiagram: React.FC<BrowserDiagramProps> = ({ browser, label }) => {
  const style = STYLES[browser];
  return (
    <svg
      viewBox="0 0 480 280"
      role="img"
      aria-label={`${label}: the developer tools Console shows a line starting with tesla://auth/callback. Copy that whole line.`}
      className="w-full max-w-lg h-auto"
    >
      <rect x="1" y="1" width="478" height="278" rx="10" fill="#ffffff" stroke="#d1d5db" strokeWidth="2" />
      <path d="M1 11 a10 10 0 0 1 10 -10 h458 a10 10 0 0 1 10 10 v25 h-478 z" fill={style.tabBar} />
      {browser === 'safari' ? (
        <g>
          <circle cx="18" cy="18" r="5" fill="#f87171" />
          <circle cx="34" cy="18" r="5" fill="#fbbf24" />
          <circle cx="50" cy="18" r="5" fill="#34d399" />
        </g>
      ) : (
        <rect x="14" y="8" width="120" height="22" rx="6" fill="#ffffff" />
      )}
      <rect x="150" y="9" width="300" height="20" rx="10" fill="#ffffff" stroke="#e5e7eb" />
      <text x="164" y="23" fontSize="11" fill="#6b7280" fontFamily="ui-sans-serif, system-ui">
        auth.tesla.com
      </text>

      <text x="240" y="82" fontSize="12" fill="#9ca3af" textAnchor="middle" fontFamily="ui-sans-serif, system-ui">
        Blank page after signing in to Tesla
      </text>

      <rect x="2" y="120" width="476" height="158" fill="#f9fafb" />
      <line x1="2" y1="120" x2="478" y2="120" stroke="#d1d5db" />
      {style.devtoolsTabs.map((tab, index) => {
        const x = 16 + index * 86;
        const active = tab === 'Console';
        return (
          <g key={tab}>
            <text
              x={x}
              y="140"
              fontSize="11"
              fontWeight={active ? 700 : 400}
              fill={active ? '#1d4ed8' : '#4b5563'}
              fontFamily="ui-sans-serif, system-ui"
            >
              {tab}
            </text>
            {active && <rect x={x} y="145" width="48" height="2" fill="#1d4ed8" />}
          </g>
        );
      })}
      <line x1="2" y1="150" x2="478" y2="150" stroke="#e5e7eb" />

      <text x="14" y="170" fontSize="10" fill="#9ca3af" fontFamily="ui-monospace, monospace">
        Navigated to auth.tesla.com/oauth2/v3/authorize
      </text>
      <rect x="8" y="180" width="464" height="26" rx="4" fill="#fef2f2" stroke="#dc2626" strokeWidth="2" />
      <text x="16" y="197" fontSize="10.5" fill="#b91c1c" fontFamily="ui-monospace, monospace">
        {style.message}
      </text>

      <path d="M300 250 L300 214" stroke="#1d4ed8" strokeWidth="2" markerEnd="url(#tesla-help-arrow)" />
      <defs>
        <marker id="tesla-help-arrow" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto">
          <path d="M0 0 L8 4 L0 8 z" fill="#1d4ed8" />
        </marker>
      </defs>
      <text x="310" y="256" fontSize="12" fontWeight={700} fill="#1d4ed8" fontFamily="ui-sans-serif, system-ui">
        Copy this whole line
      </text>
    </svg>
  );
};

export default BrowserDiagram;
