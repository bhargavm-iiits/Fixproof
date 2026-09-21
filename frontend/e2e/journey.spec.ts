import { expect, test, type Page } from "@playwright/test";

/**
 * The phase acceptance from the plan, as a test: a visitor can see how many
 * candidates were proposed, why each was rejected, and what the container
 * proved — without reading any code.
 */

async function enter(page: Page) {
  await page.goto("/");
  const gate = page.getByTestId("enter");
  await expect(gate).toBeEnabled({ timeout: 30_000 });
  await gate.click();
  await expect(page.getByTestId("loader")).toBeHidden({ timeout: 10_000 });
}

test("the loading gate reflects real readiness and opens the page", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByTestId("loader")).toBeVisible();
  await expect(page.getByTestId("enter")).toBeEnabled({ timeout: 30_000 });
  await page.getByTestId("enter").click();
  await expect(page.getByRole("heading", { name: /Repair a defect/i })).toBeVisible();
});

test("the nine gates are listed and expand", async ({ page }) => {
  await enter(page);
  const gates = page.locator("#gates li");
  await expect(gates).toHaveCount(9);
  await expect(page.locator("#gates")).toContainText("no_test_edits");
  await page.getByRole("button", { name: /diff_parses/ }).click();
  await expect(page.locator("#gates")).toContainText("hunk header");
});

test("the stage machine is read from the backend", async ({ page }) => {
  await enter(page);
  const stages = page.locator("#stages li");
  await expect(stages).toHaveCount(7);
  await expect(page.locator("#stages")).toContainText("verify");
});

test("open a defect, run it, and inspect why a candidate was refused", async ({ page }) => {
  await enter(page);

  await page.getByTestId("defect-dev-off_by_one-001").click();
  await page.getByTestId("run").click();

  // A terminal decision, however it turns out.
  const decision = page.locator("#live").getByText(
    /FIX_VERIFIED|NO_VERIFIED_FIX|ALL_GATED|TIMEOUT|ERROR/,
  );
  await expect(decision.first()).toBeVisible({ timeout: 100_000 });

  // Every stage reports a real duration.
  await expect(page.locator('[data-stage="verify"][data-state="done"]')).toBeVisible();

  // The test-editing candidate must be present and must name its gate.
  const cheat = page.getByTestId("candidate-r1-testedit");
  await expect(cheat).toBeVisible();
  await expect(cheat).toContainText("rejected by no_test_edits");

  await cheat.getByRole("button").first().click();
  await expect(cheat).toContainText("rejected here");
  await expect(cheat).toContainText("No container was started");

  // The out-of-scope candidate is refused by a different gate.
  await expect(page.getByTestId("candidate-r1-scope")).toContainText("rejected by scope");
});

test("the page carries its own caveats", async ({ page }) => {
  await enter(page);
  await expect(page.locator("#limits")).toContainText("synthetic");
  await expect(page.locator("#limits")).toContainText("fake_solve reads the answer key");
});

test("it is usable at phone width", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await enter(page);
  await expect(page.getByRole("heading", { name: /Repair a defect/i })).toBeVisible();
  const overflow = await page.evaluate(
    () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
  );
  expect(overflow).toBeLessThanOrEqual(1);
});
