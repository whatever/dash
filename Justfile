set dotenv-load := false

default:
    @just --list

up *args:
    docker compose up --build --detach {{args}}

down:
    docker compose down

nuke:
    docker compose down --volumes

logs *services:
    docker compose logs --follow {{services}}

ps:
    docker compose ps
