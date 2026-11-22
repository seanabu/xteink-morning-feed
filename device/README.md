# Phone and X3 hookups

Two small pieces send events to the `Record` workflow
(`.github/workflows/record.yml`), which writes them to the repo's `state`
branch. The next daily build reads them.

Both use the same GitHub token.

## 1. Make a token (once)

GitHub → Settings → Developer settings → Fine-grained personal access tokens →
Generate new token.

- Repository access: **Only select repositories** → this repo.
- Permissions → Repository permissions → **Actions: Read and write**. Nothing else.
- Expiration: up to a year; put a reminder in your calendar.

This token can start and cancel workflow runs in this repo. It cannot read or
change code, so losing the SD card or phone doesn't expose the repo.

## 2. Read-later: iPhone share sheet

Shortcuts app → **+** → name it "Save to Morning Feed".

1. Tap the **ⓘ** (Details) → turn on **Show in Share Sheet**. Under "Receive",
   pick **URLs** and **Safari web pages** only.
2. Add action **Get URLs from Input** (input: Shortcut Input).
3. Add action **Get Contents of URL**:
   - URL: `https://api.github.com/repos/OWNER/REPO/actions/workflows/record.yml/dispatches`
   - Method: **POST**
   - Headers:
     - `Authorization`: `Bearer <your token>`
     - `Accept`: `application/vnd.github+json`
   - Request Body: **JSON**
     - `ref` (Text): `main`
     - `inputs` (Dictionary):
       - `kind` (Text): `save`
       - `profile` (Text): your profile name, e.g. `sean`
       - `url` (Text): the **URLs** variable from step 2
4. Add action **Show Notification**: "Saved for tomorrow's issue".

Use it from any app's Share button. GitHub answers with an empty 204 when it
worked. The link shows up in the next morning's issue under "Saved"; if the
page won't extract (paywall, app-only page) it appears as a card with the URL.

## 3. Reading feedback: the X3 plugin

1. Copy `config.example.json` to `config.json` in `device/morningfeed/` and set
   `repo` (e.g. `you/xteink-morning-feed`) and `profile`.
2. Copy `token.example.json` to `token.json` and paste the token. Both filled-in
   files are git-ignored so the token never gets committed.
3. Copy the `morningfeed` folder (with `device.json`, `config.json`, `token.json`) to the SD card at `/.crosspoint/plugins/morningfeed/`
   (Wi‑Fi upload at `crosspoint.local` works, or the card reader).
4. On the X3: Settings → Connectivity → **Plugins: On**, then restart the device.

After that, when you put the X3 to sleep after reading, it joins Wi‑Fi for a
few seconds and reports the session: which issue, where you started and
stopped, and how long you read. Sessions in any other book are dropped by the
workflow and never stored. Nothing is sent below 20% battery; queued sessions
go out on the next connection.

The daily build maps each session onto the articles it covered and nudges
source and topic weights (by at most ±30%, set by `learn_strength` in
`profile.yaml`). See `state/<profile>/learned.json` on the `state` branch.

**Note:** the repo is public, so the `state` branch is too: saved links and
which issue articles were read are visible to anyone who looks.
