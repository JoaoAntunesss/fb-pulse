# FB Pulse

A small, **free**, local dashboard for the health of your Firebase projects: are the servers up, how many users
are active right now, how many are registered, and what errors your apps reported in the last 24 hours.

![dashboard](docs/dashboard-demo.png)

> The screenshots use fake data (`python main.py --demo`). On a phone-sized window the cards stack in one column:
>
> <img src="docs/dashboard-phone.png" width="260" alt="phone layout">

## How it works

```mermaid
flowchart LR
  A[Your URLs] -->|every 60 s, simple GET| M[FB Pulse on your PC]
  B[Firebase Auth] -->|user count, every 10 min| M
  C[Google Analytics 4] -->|active users now, every 10 min| M
  D[Firestore app_errors] -->|count + latest 8, every 10 min| M
  M -->|127.0.0.1 only| W[Your browser]
  K[keys/ folder] -.read only by M.- M
```

1. **Servers:** every 60 s it requests each URL you listed. Any answer below HTTP 500 means up; over 2 s means slow;
   no answer or a 5xx means down. A small history is kept in `data/history.json` for the sparklines.
2. **Users and active users:** every 10 min it asks Firebase Auth for the user count and the GA4 realtime API for the
   number of people active right now.
3. **Errors:** your apps write short documents to a Firestore collection; the dashboard counts the last 24 h and shows
   the latest ones. [SETUP.md](SETUP.md) has the copy-paste code for Android and web and the security rules.
4. **The page** refreshes itself every 10 s and talks only to the local server. Keys are read from `keys/` by the
   Python side and are never sent to the browser.

- Runs on your own computer (`127.0.0.1`). No hosting, no account, nothing uploaded.
- Works with the Firebase **Spark** (free) plan. Reads of your Firebase data are tiny and every panel is optional.
- Your keys stay in the `keys/` folder, which git ignores. **Read [SETUP.md](SETUP.md) for exactly where to put them.**

## Quick start

```bash
python -m pip install -r requirements.txt
python main.py --demo          # try it with fake data
cp config.example.json config.json   # then edit it and follow SETUP.md
python main.py
```

## As a website

Prefer a page you can open from anywhere? A free GitHub Actions job can publish it to GitHub Pages: see [SETUP.md step 6](SETUP.md#6-optional-run-it-as-a-website-free-github-pages).

![hosted](docs/hosted-demo.png)

## Honest limits

- Crashlytics crash reports cannot be read for free by a custom dashboard (only through BigQuery, which can cost
  money). FB Pulse uses a small error log that your apps write to Firestore instead (SETUP.md, step 5).
- Active users come from the GA4 realtime API and can differ a little from the number in the Firebase console.
- Written and tested against simulated data only; the Firebase calls have not been run against a real project yet.
  If a panel shows an error, it shows the exact message so you can fix the setup.

## Tests

```bash
python -m unittest discover -s tests -v
```
