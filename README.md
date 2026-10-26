# Slaymusic

[![CI](https://github.com/ResetPlease/slaymu5ic/actions/workflows/ci.yml/badge.svg)](https://github.com/ResetPlease/slaymu5ic/actions/workflows/ci.yml)

Аудиоредактор для коротких музыкальных дорожек, подкастов и звуковых эффектов. Загрузи файл, выдели фрагмент, измени звучание, сравни результат с оригиналом и скачай его. Для знакомства есть синтезаторный демотрек.

**[Открыть студию](https://wrink.tech/slaymusic/)** · [Документация API](https://wrink.tech/slaymusic/docs) · [Запуски CI](https://github.com/ResetPlease/slaymu5ic/actions/workflows/ci.yml)

## Возможности

- Конвертация WAV, MP3, FLAC, OGG Vorbis и AAC ADTS; выбор частоты дискретизации, каналов и битрейта.
- Обрезка дорожки или удаление выделенного фрагмента. Границы задаются на осциллограмме либо в секундах.
- Скорость от 0,5× до 2× с сохранением тона; тональность от −12 до +12 полутонов с сохранением темпа.
- Громкость, плавное начало и затухание, обратное воспроизведение.
- Низкие и высокие частоты, reverb «Комната» и «Зал», delay, distortion, tremolo, телефон, lo-fi, нормализация и три пресета.
- Осциллограмма с выделением фрагмента, сведения об аудио и прослушивание результата.

В режиме «Вживую» скорость, тональность, громкость, эквалайзер, reverb и эффекты характера меняются сразу в браузере, без запросов к серверу. Play воспроизводит выбранный интервал. Кнопка «Прослушать обработку» применяет настройки обработки через FFmpeg и включает результат в WAV; выбранные формат и битрейт используются при скачивании. Удаление фрагмента, реверс, фейды и нормализация прослушиваются через эту кнопку. Reverb добавляет затухание длиной 0,65 или 1,6 секунды после фрагмента. Все настройки экспортируются на сервере; звучание в браузере может немного отличаться.

Регистрация не нужна. Загрузки и результаты обрабатываются только в оперативной памяти: приложение передаёт байты FFmpeg через stdin/stdout, nginx не буферизует их на диск. Базы данных, каталога загрузок и истории файлов нет. Имя файла остаётся в браузере; в логах сервера — маршрут, статус, время обработки и размер данных. В production отключены swap для процесса и дампы памяти.

По умолчанию файл ограничен 30 МБ и 5 минутами, одновременно обрабатывается одна загрузка. Таймаут каждой загрузки и каждого запуска FFmpeg — 60 секунд. Вход приводится к PCM 16 bit / 44,1 кГц / стерео, затем применяются настройки экспорта. «Без потерь» означает сжатие выходным кодеком: исходный мастер-файл при обработке может терять точность. AAC принимается в контейнере ADTS; M4A/MP4 не поддерживаются. Из разрешённых контейнеров извлекается первая аудиодорожка, видео игнорируется. Спектрограммы, склейки дорожек, выделения вокала и шумоподавления в этой версии нет.

## Локальный запуск

Нужны Python 3.12 и FFmpeg с кодеками libmp3lame, libvorbis, flac, aac, pcm_s16le. Node.js нужен для браузерных тестов и обновления сторонних ресурсов. Готовые модули и шрифты лежат в репозитории, сборка для запуска не требуется.

Ubuntu / Debian:

```bash
sudo apt-get update
sudo apt-get install -y python3-venv ffmpeg git
```

macOS: [полная сборка FFmpeg](https://formulae.brew.sh/formula/ffmpeg-full) включает libvorbis, которого может не быть в обычном пакете.

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

Студия: [localhost:8000](http://localhost:8000/). Swagger: [localhost:8000/docs](http://localhost:8000/docs). Команда выше подходит для обычного запуска без перезагрузки. Для разработки можно добавить `--reload`.

Настройки читаются из окружения. Файл `.env` автоматически не загружается; `.env.example` содержит безопасные значения. Например, запуск под тем же префиксом, что и на сервере:

```bash
APP_BASE_PATH=/slaymusic python -m uvicorn app_final:app --host 127.0.0.1 --port 8000
```

После этого интерфейс доступен по `/slaymusic/`, документация — по `/slaymusic/docs`.

Маршруты API получают префикс /slaymusic/api/.

## Тесты

```bash
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -v
python -m pytest --cov=slaymusic --cov=app_final --cov-fail-under=90
ruff check .
ruff format --check .
```

Тесты генерируют короткие WAV-сигналы в памяти. Проверяются форматы, реальные частоты и длительности результата, громкость, фейды, удаление фрагмента, ошибки параметров, лимиты, отказ от временных файлов, таймаут и отмена FFmpeg, отказ от чтения лишних загрузок при перегрузке, ограничения дочернего процесса на Linux, маршруты под префиксом и откат релиза.

Для браузерных тестов сначала установи Node.js 22+ по [инструкции Node.js](https://nodejs.org/en/download). Проверка установки: `node --version` и `npm --version`.

Затем:

```bash
npm ci
npx playwright install --with-deps chromium
npm run test:e2e
```

Playwright сам запускает приложение на порту 8765. Сценарии проверяют выделение и воспроизведение фрагмента, сохранение позиции при движении ползунков, частоту и амплитуду звука в Web Audio, пресеты, скачивание, ошибки и мобильную ширину. Для проверки уже запущенного сервиса:

```bash
E2E_BASE_URL=https://wrink.tech/slaymusic/ npm run test:e2e
```

Для обновления локальных модулей SoundTouchJS и шрифта Manrope выполни `npm run vendor` после установки зависимостей. CI проверяет, что ресурсы воспроизводятся из package-lock.json. Лицензии и источники перечислены в [THIRD_PARTY.md](THIRD_PARTY.md).

## API

| Метод и путь | Назначение |
| --- | --- |
| `GET /health` | Готовность сервиса и наличие FFmpeg; 503, если движок недоступен |
| `GET /version` | Версия из окружения |
| `GET /api/formats` | Форматы и ограничения загрузки |
| `POST /api/audio/info` | Длительность, уровни и до 600 точек осциллограммы |
| `POST /api/convert` | Конвертация формата |
| `POST /api/trim` | Обрезка либо удаление фрагмента |
| `POST /api/effects` | Изменение звучания |
| `POST /api/process` | Обработка с любым сочетанием настроек |

Все POST-маршруты принимают байты файла в теле с `Content-Type: application/octet-stream`. Multipart не используется, чтобы избежать автоматического создания временных файлов. Настройки передаются в query string; полная схема доступна в `/docs`. Маршруты обработки используют один движок и один набор параметров: преобразования можно комбинировать.

```bash
curl --fail http://127.0.0.1:8000/health
curl --fail http://127.0.0.1:8000/version
curl --fail -H 'Content-Type: application/octet-stream' \
  --data-binary @track.wav http://127.0.0.1:8000/api/audio/info
curl --fail -H 'Content-Type: application/octet-stream' \
  --data-binary @track.wav \
  'http://127.0.0.1:8000/api/trim?start=1&end=4&format=mp3' -o cut.mp3
curl --fail -H 'Content-Type: application/octet-stream' \
  --data-binary @track.wav \
  'http://127.0.0.1:8000/api/effects?speed=1.25&pitch=3&fade_out=0.5&format=wav' -o edited.wav
```

| Настройка эффекта | Значения |
| --- | --- |
| `reverb` | Доля реверберации от 0 до 0,75 |
| `reverb_room` | `room` или `hall` |
| `effect` | `none`, `echo`, `distortion`, `tremolo`, `telephone`, `lofi` |

Reverb можно сочетать с любым эффектом характера.

Битрейт — целевой, фактическое значение зависит от кодека и сигнала. Интерфейс ограничивает сочетания параметров: для OGG 22,05 кГц предел — 64 кбит/с в моно или 128 в стерео, для OGG моно 44,1/48 кГц — 192, для MP3 22,05 кГц — 128.

Ошибки возвращаются в JSON с полем `detail`: 413 — превышение размера или длительности; 415 — неподдерживаемый тип тела; 422 — ошибка аудио или параметров; 429 — заняты все места обработки; 408 — таймаут загрузки; 503 — нет FFmpeg; 504 — таймаут обработки. При 429 можно повторить запрос через время из `Retry-After`.

## Переменные окружения

| Имя | По умолчанию | Назначение |
| --- | --- | --- |
| `APP_VERSION` | `1.0.0` | Значение `/version`; при развёртывании содержит короткий SHA |
| `APP_BASE_PATH` | пусто | Префикс всех маршрутов, в production `/slaymusic` |
| `MAX_UPLOAD_MB` | `30` | Максимум байтов входного файла в МиБ |
| `MAX_DURATION_SECONDS` | `300` | Максимальная длительность входного аудио |
| `PROCESS_TIMEOUT_SECONDS` | `60` | Таймаут загрузки и отдельного запуска FFmpeg |
| `MAX_CONCURRENT_JOBS` | `1` | Число одновременных POST-запросов в одном процессе |
| `FFMPEG_MEMORY_MB` | `768` | Лимит виртуальной памяти каждого FFmpeg на Linux, в МиБ |
| `LOG_LEVEL` | `INFO` | Уровень логирования |
| `FFMPEG_BINARY` | `ffmpeg` | Путь к исполняемому файлу FFmpeg |

В production используется один worker. Увеличение числа workers умножает лимит одновременно обрабатываемых файлов и расход памяти.

## CI и автоматическое развёртывание

GitHub Actions запускается при push и pull request: устанавливает зависимости, проверяет форматирование, запускает pytest и Playwright. После успешных проверок создаётся артефакт `slaymusic-<SHA>` с архивом приложения. Он хранится 14 дней. Содержимое архива выбирается явно; файлы окружения, secret.txt, ключи и локальное окружение в него не входят.

CD работает на сервере через systemd timer. Раз в две минуты сервер получает `origin/main` и проверяет последний запуск workflow `ci.yml` именно для этого коммита и события push. Незавершённый или неуспешный CI блокирует обновление. Для публичного репозитория токен GitHub и SSH-ключ в GitHub Actions не нужны.

Проверенный коммит устанавливается в отдельный каталог с виртуальным окружением. Ссылка current переключается на релиз, сервис перезапускается. Проверяются `/health` и совпадение `/version` с коммитом. При ошибке возвращается предыдущий релиз; неудачный SHA блокируется до исправления или ручного снятия блокировки. Изменения unit-файлов и nginx требуют отдельной установки администратором, обычные изменения приложения выкатываются автоматически.

Структура на сервере:

```text
/opt/slaymusic/repository       Git checkout
/opt/slaymusic/releases/<SHA>   Код и окружение каждого релиза
/opt/slaymusic/current          Активный релиз
/etc/slaymusic.env              Настройки сервиса
/etc/nginx/snippets/slaymusic.conf
/etc/nginx/conf.d/slaymusic-limits.conf
```

Первичная установка на Ubuntu 24.04 от root предполагает уже настроенные DNS домена, HTTPS-блок nginx и сертификат. Команды ниже дополняют существующий сервер wrink.tech:

```bash
apt-get update
apt-get install -y python3-venv ffmpeg git nginx
useradd --system --no-create-home --shell /usr/sbin/nologin slaymusic
mkdir -p /opt/slaymusic/releases
git clone https://github.com/ResetPlease/slaymu5ic.git /opt/slaymusic/repository
cd /opt/slaymusic/repository
cp .env.example /etc/slaymusic.env
sed -i 's|^APP_BASE_PATH=.*|APP_BASE_PATH=/slaymusic|' /etc/slaymusic.env
chmod 600 /etc/slaymusic.env
cp deploy/slaymusic.service deploy/slaymusic-update.service deploy/slaymusic-update.timer /etc/systemd/system/
cp deploy/nginx-limits.conf /etc/nginx/conf.d/slaymusic-limits.conf
cp deploy/nginx-location.conf /etc/nginx/snippets/slaymusic.conf
systemctl daemon-reload
systemctl enable slaymusic
systemctl enable --now slaymusic-update.timer
systemctl start slaymusic-update.service
```

Сохрани копию существующей конфигурации nginx. В HTTPS-блок server домена добавь:

```nginx
include /etc/nginx/snippets/slaymusic.conf;
```

Проверь и примени конфигурацию:

```bash
nginx -t && systemctl reload nginx
```

Остальные маршруты домена сохраняются. Префикс проксируется целиком; запрос /slaymusic перенаправляется на /slaymusic/.

Сервис работает от отдельного пользователя и слушает только `127.0.0.1:8093`. Systemd ограничивает весь процесс с дочерними FFmpeg: 1 ГиБ памяти, без swap, до 150% одного CPU и 32 задач. Системные и временные каталоги доступны только для чтения. FFmpeg дополнительно получает лимиты виртуальной памяти, CPU, размера отдельного выделения памяти и открытых файлов; разрешены только pipe и пять аудиоконтейнеров. Сетевые адреса, плейлисты и обращения к файлам не принимаются.

Лишний POST-запрос получает 429 до чтения тела: очереди аудиофайлов в памяти нет. Nginx допускает до двух одновременных загрузок с IP и восьми суммарно, с частотой 30 запросов в минуту на IP и кратковременным всплеском до десяти. Эти правила действуют только для POST в /slaymusic/api/. Чтение страницы и health не занимает слот обработки. Буферизация тел запросов и ответов на диск отключена.

Нагрузочный скрипт создаёт пятиминутный FLAC, проверяет 24 параллельных отказа, доступность health, тяжёлые сочетания эффектов и ошибочные входы. На сервере с установленным сервисом выполни от root команды ниже. Они запускают копию активного релиза на локальном порту 8094 с теми же ограничениями; потребуется дополнительная память для тестового экземпляра.

```bash
cd /opt/slaymusic/repository
python3 -m venv /tmp/slaymusic-check-tools
/tmp/slaymusic-check-tools/bin/pip install -r requirements-dev.txt
sed 's/--port 8093/--port 8094/' /etc/systemd/system/slaymusic.service > /run/systemd/system/slaymusic-check.service
systemctl daemon-reload
systemctl start slaymusic-check
curl --fail http://127.0.0.1:8094/slaymusic/health
/tmp/slaymusic-check-tools/bin/python scripts/load_check.py
systemctl show slaymusic-check -p MemoryPeak -p MemoryCurrent -p NRestarts
cat /sys/fs/cgroup/system.slice/slaymusic-check.service/memory.events
systemctl stop slaymusic-check
rm /run/systemd/system/slaymusic-check.service
systemctl daemon-reload
```

Проверку выполняй на отдельном экземпляре: она намеренно занимает слот обработки. Ограничения защищают остальную машину, но не исключают отказ самого сервиса на произвольном повреждённом файле.

При изменении лимита загрузки синхронизируй `MAX_UPLOAD_MB` и `client_max_body_size`.

## Диагностика и откат

При локальном запуске события запуска, запросов и обработки выводятся в терминал. На сервере wrink.tech (при установке на другом домене замени адрес в curl):

```bash
curl --fail https://wrink.tech/slaymusic/health
curl --fail https://wrink.tech/slaymusic/version
systemctl status slaymusic slaymusic-update.timer
journalctl -u slaymusic -n 100 --no-pager
journalctl -u slaymusic-update -n 100 --no-pager
nginx -t
```

| Симптом | Проверка |
| --- | --- |
| 502 от nginx | Состояние `slaymusic`, логи, доступность порта 8093 |
| 503 от приложения | `ffmpeg -version`, значение `FFMPEG_BINARY` |
| 422 при экспорте OGG | `ffmpeg -encoders` должен содержать `libvorbis`; на macOS установи `ffmpeg-full` |
| 413 | Размер и длительность файла; лимиты приложения и nginx |
| 429 или 504 | Повтори позже или используй более короткий файл |
| Новая версия не появилась | CI нужного SHA, журнал `slaymusic-update`, доступ сервера к GitHub, файл `failed-release` |
| `/docs` или статика возвращают 404 | Совпадение `APP_BASE_PATH` и пути nginx |

Ручной откат: останови таймер, выбери предыдущий SHA из каталога releases, переключи ссылку и перезапусти сервис. Таймер оставь выключенным до исправления проблемного коммита, иначе он снова установит вершину main, если её CI успешен.

```bash
systemctl stop slaymusic-update.timer
systemctl stop slaymusic-update.service
ls /opt/slaymusic/releases
ln -s /opt/slaymusic/releases/PREVIOUS_SHA /opt/slaymusic/current.rollback
mv -Tf /opt/slaymusic/current.rollback /opt/slaymusic/current
systemctl restart slaymusic
curl --fail https://wrink.tech/slaymusic/version
```

Чтобы повторить автоматически отклонённый релиз после устранения причины, удали `/opt/slaymusic/failed-release` и запусти `slaymusic-update.service`.

После исправления и проверки верни таймер командой `systemctl start slaymusic-update.timer`.

## Структура проекта

```text
app_final.py           FastAPI, маршруты и префикс
slaymusic/             Настройки, защита запросов и аудиодвижок
static/                Интерфейс без сборки и внешних ресурсов
test_app.py            Проверки сервиса и конфигурации
tests/                 Аудиотесты, CD и браузерные сценарии
deploy/                systemd, nginx и обновление релизов
scripts/               Сборка ресурсов и нагрузочная проверка
.github/workflows/     CI с артефактом приложения
```

FastAPI отвечает за HTTP и валидацию, FFmpeg — за экспорт и эффекты, NumPy — за анализ сигнала. Web Audio и SoundTouchJS меняют темп и тон в браузере; Canvas API рисует осциллограмму, демотрек синтезируется локально. Интерфейс использует Manrope с кириллицей, шрифт загружается с того же сервера. При сильном изменении темпа или тона возможны слышимые артефакты; прослушивание в браузере и обработка FFmpeg используют разные алгоритмы.
