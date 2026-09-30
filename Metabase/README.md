# Metabase with MySQL & Adminer

## About
This document does not explain how to use Metabase, please refer to the official documentation for usage instructions.

The Compose uses the following images:

+ [Metabase](https://hub.docker.com/r/metabase/metabase)
+ [MySQL](https://hub.docker.com/_/mysql)
+ [Adminer](https://hub.docker.com/_/adminer)
+ [PostgreSQL](https://hub.docker.com/_/postgres) — Metabase's application database


### Requirements
+ [Docker](https://docs.docker.com/)
+ [Docker Compose](https://docs.docker.com/compose/#compose-documentation)


### Configuration
Container configurations depend on environment variables defined in an `.env` file.

+ Copy the `env.sample` file and rename it to `.env`
+ Replace the environment values to your desire. See environment explanatory chart below


### Environment variables
+ `DB_NAME` — the name of the database (e.g. `Micro-Surveys`)
+ `DB_USER` — a non-root database user (used by Metabase for read access)
+ `DB_USER_PASSWORD` — password for `DB_USER`
+ `DB_PASSWORD` — password for the MySQL root user (used by `upload_app.py` for writes)
+ `MB_JAVA_TIMEZONE` — JVM timezone for Metabase (e.g. `America/New_York`)


### Get started
+ Run `docker-compose build` to create a database image (`mysql` or `postgres`)
+ Run `docker-compose up -d` to run the applications
+ Use `docker-compose down` to shutdown all services
+ There is no need to re-run `docker-compose build` unless you change the database strategy, database name, database credentials or the volumes.


### Log In
+ [Metabase](http://localhost:3000/)
+ [Adminer](http://localhost:8081/) — server `db`

> **Production serves Adminer on 8080; this compose file uses 8081.** Same `adminer:4.8.1` image. phpMyAdmin was dropped after it leaked memory in production.


### Login fails with "Access denied for user 'root'@'&lt;ip&gt;'"

Root exists as several accounts — `root@'localhost'` (socket), `root@'%'` (network), and possibly stale ones pinned to old container IPs — each with **its own password**. The MySQL healthcheck uses the socket account, so the container can report `healthy` while every browser and import-tool login is rejected. `MYSQL_ROOT_PASSWORD` in `.env` only applies when the volume is first created; after that it is decorative unless the accounts are kept in sync.

Inspect the accounts, then repair `root@'%'` in place — no need to destroy the volume:

```bash
P=$(docker exec mysql-container printenv MYSQL_ROOT_PASSWORD)
docker exec mysql-container mysql -uroot -p"$P" -e "select user,host,plugin from mysql.user"
docker exec mysql-container mysql -uroot -p"$P" -e "ALTER USER 'root'@'%' IDENTIFIED WITH mysql_native_password BY '$P'; FLUSH PRIVILEGES;"
```

Never grant root from a literal container IP: Docker reassigns bridge subnets when it recreates the network, and the grant stops matching on the next restart. Full write-up in the [root README](../README.md#mysql-accounts-are-per-source-host).


### Database
For the prebuilt dashboard and reports to work the MySQL must be loaded. This file is not included in the distribution. This is not needed to run the application. You can still create your own reports and dashboards.


#### Changes
When you set up a database like Postgres or MySQL in Docker, it creates a volume to store data. If the volume already exists, trying to create a new database will fail. If you switch database types later, you'll need to either rename the volume or delete it. Like this:

+ `docker volume rm $(docker volume ls | grep db-data | awk '{print $2}')`

> `db-data` is the default volume name assigned in `env.sample`. Replace that with your volume name, if you used another value in `.env`.
>

If you can't remove the volume, then it's probably it's in use. Use `docker-compose down` to shut the application down.


### Helpful Docker CLI
+ `docker system prune -a --volumes -f`
+ `docker exec -it metabase-container ls -la`
+ `docker ps`
+ `docker logs metabase-container > logs.txt`


## Documentation Reference
+ [Metabase](https://www.metabase.com/docs/latest/operations-guide/configuring-application-database.html)


## License
+ [**GNU General Public License version 3**](https://opensource.org/licenses/GPL-3.0)
