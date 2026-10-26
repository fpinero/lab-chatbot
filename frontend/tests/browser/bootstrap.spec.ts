import { expect, test } from '@playwright/test';

test('network-free local preview works without horizontal overflow', async ({ page }, info) => {
  await page.goto('/');
  await page.getByLabel('Preview prompt').fill('A deliberate experiment');
  await expect(page.getByRole('button', { name: /Run preview/ })).toBeEnabled();
  await page.getByRole('button', { name: /Run preview/ }).click();
  await expect(page.getByText('Local preview: A deliberate experiment')).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: `../artifacts/m0-${info.project.name}.png`, fullPage: true });
});
