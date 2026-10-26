"use strict";

const $ = (id) => document.getElementById(id);
const audio = new Audio();
const state = {
  file: null,
  info: null,
  originalURL: null,
  resultURL: null,
  source: "original",
  busy: false,
  sequence: 0,
  controller: null,
  noticeTimer: null,
  limits: { max_upload_mb: 30, max_duration_seconds: 300 },
};
const numericFields = [
  "start",
  "end",
  "speed",
  "pitch",
  "volume",
  "fade_in",
  "fade_out",
  "bass",
  "treble",
  "sample_rate",
  "channels",
  "bitrate",
];
const effectFields = ["bass", "treble", "effect", "normalize"];
const defaults = {
  start: 0,
  speed: 1,
  pitch: 0,
  volume: 1,
  fade_in: 0,
  fade_out: 0,
  bass: 0,
  treble: 0,
  effect: "none",
  mode: "keep",
  reverse: false,
  normalize: false,
  format: "mp3",
  sample_rate: 44100,
  channels: 2,
  bitrate: 192,
};

function time(value, precise = false) {
  if (!Number.isFinite(value)) value = 0;
  const minutes = Math.floor(value / 60);
  const seconds = value % 60;
  return `${minutes}:${(precise ? seconds.toFixed(1) : Math.floor(seconds).toString()).padStart(precise ? 4 : 2, "0")}`;
}

function notice(message, error = false, persist = false) {
  clearTimeout(state.noticeTimer);
  $("status-message").textContent = message;
  $("status-message").classList.toggle("error", error);
  $("status-message").hidden = false;
  if (!persist)
    state.noticeTimer = setTimeout(
      () => {
        $("status-message").hidden = true;
      },
      error ? 9000 : 4500,
    );
}

function syncDisabled() {
  const unavailable = state.busy || !state.file;
  $("controls").disabled = unavailable;
  for (const id of [
    "preview-button",
    "export-button",
    "reset-button",
    "play-button",
    "original-button",
  ])
    $(id).disabled = unavailable;
  $("result-button").disabled = unavailable || !state.resultURL;
  $("demo-button").disabled = state.busy;
  $("file-input").disabled = state.busy;
  $("bitrate").disabled = ["wav", "flac"].includes($("format").value);
  document.body.classList.toggle("busy", state.busy);
  $("track-status").textContent = state.busy
    ? "ОБРАБОТКА"
    : state.file
      ? "ГОТОВ К РАБОТЕ"
      : "НЕТ АУДИО";
  $("preview-button").setAttribute("aria-busy", String(state.busy));
}

function updateControls() {
  $("speed-value").textContent = `${Number($("speed").value).toFixed(2)}×`;
  $("pitch-value").textContent =
    `${Number($("pitch").value) > 0 ? "+" : ""}${$("pitch").value} st`;
  $("volume-value").textContent =
    `${Math.round(Number($("volume").value) * 100)}%`;
  for (const id of ["bass", "treble"])
    $(`${id}-value`).textContent =
      `${Number($(id).value) > 0 ? "+" : ""}${$(id).value} dB`;
  const format = $("format").value;
  const lossless = ["wav", "flac"].includes(format);
  const lowRate = $("sample_rate").value === "22050";
  const mono = $("channels").value === "1";
  const maxBitrate =
    format === "ogg"
      ? lowRate
        ? mono
          ? 64
          : 128
        : mono
          ? 192
          : 320
      : format === "mp3" && lowRate
        ? 128
        : 320;
  for (const option of $("bitrate").options)
    option.disabled = Number(option.value) > maxBitrate;
  if (Number($("bitrate").value) > maxBitrate)
    $("bitrate").value = String(maxBitrate);

  $("bitrate").disabled = lossless;
  $("export-summary").textContent =
    `${format.toUpperCase()} · ${lossless ? "без потерь" : `${$("bitrate").value} кбит/с`} · ${(Number($("sample_rate").value) / 1000).toLocaleString("ru")} кГц · ${$("channels").value === "1" ? "моно" : "стерео"}`;
  if (state.info) {
    let duration = Math.max(
      0,
      Number($("end").value) - Number($("start").value),
    );
    if ($("mode").value === "remove") duration = state.info.duration - duration;
    duration =
      duration / Number($("speed").value) +
      ($("effect").value === "echo" ? 0.36 : 0);
    $("duration-estimate").textContent =
      `Результат ≈ ${time(Math.max(0, duration), true)}`;
    $("selection-caption").textContent =
      `${time(Number($("start").value), true)} — ${time(Number($("end").value), true)}`;
    const left = Math.max(
      0,
      Math.min(100, (Number($("start").value) / state.info.duration) * 100),
    );
    const right = Math.max(
      left,
      Math.min(100, (Number($("end").value) / state.info.duration) * 100),
    );
    $("selection").style.left = `${left}%`;
    $("selection").style.width = `${right - left}%`;
    $("selection").hidden = false;
  }
}

function clearResult() {
  audio.pause();
  if (state.resultURL) URL.revokeObjectURL(state.resultURL);
  state.resultURL = null;
  if (state.originalURL) setSource("original");
  syncDisabled();
}

function resetSettings() {
  for (const [id, value] of Object.entries(defaults)) {
    if (typeof value === "boolean") $(id).checked = value;
    else $(id).value = value;
  }
  $("end").value = state.info ? state.info.duration : 0.01;
  document
    .querySelectorAll(".preset")
    .forEach((button) => button.classList.remove("active"));
  clearResult();
  updateControls();
}

function setSource(source) {
  audio.pause();
  state.source = source;
  audio.src = source === "original" ? state.originalURL : state.resultURL;
  $("original-button").classList.toggle("active", source === "original");
  $("result-button").classList.toggle("active", source === "result");
  $("original-button").setAttribute(
    "aria-pressed",
    String(source === "original"),
  );
  $("result-button").setAttribute("aria-pressed", String(source === "result"));
  $("playhead").hidden = source === "result";
  $("current-time").textContent = "0:00.0";
}

function drawWave() {
  const canvas = $("waveform");
  const box = canvas.getBoundingClientRect();
  const ratio = window.devicePixelRatio || 1;
  canvas.width = box.width * ratio;
  canvas.height = box.height * ratio;
  const ctx = canvas.getContext("2d");
  ctx.scale(ratio, ratio);
  if (!state.info) return;
  const peaks = state.info.waveform;
  const count = Math.max(1, Math.floor(box.width / 4));
  const peakMax = Math.max(0.01, ...peaks);
  ctx.fillStyle = "#b4e66a";
  for (let i = 0; i < count; i++) {
    const from = Math.floor((i / count) * peaks.length);
    const to = Math.max(from + 1, Math.floor(((i + 1) / count) * peaks.length));
    const value = Math.max(...peaks.slice(from, to)) / peakMax;
    const height = Math.max(2, value * box.height * 0.82);
    ctx.fillRect((i * box.width) / count, (box.height - height) / 2, 2, height);
  }
}

async function requestAudio(route, params, file, signal) {
  const response = await fetch(`api/${route}${params ? `?${params}` : ""}`, {
    method: "POST",
    headers: { "Content-Type": "application/octet-stream" },
    body: file,
    signal,
  });
  if (!response.ok) {
    let message =
      response.status === 413
        ? "Файл слишком большой."
        : `Не удалось обработать файл (${response.status}). Попробуй ещё раз.`;
    try {
      const data = await response.json();
      if (typeof data.detail === "string") message = data.detail;
      else if (Array.isArray(data.detail))
        message = "Проверь значения настроек и границы выделенного фрагмента.";
    } catch {}
    throw new Error(message);
  }
  return response;
}

async function loadFile(file) {
  if (!file || state.busy) return;
  if (file.size > state.limits.max_upload_mb * 1024 * 1024)
    return notice(
      `Максимальный размер файла — ${state.limits.max_upload_mb} МБ.`,
      true,
    );
  if (!file.size) return notice("Этот файл пустой. Выбери другой.", true);
  state.busy = true;
  syncDisabled();
  notice("Читаем аудио и строим осциллограмму…", false, true);
  const sequence = ++state.sequence;
  state.controller?.abort();
  state.controller = new AbortController();
  try {
    const response = await requestAudio(
      "audio/info",
      null,
      file,
      state.controller.signal,
    );
    const info = await response.json();
    if (sequence !== state.sequence) return;
    audio.pause();
    if (state.originalURL) URL.revokeObjectURL(state.originalURL);
    state.file = file;
    state.info = info;
    state.originalURL = URL.createObjectURL(file);
    $("file-name").textContent = file.name;
    $("file-name").title = file.name;
    $("track-title").textContent = file.name.replace(/\.[^.]+$/, "");
    $("file-size").textContent =
      `${(file.size / 1024 / 1024).toFixed(2)} МБ · ${file.name.split(".").pop().toUpperCase()}`;
    $("meta-duration").textContent = time(info.duration, true);
    $("meta-peak").textContent =
      info.peak_db === null ? "−∞ dBFS" : `${info.peak_db} dBFS`;
    $("meta-rms").textContent =
      info.rms_db === null ? "−∞ dBFS" : `${info.rms_db} dBFS`;
    $("file-card").hidden = false;
    $("metadata").hidden = false;
    $("wave-empty").hidden = true;
    $("start").max = info.duration;
    $("end").max = info.duration;
    $("total-time").textContent = time(info.duration, true);
    $("ruler").replaceChildren(
      ...Array.from({ length: 5 }, (_, i) => {
        const span = document.createElement("span");
        span.textContent = time((info.duration * i) / 4);
        return span;
      }),
    );
    resetSettings();
    drawWave();
    notice("Трек загружен. Выдели фрагмент или начни со звучания.");
  } catch (error) {
    if (error.name !== "AbortError") notice(error.message, true);
  } finally {
    if (sequence === state.sequence) {
      state.busy = false;
      syncDisabled();
    }
    $("file-input").value = "";
  }
}

function getOptions(format) {
  const options = {
    format,
    mode: $("mode").value,
    effect: $("effect").value,
    reverse: $("reverse").checked,
    normalize: $("normalize").checked,
  };
  for (const id of numericFields) {
    const value = Number($(id).value);
    if ($(id).value === "" || !Number.isFinite(value))
      throw new Error("Заполни числовые настройки.");
    if (!$(id).checkValidity())
      throw new Error(
        `Проверь значение: ${$(id).closest("label").childNodes[0].textContent.trim()}.`,
      );
    options[id] = value;
  }
  if (options.start >= options.end || options.end > state.info.duration + 0.025)
    throw new Error(
      "Начало должно быть раньше конца, а фрагмент — внутри дорожки.",
    );
  if (
    options.mode === "remove" &&
    options.start === 0 &&
    options.end >= state.info.duration
  )
    throw new Error("Нельзя удалить всю дорожку. Выдели фрагмент поменьше.");
  return new URLSearchParams(options);
}

async function renderAudio(download) {
  if (!state.file || state.busy) return;
  let params;
  const format = download ? $("format").value : "wav";
  try {
    params = getOptions(format);
  } catch (error) {
    return notice(error.message, true);
  }
  state.busy = true;
  audio.pause();
  syncDisabled();
  notice(
    download ? "Готовим трек к скачиванию…" : "Применяем настройки…",
    false,
    true,
  );
  state.controller = new AbortController();
  try {
    const response = await requestAudio(
      "process",
      params,
      state.file,
      state.controller.signal,
    );
    const blob = await response.blob();
    if (download) {
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `${state.file.name.replace(/\.[^.]+$/, "")}-slaymusic.${format}`;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 60000);
      notice("Готово! Трек отправлен в загрузки.");
    } else {
      if (state.resultURL) URL.revokeObjectURL(state.resultURL);
      state.resultURL = URL.createObjectURL(blob);
      setSource("result");
      notice("Результат готов. Сравни его с оригиналом.");
      try {
        await audio.play();
      } catch {
        notice("Результат готов. Нажми кнопку воспроизведения.");
      }
    }
  } catch (error) {
    if (error.name !== "AbortError") notice(error.message, true);
  } finally {
    state.busy = false;
    syncDisabled();
  }
}

function demoFile() {
  const rate = 44100;
  const duration = 16;
  const frames = rate * duration;
  const buffer = new ArrayBuffer(44 + frames * 4);
  const view = new DataView(buffer);
  const text = (offset, value) =>
    [...value].forEach((letter, i) =>
      view.setUint8(offset + i, letter.charCodeAt(0)),
    );
  text(0, "RIFF");
  view.setUint32(4, buffer.byteLength - 8, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 2, true);
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 4, true);
  view.setUint16(32, 4, true);
  view.setUint16(34, 16, true);
  text(36, "data");
  view.setUint32(40, frames * 4, true);
  const notes = [
    220, 261.626, 329.628, 391.995, 293.665, 329.628, 261.626, 195.998,
  ];
  for (let i = 0; i < frames; i++) {
    const t = i / rate;
    const beat = t % 0.5;
    const note = notes[Math.floor(t * 2) % notes.length];
    const env = Math.min(1, beat * 100) * Math.exp(-beat * 6);
    const synth =
      (Math.sin(t * note * Math.PI * 2) +
        0.25 * Math.sin(t * note * Math.PI * 4)) *
      env *
      0.23;
    const kick =
      Math.sin(2 * Math.PI * (55 * beat + 2 * (1 - Math.exp(-beat * 25)))) *
      Math.exp(-beat * 20) *
      0.32;
    const hat =
      Math.sin(t * 12431) *
      Math.sin(t * 17173) *
      Math.exp(-(t % 0.25) * 70) *
      0.1;
    const fade = Math.min(1, t * 5, (duration - t) * 2);
    view.setInt16(44 + i * 4, (synth + kick + hat) * fade * 32767, true);
    view.setInt16(
      46 + i * 4,
      (synth * (0.85 + 0.15 * Math.sin(t)) + kick + hat) * fade * 32767,
      true,
    );
  }
  return new File([buffer], "midnight-loop.wav", { type: "audio/wav" });
}

$("file-input").addEventListener("change", (event) =>
  loadFile(event.target.files[0]),
);
$("demo-button").addEventListener("click", () => loadFile(demoFile()));
for (const type of ["dragenter", "dragover"])
  $("dropzone").addEventListener(type, (event) => {
    event.preventDefault();
    $("dropzone").classList.add("dragging");
  });
for (const type of ["dragleave", "drop"])
  $("dropzone").addEventListener(type, (event) => {
    event.preventDefault();
    $("dropzone").classList.remove("dragging");
  });
$("dropzone").addEventListener("drop", (event) =>
  loadFile(event.dataTransfer.files[0]),
);
window.addEventListener("dragover", (event) => event.preventDefault());
window.addEventListener("drop", (event) => event.preventDefault());
$("settings-form").addEventListener("submit", (event) =>
  event.preventDefault(),
);
$("settings-form").addEventListener("input", (event) => {
  clearResult();
  if (effectFields.includes(event.target.id))
    document
      .querySelectorAll(".preset")
      .forEach((button) => button.classList.remove("active"));
  updateControls();
});
$("reset-button").addEventListener("click", resetSettings);
$("select-all").addEventListener("click", () => {
  $("start").value = 0;
  $("end").value = state.info.duration;
  clearResult();
  updateControls();
});
$("preview-button").addEventListener("click", () => renderAudio(false));
$("export-button").addEventListener("click", () => renderAudio(true));
$("original-button").addEventListener("click", () => setSource("original"));
$("result-button").addEventListener("click", () => setSource("result"));
$("play-button").addEventListener("click", async () => {
  if (!audio.paused) return audio.pause();
  try {
    await audio.play();
  } catch {
    notice(
      "Браузер не воспроизводит этот формат. Нажми «Применить и слушать» — подготовим WAV.",
      true,
    );
  }
});
audio.addEventListener("play", () => {
  $("play-button").setAttribute("aria-label", "Пауза");
  $("play-button").querySelector("use").setAttribute("href", "#i-pause");
});
audio.addEventListener("pause", () => {
  $("play-button").setAttribute("aria-label", "Воспроизвести");
  $("play-button").querySelector("use").setAttribute("href", "#i-play");
});
audio.addEventListener("loadedmetadata", () => {
  $("total-time").textContent = time(audio.duration, true);
});
audio.addEventListener("timeupdate", () => {
  $("current-time").textContent = time(audio.currentTime, true);
  if (state.info && state.source === "original") {
    $("playhead").hidden = false;
    $("playhead").style.left =
      `${Math.min(100, (audio.currentTime / state.info.duration) * 100)}%`;
  }
});

const tabs = [...document.querySelectorAll("[data-tab]")];
function activateTab(button) {
  for (const tab of tabs) {
    const active = tab === button;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
    tab.tabIndex = active ? 0 : -1;
    $(`panel-${tab.dataset.tab}`).hidden = !active;
  }
}
for (const button of tabs) {
  button.addEventListener("click", () => activateTab(button));
  button.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const index =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? tabs.length - 1
          : (tabs.indexOf(button) +
              (event.key === "ArrowRight" ? 1 : -1) +
              tabs.length) %
            tabs.length;
    activateTab(tabs[index]);
    tabs[index].focus();
  });
}
for (const button of document.querySelectorAll("[data-preset]"))
  button.addEventListener("click", () => {
    const preset = {
      clean: { bass: 0, treble: 0, effect: "none", normalize: true },
      warm: { bass: 5, treble: -2, effect: "none", normalize: false },
      lofi: { bass: 2, treble: -5, effect: "lofi", normalize: false },
    }[button.dataset.preset];
    for (const [id, value] of Object.entries(preset)) {
      if (typeof value === "boolean") $(id).checked = value;
      else $(id).value = value;
    }
    document
      .querySelectorAll(".preset")
      .forEach((item) => item.classList.toggle("active", item === button));
    clearResult();
    updateControls();
  });

let drag = null;
const wavePosition = (event) =>
  Math.max(
    0,
    Math.min(
      1,
      (event.clientX - $("wave-area").getBoundingClientRect().left) /
        $("wave-area").getBoundingClientRect().width,
    ),
  );
$("wave-area").addEventListener("pointerdown", (event) => {
  if (!state.info || state.busy || event.button !== 0) return;
  const point = wavePosition(event);
  drag = { start: point, x: event.clientX, moved: false };
  $("wave-area").setPointerCapture(event.pointerId);
});
$("wave-area").addEventListener("pointermove", (event) => {
  if (!drag) return;
  if (Math.abs(event.clientX - drag.x) < 4 && !drag.moved) return;
  if (!drag.moved) clearResult();
  drag.moved = true;
  const point = wavePosition(event);
  $("start").value = (
    Math.min(point, drag.start) * state.info.duration
  ).toFixed(2);
  $("end").value = Math.min(
    state.info.duration,
    Math.max(
      Number($("start").value) + 0.01,
      Math.max(point, drag.start) * state.info.duration,
    ),
  ).toFixed(2);
  updateControls();
});
$("wave-area").addEventListener("pointerup", (event) => {
  if (!drag) return;
  if (!drag.moved) {
    if (state.source !== "original") setSource("original");
    audio.currentTime = wavePosition(event) * state.info.duration;
  }
  drag = null;
});
$("wave-area").addEventListener("pointercancel", () => {
  drag = null;
});
new ResizeObserver(drawWave).observe($("wave-area"));
fetch("api/formats")
  .then((response) => {
    if (!response.ok) throw new Error();
    return response.json();
  })
  .then((limits) => {
    state.limits = limits;
    $("upload-limit").textContent =
      `До ${limits.max_upload_mb} МБ · до ${Math.floor(limits.max_duration_seconds / 60)} минут`;
  })
  .catch(() =>
    notice(
      "Не удалось связаться с сервером. Попробуй обновить страницу.",
      true,
    ),
  );
updateControls();
syncDisabled();
