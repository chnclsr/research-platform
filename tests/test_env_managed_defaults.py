from research_platform import gateway_client, schemas
from research_platform.config import Settings
from research_platform.gateway_client import ResearchGatewayClient
from research_platform.schemas import ConnectorSelection, ResearchBudget


def test_run_defaults_are_loaded_from_settings(monkeypatch):
    configured = Settings(
        _env_file=None,
        acquisition_concurrency=7,
        frontier_max_depth=3,
    )
    monkeypatch.setattr(schemas, "get_settings", lambda: configured)

    assert ResearchBudget(max_wall_minutes=15).acquisition_concurrency == 7
    assert ConnectorSelection().citation_depth == 3


def test_gateway_limits_are_loaded_from_settings(monkeypatch):
    configured = Settings(
        _env_file=None,
        gateway_client_timeout_s=41,
        gateway_artifact_max_chars=4321,
    )
    monkeypatch.setattr(gateway_client, "get_settings", lambda: configured)

    client = ResearchGatewayClient("http://research.test", "token")

    assert client.timeout_s == 41
    assert client.artifact_max_chars == 4321
