const { chromium } = require(process.env.PLAYWRIGHT_MODULE || "playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const base = process.env.CAPTURE_URL || "http://localhost:5178";
assert(["localhost", "127.0.0.1"].includes(new URL(base).hostname));
const out = __dirname;
fs.mkdirSync(out, { recursive: true });
(async () => {
  const browser = await chromium.launch({ headless: true });
  const results = [];
  for (const [name, viewport] of Object.entries({
    desktop: { width: 1440, height: 900 },
    mobile: { width: 390, height: 844 },
  })) {
    const context = await browser.newContext({ viewport });
    const page = await context.newPage();
    const errors = [];
    page.on("pageerror", (err) => errors.push(err.message));
    const waitResults = async (n) => {
      await page
        .getByRole("status")
        .filter({ hasText: `${n} results` })
        .waitFor();
      await page.waitForTimeout(250);
    };
    const overflow = async () =>
      assert(
        await page.evaluate(
          () => document.documentElement.scrollWidth <= innerWidth,
        ),
      );
    await page.goto(
      base +
        "/documents?library=preview-table&min_faces_manual_count=1&min_mentions_total_count=3&sort=annotations_verified_count&dir=desc",
    );
    await waitResults(1);
    if (name === "mobile") {
      await page
        .getByRole("button", { name: "Show filters", exact: true })
        .waitFor();
      assert.equal(
        await page
          .getByRole("button", { name: "Minimum annotations", exact: true })
          .isVisible(),
        false,
      );
      assert(
        await page
          .getByRole("button", {
            name: "Remove Faces: Manual ≥ 1",
            exact: true,
          })
          .isVisible(),
      );
      await page.mouse.move(0, 0);
      await page.waitForTimeout(200);
      await page.screenshot({
        animations: "disabled",
        path: `${out}/documents-collapsed-mobile.png`,
      });
      await page
        .getByRole("button", { name: "Show filters", exact: true })
        .click();
      assert.equal(
        await page
          .getByRole("button", { name: "Hide filters", exact: true })
          .getAttribute("aria-expanded"),
        "true",
      );
    }
    await overflow();
    await page.mouse.move(0, 0);
    await page.waitForTimeout(200);
    await page.screenshot({
      animations: "disabled",
      path: `${out}/documents-${name}.png`,
    });
    const queryBefore = new URL(page.url()).search;
    await page.getByRole("button", { name: "Columns", exact: true }).click();
    await page
      .getByRole("checkbox", { name: "Faces: Total", exact: true })
      .click();
    await page.keyboard.press("Escape");
    assert.equal(new URL(page.url()).search, queryBefore);
    const header = page.getByRole("button", {
      name: "Sort by Faces: Total",
      exact: true,
    });
    await header.click();
    await page.waitForTimeout(250);
    assert.equal(
      new URL(page.url()).searchParams.get("sort"),
      "faces_total_count",
    );
    assert.equal(new URL(page.url()).searchParams.get("dir") ?? "desc", "desc");
    await header.click();
    await page.waitForTimeout(250);
    assert.equal(new URL(page.url()).searchParams.get("dir"), "asc");
    // The table scrolls inside its region; the viewport stays contained.
    const region = page
      .locator('[role="region"]')
      .filter({ has: page.locator("table") });
    await region.evaluate((el) => {
      el.scrollLeft = el.scrollWidth;
    });
    if (name === "mobile")
      assert(await region.evaluate((el) => el.scrollLeft > 0));
    await page
      .getByRole("button", { name: "Minimum annotations", exact: true })
      .click();
    await page.getByLabel("Annotation category", { exact: true }).click();
    await page.getByRole("option", { name: "Faces", exact: true }).click();
    await page.getByLabel("Annotation state", { exact: true }).click();
    await page.getByRole("option", { name: "Unassigned", exact: true }).click();
    await page
      .getByRole("textbox", { name: "Minimum count", exact: true })
      .fill("1.5");
    await page
      .getByRole("button", { name: "Apply minimum", exact: true })
      .click();
    await page.getByRole("alert").filter({ hasText: "whole number" }).waitFor();
    await page
      .getByRole("textbox", { name: "Minimum count", exact: true })
      .fill("1");
    await page.mouse.move(0, 0);
    await page.waitForTimeout(200);
    await page.screenshot({
      animations: "disabled",
      path: `${out}/minimum-editor-${name}.png`,
    });
    await page
      .getByRole("textbox", { name: "Minimum count", exact: true })
      .press("Enter");
    await page.waitForTimeout(250);
    assert.equal(
      new URL(page.url()).searchParams.get("min_faces_unassigned_count"),
      "1",
    );
    await page
      .getByRole("button", {
        name: "Remove Faces: Unassigned ≥ 1",
        exact: true,
      })
      .click();
    await page.waitForTimeout(250);
    assert.equal(
      new URL(page.url()).searchParams.has("min_faces_unassigned_count"),
      false,
    );
    await page.goBack();
    await page.waitForTimeout(250);
    assert.equal(
      new URL(page.url()).searchParams.get("min_faces_unassigned_count"),
      "1",
    );
    await page.goForward();
    await page.waitForTimeout(250);
    assert.equal(
      new URL(page.url()).searchParams.has("min_faces_unassigned_count"),
      false,
    );
    await page
      .getByRole("textbox", { name: "Search documents", exact: true })
      .fill("Document table ledger");
    await page.waitForTimeout(350);
    await page
      .getByRole("button", { name: "Clear search documents", exact: true })
      .click();
    await page.waitForTimeout(250);
    assert.equal(
      new URL(page.url()).searchParams.get("min_faces_manual_count"),
      "1",
    );
    await page
      .getByRole("textbox", { name: "Search documents", exact: true })
      .fill("ledger");
    await page.waitForTimeout(350);
    await page
      .getByRole("button", { name: "Clear all filters", exact: true })
      .click();
    await page.waitForTimeout(250);
    assert.equal(new URL(page.url()).searchParams.get("q"), "ledger");
    assert.equal(
      new URL(page.url()).searchParams.get("sort"),
      "faces_total_count",
    );
    assert(
      ![...new URL(page.url()).searchParams.keys()].some((key) =>
        key.startsWith("min_"),
      ),
    );
    await page.goto(
      base +
        "/scans?library=preview-counts&min_faces_unassigned_count=1&sort=faces_total_count&dir=asc",
    );
    await waitResults(2);
    if (name === "mobile")
      await page
        .getByRole("button", { name: "Show filters", exact: true })
        .click();
    await overflow();
    await page.mouse.move(0, 0);
    await page.waitForTimeout(200);
    await page.screenshot({
      animations: "disabled",
      path: `${out}/scans-${name}.png`,
    });
    await page.getByRole("combobox", { name: "Sort by", exact: true }).click();
    await page.mouse.move(0, 0);
    await page.waitForTimeout(200);
    await page.screenshot({ animations: "disabled", path: `${out}/sort-options-${name}.png` });
    await overflow();
    await page
      .getByRole("option", {
        name: "Faces: Total · Highest first",
        exact: true,
      })
      .click();
    await page.waitForTimeout(250);
    assert.equal(new URL(page.url()).searchParams.get("dir") ?? "desc", "desc");
    await page.reload();
    await waitResults(2);
    if (name === "mobile")
      await page
        .getByRole("button", { name: "Show filters", exact: true })
        .click();
    assert(
      (
        await page
          .getByRole("combobox", { name: "Sort by", exact: true })
          .innerText()
      ).includes("Highest first"),
    );
    // Standard Select remains keyboard operable, including Escape focus recovery.
    await page.getByRole("combobox", { name: "Sort by", exact: true }).focus();
    await page.keyboard.press("Enter");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("Escape");
    assert(
      await page
        .getByRole("combobox", { name: "Sort by", exact: true })
        .evaluate((el) => el === document.activeElement),
    );
    await page.evaluate(() => document.documentElement.classList.add("dark"));
    await page.waitForTimeout(300);
    await page
      .getByRole("button", { name: "Minimum annotations", exact: true })
      .click();
    await page.mouse.move(0, 0);
    await page.waitForTimeout(200);
    await page.screenshot({
      animations: "disabled",
      path: `${out}/scans-dark-${name}.png`,
    });
    await overflow();
    assert.deepEqual(errors, []);
    results.push({
      viewport,
      checks:
        "Count tags, header/selector synchronization, column visibility query preservation, whole-number validation, AND minima, Back/Forward, clear search/all, reload, keyboard Select/Escape focus, contained horizontal table scrolling, responsive collapse, light/dark and zero console errors passed.",
    });
    await context.close();
  }
  fs.writeFileSync(
    out + "/browser-checks.json",
    JSON.stringify(results, null, 2) + "\n",
  );
  await browser.close();
  console.log(JSON.stringify(results, null, 2));
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
