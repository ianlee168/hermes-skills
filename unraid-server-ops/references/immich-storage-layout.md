# Immich storage layout — which copy is live, and what the folders mean (v3.x)

Use when the user maps the photos share over SMB and reports that the newest folder is years old,
that files "look stale", or that a sync/backup seems to have stopped. Answer from the app's INDEX.

## Why the date tree looks old

- The **Storage Template is disabled by default on new instances (Immich ≥1.92)**; the feature is
  still present in v3.x (frontend strings + `storage-template` endpoints exist). With it OFF, originals
  keep UUID names under `upload/<owner-user-UUID>/<2hex>/<2hex>/<asset-UUID>.<ext>`.
- With it ON, Immich *moves* originals to `library/<user>/<yyyy>/<mm>/<dd>/<original filename>` — the
  only thing that makes an SMB view browsable by date.
- So a `library/<year>/…` tree that stops at some past year = the template ran once (usually during an
  earlier install or a migration) over the assets that existed then. Everything uploaded since is in
  `upload/`, invisibly (UUID names), which is exactly what makes users think the library died.

## Ground truth: ask the DB where each asset lives

```bash
# per-prefix counts + exif date span  (note the \$\$ quoting — see the pitfall below)
docker exec immich_postgres psql -U postgres -d immich -c "select case when \"originalPath\" like \$\$/library/%\$\$ then \$\$library\$\$ when \"originalPath\" like \$\$/upload/%\$\$ then \$\$upload\$\$ else \$\$other\$\$ end as where_it_lives, count(*), min(\"fileCreatedAt\")::date, max(\"fileCreatedAt\")::date from asset where \"deletedAt\" is null group by 1;"

# newest assets: exif date vs upload time vs where the file actually is
docker exec immich_postgres psql -U postgres -d immich -c "select \"fileCreatedAt\"::date as exif, \"createdAt\"::date as uploaded, \"originalPath\" from asset where \"deletedAt\" is null order by \"createdAt\" desc limit 5;"

# is an external library in play at all?
docker exec immich_postgres psql -U postgres -d immich -c "select id, name, \"importPaths\" from library;"
```

**0 rows for `%/library/%` = the entire date tree is orphan data**, no matter how complete it looks.
Rows whose `originalPath` points into `encoded-video/` or `thumbs/` are normal (transcodes/previews) —
the orphan signal is specifically a staging tree that no row references.

`asset.originalPath` inside the container is the path under the UPLOAD_LOCATION mount
(`/data/...`), so map it back to the host with the container's mount:
`docker inspect immich_server --format '{{range .Mounts}}{{.Source}} -> {{.Destination}}{{println}}{{end}}'`.

## Prove "this is a duplicate" before calling anything orphan

```bash
for f in $(find /mnt/user/imch_photos/library -type f -name "*.jpg" | head -3); do
  b=$(basename "$f")
  p=$(docker exec immich_postgres psql -U postgres -d immich -Atc "select \"originalPath\" from asset where \"originalFileName\" = \$\$$b\$\$ limit 1;")
  real="/mnt/user/imch_photos${p#/data}"
  sha256sum "$f" "$real"      # identical hash + size = true duplicate of the live file
  stat -c '%s %n' "$f" "$real"
done
```

Filename match alone is weak; hash + size equality is the evidence to show the user.

## Quoting pitfall (cost time twice)

Inside `ssh root@<host> '<command>'` you cannot single-quote SQL string literals (they'd end the ssh
argument), and a bare `$$` inside the double-quoted `-c "..."` is expanded by bash as the PID. Write
dollar-quoting as `\$\$...\$\$`: the ssh-level single quotes preserve the backslash, bash then hands
`$$` to Postgres. Using `"..."` instead makes Postgres read them as identifiers and fail with
`column "%/library/%" does not exist`. Same trick for the config key: `where key = \$\$system-config\$\$`.

## What each subdirectory of UPLOAD_LOCATION is

| dir | contents |
|---|---|
| `upload/` | **live originals** (UUID names, e.g. JPG, NEF RAW, MP4) |
| `thumbs/` | generated previews/thumbnails (`*_thumbnail.webp`, `*_preview.jpeg`) — NOT originals |
| `encoded-video/` | transcodes |
| `profile/` | user avatars |
| `backups/` | Immich's own DB dumps (written by its backup job) |
| `library/` | storage-template output — **may be entirely orphan** |
| extra roots (e.g. `photos_backup/`) | leftover copy of an older install root |

`/.immich` marker files inside most of these are written by Immich on startup — their mtime is a
container-restart timestamp, not a data-change timestamp.

## Cloud sync / backup from Immich to Google Photos or cloud drives

When the user attempts to back up Immich photos to Google Photos or Google Drive via desktop sync clients:

1. **Target directory trap (`thumbs` vs `upload`)**:
   - `thumbs/` contains ONLY `*_thumbnail.webp` and `*_preview.jpeg` (~2.9GB of generated low-res preview tiles).
   - If selected in backup tools, either nothing uploads (tools skip `.webp` or small thumbnails) or the cloud library is polluted with thousands of low-res web previews.
   - Real camera originals, RAW files (.NEF), and full-res JPGs/videos live in `upload/<user-UUID>/...` (or `library/...` if Storage Template is enabled).

2. **Google Drive for Desktop UNC path limitation & Google Photos Deprecation**:
   - Google Drive for Desktop (`GoogleDriveFS.exe`) only monitors local physical drive letters (C:, D:, E:, etc., recorded in `root_preference_sqlite.db`).
   - Entering or selecting a network UNC path (e.g. `\\IANS\immich\...`) in the desktop app fails to register in the backup queue (`roots` table) because remote SMB paths do not provide reliable Windows `ReadDirectoryChangesW` filesystem events. The folder is ignored and **nothing uploads, with zero explicit error**.
   - **Google Photos backup deprecated**: Google Drive for Desktop officially deprecated and disabled local folder backup to Google Photos in mid-2026 (logs show `NotifyIfDeprecated Photos deprecation warnings` and `PhotosSlurpTransporter` pause). Even for local folders, setting "Back up to Google Photos" in Drive for Desktop no longer syncs new items.

- **Google Photos API 429 trap**: Setting up an rclone remote for Google Photos (`type = google photos`) with default client ID fails uploads with `429 Quota exceeded for quota metric 'Size of uploads' and limit 'Size of uploads per day' of photoslibrary.googleapis.com for project 202264815644`. Must create a dedicated OAuth Client ID & Secret in personal Google Cloud project.
- **Google Auth Platform (2026 UI) settings**:
  - Do NOT select "Use this client for an AI-powered agent" when creating credentials (it adds Workspace MCP restrictions).
  - Keep publishing status in **Production (正式版)**: refresh tokens are permanent. In Testing mode (测试版), refresh tokens expire every 7 days.
- **Backfill queue ordering trap (Newest First)**:
  - When building a backfill queue of existing photos, naive `find "$WATCH_DIR"` walks directories in filesystem order (e.g. legacy user UUIDs with 2008 photos first).
  - Because Google Photos places photos according to EXIF capture date, ancient photos appear far down the timeline; recent photos sit at the back of the queue (item 12,000+), leading users to believe sync failed.
  - **Rule**: Always sort backfill queues by newest mtime first: `find ... -printf '%T@ %p\n' | sort -rn | cut -d' ' -f2-`. On initial rollout, prepend the last 7 days (`find -mtime -7`) straight into the high-priority real-time queue.
- **`gphotos:upload` is write-only**: Listing `gphotos:upload` returns `directory not found`. Rclone cannot query remote files to skip existing ones. Any automated sync script targeting `gphotos:upload` MUST maintain a local upload ledger (e.g. `uploaded.list`) to prevent attempting to re-upload thousands of historical files.

4. **Google Drive (`gdrive:`) vs Google Photos (`gphotos:`) Storage Silos**:
   - Google severed Drive and Photos integration in July 2019. Files uploaded to Google Drive (`drive.google.com`) do NOT appear in the Google Photos (`photos.google.com`) timeline or mobile app.
   - However, Google Drive (`gdrive:`) has NO daily upload bandwidth quota traps on rclone's default client ID, making it immediately viable for full-library disaster recovery backup (e.g. user's 5TB account).

5. **Real-Time NAS Auto-Upload Architecture (inotifywait + rclone)**:
   - Unraid includes `/usr/bin/inotifywait` by default (`fs.inotify.max_user_watches = 524288`, easily covering Immich's ~14k upload subdirectories).
   - Event trigger: `inotifywait -m -r -e close_write /mnt/user/imch_photos/upload/` with a debounce buffer (30–60s) to wait for photo bursts from phones/cameras to finish writing.
   - Execution: Deduplicate against the local uploaded ledger, then invoke `rclone copyto` only for new files.

## If the user wants the SMB view browsable by date

1. Administration → Settings → **Storage Template**, enable it and confirm the template
   (e.g. `{{y}}/{{mm}}/{{dd}}/{{filename}}`).
2. Run the **Storage Template Migration** job once. It moves all originals into `library/…` and rewrites
   `originalPath` in the DB.
3. Say the caveats out loud: multi-GB move runs in the background (don't power off mid-job); same-disk
   moves are renames, cross-disk ones are real copies (check free space first); browsing in the app keeps
   working throughout.

Otherwise the honest answer is: browsing by date is the app's job, SMB is the raw store — UUID names
there are by design.

## Cleaning an orphan tree — protocol

Never `rm`. First give the user: file count, size, the 0-rows DB evidence, and the sha256 samples.
Then `mv` the tree to a dated array-backup directory, and delete later only with explicit consent
(the standing delete rule). If an extra root looks like a deliberate old backup, ask before proposing
anything — it may be the only copy of something the user chose to keep.
