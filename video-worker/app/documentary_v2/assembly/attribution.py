"""Attribution / provenance manifest for Stage F review package."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from app.documentary_v2.schemas import EditDecisionList


@dataclass
class AttributionEntry:
    asset_id: str
    beat_id: str = ""
    provider: str = ""
    source_url: str = ""
    creator: str = ""
    license: str = "UNKNOWN"
    license_policy: str = "UNKNOWN"
    license_url: str = ""
    attribution: str = ""
    attribution_required: bool = False
    synthetic: bool = False
    internal: bool = False
    local_path: str = ""
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def build_attribution_manifest(
    edl: EditDecisionList,
    *,
    provenance_by_asset: dict[str, dict] | None = None,
) -> list[dict[str, Any]]:
    provenance_by_asset = provenance_by_asset or {}
    out: list[AttributionEntry] = []
    seen: set[str] = set()
    for d in edl.decisions or []:
        key = d.asset_id or d.local_path
        if key in seen:
            continue
        seen.add(key)
        prov = provenance_by_asset.get(d.asset_id) or provenance_by_asset.get(d.local_path) or {}
        internal = d.source_kind == "motion_graphic"
        license_state = str(prov.get("license") or ("INTERNAL" if internal else "UNKNOWN"))
        license_policy = str(prov.get("license_policy") or "UNKNOWN")
        out.append(
            AttributionEntry(
                asset_id=d.asset_id,
                beat_id=d.beat_id,
                provider=str(prov.get("provider") or d.source_kind or ""),
                source_url=str(prov.get("source_url") or ""),
                creator=str(prov.get("creator") or prov.get("author") or ""),
                license=license_state,
                license_policy=license_policy,
                license_url=str(prov.get("license_url") or ""),
                attribution=str(prov.get("attribution") or ""),
                attribution_required=bool(
                    prov.get("attribution_required")
                    or license_policy == "ATTRIBUTION_REQUIRED"
                    or license_state in {"CC_BY", "CC_BY_SA"}
                ),
                synthetic=bool(d.synthetic),
                internal=internal,
                local_path=d.local_path,
                notes=str(prov.get("notes") or ("Source license not verified" if license_state == "UNKNOWN" else "")),
            )
        )
    return [e.to_dict() for e in out]
