# Local Docker OpenEMR

This project uses OpenEMR's official easy development Docker stack for local testing.

## Start

```powershell
cd "C:\Users\Roy Harden\OneDrive\PJ-OD\EMR-SO\openemr\docker\development-easy"
docker compose up -d
```

First launch can take a long time while Docker pulls images, installs Composer and npm dependencies, builds themes, installs browser test tooling, performs quick setup, and starts Apache.

## Open

- OpenEMR HTTPS: https://localhost:9300/
- OpenEMR HTTP: http://localhost:8300/
- phpMyAdmin: http://localhost:8310/
- Mailpit: http://localhost:8025/
- CouchDB: http://localhost:5984/_utils/
- Selenium: http://localhost:4444/

Default OpenEMR login:

```text
Username: admin
Password: pass
```

CouchDB login:

```text
Username: admin
Password: password
```

## Check Status

```powershell
cd "C:\Users\Roy Harden\OneDrive\PJ-OD\EMR-SO\openemr\docker\development-easy"
docker compose ps
docker compose logs --tail 200 openemr
```

The OpenEMR container may show `health: starting` or `unhealthy` during first bootstrap. Prefer checking the OpenEMR logs before restarting.

## Verify Login

Open https://localhost:9300/ and log in with `admin` / `pass`.

From PowerShell, a lightweight login-flow check is:

```powershell
$cookie = Join-Path $env:TEMP 'openemr-cookies.txt'
if (Test-Path $cookie) { Remove-Item -LiteralPath $cookie -Force }
curl.exe -k -s -S -c $cookie 'https://localhost:9300/interface/login/login.php?site=default' > $null
curl.exe -k -s -S -i -b $cookie -c $cookie -X POST 'https://localhost:9300/interface/main/main_screen.php?auth=login&site=default' --data-urlencode 'new_login_session_management=1' --data-urlencode 'authUser=admin' --data-urlencode 'clearPass=pass' --data-urlencode 'languageChoice=1'
Remove-Item -LiteralPath $cookie -Force
```

A successful login returns a `302 Found` redirect to `/interface/main/tabs/main.php`.

## Stop

Preserve warmed dependencies and database:

```powershell
docker compose down
```

Full reset, including database and generated dependency volumes:

```powershell
docker compose down -v
```

Use `down -v` only when intentionally starting from scratch.

## Useful Dev Commands

Run commands from `openemr/docker/development-easy`.

```powershell
docker compose exec openemr /root/devtools build-themes
docker compose exec openemr /root/devtools php-log
docker compose exec openemr /root/devtools unit-test
docker compose exec openemr /root/devtools dev-reset-install-demodata
```

Note: An initial attempt to run `docker compose exec -T openemr /root/devtools register-oauth2-client` returned `client id: null` and `client secret: null`. Revisit OAuth key/client setup before using Swagger or API authorization as a verification path.
