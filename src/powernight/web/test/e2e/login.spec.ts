import { test, expect } from '@playwright/test';

test.describe('Login Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.route('**/api/v1/auth/check', async (route) => {
      await route.fulfill({
        status: 401,
        contentType: 'application/json',
        body: JSON.stringify({ error: 'Authentication required' }),
      });
    });
    await page.route('**/api/v1/config/timezone', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: { timezone: 'UTC', offset: '+00:00', name: 'UTC', current_time: null },
        }),
      });
    });
    await page.goto('/');
  });

  test('should display login form', async ({ page }) => {
    // Should redirect to login since not authenticated
    await expect(page).toHaveURL('/');
    
    // Check for login form elements
    await expect(page.getByRole('heading', { name: 'PowerNight' })).toBeVisible();
    await expect(page.getByText('Enter the API key configured for this PowerNight server')).toBeVisible();
    await expect(page.getByPlaceholder('Enter your API key')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  });

  test('should show error for invalid API key', async ({ page }) => {
    // Enter invalid API key
    await page.fill('input[name="api-key"]', 'invalid-key');
    await page.click('button[type="submit"]');
    
    // Should show error message
    await expect(page.getByText('Authentication Error')).toBeVisible();
  });

  test('should disable submit button when input is empty', async ({ page }) => {
    const submitButton = page.getByRole('button', { name: 'Sign In' });
    await expect(submitButton).toBeDisabled();
    
    // Type and clear input
    await page.fill('input[name="api-key"]', 'test');
    await expect(submitButton).toBeEnabled();
    
    await page.fill('input[name="api-key"]', '');
    await expect(submitButton).toBeDisabled();
  });
});
