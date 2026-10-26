# Развёртывание и обслуживание

[← README](../README.md)

## CI и ручное обновление

GitHub Actions запускается при push и pull request: устанавливает зависимости, проверяет форматирование, запускает pytest и Playwright. После успешных проверок создаётся артефакт `slaymusic-<SHA>` с архивом приложения. Он хранится 14 дней. Содержимое архива выбирается явно; рабочие файлы окружения, secret.txt, ключи и локальное окружение в него не входят; безопасный пример .env.example включён.

На wrink.tech автоматический деплой отключён: таймер остановлен и исключён из автозапуска. Для ручного обновления после успешного CI выполни от root:

```bash
systemctl start slaymusic-update.service
```

Скрипт получает `origin/main` и проверяет последний запуск workflow `ci.yml` именно для этого коммита и события push. Незавершённый или неуспешный CI блокирует обновление; команду потребуется повторить после успешного CI. Для публичного репозитория токен GitHub и SSH-ключ в GitHub Actions не нужны. Скрипт развёртывания выполняется от root, поэтому право записи в main означает доверие к коду, устанавливаемому на сервер.

Проверенный коммит устанавливается в отдельный каталог с виртуальным окружением. Ссылка current переключается на релиз, сервис перезапускается. Проверяются /health и совпадение /version с коммитом. При ошибке возвращается предыдущий релиз; неудачный SHA блокируется до исправления или ручного снятия блокировки. Изменения unit-файлов и nginx требуют отдельной установки администратором, изменения приложения устанавливаются командой выше. Одного `git pull` недостаточно: сервис запускается из каталога релиза.

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
systemctl disable --now slaymusic-update.timer
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

Файл таймера сохранён для необязательного автодеплоя раз в две минуты. Если он нужен, включи его явно: `systemctl enable --now slaymusic-update.timer`. Отключение: `systemctl disable --now slaymusic-update.timer`.
