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
  await page.getByRole("tab", { name: "Эффекты" }).click();
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
  await page.locator("#file-input").setInputFiles({
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

test("loaded track replaces upload prompt and removes visual noise", async ({
  page,
}) => {
  await demo(page);
  await expect(page.locator("#dropzone")).toBeHidden();
  await expect(page.locator("#replace-button")).toBeVisible();
  await expect(page.locator("#demo-block")).toBeHidden();
  await expect(
    page.locator(".intro, .studio-label, #track-status, .tiny-label"),
  ).toHaveCount(0);
  expect(
    await page
      .locator("body")
      .evaluate((element) => getComputedStyle(element).fontFamily),
  ).toContain("Manrope");
});

test("play starts and stops inside the selected interval and can replay it", async ({
  page,
}) => {
  await demo(page);
  await page.locator("#start").fill("2");
  await page.locator("#end").fill("2.7");
  await page.locator("#play-button").click();
  await expect(page.locator("#play-button")).toHaveAttribute(
    "aria-label",
    "Пауза",
  );
  await expect(page.locator("#current-time")).toContainText("0:02.");
  await expect(page.locator("#play-button")).toHaveAttribute(
    "aria-label",
    "Воспроизвести",
  );
  await expect(page.locator("#current-time")).toHaveText("0:02.7");
  await page.locator("#play-button").click();
  await expect(page.locator("#play-button")).toHaveAttribute(
    "aria-label",
    "Пауза",
  );
  await expect(page.locator("#current-time")).toContainText("0:02.");
  const border = await page
    .locator("#selection")
    .evaluate((element) => getComputedStyle(element).borderLeftColor);
  expect(border).toBe("rgb(189, 149, 255)");
});

test("live sliders preserve playback position without server processing", async ({
  page,
}) => {
  await demo(page);
  const processing = [];
  page.on("request", (request) => {
    if (/api\/(process|effects|convert)/.test(request.url()))
      processing.push(request.url());
  });
  await page.locator("#start").fill("4");
  await page.locator("#play-button").click();
  await expect(page.locator("#play-button")).toHaveAttribute(
    "aria-label",
    "Пауза",
  );
  await page.getByRole("tab", { name: "Эффекты" }).click();
  await page.locator("#speed").fill("1.5");
  await page.locator("#pitch").fill("7");
  await page.locator("#volume").fill("0.35");
  await expect(page.locator("#play-button")).toHaveAttribute(
    "aria-label",
    "Пауза",
  );
  const text = await page.locator("#current-time").textContent();
  expect(Number(text.split(":")[1])).toBeGreaterThanOrEqual(4);
  await expect(page.locator("#pitch-value")).toHaveText("+7 st");
  expect(processing).toEqual([]);
  await page.locator("#play-button").click();
  await expect(page.locator("#play-button")).toHaveAttribute(
    "aria-label",
    "Воспроизвести",
  );
});

test("audio worklet changes measured pitch and gain independently of tempo", async ({
  page,
}) => {
  await demo(page);
  const measurements = await page.evaluate(async () => {
    const { StudioPlayer } = await import("./static/player.js");
    const player = new StudioPlayer();
    await player.initialize();
    const rate = player.context.sampleRate;
    const buffer = player.context.createBuffer(2, rate * 10, rate);
    for (let channel = 0; channel < 2; channel++) {
      const samples = buffer.getChannelData(channel);
      for (let i = 0; i < samples.length; i++)
        samples[i] = 0.2 * Math.sin((2 * Math.PI * 440 * i) / rate);
    }
    player.setBuffer(buffer);
    const analyser = player.context.createAnalyser();
    analyser.fftSize = 8192;
    analyser.smoothingTimeConstant = 0;
    player.gain.connect(analyser);
    await player.play();
    const sample = async () => {
      await new Promise((resolve) => setTimeout(resolve, 450));
      const spectrum = new Float32Array(analyser.frequencyBinCount);
      analyser.getFloatFrequencyData(spectrum);
      const peak = spectrum.reduce(
        (best, value, i) => (value > spectrum[best] ? i : best),
        1,
      );
      const waveform = new Float32Array(analyser.fftSize);
      analyser.getFloatTimeDomainData(waveform);
      return {
        hz: (peak * rate) / analyser.fftSize,
        rms: Math.sqrt(
          waveform.reduce((sum, value) => sum + value * value, 0) /
            waveform.length,
        ),
        position: player.currentTime,
      };
    };
    const original = await sample();
    player.setParameters({ speed: 1, pitch: 12, volume: 1 });
    const pitched = await sample();
    player.setParameters({ speed: 1.5, pitch: 12, volume: 0.25 });
    const faster = await sample();
    player.pause();
    const pending = player.play();
    player.pause();
    await pending;
    const paused = player.paused;
    await player.context.close();
    return { original, pitched, faster, paused };
  });
  expect(measurements.original.hz).toBeGreaterThan(430);
  expect(measurements.original.hz).toBeLessThan(450);
  expect(measurements.pitched.hz).toBeGreaterThan(860);
  expect(measurements.pitched.hz).toBeLessThan(900);
  expect(measurements.faster.hz).toBeGreaterThan(860);
  expect(measurements.faster.hz).toBeLessThan(900);
  expect(measurements.faster.rms / measurements.pitched.rms).toBeGreaterThan(
    0.18,
  );
  expect(measurements.faster.rms / measurements.pitched.rms).toBeLessThan(0.32);
  expect(measurements.faster.position).toBeGreaterThan(
    measurements.pitched.position + 0.5,
  );
  expect(measurements.paused).toBe(true);
});

test("reverb and character effects change live playback and export settings", async ({
  page,
}) => {
  await demo(page);
  await page.locator("#start").fill("2");
  await page.locator("#end").fill("5");
  await page.locator("#play-button").click();
  await page.getByRole("tab", { name: "Эффекты" }).click();
  const requests = [];
  page.on("request", (request) => {
    if (request.url().includes("api/process")) requests.push(request.url());
  });
  await page.locator("#reverb").fill("0.5");
  await page.locator("#reverb_room").selectOption("room");
  await page.locator("#effect").selectOption("distortion");
  await page.locator("#bass").fill("4");
  await expect(page.locator("#play-button")).toHaveAttribute(
    "aria-label",
    "Пауза",
  );
  expect(requests).toEqual([]);
  await page.locator("#preview-button").click();
  await expect(page.locator("#result-button")).toBeEnabled();
  expect(new URL(requests[0]).searchParams.get("reverb")).toBe("0.5");
  expect(new URL(requests[0]).searchParams.get("reverb_room")).toBe("room");
  await expect(page.locator("#total-time")).toHaveText("0:03.6");
});

test("live reverb produces a decaying stereo impulse response", async ({
  page,
}) => {
  await page.goto("./");
  const result = await page.evaluate(async () => {
    const { LiveEffects } = await import("./static/effects.js");
    const render = async (reverb) => {
      const context = new OfflineAudioContext(2, 44100 * 3, 44100);
      const fx = new LiveEffects(context);
      fx.setParameters({ reverb });
      fx.output.connect(context.destination);
      const source = context.createBufferSource();
      source.buffer = context.createBuffer(2, 44100, 44100);
      source.buffer.getChannelData(0)[0] = 0.5;
      source.buffer.getChannelData(1)[0] = 0.5;
      source.connect(fx.input);
      source.start(0.1);
      const audio = await context.startRendering();
      fx.disconnect();
      const energy = (channel, start, end) => {
        const samples = audio
          .getChannelData(channel)
          .slice(start * 44100, end * 44100);
        return Math.sqrt(
          samples.reduce((sum, value) => sum + value * value, 0) /
            samples.length,
        );
      };
      return {
        early: energy(0, 0.15, 0.3),
        late: energy(0, 1.2, 1.6),
        left: audio.getChannelData(0)[8000],
        right: audio.getChannelData(1)[8000],
      };
    };
    return { dry: await render(0), wet: await render(0.5) };
  });
  expect(result.wet.early).toBeGreaterThan(0.001);
  expect(result.wet.early).toBeGreaterThan(result.dry.early * 5);
  expect(result.wet.late).toBeLessThan(result.wet.early * 0.1);
  expect(result.wet.left).not.toBeCloseTo(result.wet.right, 5);
});
