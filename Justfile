set dotenv-load := false

default:
    @just --list

[arg('open', long='open', value='true')]
up open="" *args:
    docker compose up --build --detach {{ if open == "true" { "--wait" } else { "" } }} {{args}}
    {{ if open == "true" { "just browse" } else { "" } }}

down:
    docker compose down

nuke:
    docker compose down --volumes

[arg('follow', short='f', long='follow', value='--follow')]
[arg('tail', long='tail')]
logs follow="" tail="all" *services:
    docker compose logs {{follow}} --tail={{tail}} {{services}}

ps:
    docker compose ps

browse:
    open http://localhost:8000
