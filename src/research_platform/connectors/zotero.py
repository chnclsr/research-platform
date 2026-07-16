from __future__ import annotations

from typing import Any

from .base import SourceConnector
from ..schemas import ConnectorCandidate, ConnectorHealth, SourceFamily
from ..scholarly import normalize_doi


class ZoteroConnector(SourceConnector):
    family = SourceFamily.ACADEMIC
    capabilities = ("search", "metadata", "content", "versions", "incremental_sync")

    def __init__(self, *args, mode: str, **kwargs):
        super().__init__(*args, **kwargs)
        self.mode = mode
        self.id = f"zotero_{mode}"

    def _scope(self) -> tuple[str, str] | None:
        if self.mode == "local":
            return "", self.settings.zotero_local_url.rstrip("/")
        if self.settings.zotero_user_id:
            return (
                f"users/{self.settings.zotero_user_id}",
                f"https://api.zotero.org/users/{self.settings.zotero_user_id}",
            )
        if self.settings.zotero_group_id:
            return (
                f"groups/{self.settings.zotero_group_id}",
                f"https://api.zotero.org/groups/{self.settings.zotero_group_id}",
            )
        return None

    def _headers(self) -> dict[str, str]:
        headers = {"Zotero-API-Version": "3"}
        if self.mode == "web" and self.settings.zotero_api_key:
            headers["Zotero-API-Key"] = self.settings.zotero_api_key
        return headers

    async def health(self) -> ConnectorHealth:
        if self.mode == "local" and not self.settings.zotero_local_enabled:
            return ConnectorHealth(
                id=self.id, family=self.family, enabled=False, healthy=False,
                capabilities=list(self.capabilities), detail="disabled by configuration",
            )
        scope = self._scope()
        if scope is None:
            return ConnectorHealth(
                id=self.id, family=self.family, enabled=False, healthy=False,
                requires_credentials=True,
                missing_credentials=["zotero_user_id or zotero_group_id"],
                capabilities=list(self.capabilities), detail="library scope missing",
            )
        try:
            _, base = scope
            response = await self.client.get(
                f"{base}/items", params={"limit": 1}, headers=self._headers(), timeout=3
            )
            return ConnectorHealth(
                id=self.id, family=self.family, enabled=True,
                healthy=response.is_success, requires_credentials=self.mode == "web",
                capabilities=list(self.capabilities),
                detail=(
                    "local Zotero API available" if self.mode == "local"
                    else "Zotero Web API configured"
                ),
            )
        except Exception as exc:
            return ConnectorHealth(
                id=self.id, family=self.family, enabled=True, healthy=False,
                requires_credentials=self.mode == "web",
                capabilities=list(self.capabilities), detail=str(exc)[:200],
            )

    async def search(self, query: str, limit: int = 20) -> list[ConnectorCandidate]:
        return await self.search_since(query, limit)

    async def search_since(
        self, query: str, limit: int = 20, since: int | None = None,
    ) -> list[ConnectorCandidate]:
        scope = self._scope()
        if scope is None:
            return []
        _, base = scope
        params: dict[str, Any] = {
            "format": "json", "limit": min(limit, 100), "itemType": "-attachment",
        }
        if query:
            params.update({"q": query, "qmode": "everything"})
        if since is not None:
            params["since"] = since
        response = await self.client.get(
            f"{base}/items", params=params, headers=self._headers()
        )
        response.raise_for_status()
        library_version = int(response.headers.get("Last-Modified-Version", "0") or 0)
        output: list[ConnectorCandidate] = []
        for row in response.json():
            candidate = await self._candidate_from_item(base, row, library_version)
            if candidate:
                output.append(candidate)
        return output

    async def list_collections(self) -> list[dict[str, Any]]:
        scope = self._scope()
        if scope is None:
            return []
        _, base = scope
        response = await self.client.get(
            f"{base}/collections", params={"format": "json", "limit": 100},
            headers=self._headers(),
        )
        response.raise_for_status()
        return [
            {
                "key": (row.get("data") or {}).get("key") or row.get("key"),
                "name": (row.get("data") or {}).get("name", ""),
                "parent_collection": (row.get("data") or {}).get("parentCollection"),
                "version": (row.get("data") or {}).get("version"),
            }
            for row in response.json()
        ]

    async def _candidate_from_item(
        self, base: str, row: dict[str, Any], library_version: int,
    ) -> ConnectorCandidate | None:
        data = row.get("data") or {}
        item_key = data.get("key") or row.get("key")
        item_type = data.get("itemType")
        if item_type == "note" and not self.settings.zotero_include_notes:
            return None
        creators = []
        for creator in data.get("creators", []):
            creators.append(
                creator.get("name")
                or " ".join(filter(None, [creator.get("firstName"), creator.get("lastName")]))
            )
        doi = normalize_doi(data.get("DOI"))
        alternate = ((row.get("links") or {}).get("alternate") or {}).get("href")
        url = data.get("url") or alternate or f"{base}/items/{item_key}"
        inline_content = data.get("note", "") if item_type == "note" else ""
        attachment_keys: list[str] = []
        if (
            item_type != "note"
            and item_key
            and self.settings.zotero_include_attachments
        ):
            children = await self.client.get(
                f"{base}/items/{item_key}/children",
                params={"format": "json", "limit": 100},
                headers=self._headers(),
            )
            if children.is_success:
                for child in children.json():
                    child_data = child.get("data") or {}
                    if child_data.get("itemType") != "attachment":
                        continue
                    child_key = child_data.get("key")
                    attachment_keys.append(child_key)
                    fulltext = await self.client.get(
                        f"{base}/items/{child_key}/fulltext", headers=self._headers()
                    )
                    if fulltext.is_success:
                        content = fulltext.json().get("content") or ""
                        if content:
                            inline_content = (
                                f"{inline_content}\n\n{content}".strip()
                            )
        metadata = {
            "provider": "zotero",
            "provider_snapshots": {"zotero": row},
            "zotero_item_key": item_key,
            "zotero_item_type": item_type,
            "zotero_library_version": library_version,
            "zotero_attachment_keys": attachment_keys,
            "scholarly_ids": {"doi": doi, "zotero_item_key": item_key},
            "inline_fulltext": inline_content,
            "inline_content_type": "text/html" if item_type == "note" else "text/plain",
            "evidence_eligible": item_type != "note",
            "user_annotation": item_type == "note",
            "tags": [tag.get("tag") for tag in data.get("tags", []) if tag.get("tag")],
            "collections": data.get("collections", []),
            "citation_relations": [
                {
                    "relation_type": "has_attachment",
                    "target_persistent_id": f"zotero:{key}",
                    "provider": "zotero",
                }
                for key in attachment_keys
            ],
        }
        return self.candidate(
            title=data.get("title") or f"Zotero {item_type} {item_key}",
            url=url,
            snippet=data.get("abstractNote") or "",
            persistent_id=doi or f"zotero:{item_key}",
            authors=[author for author in creators if author],
            publisher=data.get("publicationTitle") or data.get("publisher"),
            metadata=metadata,
        )
