from __future__ import annotations

import asyncio

import httpx

from .base import SourceConnector
from .implementations import (
    AgentSearchConnector, ArxivConnector, CrossrefConnector, DataCiteConnector,
    DomainAgentSearchConnector, EpoOpsConnector, EuropePmcConnector, FederalRegisterConnector,
    GdeltConnector, GitHubConnector, HuggingFaceConnector, IetfConnector, OpenAlexConnector,
    OpenLibraryConnector, SecEdgarConnector, WaybackConnector, ZenodoConnector,
)
from ..config import Settings
from ..schemas import ConnectorHealth, ConnectorSelection, SourceFamily


class ConnectorRegistry:
    def __init__(self, connectors: list[SourceConnector]):
        self._connectors = {c.id: c for c in connectors}

    @property
    def connectors(self) -> list[SourceConnector]:
        return list(self._connectors.values())

    def selected(self, selection: ConnectorSelection) -> list[SourceConnector]:
        result = []
        for connector in self.connectors:
            if connector.family not in selection.included_families:
                continue
            if connector.id in selection.excluded_connectors:
                continue
            if selection.included_connectors and connector.id not in selection.included_connectors:
                continue
            result.append(connector)
        return result

    async def health(self) -> list[ConnectorHealth]:
        return list(await asyncio.gather(*(c.health() for c in self.connectors)))

    def get(self, connector_id: str) -> SourceConnector | None:
        return self._connectors.get(connector_id)


def build_registry(settings: Settings, client: httpx.AsyncClient) -> ConnectorRegistry:
    common = {"settings": settings, "client": client}
    return ConnectorRegistry([
        AgentSearchConnector(**common), OpenAlexConnector(**common), CrossrefConnector(**common),
        ArxivConnector(**common), EuropePmcConnector(**common),
        OpenLibraryConnector(**common), OpenAlexConnector(**common, work_type="dissertation"),
        EpoOpsConnector(**common), IetfConnector(**common),
        DomainAgentSearchConnector(**common, connector_id="standards_web", family=SourceFamily.PATENTS_STANDARDS),
        FederalRegisterConnector(**common),
        DomainAgentSearchConnector(**common, connector_id="eur_lex", family=SourceFamily.OFFICIAL_LEGAL, domain="eur-lex.europa.eu"),
        DomainAgentSearchConnector(**common, connector_id="official_registry", family=SourceFamily.OFFICIAL_LEGAL),
        GdeltConnector(**common), WaybackConnector(**common),
        DomainAgentSearchConnector(**common, connector_id="agentsearch_news", family=SourceFamily.NEWS_ARCHIVES, mode="news"),
        GitHubConnector(**common), HuggingFaceConnector(**common), ZenodoConnector(**common),
        DataCiteConnector(**common), SecEdgarConnector(**common),
        DomainAgentSearchConnector(**common, connector_id="company_domains", family=SourceFamily.COMPANY),
        ZenodoConnector(**common, connector_id="zenodo_grey", family=SourceFamily.GREY_LITERATURE),
        DomainAgentSearchConnector(**common, connector_id="institutional_grey", family=SourceFamily.GREY_LITERATURE),
    ])

