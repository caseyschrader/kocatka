# Deploying Kocatka to a server

Target: a Debian 13 virtual machine on Google Cloud (GCP) with SSH access. Ubuntu 24.04 works too, see the note in step 1. The bot uses polling, so the server needs no open ports except SSH (22), and no domain or HTTPS. GCP's default firewall already allows SSH.

Data location: GCP has no region in Russia, while 152-FZ asks for Russian users' personal data to be stored in Russia. Acceptable for a small friends-only pilot after checking with the lawyer; move to a Russian host (for example cloud.ru) before a public launch. Moving is copying one file, see step 4.

SSH from the laptop: add the contents of `~\.ssh\id_ed25519.pub` to the VM's SSH keys in the GCP console. Browser SSH alone is not enough, because steps 2 to 4 copy files from the laptop.

In the commands below, replace `kocatka` with your server user name and `SERVER_IP` with the server's public IP. Commands marked **laptop** run in PowerShell in the project folder. Commands marked **server** run after `ssh kocatka@SERVER_IP`.

## 1. Prepare the server (once)

**Server:**

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io docker-compose git
sudo usermod -aG docker $USER
exit
```

On Ubuntu 24.04 the compose package is called `docker-compose-v2` instead of `docker-compose`.

Log in again so the `docker` group takes effect, then check:

```bash
docker compose version
whoami
id -u
```

* `docker compose version` must print version 2 or later. If the command is not found, install Docker from Docker's own repository instead (docs.docker.com, "Install Docker Engine on Debian").
* `whoami` is the user name to use wherever this guide says `kocatka`.
* `id -u` should print `1000`, the user id the container runs as. On GCP it is often `1001`. If it is not `1000`, run `sudo chown -R 1000:1000 ~/kocatka/data` after step 3.

## 2. Send the code (once)

The code goes to a git repository on the server itself, over SSH. No GitHub needed.

**Server:**

```bash
git init --bare ~/kocatka.git
```

**Laptop:**

```powershell
git remote add server kocatka@SERVER_IP:kocatka.git
git push server main
```

**Server:**

```bash
git clone ~/kocatka.git ~/kocatka
mkdir -p ~/kocatka/data
```

## 3. Send the secrets (once)

`.env` is never in git. Copy it directly.

**Laptop:**

```powershell
scp .env kocatka@SERVER_IP:kocatka/.env
```

**Server:**

```bash
chmod 600 ~/kocatka/.env
```

## 4. Optional: bring the existing data along

Skip this to start with an empty database. To keep the current profiles and matches, first **stop the bot on the laptop** (Ctrl+C), then:

**Laptop:**

```powershell
scp kocatka.db kocatka@SERVER_IP:kocatka/data/kocatka.db
```

## 5. Start the bot

Make sure the bot is not running on the laptop. Telegram allows only one copy per token.

**Server:**

```bash
cd ~/kocatka
docker compose up -d --build
docker compose logs -f
```

You should see `Run polling for bot @Kocatka_App`. Press Ctrl+C to stop watching the logs. The bot keeps running, and restarts by itself after a crash or a server reboot.

## 6. Nightly backups (once)

**Server:** open the cron table with `crontab -e` and add this line (one line):

```
0 3 * * * cd /home/kocatka/kocatka && docker compose exec -T bot python scripts/backup_db.py /data/kocatka.db /data/backups >> /home/kocatka/backup.log 2>&1
```

Every night at 03:00 server time (usually UTC, so 06:00 in St Petersburg) a copy goes to `~/kocatka/data/backups`, keeping the last 14 days. Test it once by hand:

```bash
cd ~/kocatka && docker compose exec -T bot python scripts/backup_db.py /data/kocatka.db /data/backups
```

These backups sit on the same server. To keep one on the laptop too:

**Laptop:**

```powershell
scp kocatka@SERVER_IP:kocatka/data/backups/kocatka-2026-11-22.db .
```

## Everyday commands

Deploy a new version:

**Laptop:**

```powershell
git push server main
```

**Server:**

```bash
cd ~/kocatka && git pull && docker compose up -d --build
```

On the server, from `~/kocatka`:

| Task | Command |
| --- | --- |
| Watch logs | `docker compose logs -f` |
| Restart | `docker compose restart` |
| Stop | `docker compose down` |
| Analytics report | `docker compose exec bot python -m analytics.report /data/kocatka.db` |
| Quick stats | `docker compose exec bot python scripts/stats.py /data/kocatka.db` |

## Things to know

* The database is the single file `~/kocatka/data/kocatka.db`. Losing the server without a backup elsewhere loses the pilot data.
* Ubuntu installs security updates by itself. A rare reboot is fine, because the bot restarts automatically.
* Tests are not part of the image. Run them on the laptop before deploying.
