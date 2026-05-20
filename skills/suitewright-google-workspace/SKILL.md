---
name: suitewright-google-workspace
description: "Gmail, Calendar, Drive, Docs, Sheets, Contacts, and Forms via the suitewright CLI. Use when automating Google Workspace tasks: reading or sending email, managing calendar events, uploading or downloading Drive files, editing Docs, reading or writing Sheets, or working with Forms. Follows a cache-first workflow: fetch, inspect locally, validate, mutate, refresh. Handles OAuth setup and agent-safe mutation patterns."
license: Apache-2.0
compatibility: "Requires Python 3.11+. Google OAuth2 credentials required (see auth setup). Works on Linux, macOS, and Windows."
metadata:
  author: glenkusuma
  version: "1.0.0"
  tags: [Google, Gmail, Calendar, Drive, Sheets, Docs, Contacts, Forms, OAuth]
  homepage: https://github.com/glenkusuma/suitewright
---

# suitewright Google Workspace

Gmail, Calendar, Drive, Contacts, Sheets, Docs, and Forms - through local OAuth and the `suitewright` CLI.

**Required credentials (dev mode):**
- `$SUITEWRIGHT_AUTH_DIR/google_token.json` - Google OAuth2 token (created by `suitewright auth login`)
- `$SUITEWRIGHT_AUTH_DIR/google_client_secret.json` - Google OAuth2 client credentials (downloaded from Google Cloud Console)

In dev mode, `SUITEWRIGHT_AUTH_DIR` defaults to `../suitewright-auth` relative to the repo root.
When installed as a package, auth files live in `~/.config/suitewright/auth/` by default.

## References

- `references/gmail-search-syntax.md` - Gmail search operators (is:unread, from:, newer_than:, etc.)
- `references/forms-auth.md` - Forms scopes and reauth note for Google Forms workflows
- `references/python-client-source.md` - Python package provenance and install instructions
- `references/docs-request-template-styling.md` - reusable styling guidance for `docs request-template style-range`

## First-Time Setup

The setup is fully non-interactive - you drive it step by step so it works
on CLI, Telegram, Discord, or any platform.

### Step 0: Check if already set up

```bash
suitewright auth check
```

If it prints `AUTHENTICATED`, skip to Usage - setup is already done.

### Step 1: Triage - ask the user what they need

Before starting OAuth setup, ask the user TWO questions:

**Question 1: "What Google services do you need? Just email, or also
Calendar/Drive/Sheets/Docs?"**

- **Email only** -> They may not need this skill at all. A Gmail App Password
  (Settings -> Security -> App Passwords) may be sufficient and takes 2 minutes
  to set up with no Google Cloud project needed.

- **Email + Calendar** -> Continue with this skill using the standard auth flow below.

- **Calendar/Drive/Sheets/Docs only** -> Continue with this skill using the standard auth flow below.

- **Full Workspace access** -> Continue with this skill using the standard auth flow below.

**Question 2: "Does your Google account use Advanced Protection (hardware
security keys required to sign in)? If you're not sure, you probably don't
- it's something you would have explicitly enrolled in."**

- **No / Not sure** -> Normal setup. Continue below.
- **Yes** -> Their Workspace admin must add the OAuth client ID to the org's
  allowed apps list before Step 4 will work. Let them know upfront.

### Step 2: Create OAuth credentials (one-time, ~5 minutes)

Tell the user:

> You need a Google Cloud OAuth client. This is a one-time setup:
>
> 1. Create or select a project:
>    https://console.cloud.google.com/projectselector2/home/dashboard
> 2. Enable the required APIs from the API Library:
>    https://console.cloud.google.com/apis/library
>    Enable: Gmail API, Google Calendar API, Google Drive API,
>    Google Sheets API, Google Docs API, People API, Google Forms API
> 3. Create the OAuth client here:
>    https://console.cloud.google.com/apis/credentials
>    Credentials -> Create Credentials -> OAuth 2.0 Client ID
> 4. Application type: "Desktop app" -> Create
> 5. If the app is still in Testing, add the user's Google account as a test user here:
>    https://console.cloud.google.com/auth/audience
>    Audience -> Test users -> Add users
> 6. Download the JSON file and tell me the file path
>
> Important CLI note: if the file path starts with `/`, do NOT send only the bare path as its own message in the CLI, because it can be mistaken for a slash command. Send it in a sentence instead, like:
> `The JSON file path is: /home/user/Downloads/client_secret_....json`

Once they provide the path:

```bash
suitewright auth init --client-secret /path/to/client_secret.json
```

If they do not have a client secret JSON file yet, stop and ask them to download
the Desktop OAuth JSON file first. Do not ask them to paste raw client-secret
values into chat.

### Step 3: Get authorization URL

```bash
suitewright auth login --auth-url
```

Agent rules for this step:
- Send the printed URL to the user as a single line.
- Tell the user that the browser will likely fail on `http://localhost:1` after approval, and that this is expected.
- Tell them to copy the ENTIRE redirected URL from the browser address bar.
- If the user gets `Error 403: access_denied`, send them directly to `https://console.cloud.google.com/auth/audience` to add themselves as a test user.

### Step 4: Exchange the code

The user will paste back either a URL like `http://localhost:1/?code=4/0A...&scope=...`
or just the code string. Either works. The `--auth-url` step stores a temporary
pending OAuth session locally so `--auth-code` can complete the PKCE exchange
later, even on headless systems:

```bash
suitewright auth login --auth-code "THE_URL_OR_CODE_THE_USER_PASTED"
```

### Step 5: Verify

```bash
suitewright auth check
```

Should print `AUTHENTICATED`. Setup is complete - token refreshes automatically from now on.

### Notes

- Token is stored at `$SUITEWRIGHT_AUTH_DIR/google_token.json` (dev mode) or `~/.config/suitewright/auth/` (installed) and auto-refreshes.
- Pending OAuth session state/verifier are stored temporarily at `$SUITEWRIGHT_AUTH_DIR/google_oauth_pending.json` until exchange completes.
- To revoke: `suitewright auth revoke`

## Usage

### Gmail

```bash
# Search (returns JSON array with id, from, subject, date, snippet)
suitewright gmail search "is:unread" --max 10
suitewright gmail search "from:boss@company.com newer_than:1d"
suitewright gmail search "has:attachment filename:pdf newer_than:7d"

# Read full message (returns JSON with body text)
suitewright gmail get MESSAGE_ID

# Send
suitewright gmail send --to user@example.com --subject "Hello" --body "Message text"
suitewright gmail send --to user@example.com --subject "Report" --body "<h1>Q4</h1><p>Details...</p>" --html

# Reply (automatically threads and sets In-Reply-To)
suitewright gmail reply MESSAGE_ID --body "Thanks, that works for me."

# Labels
suitewright gmail labels
suitewright gmail modify MESSAGE_ID --add-labels LABEL_ID
suitewright gmail modify MESSAGE_ID --remove-labels UNREAD

# Trash
suitewright gmail trash MESSAGE_ID
```

### Calendar

```bash
# List events
suitewright calendar list --calendar CALENDAR_ID
suitewright calendar list --calendar CALENDAR_ID --start 2026-03-01T00:00:00Z --end 2026-03-07T23:59:59Z

# Create event (ISO 8601 with timezone required)
suitewright calendar create --calendar CALENDAR_ID --summary "Team Standup" --start 2026-03-01T10:00:00-06:00 --end 2026-03-01T10:30:00-06:00
suitewright calendar create --calendar CALENDAR_ID --summary "Lunch" --start 2026-03-01T12:00:00Z --end 2026-03-01T13:00:00Z --location "Cafe"
suitewright calendar create --calendar CALENDAR_ID --summary "Review" --start 2026-03-01T14:00:00Z --end 2026-03-01T15:00:00Z --attendees "alice@co.com,bob@co.com"

# Delete event
suitewright calendar delete EVENT_ID --calendar CALENDAR_ID
```

### Drive

```bash
# Search existing files
suitewright drive search "quarterly report" --max 10
suitewright drive search "mimeType='application/pdf'" --raw-query --max 5

# Get file metadata
suitewright drive get FILE_ID

# Upload
suitewright drive upload /path/to/file.pdf --parent FOLDER_ID

# Download
suitewright drive download FILE_ID --output /path/to/save

# Create folder
suitewright drive create-folder "Reports" --parent FOLDER_ID

# Share
suitewright drive share FILE_ID --email user@example.com --role reader

# Delete (trash by default)
suitewright drive delete FILE_ID
suitewright drive delete FILE_ID --permanent
```

### Contacts

```bash
suitewright contacts list --max 20
```

### Sheets

```bash
# Read
suitewright sheets get SHEET_ID "Sheet1!A1:D10"

# Write
suitewright sheets update SHEET_ID "Sheet1!A1:B2" --values '[["Name","Score"],["Alice","95"]]'

# Append rows
suitewright sheets append SHEET_ID "Sheet1!A:C" --values '[["new","row","data"]]'
```

### Docs

```bash
# Read
suitewright docs get DOC_ID
suitewright docs show-structure DOC_ID
suitewright docs show-structure DOC_ID --full-text

# Generate starter Docs request payloads
suitewright docs request-template replace-all
suitewright docs request-template insert-table
suitewright docs request-template insert-image
suitewright docs request-template style-range

# Create a new Doc (optionally seeded with body text)
suitewright docs create --title "Meeting Notes"
suitewright docs create --title "Draft" --body "First paragraph..."

# Append text to the end of an existing Doc
suitewright docs append DOC_ID --text "Additional content to append"

# Replace the full document body
suitewright docs replace DOC_ID --text "Fresh replacement body"

# Apply raw Docs API batchUpdate requests
suitewright docs update DOC_ID --requests '[{"insertText":{"location":{"index":1},"text":"Hello"}}]'
suitewright docs update DOC_ID --requests-file /path/to/requests.json
suitewright docs update DOC_ID --dry-run --requests '[{"insertText":{"location":{"index":1},"text":"Hello"}}]'

# Semantic helpers
suitewright docs replace-all DOC_ID --find "old text" --replace "new text"
suitewright docs insert-table DOC_ID --rows 3 --cols 4 --index 1
suitewright docs insert-image DOC_ID --uri https://example.com/image.png --index 1
suitewright docs style-range DOC_ID --start-index 1 --end-index 10 --bold

# Table helpers
suitewright docs table-get DOC_ID
suitewright docs table-get DOC_ID --table 0
suitewright docs table-update-cell DOC_ID --table 0 --row 1 --col 2 --text "Updated"
suitewright docs table-append-row DOC_ID --table 0 --values '["A","B","C"]'

# Comments
suitewright docs comments list DOC_ID
suitewright docs comments get DOC_ID COMMENT_ID
suitewright docs comments reply DOC_ID COMMENT_ID --text "Reply text"

# Plan (inspect without mutating)
suitewright docs plan DOC_ID --requests-file /path/to/requests.json
```

### Forms

State lifecycle commands:

```bash
# Fetch live form and write local cache
suitewright forms fetch FORM_ID

# Print current local cache path
suitewright forms show-cache FORM_ID

# Validate cache assumptions (revisionId, cacheHash, title/itemId)
suitewright forms validate FORM_ID
suitewright forms validate FORM_ID --expected-revision REV_ID
suitewright forms validate FORM_ID --expect-item-id ITEM_ID

# Guarded update + refresh cache
suitewright forms cache-update FORM_ID /path/to/requests.json
```

Direct API commands:

```bash
suitewright forms list
suitewright forms get FORM_ID
suitewright forms create --title "My Survey"
suitewright forms update FORM_ID --requests '[...]'
```

Cache-first query helpers:

```bash
suitewright forms query locate FORM_ID --item-id ITEM_ID
suitewright forms query locate FORM_ID --title "Question title"
suitewright forms query after FORM_ID --item-id ITEM_ID
suitewright forms query delete-request FORM_ID --item-id ITEM_ID
suitewright forms query get-item FORM_ID --title "Question title"
suitewright forms query neighbors FORM_ID --item-id ITEM_ID --before 1 --after 1
suitewright forms query section FORM_ID --title "Section title"
suitewright forms query indexer FORM_ID
suitewright forms query indexer FORM_ID --pattern "^Q\d+\."
```

Cache-first workflow pattern:

```
suitewright forms fetch FORM_ID          # pull live state into local cache
suitewright forms validate FORM_ID       # confirm cache is fresh
suitewright forms query locate FORM_ID   # inspect positions locally
suitewright forms cache-update FORM_ID   # apply guarded update + refresh
```

When the form has already been fetched, prefer small local queries over repeated
live API calls. Use `forms query` subcommands to extract item positions, IDs, or
title patterns before preparing guarded update requests.

## Output Format

Most success paths return JSON. Some auth and error paths print plain text or stderr status messages. Key successful output shapes:

- **Gmail search**: `[{id, threadId, from, to, subject, date, snippet, labels}]`
- **Gmail get**: `{id, threadId, from, to, subject, date, labels, body}`
- **Gmail send/reply**: `{status: "sent", id, threadId}`
- **Calendar list**: `[{id, summary, start, end, location, description, htmlLink}]`
- **Calendar create**: `{status: "created", id, summary, htmlLink}`
- **Drive search**: `[{id, name, mimeType, modifiedTime, webViewLink}]`
- **Drive delete**: `{status: "trashed", fileId, permanent: false}` by default, or `{status: "deleted", fileId, permanent: true}` with `--permanent`
- **Contacts list**: `[{name, emails: [...], phones: [...]}]`
- **Sheets get**: `[[cell, cell, ...], ...]`
- **Docs create**: `{status: "created", documentId, title, url}`
- **Docs append**: `{status: "appended", documentId, inserted_at, characters}`
- **Docs replace**: `{status: "replaced", documentId, characters}`
- **Docs request-template**: JSON list of starter Docs API requests
- **Docs show-structure**: `{documentId, title, summary, blocks}`
- **Docs update**: raw Docs API `batchUpdate` response JSON, or `{documentId, dryRun, requestCount, requestKinds, requests}` when `--dry-run` is used

## Rules

1. **Never send email, create/delete calendar events, delete Drive files, or modify Docs/Sheets/Forms without confirming with the user first.** Show what will be done (recipients, file IDs, content) and ask for approval. `drive delete` moves files to trash by default; use `--permanent` only for intentional irreversible deletion.
2. **Check auth before first use** - run `suitewright auth check`. If it fails, guide the user through setup.
3. **Use the Gmail search syntax reference** for complex queries - load `references/gmail-search-syntax.md`.
4. **Calendar times must include timezone** - always use ISO 8601 with offset (e.g., `2026-03-01T10:00:00-06:00`) or UTC (`Z`).
5. **Respect rate limits** - avoid rapid-fire sequential API calls. Batch reads when possible.
6. **Inspect before mutate** - use `docs show-structure` and `forms validate` before write operations.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `NOT_AUTHENTICATED` | Run setup Steps 2-5 above |
| `REFRESH_FAILED` | Token revoked or expired - redo Steps 3-5 |
| `HttpError 403: Insufficient Permission` | Missing API scope - `suitewright auth revoke` then redo Steps 3-5 |
| `AUTHENTICATED (partial)` or "Token missing scopes" | New write capabilities require re-authorization. `suitewright auth revoke` then redo Steps 3-5 to grant the upgraded scopes. |
| `HttpError 403: Access Not Configured` | API not enabled - user needs to enable it in Google Cloud Console |
| `ModuleNotFoundError` | Run `pip install suitewright` or `uv tool install suitewright` |
| Advanced Protection blocks auth | Workspace admin must allowlist the OAuth client ID |

## Revoking Access

```bash
suitewright auth revoke
```
