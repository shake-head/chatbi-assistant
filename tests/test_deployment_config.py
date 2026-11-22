"""Static checks for deployment and CI configuration."""

from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_compose_defines_api_redis_health_checks_and_persistence() -> None:
    compose = yaml.safe_load((PROJECT_ROOT / "compose.yaml").read_text(encoding="utf-8"))

    assert set(compose["services"]) == {"api", "redis"}
    assert compose["services"]["api"]["depends_on"]["redis"]["condition"] == "service_healthy"
    assert compose["services"]["api"]["healthcheck"]["test"]
    assert compose["services"]["api"]["read_only"] is True
    assert "no-new-privileges:true" in compose["services"]["api"]["security_opt"]
    assert compose["services"]["api"]["cap_drop"] == ["ALL"]
    assert compose["services"]["redis"]["healthcheck"]["test"] == ["CMD", "redis-cli", "ping"]
    assert compose["services"]["redis"]["user"] == "redis"
    assert "chatbi_data" in compose["volumes"]


def test_docker_build_includes_migration_inputs() -> None:
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text(encoding="utf-8")
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text(encoding="utf-8")

    assert "COPY alembic.ini" in dockerfile
    assert "COPY migrations" in dockerfile
    assert "alembic upgrade head" in dockerfile
    assert "README.md" not in dockerignore.splitlines()


def test_ci_uses_python_311_and_runs_quality_gates() -> None:
    workflow = yaml.safe_load(
        (PROJECT_ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    )
    steps = workflow["jobs"]["quality"]["steps"]
    commands = "\n".join(step.get("run", "") for step in steps)

    assert any(step.get("with", {}).get("python-version") == "3.11" for step in steps)
    assert "ruff check ." in commands
    assert "ruff format --check ." in commands
    assert "pytest" in commands
    assert "container" in workflow["jobs"]
    assert "docker build --tag chatbi:ci ." in str(workflow)
