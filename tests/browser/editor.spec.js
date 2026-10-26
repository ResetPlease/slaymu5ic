const { test, expect } = require("@playwright/test");

async function demo(page) {
  await page.goto("./");
  await page.getByRole("button", { name: /Попробовать демотрек/ }).click();
  await expect(page.locator("#track-title")).toHaveText("midnight-loop");
  await expect(page.locator("#preview-button")).toBeEnabled();
}

test("upload, select, process, compare and download", async ({ page }) => {
  const errors = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await demo(page);
  await page.locator("#start").fill("2");
  await page.locator("#end").fill("6");
  await page.locator("#speed").fill("2");
  await page.locator("#preview-button").click();
  await expect(page.locator("#result-button")).toBeEnabled();
  await expect(page.locator("#result-button")).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.locator("#total-time")).toHaveText("0:02.0");
  await page.locator("#original-button").click();
  await expect(page.locator("#total-time")).toHaveText("0:16.0");
  await page.getByRole("tab", { name: "Экспорт" }).click();
  await page.locator("#format").selectOption("wav");
  await expect(page.locator("#bitrate")).toBeDisabled();
  const downloadPromise = page.waitForEvent("download");
  await page.locator("#export-button").click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("midnight-loop-slaymusic.wav");
  expect(await download.failure()).toBeNull();
  await expect(page.locator("#status-message")).toContainText("Готово");
  expect(errors).toEqual([]);
});

test("presets, reset and stale result invalidation", async ({ page }) => {
  await demo(page);
  await page.getByRole("tab", { name: "Эффекты" }).click();
  await page.locator('[data-preset="lofi"]').click();
  await expect(page.locator("#effect")).toHaveValue("lofi");
  await expect(page.locator("#bass")).toHaveValue("2");
  await page.locator("#preview-button").click();
  await expect(page.locator("#result-button")).toBeEnabled();
  await page.locator("#bass").fill("4");
  await expect(page.locator("#result-button")).toBeDisabled();
  await page.locator("#reset-button").click();
  await expect(page.locator("#effect")).toHaveValue("none");
  await expect(page.locator("#bass")).toHaveValue("0");
});

test("invalid uploads and invalid selection stay recoverable", async ({
  page,
}) => {
  await page.goto("./");
  await page
    .locator("#file-input")
    .setInputFiles({
      name: "broken.wav",
      mimeType: "audio/wav",
      buffer: Buffer.from("not audio"),
    });
  await expect(page.locator("#status-message")).toContainText(
    "Не удалось прочитать",
  );
  await expect(page.locator("#demo-button")).toBeEnabled();
  await demo(page);
  await page.locator("#start").fill("12");
  await page.locator("#end").fill("2");
  await page.locator("#preview-button").click();
  await expect(page.locator("#status-message")).toContainText(
    "Начало должно быть раньше",
  );
  await expect(page.locator("#preview-button")).toBeEnabled();
});

test("waveform selection and keyboard tabs", async ({ page }) => {
  await demo(page);
  const wave = await page.locator("#wave-area").boundingBox();
  await page.mouse.move(wave.x + wave.width * 0.25, wave.y + wave.height / 2);
  await page.mouse.down();
  await page.mouse.move(wave.x + wave.width * 0.75, wave.y + wave.height / 2, {
    steps: 6,
  });
  await page.mouse.up();
  expect(Number(await page.locator("#start").inputValue())).toBeCloseTo(4, 0);
  expect(Number(await page.locator("#end").inputValue())).toBeCloseTo(12, 0);
  await page.getByRole("tab", { name: "Редактор" }).focus();
  await page.keyboard.press("ArrowRight");
  await expect(page.getByRole("tab", { name: "Эффекты" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});

test("mobile fits viewport and supports processing", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await demo(page);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth,
    ),
  ).toBe(true);
  await page.locator("#preview-button").click();
  await expect(page.locator("#result-button")).toBeEnabled();
  await expect(page.locator(".site-footer")).toContainText(
    "не сохраняются на сервере",
  );
});
