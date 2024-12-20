# Metabase with MySQL & PHPMyAdmin

## About
This document does not explain how to use Metabase, please refer to the official documentation for usage instructions.

The Compose uses the following images:

+ [Metabase](https://hub.docker.com/r/metabase/metabase)
+ [MySQL](https://hub.docker.com/_/mysql)
+ [PHPMyAdmin](https://hub.docker.com/_/phpmyadmin)


### Requirements
+ [Docker](https://docs.docker.com/)
+ [Docker Compose](https://docs.docker.com/compose/#compose-documentation)


### Configuration
Container configurations depend on environment variables defined in an `.env` file.

+ Copy the `env.sample` file and rename it to `.env`
+ Replace the environment values to your desire. See environment explanatory chart below


### Environment variables
+ `DB_TYPE:` `mysql`
+ `DB_NAME:` the name of the database
+ `DB_USER:` a database user different than root
+ `DB_PASSWORD:` a password for `DB_USER`
+ `DB_ROOT_PASSWORD:` a password for the root user *(only for MySQL)*
+ `DB_PORT:` use `3306` for mysql.


### Get started
+ Run `docker-compose build` to create a database image (`mysql` or `postgres`)
+ Run `docker-compose up -d` to run the applications
+ Use `docker-compose down` to shutdown all services
+ There is no need to re-run `docker-compose build` unless you change the database strategy, database name, database credentials or the volumes.


### Log In
+ [Metabase](http://localhost:3000/)
+ [PHPMyAdmin](http://localhost:8080/)


### Database
For the prebuilt dashboard and reports to work the MySQL must be loaded. This file is not included in the distribution. This is not needed to run the application. You can still create your own reports and dashboards.


#### Changes
When you set up a database like Postgres or MySQL in Docker, it creates a volume to store data. If the volume already exists, trying to create a new database will fail. If you switch database types later, you'll need to either rename the volume or delete it. Like this:

+ `docker volume rm $(docker volume ls | grep db-data | awk '{print $2}')`

> `db-data` is the default volume name assigned in `env.sample`. Replace that with your volume name, if you used another value in `.env`.
>

If you can't remove the volume, then it's probably it's in use. Use `docker-compose down` to shut the application down.



## Documentation Reference
+ [Metabase](https://www.metabase.com/docs/latest/operations-guide/configuring-application-database.html)


## License
+ [**GNU General Public License version 3**](https://opensource.org/licenses/GPL-3.0)
