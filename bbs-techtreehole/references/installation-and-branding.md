# NodeBB Installation & Branding

## Clean Install Flow

### Prerequisites
- Docker Compose with MongoDB + Redis
- Image: `ghcr.io/nodebb/nodebb:4.12.0` (or latest)
- `setup.json` at `/opt/config/setup.json` for auto-population

### Steps

1. Prepare `config/setup.json` (guide fills db config fields):
   ```json
   {
     "url": "http://192.168.50.1:4567",
     "admin:username": "admin",
     "admin:password": "<ADMIN_PASSWORD_从_gbrain_获取>",
     "admin:email": "admin@example.com",
     "database": "mongo",
     "mongo:host": "mongo",
     "mongo:port": 27017,
     "mongo:database": "nodebb"
   }
   ```

2. Start containers:
   ```bash
   docker compose up -d
   ```

3. Wait ~120s for build + installer, then visit http://host:4567 and click "Install NodeBB"

4. The web installer requires a browser (CSRF + session cookie protection)

### Branding Configuration

NodeBB 4.x stores different settings in different places:

| Setting | Storage | How to set |
|---------|---------|-----------|
| `title` / `browserTitle` | MongoDB `objects.config` | `db.collection("objects").updateOne({_key:"config"}, {$set: {title: "tthbbs"}})` |
| `brand:logo` | Redis `config` hash | `redis-cli HSET config brand:logo "/assets/uploads/logo.svg"` |
| `brand:name` | Redis `config` hash | `redis-cli HSET config brand:name "tthbbs"` |
| `email:smtp:xxx` | Redis `config` hash | `redis-cli HSET config email:smtp:host smtp.gmail.com` |
| Theme | Redis `config` hash | `redis-cli HSET config theme:id nodebb-theme-persona` |

**Logo path**: Upload to `public/uploads/` inside container, access via `/assets/uploads/filename.svg`.

### Themes

- **Persona** (lcz.me style, most popular): `npm install nodebb-theme-persona@latest`
- **Harmony** (default in 4.x)
- After npm install, activate via: `redis-cli HSET config theme:id nodebb-theme-persona`

## Upgrade from 4.11.x

1. Update image tag in docker-compose.yml
2. `docker pull ghcr.io/nodebb/nodebb:4.12.0`
3. `docker compose up -d` (START_BUILD=true handles rebuild)
4. Wait 90s for build completion
