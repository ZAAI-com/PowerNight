import { test, expect } from '@playwright/test';

// Mock API responses
test.beforeEach(async ({ page }) => {
  // Mock API responses
  await page.route('**/api/v1/health', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        status: 'healthy',
        timestamp: '2023-01-01T00:00:00Z',
        version: '1.0.0',
        uptime_seconds: 3600,
        configuration: {
          loaded: true,
          automation_enabled: true,
          powerwall_configured: true
        }
      })
    });
  });

  await page.route('**/api/v1/status', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          status: 'healthy',
          timestamp: '2023-01-01T00:00:00Z',
          powerwall: {
            connected: true,
            backup_reserve_percentage: 20,
            last_communication: '2023-01-01T00:00:00Z',
            error: null,
            powerwall_name: 'Test Powerwall'
          },
          automation: {
            enabled: true,
            next_action: 'Set reserve to 30%',
            next_action_time: '2023-01-01T06:00:00Z'
          },
          configuration: {
            loaded: true,
            automation_enabled: true,
            powerwall_configured: true
          }
        }
      })
    });
  });

  await page.route('**/api/v1/backup-reserve', async (route) => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        success: true,
        data: {
          backup_reserve_percentage: 20,
          connected: true,
          demo_mode: false,
          powerwall_name: 'Test Powerwall',
          last_communication: '2023-01-01T00:00:00Z',
          error: null
        }
      })
    });
  });
});

test.describe('Dashboard', () => {
  test('should display dashboard after successful login', async ({ page }) => {
    // Mock successful authentication
    await page.route('**/api/v1/health', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ status: 'healthy' })
      });
    });

    // Go to login page
    await page.goto('/');
    
    // Fill in API key
    await page.fill('input[name="api-key"]', 'test-api-key');
    await page.click('button[type="submit"]');
    
    // Should redirect to dashboard
    await expect(page).toHaveURL('/dashboard');
    
    // Check dashboard elements
    await expect(page.getByText('Dashboard')).toBeVisible();
    await expect(page.getByText('System Status')).toBeVisible();
    await expect(page.getByText('Powerwall Status')).toBeVisible();
    await expect(page.getByText('Backup Reserve')).toBeVisible();
  });

  test('should display system status cards', async ({ page }) => {
    await page.goto('/dashboard');
    
    // Check status cards
    await expect(page.getByText('healthy')).toBeVisible();
    await expect(page.getByText('Connected')).toBeVisible();
    await expect(page.getByText('20%')).toBeVisible();
  });

  test('should show system information section', async ({ page }) => {
    await page.goto('/dashboard');
    
    // Check system information
    await expect(page.getByText('System Information')).toBeVisible();
    await expect(page.getByText('Configuration Status')).toBeVisible();
    await expect(page.getByText('Automation Status')).toBeVisible();
    await expect(page.getByText('Powerwall Configuration')).toBeVisible();
    await expect(page.getByText('Last Communication')).toBeVisible();
  });

  test('should handle API errors gracefully', async ({ page }) => {
    // Mock API error
    await page.route('**/api/v1/status', async (route) => {
      await route.fulfill({
        status: 500,
        contentType: 'application/json',
        body: JSON.stringify({
          success: false,
          error: 'Internal Server Error'
        })
      });
    });

    await page.goto('/dashboard');
    
    // Should still show the dashboard structure
    await expect(page.getByText('Dashboard')).toBeVisible();
  });

  test('should show loading state initially', async ({ page }) => {
    // Mock slow API response
    await page.route('**/api/v1/status', async (route) => {
      await new Promise(resolve => setTimeout(resolve, 1000));
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: { status: 'healthy', timestamp: '2023-01-01T00:00:00Z' }
        })
      });
    });

    await page.goto('/dashboard');
    
    // Should show loading state
    await expect(page.getByText('Loading system status...')).toBeVisible();
  });

  test('should display demo mode indicator', async ({ page }) => {
    // Mock demo mode response
    await page.route('**/api/v1/backup-reserve', async (route) => {
      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          success: true,
          data: {
            backup_reserve_percentage: 20,
            connected: false,
            demo_mode: true,
            powerwall_name: 'Demo Powerwall',
            last_communication: null,
            error: null
          }
        })
      });
    });

    await page.goto('/dashboard');
    
    // Should show demo mode indicator
    await expect(page.getByText('(Demo)')).toBeVisible();
  });
});
