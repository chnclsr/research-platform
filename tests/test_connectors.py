import httpx
import pytest

from research_platform.config import get_settings
from research_platform.connectors import build_registry
from research_platform.schemas import ConnectorSelection, SourceFamily


@pytest.mark.asyncio
async def test_registry_covers_all_source_families():
    async with httpx.AsyncClient() as client:
        registry = build_registry(get_settings(), client)
        assert {c.family for c in registry.connectors} == set(SourceFamily)


@pytest.mark.asyncio
async def test_credential_connector_reports_disabled():
    async with httpx.AsyncClient() as client:
        registry = build_registry(get_settings(), client)
        health = await registry.get("epo_ops").health()
        assert health.enabled is False
        assert set(health.missing_credentials) == {"epo_ops_key", "epo_ops_secret"}


@pytest.mark.asyncio
async def test_core_profile_selects_only_core_families():
    async with httpx.AsyncClient() as client:
        registry = build_registry(get_settings(), client)
        selected = registry.selected(ConnectorSelection(profile="core"))
        assert selected
        assert {c.family for c in selected} <= {
            SourceFamily.WEB, SourceFamily.ACADEMIC,
            SourceFamily.OFFICIAL_LEGAL, SourceFamily.CODE_DATA,
        }

