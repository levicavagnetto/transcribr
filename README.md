# Transcribr

Transcribr collects a store's call recordings from the Ravon admin site, transcribes them on the
shop PC, and shows the calls in a web app on the shop network. It only ever reads from Ravon.
Recordings are fetched into memory when needed and never saved.

It runs as two Docker services from one image:

- `web` serves the web app and its API on one port.
- `worker` checks Ravon for new calls and transcribes them.

Both keep everything in one Docker volume: the database, backups and logs.

## What you need

- A computer that stays on during shop hours. Linux, Windows 10/11 or an Intel Mac, with a 64-bit Intel or AMD
  processor.
  Allow 4 GB of free memory and 6 GB of disk.
- Docker:
  - **Linux:** Docker Engine with the Compose plugin
    ([install guide](https://docs.docker.com/engine/install/)).
  - **Windows:** Docker Desktop with the WSL 2 backend.
  - **macOS:** Docker Desktop.
- A Ravon admin login that can see the store's call recordings.

## Install

1. Get this folder onto the computer, with `git clone` or by unzipping a copy.

2. In that folder, copy `.env.example` to `.env`, then fill in `RAVON_USERNAME` and
   `RAVON_PASSWORD`. Keep `.env` private. If the password contains a `$`, wrap it in single
   quotes: `RAVON_PASSWORD='pa$$word'`.

3. Build and start Transcribr. The first build downloads about 1.5 GB and takes 5 to 15 minutes.

   ```sh
   docker compose up -d --build
   ```

4. Check that both services say `healthy`. The worker can take up to 3 minutes:

   ```sh
   docker compose ps
   ```

5. Open `http://<this-computer>:8000` from any computer on the shop network. On the computer
   itself, use `http://localhost:8000`. Set `TRANSCRIBR_PORT` in `.env` to use another port.

### Start automatically

Compose restarts both services after a crash or reboot (`restart: unless-stopped`). Docker
itself has to start with the computer:

- **Linux:** `sudo systemctl enable docker`
- **Windows:** in Docker Desktop, open **Settings → General** and tick **Start Docker Desktop
  when you sign in to your computer**. Docker Desktop only runs while a user is signed in. On a
  shop PC, use an account that signs in automatically and doesn't sign out.
- **macOS:** in Docker Desktop, open **Settings → General** and tick **Start Docker Desktop
  when you sign in to your computer**.

## First setup

1. Click the small **Admin** link in the top bar of the web app.

2. Enter the one-time setup code. The web service prints it in its log:

   ```sh
   docker compose logs web | grep "setup code"
   ```

   In Windows PowerShell, use `docker compose logs web | Select-String "setup code"`.

3. Choose an admin username and a password of at least 12 characters.

4. In **Settings**, tick the store's queues and save. From then on, calls that end while
   Transcribr runs are listed and transcribed automatically. The first check also lists the
   past 7 days, but calls that ended before Transcribr was running aren't transcribed
   automatically. Staff can transcribe any listed call with its Transcribe button.

### Forgot the admin password

```sh
docker compose exec web transcribr reset-admin
```

This removes the admin account and ends every admin session. It prints a new setup code, so
first setup starts again. Settings and calls are kept.

## Update

```sh
git pull
docker compose up -d --build
```

Database changes apply on start. A copy of the database from before the change is kept in
the volume's `backups` folder. If an update fails to start, `docker compose logs web` says
why, and nothing in the database has been changed.

## Backup and restore

To make a backup, run this and copy the file to somewhere safe:

```sh
docker compose exec web transcribr backup
# Backup written to /data/backups/transcribr-20261023T150000Z.db
docker compose cp web:/data/backups/transcribr-20261023T150000Z.db .
```

The backup is a complete, consistent copy of the database. It includes calls, transcripts,
line voiceprints, settings and the admin account (with the password stored only as a hash).
It never contains the Ravon password or any audio. Voiceprints are personal data, so
keep backups as private as the computer itself.

To restore, on the same or another computer that has this folder and a `.env`:

1. Put the backup file in this folder.

2. Run these commands, with your backup's file name:

   ```sh
   docker compose up -d --build        # creates the volume if it's new
   docker compose stop
   docker compose run --rm --no-deps -v "$(pwd):/restore:ro" web sh -c \
     "rm -f /data/transcribr.db-wal /data/transcribr.db-shm && cp /restore/transcribr-20261023T150000Z.db /data/transcribr.db"
   docker compose up -d
   ```

   In Windows PowerShell, write the `run` command on one line without the `\`.

## Logs

`docker compose logs web` and `docker compose logs worker` show each service's log as JSON
lines. The same lines are kept in the volume, in `/data/logs/web.log` and
`/data/logs/worker.log`, with 5 older files of 5 MB each. Passwords and session cookies are
removed before anything is logged.

## Troubleshooting

The web app shows a banner on every page when something needs attention.

| Banner | What to do |
| --- | --- |
| **Ravon login details are missing.** | Set `RAVON_USERNAME` and `RAVON_PASSWORD` in `.env`, then run `docker compose up -d`. |
| **Ravon login failed.** | Ravon refused the login, and Transcribr won't try the same login again. Fix the details in `.env` and run `docker compose up -d`. If the password was only changed in Ravon itself, use **Retry login** in the banner or under Admin → Settings. |
| **Ravon isn't answering.** | Ravon or the internet connection is down. Transcribr keeps retrying, more slowly over time, and catches up when Ravon answers again. Nothing needs doing unless it lasts. |
| **The worker has stopped.** / **hasn't started yet.** | Run `docker compose ps` and `docker compose logs worker`. Docker restarts a crashed worker by itself. If the worker keeps stopping, the log says why. |
| **Ravon's recordings page has changed.** | Ravon changed its page, and Transcribr stopped rather than guess. It needs a software update. |
| **Refused requests** (allow-list violations) | Transcribr blocked requests that aren't on its read-only list, so nothing was changed in Ravon. Report it as a bug, including `docker compose logs worker`. |

**The page is light when Windows is dark, or dark when Windows is light.** Transcribr follows
the browser's appearance setting when its own menu is set to System. In **Firefox**, open
**Settings → General → Website appearance** and choose **Automatic**. In **Chrome or Edge**,
set the browser's appearance (Settings → Appearance) to follow the device. Or pick Light or
Dark in Transcribr's own menu.

**Nothing at `http://<this-computer>:8000` from other computers.** Check that it works on
the computer itself (`http://localhost:8000`). If it does, allow the port through that
computer's firewall.

## Development

See `docs/architecture.md`. Run every check with:

```sh
uv run --directory backend ../scripts/check.py
```

To check the container stack against a fake Ravon, with the worker cut off from the
internet, run `uv run --directory backend ../scripts/stack_check.py`. This needs Docker.
