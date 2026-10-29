"""Regression tests keeping deployment config in sync with the image CI publishes."""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker-compose.prod.yml"
DEPLOY_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy.yml"

# CI publishes ghcr.io/${{ github.repository }}, i.e. ghcr.io/woolnerd/cited-doc-qa
PUBLISHED_IMAGE = "cited-doc-qa"


def test_compose_pulls_the_image_ci_publishes():
    """Compose must pull the image CI pushes, or deploys silently keep the old one."""
    compose = COMPOSE_FILE.read_text()

    match = re.search(r"^\s*image:\s*\S+/([\w.-]+):", compose, re.MULTILINE)

    assert match is not None
    assert match.group(1) == PUBLISHED_IMAGE


def test_rollback_looks_up_the_published_image():
    """Rollback must search local images under the published name."""
    workflow = DEPLOY_WORKFLOW.read_text()

    assert f"grep {PUBLISHED_IMAGE}" in workflow
    assert "grep production-rag-system" not in workflow


def test_compose_mounts_gcs_credentials_read_only():
    """Signed source URLs need the GCS service-account key mounted into the container."""
    compose = COMPOSE_FILE.read_text()

    assert re.search(
        r"-\s*\$\{GCS_CREDENTIALS_FILE:-[^}]+\}:/run/secrets/[\w.-]+\.json:ro",
        compose,
    )
