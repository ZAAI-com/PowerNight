import { test, expect } from '@playwright/test';

for (const authEnabled of [false, true]) {
  test(`Tesla setup remains accessible with web auth ${authEnabled ? 'enabled' : 'disabled'}`, async ({ page }) => {
    const apiKey = 'valid-app-key';
    if (authEnabled) {
      await page.addInitScript((key) => localStorage.setItem('powernight_api_key', key), apiKey);
    }

    let siteRequests = 0;
    await page.route('**/api/**', async (route) => {
      const path = new URL(route.request().url()).pathname;
      const validKey = route.request().headers()['x-api-key'] === apiKey;
      if (authEnabled && !validKey) {
        await route.fulfill({ status: 401, json: { success: false, error: 'Authentication required' } });
        return;
      }

      if (path === '/api/auth/site-details') {
        siteRequests++;
        await route.fulfill({ status: 503, json: {
          success: false,
          error: 'No valid authentication token available',
          code: 'TESLA_AUTH_REQUIRED',
          message: 'Connect or reconnect your Tesla account in Settings.',
        } });
      } else if (path === '/api/v1/health') {
        await route.fulfill({ json: { status: 'healthy' } });
      } else if (path === '/api/v1/config/timezone') {
        await route.fulfill({ json: { success: true, data: {
          timezone: 'UTC', offset: '+00:00', name: 'UTC', current_time: null,
        } } });
      } else if (path === '/api/auth/tesla/info') {
        await route.fulfill({ json: { success: true, data: { authenticated: false } } });
      } else if (path === '/api/v1/config/timezones') {
        await route.fulfill({ json: { success: true, data: { timezones: [] } } });
      } else if (path === '/api/v1/version-info.json') {
        await route.fulfill({ json: {
          application: 'PowerNight', version: '2.0.0', build_timestamp: '',
          python_version: '3.13', node_version: '24', npm_version: '11',
          backend_dependencies: {}, frontend_dependencies: {},
        } });
      } else {
        await route.fulfill({ json: { success: true } });
      }
    });

    await page.goto('/');
    await expect(page.getByRole('heading', { name: 'Dashboard', exact: true })).toBeVisible();
    await expect(page.getByText('Connect or reconnect your Tesla account in Settings.')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign In' })).toHaveCount(0);

    await page.getByRole('button', { name: 'Update Data' }).click();
    await expect.poll(() => siteRequests).toBeGreaterThanOrEqual(2);
    await expect(page.getByRole('button', { name: 'Update Data' })).toBeEnabled();
    expect(await page.evaluate(() => localStorage.getItem('powernight_api_key'))).toBe(authEnabled ? apiKey : null);

    const settingsLink = page.getByRole('link', { name: 'Settings' });
    if (!await settingsLink.isVisible()) {
      await page.getByRole('button', { name: 'Toggle navigation menu' }).click();
    }
    await page.getByRole('link', { name: 'Settings' }).filter({ visible: true }).click();
    await expect(page).toHaveURL(/\/settings$/);
    await expect(page.getByLabel('Tesla Account Email', { exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Connect', exact: true })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign In' })).toHaveCount(0);
  });
}
