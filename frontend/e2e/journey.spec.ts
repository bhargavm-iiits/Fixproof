import { expect, test, type Page } from "@playwright/test";

/**
 * The acceptance test for the whole project, written the way a visitor would
 * describe it: can someone who does not write software understand what
 * happened, and why an answer was refused?
 */

async function open(page: Page) {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /An AI says it fixed the bug/i })).toBeVisible();
}

test("the page explains itself without jargon", async ({ page }) => {
  await open(page);
  await expect(page.locator("#how")).toContainText("Something is broken");
  await expect(page.locator("#how")).toContainText("The AI suggests repairs");
  await expect(page.locator("#catch")).toContainText("Fix the code");
  await expect(page.locator("#catch")).toContainText("Change the test");
});

test("the nine checks are listed in plain words and expand", async ({ page }) => {
  await open(page);
  const checks = page.locator("#catch ul > li");
  await expect(checks).toHaveCount(9);
  await expect(page.locator("#catch")).toContainText("It didn't change the test");
  await page.getByRole("button", { name: /The edit makes sense/ }).click();
  await expect(page.locator("#catch")).toContainText("exactly which lines it replaces");
});

test("pick a bug, fix it, and read why an answer was refused", async ({ page }) => {
  await open(page);

  await page.getByTestId("bug-dev-off_by_one-001").click();
  await page.getByTestId("run").click();

  const outcome = page
    .locator("#try")
    .getByRole("heading", {
      name: /Fixed, and proven|Nothing worked|Every attempt was rejected|Ran out of time|Something went wrong/,
    });
  await expect(outcome).toBeVisible({ timeout: 100_000 });

  // Every step of the run reported that it finished.
  await expect(page.locator('[data-stage="verify"][data-state="done"]')).toBeVisible();

  // The attempt that tried to edit the test must say so, in plain words.
  const cheat = page.getByTestId("attempt-r1-testedit");
  await expect(cheat).toBeVisible();
  await expect(cheat).toContainText("Rejected before testing");
  await expect(cheat).toContainText("it didn't change the test");

  await cheat.getByRole("button").first().click();
  await expect(cheat).toContainText("Stopped here");
  await expect(cheat).toContainText("never made it to the sandbox");
});

test("results are described in plain words", async ({ page }) => {
  await open(page);
  await expect(page.locator("#results")).toContainText("tried to change the test");
  await expect(page.locator("#results")).toContainText("got through");
});

test("the page states what it does not prove", async ({ page }) => {
  await open(page);
  await expect(page.locator("#limits")).toContainText("The bugs were planted on purpose");
  await expect(page.locator("#limits")).toContainText("What 'proven' actually means here");
});

test("it is usable with a keyboard", async ({ page }) => {
  await open(page);
  await page.keyboard.press("Tab");
  await expect(page.locator(".skip-link")).toBeFocused();
});

test("it is usable at phone width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page);
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});
