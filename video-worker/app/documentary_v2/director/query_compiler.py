"""Compile ShotRequirement → SearchIntent families (different strategies)."""
from __future__ import annotations

from app.documentary_v2.schemas import (
    QueryFamily,
    SearchIntent,
    ShotRequirement,
)


def compile_search_intents(req: ShotRequirement) -> list[SearchIntent]:
    entities = list(req.required_entities or [])
    entity = entities[0] if entities else req.subject
    concept = req.required_visual_concept or entity or req.subject
    domain = req.semantic_domain
    types = list(req.preferred_media_types or ([req.preferred_media_type] if req.preferred_media_type else []))
    intents: list[SearchIntent] = []

    def add(family: str, query: str, *, archive: bool = False, media: list[str] | None = None) -> None:
        intents.append(
            SearchIntent(
                intent_id=f"intent:{req.shot_requirement_id}:{family}",
                beat_id=req.beat_id,
                shot_requirement_id=req.shot_requirement_id,
                query=query.strip(),
                query_family=family,
                semantic_domain=domain,
                target_concept=concept,
                target_entities=list(entities),
                preferred_media_types=media or types,
                archive_preference=archive,
            )
        )

    if entity:
        add(QueryFamily.ENTITY_EXACT.value, entity, media=types)
        if req.action and req.action not in {req.visual_purpose, ""}:
            add(QueryFamily.ENTITY_ACTION.value, f"{entity} {req.action}")
        add(QueryFamily.ENTITY_CONTEXT.value, f"{entity} {concept}".strip())
        if req.location:
            add(QueryFamily.LOCATION.value, f"{entity} {req.location}")
            add(QueryFamily.LOCATION.value, req.location)

    purpose = req.visual_purpose
    if purpose == "SHOW_PERSON" or req.authenticity_requirement.upper().startswith("AUTHENTIC"):
        add(
            QueryFamily.ARCHIVE.value,
            f"{entity} portrait historical" if entity else f"{concept} archival portrait",
            archive=True,
            media=["archive_still", "stock_photo"],
        )
    if purpose == "SHOW_EVIDENCE" or (
        req.evidence_role == "EVIDENCE_REQUIRED" and purpose not in {"EXPLAIN_RELATIONSHIP", "SHOW_PERSON"}
    ):
        add(
            QueryFamily.EVIDENCE.value,
            f"{entity} {concept} document evidence" if entity else f"{concept} document evidence",
            archive=True,
            media=["document", "archive_still"],
        )
        add(
            QueryFamily.DOCUMENT.value,
            f"{entity} {concept} source document" if entity else f"{concept} source document",
            archive=True,
            media=["document", "archive_still"],
        )
    if purpose == "SHOW_PROCESS":
        add(QueryFamily.ENTITY_ACTION.value, f"{entity} {req.action or concept} process" if entity else f"{concept} process")
    if purpose == "SHOW_LOCATION":
        loc = req.location or concept
        add(QueryFamily.LOCATION.value, loc, media=["stock_video", "stock_photo"])
    if purpose == "EXPLAIN_RELATIONSHIP":
        # Search the stated relationship, without inventing a brand or product.
        add(
            QueryFamily.ENTITY_CONTEXT.value,
            f"{entity} {concept}" if entity else concept,
            media=["stock_video", "stock_photo"],
        )
        add(
            QueryFamily.CONCEPTUAL.value,
            f"{entity} {concept}" if entity else concept,
            media=["stock_video"],
        )
    if purpose in {"ESTABLISH_CONTEXT", "IDENTIFY_ENTITY", "SHOW_PRODUCT", "CREATE_PAYOFF"} and not any(
        i.query_family == QueryFamily.CONCEPTUAL.value for i in intents
    ):
        add(QueryFamily.CONCEPTUAL.value, concept, media=types or ["stock_video"])

    if not intents:
        add(QueryFamily.CONCEPTUAL.value, concept or "scene", media=types)

    # Dedup identical queries
    seen = set()
    unique: list[SearchIntent] = []
    for it in intents:
        key = (it.query_family, it.query.lower())
        if key in seen or not it.query:
            continue
        seen.add(key)
        unique.append(it)
    req.search_intents = [i.query_family for i in unique]
    return unique
