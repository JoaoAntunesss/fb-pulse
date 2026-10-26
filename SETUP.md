# Setup: where to put your keys

Everything here is free on the Firebase **Spark** plan. You do not need a credit card. (If a project is on the
**Blaze** plan, usage beyond the free quota is billed, so keep the error log small, see step 5.)

You only need to set up what you want to see. Each of the four panels works on its own:

| Panel | Needs | Free? |
|---|---|---|
| Server status (up/slow/down, response time) | just the URLs in `config.json` | yes |
| Users (registered) | service account key | yes (Firebase Auth) |
| Active users right now | service account key + GA4 property ID + Analytics Data API | yes (within normal API limits) |
| Errors (last 24 h, latest messages) | service account key + an error log in Firestore (step 5) | yes within the daily Spark quota |

## 1. Install

```bash
python -m pip install -r requirements.txt   # Python 3.9+
cp config.example.json config.json           # Windows: copy config.example.json config.json
python main.py --demo                        # optional: see it with fake data first
```

## 2. Get a service account key (one per Firebase project)

1. Open the [Firebase console](https://console.firebase.google.com) and pick your project.
2. Click the gear icon, then **Project settings**, then the **Service accounts** tab.
3. Click **Generate new private key** and confirm. A `.json` file is downloaded.
4. **Move that file into the `keys/` folder** of this project and rename it, e.g. `keys/my-android-app.json`.
5. Write that path in `config.json` as `"service_account": "keys/my-android-app.json"`.

> The key gives **admin access** to your project. It stays on your computer: `keys/` and `config.json` are in
> `.gitignore`, so git never uploads them. Never email it, paste it in a chat, or put it in an app or website.
> If it leaks, delete it in Firebase console > Project settings > Service accounts > Manage service account permissions.

## 3. Server status

In `config.json`, list the addresses to check under `"urls"`: your Hosting site, a Cloud Function, an API.
A server counts as **up** if it answers at all with anything below HTTP 500 (a 401 or 404 still means it is alive),
**slow** above 2 seconds, **down** if it does not answer or answers 5xx. Tip: add a tiny `/health` function that returns `ok`.

## 4. Active users (GA4)

1. In [Google Analytics](https://analytics.google.com): **Admin > Property settings** and copy the **Property ID** (digits only).
   Put it in `config.json` as `"ga4_property_id": "123456789"`.
2. Still in Admin, open **Property access management**, click **+**, add the service account's e-mail
   (the `client_email` value inside your key file) with the role **Viewer**.
3. In the [Google Cloud console](https://console.cloud.google.com/apis/library/analyticsdata.googleapis.com)
   (same project) enable **Google Analytics Data API**.

## 5. Errors from your apps (free, and you control how much is sent)

Your apps write a small error document to a Firestore collection (default name `app_errors`). The dashboard counts
and shows the latest ones. Set `"errors_collection": "app_errors"` in `config.json`.

**Security rules** (Firebase console > Firestore Database > Rules). *Add* this block next to your existing rules, do
not replace them. Apps can only create small error documents; nobody can read or change them from an app. The dashboard
uses the admin key, which is not limited by these rules:

```
match /app_errors/{id} {
  allow create: if request.resource.data.keys().hasOnly(['ts', 'app', 'level', 'message'])
                && request.resource.data.message is string
                && request.resource.data.message.size() < 500;
  allow read, update, delete: if false;
}
```

**Android (Kotlin).** At most one report per minute, so a bug that loops can never use up your free quota:

```kotlin
object ErrorLog {
    private var last = 0L
    fun report(app: String, e: Throwable, level: String = "error") {
        val now = System.currentTimeMillis()
        if (now - last < 60_000) return            // max 1 per minute
        last = now
        Firebase.firestore.collection("app_errors").add(mapOf(
            "ts" to FieldValue.serverTimestamp(),
            "app" to app,
            "level" to level,
            "message" to (e::class.java.simpleName + ": " + (e.message ?: "")).take(400),
        ))
    }
}
// use it in your catch blocks:  catch (e: Exception) { ErrorLog.report("my-app", e) }
```

**Web (JavaScript):**

```js
import { getFirestore, collection, addDoc, serverTimestamp } from "firebase/firestore";
let last = 0;
export function reportError(app, err) {
  if (Date.now() - last < 60000) return;            // max 1 per minute
  last = Date.now();
  addDoc(collection(getFirestore(), "app_errors"), {
    ts: serverTimestamp(), app, level: "error", message: String(err).slice(0, 400),
  });
}
window.addEventListener("error", (e) => reportError("my-site", e.message));
```

Crashes that kill the app instantly may not manage to send their report: this log is for the errors you catch.
Real crash reports stay in Firebase Crashlytics (open in the console), which has no free API for a custom dashboard.

### What it costs in quota (check Firebase pricing for current numbers)
- Each reported error = 1 write. With 1 per minute per app the maximum is 1,440 a day.
- The dashboard reads about 9 documents per project every 10 minutes (about 1,300 a day). Change `slow_seconds` to read less often.
- Spark plan: when a daily quota is used up, requests are refused until it resets, with no charge.

## 6. Run it

```bash
python main.py
```

It opens http://127.0.0.1:8787 in your browser. The page is only reachable from your own computer.
If a panel shows an orange message, that is the exact error from Firebase (wrong path, missing role, API not enabled).
