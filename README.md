# Daily Global Tech News Scheduler

A beginner-friendly Python learning project to collect global technology news,
store articles in MongoDB, organize them by topic, and eventually create a
daily briefing.

> **Learning project status:** This project is being built in stages. At
> present, configuration, MongoDB connection/index setup, keyword-based
> categorization, fetching and normalizing news from GNews, duplicate-safe
> article storage, daily briefing generation with
> MongoDB persistence, and daily scheduling are implemented. REST API
> endpoints are implemented.

## Project objective

The completed application is intended to collect news about AI, agentic AI,
quantum computing, cloud, cybersecurity, programming, developer tools, startups,
and major technology companies. It will remove duplicate stories, select
relevant articles, save a daily briefing, and expose stored data through REST
APIs.

## Technologies

- Python
- MongoDB and PyMongo
- GNews API and Requests for news collection
- Flask for the REST API
- APScheduler for daily scheduling
- `python-dotenv` for local environment variables
- VS Code, MongoDB Compass, and Postman

## Current project files

| File | Purpose |
| --- | --- |
| `config.py` | Loads environment variables and provides MongoDB, news API, and schedule settings. Schedule hour, minute, and IANA timezone are validated. |
| `database.py` | Prepares MongoDB collection handles, checks the connection, creates unique indexes, and saves articles while counting URL duplicates. |
| `models.py` | Contains editable keyword rules and `categorize_news(title, description)`. |
| `news_service.py` | Requests English articles from GNews and normalizes valid results into the project's article dictionaries. |
| `briefing_service.py` | Selects saved articles for a date, removes URL duplicates, groups them by category, renders a concise briefing, and saves it. |
| `scheduler.py` | Runs the fetch, save, and briefing workflow daily with logging and a single-instance job limit. |
| `interval_scheduler.py` | Starts/stops an API-process background refresh at one of the dashboard's test intervals. |
| `main.py` | Starts the blocking scheduler and configures application logging. |
| `api.py` | Provides news, briefing, health, API documentation, and automatic-refresh control endpoints. |
| `templates/dashboard.html` | Browser UI for testing endpoints and controlling periodic news/briefing refresh. |
| `tests/test_database.py` | Tests article validation, inserts, URL duplicates, and database failures using mocks. |
| `tests/test_briefing_service.py` | Tests briefing selection, duplicate handling, empty results, and database errors using mocks. |
| `tests/test_scheduler.py` | Tests schedule configuration, job registration, and workflow ordering/failures without waiting for the scheduled time. |
| `tests/test_api.py` | Tests API responses, parameter validation, serialization, empty results, and database errors with mocked database methods. |
| `tests/test_news_service.py` | Tests the GNews request, response normalization, empty results, and provider/network failures with mocked HTTP responses. |
| `tests/test_workflow_integration.py` | Exercises GNews normalization through storage and briefing generation as one workflow with mocked HTTP/database operations. |
| `requirements.txt` | Lists the Python dependencies used by the project. |
| `.env.example` | Safe template of settings. Copy it to `.env` for local use; never put real credentials in this template. |
| `.gitignore` | Excludes `.env`, virtual environments, and common generated files from Git. |

The current categories are Agentic AI, AI, Quantum Computing, Cloud,
Cybersecurity, Programming, Developer Tools, Startups, Technology Companies,
and Other Technology. The first matching category wins, so specific categories
such as Agentic AI are checked before the broader AI category.

## Installation

Open PowerShell in the project folder and create a virtual environment:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

If PowerShell does not allow activating the environment, run its Python
directly instead:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

## MongoDB setup

Install and start MongoDB Community Server locally, or create a MongoDB Atlas
deployment. MongoDB Compass can be used to connect to the same server and
inspect databases, collections, documents, and indexes.

Copy the example settings file:

```powershell
Copy-Item .env.example .env
```

Edit `.env` and set `MONGODB_URI` to your local or Atlas connection string. Keep
the real URI, password, and API key private. The `.env` file is ignored by Git;
only placeholder settings belong in `.env.example`.

If you previously configured another provider, replace its key with a GNews
key and use the `GNEWS_API_KEY` variable shown below. An API key for a different
provider will not authenticate with GNews.

Current settings:

| Variable | Default | Purpose |
| --- | --- | --- |
| `MONGODB_URI` | `mongodb://localhost:27017/` | MongoDB connection string |
| `DATABASE_NAME` | `tech_news` | Database name |
| `GNEWS_API_URL` | `https://gnews.io/api/v4/search` | GNews search endpoint |
| `GNEWS_API_KEY` | empty | GNews API key; set it in local `.env` before fetching |
| `NEWS_QUERY` | technology, AI, cybersecurity, and quantum terms | Search phrase sent to GNews |
| `NEWS_SCHEDULE_HOUR` | `6` | Daily run hour, from 0 to 23 |
| `NEWS_SCHEDULE_MINUTE` | `0` | Daily run minute, from 0 to 59 |
| `NEWS_SCHEDULE_TIMEZONE` | `Asia/Kolkata` | Valid IANA timezone used for the daily schedule |

The MongoDB database and collections are created by MongoDB when data is first
written. The current connection setup prepares handles for:

- `tech_news.news` — unique index on `url` to prevent duplicate articles.
- `tech_news.daily_briefings` — unique index on `briefing_date` to allow one
  briefing per date.

Connect to MongoDB and create the indexes:

```powershell
.\.venv\Scripts\python.exe -c "from database import connect_to_mongodb; connect_to_mongodb(); print('MongoDB connected; indexes ready')"
```

This requires a running MongoDB server and a valid `MONGODB_URI`. The index
creation will fail if existing documents contain duplicate values for the
indexed fields.

## Try the categorizer

Run a simple example:

```powershell
.\.venv\Scripts\python.exe -c "from models import categorize_news; print(categorize_news('Quantum computing breakthrough'))"
```

Expected output:

```text
Quantum Computing
```

If no configured keyword appears in the title or description, the function
returns `Other Technology`. To adjust categorization, edit the
`CATEGORY_KEYWORDS` dictionary in `models.py`.

## Fetch news

Create a GNews account at [gnews.io](https://gnews.io/register), get an API key
from its dashboard, and add it to your local `.env`:

```text
GNEWS_API_KEY=your_gnews_key
```

The `.env.example` file contains only a blank placeholder. Never commit or
share your real `.env` file. See the [GNews search endpoint
documentation](https://docs.gnews.io/endpoints/search-endpoint) for provider
parameters and plan limits.

Then fetch articles:

```powershell
.\.venv\Scripts\python.exe -c "from news_service import fetch_latest_news; print(fetch_latest_news()[:2])"
```

`fetch_latest_news()` calls the GNews search endpoint for up to 10 English
results sorted by publication time. The 10-result request limit is compatible
with GNews' free plan. It checks the provider response and returns a list of
article dictionaries with title, description, source, author, URL, category,
publication time, and collection time. Publication and collection times are
timezone-aware UTC `datetime` values. Articles without a usable title or URL
are skipped. An empty list means the provider returned no usable articles;
request, provider, and invalid-response problems raise `NewsAPIError`. The API
key is sent as the GNews `apikey` request parameter.

GNews `401` indicates the key is not associated with an account; `403` can
mean the daily quota is reached or the subscription expired; `429` indicates
requests are too close together. On the free plan, GNews documents a daily
quota and a one-request-per-second limit. See your GNews dashboard for current
quota and subscription status.

To save fetched results, run:

```powershell
.\.venv\Scripts\python.exe -c "from news_service import fetch_latest_news; from database import save_news_articles; articles = fetch_latest_news(); print(save_news_articles(articles))"
```

The result reports how many documents were inserted and how many URLs already
existed. `save_news_articles()` checks the database connection and unique URL
index before inserting. Duplicate URL errors are counted rather than treated as
fatal; other database errors raise a clear `RuntimeError`. An empty list returns
zero inserted and zero duplicates. This requires a running MongoDB server.
Avoid printing or sharing your `.env` contents; the API key is sent to the
provider as part of the request.

## Test article storage

The database storage tests use mocked MongoDB operations, so they do not need a
running MongoDB server:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests check empty batches, insert and duplicate counts, missing and blank
URLs, invalid article types, connection failures, and insert failures. Before
writing, the storage function validates every article URL so an invalid article
does not cause earlier articles in that batch to be partially inserted.

## Generate a daily briefing

With MongoDB running and articles already stored, generate and save a briefing
for today's UTC date:

```powershell
.\.venv\Scripts\python.exe -c "from briefing_service import generate_daily_briefing; print(generate_daily_briefing()['text'])"
```

The briefing service retrieves articles published on the requested UTC date.
When an article has no publication time, its collection date is used instead.
It selects at most 15 articles and no more than 3 per category. If existing
`importance_score` or `score` values are present, higher scores are preferred;
category order and newer publication times break ties. No score is invented
when those fields are absent. Repeated URLs are included only once, keeping the
version with the higher available score.

Each category section uses the article title, source-provided description,
source URL, and publication time when available. Descriptions are shortened for
display; missing descriptions or publication times are identified rather than
filled with invented story details. No external AI summarization service is
connected. The saved document is upserted by `briefing_date` in the
`daily_briefings` collection, so generating the same date again updates its
briefing rather than creating a second one.

If there are no saved articles for the date, the service creates an explicit
empty briefing. Database failures raise a clear error instead of returning a
success-shaped result.

Run the unit tests for article storage and briefing generation:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

The tests mock database operations and do not replace checking the workflow
against a real MongoDB server.

## Run the daily scheduler

Set `GNEWS_API_KEY` and `MONGODB_URI` in your local `.env`, ensure MongoDB is
running, then start the scheduler from PowerShell:

```powershell
.\.venv\Scripts\python.exe main.py
```

The application stays running and executes the workflow daily at
`NEWS_SCHEDULE_HOUR:NEWS_SCHEDULE_MINUTE` in `NEWS_SCHEDULE_TIMEZONE` (default
06:00 Asia/Kolkata). Each run fetches and validates news, saves new articles
while counting URL duplicates, then generates and saves the day's briefing.
Logs report successful run counts, failures, and elapsed time. A failed step is
logged and raised; later workflow steps are not reported as successful.

The scheduler permits only one instance of this job at a time and coalesces
missed runs while the process is alive. It does not run when the application is
stopped or the machine is unavailable. Keep this process and machine running
for automatic execution; press Ctrl+C to stop it. It waits for its next
scheduled time after startup; it does not automatically execute an immediate
run.

To execute the same workflow immediately for a manual check (with the API key
and MongoDB configured), use:

```powershell
.\.venv\Scripts\python.exe -c "from scheduler import run_news_workflow; print(run_news_workflow())"
```

Test schedule parsing, job registration, and workflow execution without waiting
for the scheduled time:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

## REST API

Run the API in a separate PowerShell terminal. It serves a small testing UI and
reads saved data from MongoDB; page/API requests do not fetch news.

```powershell
.\.venv\Scripts\python.exe api.py
```

The development server listens locally at `http://127.0.0.1:5000`. Start
`main.py` separately if you also want the daily scheduler; both processes need
the same `.env` settings and must remain running for their respective jobs.

Open `http://127.0.0.1:5000/` in your browser to use the test dashboard. It can
check API/database health, load saved articles, filter by category, search
articles, load a saved briefing by date, and start/stop automatic collection at
1 minute, 5 minutes, 1 hour, or 1 day. Starting a test interval performs an
immediate workflow, then repeats at that interval. The page checks scheduler
status every three seconds and automatically reloads news and the latest
briefing after a successful run. This interval scheduler runs inside the API
process and stops when that process exits. The existing daily scheduler in
`main.py` remains separate. A one-minute GNews test can consume a free account's
daily request allowance quickly; provider 403/429 errors are shown as failures,
not successful refreshes. `http://127.0.0.1:5000/docs` remains available as the
JSON endpoint listing.

| Method and path | Description | Success / error examples |
| --- | --- | --- |
| `GET /health` | Checks API and MongoDB connectivity | `200`; `503` if MongoDB is unavailable |
| `GET /docs` | Returns the API endpoint list as JSON | `200` |
| `GET /automation` | Returns current in-process interval status | `200` |
| `POST /automation` | Starts/replaces a test interval; JSON `{"interval":"1_minute"}` (also `5_minutes`, `1_hour`, `1_day`) | `200`; `400` for invalid selection |
| `DELETE /automation` | Stops the in-process interval schedule | `200` |
| `GET /news?page=1&per_page=20` | Lists latest saved articles, newest first | `200`; `400` for invalid pagination; `503` for database failures |
| `GET /news/<id>` | Returns one article by MongoDB ObjectId | `200`; `404` if invalid or not found; `503` for database failures |
| `GET /news/category/<category>` | Lists articles for a known category | `200`; `400` for an unknown category |
| `GET /news/search?keyword=python` | Searches title, description, and category | `200`; `400` for missing/too-long keyword |
| `GET /briefings?page=1&per_page=20` | Lists saved briefings, newest date first | `200`; `400` for invalid pagination |
| `GET /briefings/<date>` | Gets a saved briefing for `YYYY-MM-DD` | `200`; `400` for invalid date; `404` if not found |
| `GET /briefings?date=YYYY-MM-DD` | Same date-specific briefing lookup | Same as path form |

Pagination defaults to 20 results per page and allows at most 100. Successful
responses use JSON. MongoDB ObjectIds become strings and date/time values use
ISO 8601 format. Database errors return a generic `503` message without
including internal exception details.

Example PowerShell requests:

```powershell
Invoke-RestMethod http://127.0.0.1:5000/health
Invoke-RestMethod "http://127.0.0.1:5000/news?page=1&per_page=10"
Invoke-RestMethod "http://127.0.0.1:5000/news/search?keyword=python"
Invoke-RestMethod "http://127.0.0.1:5000/news/category/AI"
Invoke-RestMethod http://127.0.0.1:5000/briefings/2026-10-18
Invoke-RestMethod http://127.0.0.1:5000/docs
```

Example list response:

```json
{
  "items": [
    {
      "_id": "671234567890abcdef123456",
      "title": "Example source-provided headline",
      "category": "AI",
      "url": "https://example.com/article"
    }
  ],
  "page": 1,
  "per_page": 20,
  "total": 1
}
```

Example specific-briefing response:

```json
{
  "briefing_date": "2026-10-18",
  "total_news": 1,
  "categories": {
    "AI": 1
  },
  "text": "DAILY GLOBAL TECH BRIEFING..."
}
```

Run API tests without a live MongoDB connection:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_api -v
```

Interval scheduler and API tests run without waiting for an actual timer:

```powershell
.\.venv\Scripts\python.exe -m unittest tests.test_interval_scheduler tests.test_api -v
```

## Project implementation status

1. Request current news from a configured news source. **Implemented.**
2. Validate the JSON response, normalize article fields, and categorize them.
   **Implemented.**
3. Store normalized articles in MongoDB and skip duplicate URLs.
   **Implemented.** Importance scoring is still planned.
4. Select saved stories and generate/store a category-grouped daily briefing.
   **Implemented.** Scores are only used if present in stored documents.
5. Run this workflow daily at the configured hour and minute/timezone.
   **Implemented; the application must remain running.**
6. Serve saved news and briefings through REST API endpoints. **Implemented.**

API unit tests use mocked database methods. The API has not been verified
against a live MongoDB instance or exercised in Postman in this environment.

## Final project demonstration checklist

The automated tests can verify application behavior without contacting GNews
or MongoDB. Run them with:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

To demonstrate the live application when services are available:

1. Start MongoDB and confirm `MONGODB_URI` points to it.
2. Confirm the GNews key/account can make requests; provider HTTP 403 means
   GNews denied access (for example, quota or subscription status), not that a
   successful live fetch occurred.
3. Run one collection and briefing workflow with
   `.\.venv\Scripts\python.exe -c "from scheduler import run_news_workflow; print(run_news_workflow())"`.
4. Inspect `tech_news.news` and `tech_news.daily_briefings` in MongoDB Compass.
5. Start the API with `.\.venv\Scripts\python.exe api.py` and try its endpoints
   in Postman or with the PowerShell examples above.
6. Start daily automation separately with
   `.\.venv\Scripts\python.exe main.py`. Keep the process and machine running.

The mocked end-to-end test does not create real MongoDB documents, validate a
real GNews key, exercise Postman, or prove the scheduler remains running.
