import { test, expect } from '@playwright/test';

test.describe('Login Page', () => {
  test('should display login form', async ({ page }) => {
    await page.goto('/');
    
    // Should redirect to login since not authenticated
    await expect(page).toHaveURL('/');
    
    // Check for login form elements
    await expect(page.getByText('PowerNight')).toBeVisible();
    await expect(page.getByText('Tesla Powerwall Automation System')).toBeVisible();
    await expect(page.getByPlaceholder('Enter your API key')).toBeVisible();
    await expect(page.getByRole('button', { name: 'Sign In' })).toBeVisible();
  });

  test('should show error for invalid API key', async ({ page }) => {
    await page.goto('/');
    
    // Enter invalid API key
    await page.fill('input[name="api-key"]', 'invalid-key');
    await page.click('button[type="submit"]');
    
    // Should show error message
    await expect(page.getByText('Authentication Error')).toBeVisible();
  });

  test('should disable submit button when input is empty', async ({ page }) => {
    await page.goto('/');
    
    const submitButton = page.getByRole('button', { name: 'Sign In' });
    await expect(submitButton).toBeDisabled();
    
    // Type and clear input
    await page.fill('input[name="api-key"]', 'test');
    await expect(submitButton).toBeEnabled();
    
    await page.fill('input[name="api-key"]', '');
    await expect(submitButton).toBeDisabled();
  });
});
