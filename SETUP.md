# Подключение профиля Nek1tt/Nek1tt

Этот комплект рассчитан на репозиторий **`Nek1tt/Nek1tt`**.

После подключения README будет отображаться прямо на странице
`github.com/Nek1tt`, а статистика будет автоматически обновляться GitHub Actions.

## Что уже настроено

- готовый `README.md`;
- 6 карточек основных репозиториев;
- подробная статистика GitHub;
- распределение языков;
- commits / PR / issues / reviews;
- число репозиториев, stars / forks / watchers;
- current streak / longest streak;
- contribution heatmap за 365 дней;
- ежедневное автообновление;
- ручной запуск через `Run workflow`;
- защита от сломанных карточек: при ошибке генератора остаётся последняя рабочая SVG;
- никаких обязательных сторонних API-ключей;
- никаких обязательных Personal Access Token;
- README показывает локальные `profile/*.svg`, а не картинки с внешних серверов.

## 1. Создать профильный репозиторий

На GitHub:

1. Нажми **New repository**.
2. Repository name: **`Nek1tt`**
3. Visibility: **Public**
4. Лучше создать репозиторий пустым — без README, `.gitignore` и license.
5. Нажми **Create repository**.

GitHub распознаёт публичный репозиторий, имя которого совпадает с username,
как Profile README repository.

## 2. Загрузить готовый комплект

Распакуй архив `Nek1tt-GitHub-Profile.zip`.

В PowerShell:

```powershell
git clone https://github.com/Nek1tt/Nek1tt.git
cd Nek1tt
```

Скопируй **содержимое** распакованной папки `Nek1tt-GitHub-Profile`
в только что клонированную папку `Nek1tt`.

В корне должно получиться:

```text
Nek1tt/
├── README.md
├── SETUP.md
├── profile/
├── scripts/
└── .github/
    └── workflows/
        └── update-profile.yml
```

Затем:

```powershell
git add .
git commit -m "feat: add GitHub profile README"
git push
```

## 3. Проверить разрешения GitHub Actions

Открой:

**Nek1tt/Nek1tt → Settings → Actions → General**

Проверь:

### Actions permissions
Можно оставить:

**Allow all actions and reusable workflows**

### Workflow permissions
Выбери:

**Read and write permissions**

и нажми **Save**.

В самом workflow уже указано:

```yaml
permissions:
  contents: write
```

Это нужно только для того, чтобы бот GitHub Actions мог коммитить обновлённые
SVG-файлы обратно в профильный репозиторий.

## 4. Один раз запустить генерацию

Открой:

**Nek1tt/Nek1tt → Actions → Update GitHub Profile**

Нажми:

**Run workflow → Run workflow**

Первый запуск заменит стартовые SVG на реальные карточки из твоего GitHub.

После завершения открой вкладку **Code**. В `profile/` должны быть:

```text
profile/
├── userstats.svg
├── streak.svg
├── activity.svg
├── pin-rns-llm.svg
├── pin-human-attributes.svg
├── pin-raman.svg
├── pin-ros-autorace.svg
├── pin-sound-detector.svg
└── pin-ai-agents.svg
```

## 5. Дальше ничего делать не нужно

Workflow запускается ежедневно:

```yaml
schedule:
  - cron: "17 3 * * *"
    timezone: "Europe/Berlin"
```

То есть обновление запланировано на **03:17 по Europe/Berlin**.

03:17 выбрано специально не на начало часа: GitHub предупреждает, что scheduled
workflows чаще задерживаются в периоды высокой нагрузки около начала часа.

Также workflow всегда можно запустить вручную через **Run workflow**.

## Как защищён профиль от падений генераторов

Новые SVG сначала создаются в:

```text
.generated/
```

Затем `scripts/promote_generated_svgs.py` проверяет, что файл:

- существует;
- действительно содержит SVG;
- не является error-card;
- не содержит типичные сообщения API/rate-limit ошибок.

Только после проверки SVG копируется в:

```text
profile/
```

Если конкретная генерация не удалась, старый рабочий файл в `profile/`
**не удаляется и не перезаписывается**.

Поэтому временная ошибка Action не превращает README в набор broken images.

## Откуда берётся статистика

### `userstats.svg`

Генерируется:

```text
cicirello/user-statistician
```

Включает:

- public repositories;
- stars / forks / watchers;
- commits;
- issues;
- pull requests;
- pull request reviews;
- contributed-to repositories;
- private contribution count, если GitHub разрешено показывать private contributions;
- language distribution.

Генератор выполняется внутри GitHub Actions и использует GitHub GraphQL API.

### `streak.svg` и `activity.svg`

Генерируются собственным скриптом:

```text
scripts/generate_contribution_cards.py
```

Он напрямую получает GitHub contribution calendar через GraphQL API и считает:

- current streak;
- longest streak;
- contributions за 365 дней;
- active days;
- contribution heatmap.

Внешнего streak-сервера здесь нет.

### Featured repository cards

Генерируются:

```text
stats-organization/github-readme-stats-action
```

Он запускает рендер карточек прямо внутри GitHub Actions и сохраняет их как
статические SVG в репозитории.

README не обращается к публичному `github-readme-stats.vercel.app`.

## Нужен ли Personal Access Token?

**Нет.**

По умолчанию используется:

```yaml
${{ secrets.GITHUB_TOKEN }}
```

GitHub автоматически создаёт этот временный токен для каждого workflow run.

Это самый простой и безопасный вариант: вручную создавать и хранить PAT не нужно.

## Private contributions

Если хочешь, чтобы GitHub публично показывал число приватных вкладов без раскрытия
названий приватных репозиториев:

**GitHub → Settings → Profile → Contributions & activity**

включи:

**Include private contributions on my profile**

После этого GitHub API может возвращать restricted/private contribution count.
Содержимое приватных репозиториев при этом публичным не становится.

## Важный нюанс scheduled workflows

GitHub автоматически отключает scheduled workflows в публичном репозитории,
если в нём не было активности 60 дней.

Для активного GitHub-профиля это обычно не проблема. Если GitHub когда-нибудь
отключит расписание:

**Actions → Update GitHub Profile → Enable workflow**

и всё продолжит работать.

Даже в этом случае README не ломается: сохранённые SVG продолжают отображаться.

## Какие репозитории сейчас вынесены в профиль

1. `rns-llm`
2. `Human_Attributes_Detector`
3. `Raman-Spectrum-Analyzer`
4. `ROS_autorace_competition_2025`
5. `Sound-Detector`
6. `AI-agent-autonomous-life`

Если позже захочешь заменить проект, нужно изменить две вещи:

1. ссылку/`img` в `README.md`;
2. соответствующий `repo=...` step в `.github/workflows/update-profile.yml`.

## Быстрая проверка

После первого Action открой:

```text
https://github.com/Nek1tt
```

Если README сверху профиля виден, а все SVG загружаются — настройка завершена.
