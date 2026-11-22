$ErrorActionPreference = 'Continue'
docker info --format '{{json .RegistryConfig.Mirrors}}'
docker info --format '{{.ServerVersion}}'
docker compose ps
