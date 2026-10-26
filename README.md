# Slaymusic

[![CI](https://github.com/ResetPlease/slaymu5ic/actions/workflows/ci.yml/badge.svg)](https://github.com/ResetPlease/slaymu5ic/actions/workflows/ci.yml)
[![Coverage gate ≥90%](https://img.shields.io/badge/coverage_gate-%E2%89%A590%25-a3e635)](.github/workflows/ci.yml)
[![Python 3.12](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)](https://www.python.org/downloads/)
[![FFmpeg](https://img.shields.io/badge/audio-FFmpeg-007808?logo=ffmpeg&logoColor=white)](https://ffmpeg.org/)

Браузерный аудиоредактор: загрузить дорожку, выделить фрагмент, изменить звучание и скачать результат. Без регистрации и сохранения аудиофайлов на сервере. Для знакомства есть синтезаторный демотрек.

## Возможности и ограничения

- WAV, MP3, FLAC, OGG Vorbis и AAC ADTS; выбор частоты, каналов и битрейта. M4A/MP4 не поддерживаются.
- Обрезка или удаление выделенного фрагмента, реверс, плавное начало и затухание.
- Скорость 0,5–2× с сохранением тона, тональность ±12 полутонов с сохранением темпа, громкость и нормализация.
- Эквалайзер, reverb «Комната» и «Зал», delay, distortion, tremolo, телефон, lo-fi и три пресета.
- Осциллограмма, сведения об аудио, воспроизведение выделения и сравнение с оригиналом.

В режиме «Вживую» скорость, тональность, громкость, эквалайзер, reverb и эффекты характера меняются в браузере. «Прослушать обработку» применяет все настройки через FFmpeg и возвращает WAV; так прослушиваются также удаление фрагмента, реверс, фейды и нормализация. Формат и битрейт экспорта используются при скачивании. Алгоритмы браузера и FFmpeg отличаются; при сильном изменении темпа или тона возможны артефакты. Reverb добавляет хвост 0,65 или 1,6 секунды.

По умолчанию: до 30 МиБ и 5 минут, одна обработка одновременно, до 60 секунд на загрузку и каждый запуск FFmpeg. Вход приводится к PCM 16 bit / 44,1 кГц / стерео: при обработке исходная точность мастер-файла может теряться даже при экспорте в lossless. Из контейнера извлекается первая аудиодорожка, видео игнорируется. Склейки, спектрограммы, выделения вокала и шумоподавления нет.

Файлы передаются через stdin/stdout и обрабатываются в RAM. Имя файла остаётся в браузере; логи содержат маршрут, статус, время и размер данных. В серверной конфигурации отключены запись тел запросов и ответов nginx на диск, swap процесса и дампы памяти. Systemd ограничивает сервис 1 ГиБ памяти; лишние загрузки получают 429 до чтения тела. Эти меры ограничивают нагрузку, но не исключают отказ сервиса на повреждённом файле.

## Локальный запуск

Нужны Python 3.12 и FFmpeg с кодеками libmp3lame, libvorbis, flac, aac и pcm_s16le. На Ubuntu 24.04: `sudo apt-get install python3.12-venv ffmpeg git`. На macOS — полная сборка с libvorbis:

```bash
brew install python@3.12 ffmpeg-full
export PATH="$(brew --prefix ffmpeg-full)/bin:$PATH"
```

```bash
git clone https://github.com/ResetPlease/slaymu5ic.git
cd slaymu5ic
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app_final:app --host 127.0.0.1 --port 8000
```

Интерфейс: [localhost:8000](http://localhost:8000/), Swagger: [localhost:8000/docs](http://localhost:8000/docs). Для разработки добавь `--reload`. Сборка фронтенда не нужна: модули и шрифты уже в репозитории.

Настройки читаются из окружения; файл `.env` автоматически не загружается. Пример настроек — в [.env.example](.env.example).

| Переменная | По умолчанию | Назначение |
| --- | --- | --- |
| `APP_VERSION` | `1.0.0` | Версия в `/version`; в релизе содержит короткий SHA |
| `APP_BASE_PATH` | пусто | Префикс всех маршрутов |
| `MAX_UPLOAD_MB` | `30` | Размер входа, МиБ |
| `MAX_DURATION_SECONDS` | `300` | Длительность входа, секунды |
| `PROCESS_TIMEOUT_SECONDS` | `60` | Таймаут загрузки и каждого FFmpeg, секунды |
| `MAX_CONCURRENT_JOBS` | `1` | Одновременные POST-запросы на процесс |
| `FFMPEG_MEMORY_MB` | `768` | Виртуальная память каждого FFmpeg на Linux, МиБ |
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `FFMPEG_BINARY` | `ffmpeg` | Исполняемый файл FFmpeg |

Для префикса сайта задай `APP_BASE_PATH=/slaymusic` перед командой запуска: интерфейс будет на /slaymusic/, API — на /slaymusic/api/, Swagger — на /slaymusic/docs. В production используется один worker: дополнительные процессы умножают число обработок и расход памяти. При изменении размера загрузки синхронизируй лимит приложения с `client_max_body_size` nginx.

## API

[Swagger на сервере](https://wrink.tech/slaymusic/docs) содержит полную схему параметров. Пути ниже указаны без префикса.

| Маршрут | Назначение |
| --- | --- |
| `GET /health` | Готовность и наличие FFmpeg; 503, если движок недоступен |
| `GET /version` | Версия сервиса |
| `GET /api/formats` | Форматы и ограничения |
| `POST /api/audio/info` | Длительность, уровни и до 600 точек осциллограммы |
| `POST /api/convert`, `/api/trim`, `/api/effects`, `/api/process` | Конвертация, обрезка и эффекты; любой маршрут поддерживает сочетание настроек |

POST принимает байты файла с `Content-Type: application/octet-stream`, параметры — в query string. Multipart не используется, чтобы избежать временных файлов.

```bash
curl --fail -H 'Content-Type: application/octet-stream' \
  --data-binary @track.wav \
  'http://127.0.0.1:8000/api/process?start=1&end=4&speed=1.25&pitch=3&format=mp3' \
  -o edited.mp3
```

Реверберация задаётся долей от 0 до 0,75 и типом комнаты room/hall; её можно сочетать с любым эффектом характера. Допустимые значения параметра `effect`: none, echo, distortion, tremolo, telephone, lofi.

Битрейт целевой и зависит от кодека и сигнала. Пределы в кбит/с: OGG при 22,05 кГц — 64 в моно / 128 в стерео; OGG моно при 44,1/48 кГц — 192; MP3 при 22,05 кГц — 128. Интерфейс учитывает эти ограничения.

Ошибки — JSON с полем `detail`: 413 — размер/длительность, 415 — тип тела, 422 — аудио/параметры, 429 — сервис занят, 408 — таймаут загрузки, 503 — нет FFmpeg, 504 — таймаут обработки. При 429 повтори запрос через время из `Retry-After`.

## Тесты и CI

В активированном виртуальном окружении:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest --cov=slaymusic --cov=app_final --cov-fail-under=90
ruff check .
ruff format --check .
```

Тесты проверяют реальные характеристики аудио, эффекты, ошибки, лимиты, отсутствие временных файлов, таймаут и отмену FFmpeg, перегрузку, Linux-ограничения, префикс API и откат релиза. Значок coverage gate обозначает обязательный порог покрытия Python-кода в CI.

Для браузерных тестов нужен Node.js 22+:

```bash
npm ci
npx playwright install --with-deps chromium
npm run test:e2e
```

Playwright сам запускает приложение на порту 8765 и проверяет воспроизведение, выделение, изменения звука, экспорт, ошибки и мобильный интерфейс. Для готового сервиса задай `E2E_BASE_URL=https://wrink.tech/slaymusic/` перед командой тестов.

GitHub Actions выполняет проверки при push и pull request, требует покрытие ≥90% и сохраняет архив приложения на 14 дней. Секреты и локальное окружение в архив не входят. Автодеплой на сервере отключён; установка, ручное обновление, нагрузочная проверка, диагностика и откат описаны в [deploy/README.md](deploy/README.md).

## Устройство проекта

FastAPI и маршруты находятся в [app_final.py](app_final.py), настройки, защита запросов, FFmpeg и анализ через NumPy — в [slaymusic/](slaymusic/). Интерфейс в [static/](static/) использует Web Audio, SoundTouchJS, Canvas и Manrope с кириллицей; ресурсы загружаются с того же сервера.

Проверки: [test_app.py](test_app.py) и [tests/](tests/). Серверные конфигурации: [deploy/](deploy/), вспомогательные команды: [scripts/](scripts/). Для обновления сторонних ресурсов после установки npm-зависимостей выполни `npm run vendor`; CI сверяет их с package-lock.json. Источники и лицензии — в [THIRD_PARTY.md](THIRD_PARTY.md).
