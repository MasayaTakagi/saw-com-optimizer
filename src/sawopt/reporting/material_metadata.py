"""Explicit separation of legacy geometry fields and material metadata.

The numerical solver intentionally continues to receive the same design and
provider objects.  This module only builds display/serialization metadata so
that a literature profile's effective material values cannot be confused with
the historical ``FilterDesign`` fields.
"""
from __future__ import annotations

import html
import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Mapping


LEGACY_FIELD_SEMANTICS = {
    "metallization_ratio": (
        "legacy geometry metadata; not used to generate MLIT COM parameters"
    ),
    "thickness_over_lambda": (
        "legacy geometry metadata; not used to generate MLIT COM parameters"
    ),
}


def _source_text(source: Mapping[str, Any] | None) -> str:
    if not source:
        return "unspecified"
    title = str(source.get("title", "")).strip()
    doi = str(source.get("doi", "")).strip()
    if title and doi:
        return f"{title} (doi:{doi})"
    return title or doi or "unspecified"


def material_profile_metadata(
    profile_data: Mapping[str, Any] | None = None,
    *,
    profile_id: str = "M0",
    design: Any | None = None,
    com_parameter_source: str | None = None,
    normalization_definition_source: str | None = None,
) -> dict[str, Any]:
    """Return the effective material profile shown in a result/report.

    ``profile_data`` is the normalized literature YAML mapping.  When it is
    absent, a backward-compatible M0 record is emitted from the legacy design
    values.  No provider or solver object is modified.
    """
    if profile_data is None:
        effective_h = getattr(design, "thickness_over_lambda", None)
        effective_duty = getattr(design, "metallization_ratio", None)
        return {
            "id": str(profile_id),
            "source": "configs/models/com_params_hypothetical.yaml",
            "substrate": "hypothetical",
            "electrode_material": "hypothetical",
            "temperature_c": 25.0,
            "effective_h_over_lambda": effective_h,
            "effective_duty": effective_duty,
            "phase_policy": "M0_FIXED_PROVIDER",
            "com_parameter_source": com_parameter_source or "FixedProvider legacy configuration",
            "normalization_definition_source": (
                normalization_definition_source or "FixedProvider legacy normalization"
            ),
            "display_note": "M0 legacy profile; design fields retain historical display semantics",
        }

    source = profile_data.get("source")
    definition_source = profile_data.get("definition_source")
    return {
        "id": str(profile_data["profile_id"]),
        "source": _source_text(source if isinstance(source, Mapping) else None),
        "substrate": str(profile_data["substrate"]),
        "electrode_material": str(profile_data.get("electrode_material") or "unspecified"),
        "temperature_c": float(profile_data["temperature_c"]),
        "effective_h_over_lambda": float(profile_data["h_over_lambda"]),
        "effective_duty": float(profile_data["metallization_ratio"]),
        "phase_policy": str(profile_data.get("phase_policy", "unspecified")),
        "com_parameter_source": com_parameter_source or _source_text(source if isinstance(source, Mapping) else None),
        "normalization_definition_source": normalization_definition_source or _source_text(
            definition_source if isinstance(definition_source, Mapping) else None
        ),
        "display_note": (
            "effective MLIT profile values above override display semantics; "
            "legacy design fields are not used to generate MLIT COM parameters"
        ),
    }


def design_metadata(design: Any, profile: Mapping[str, Any]) -> dict[str, Any]:
    """Build a serializable result metadata block without changing ``design``."""
    values = asdict(design) if is_dataclass(design) else dict(design)
    return {
        "design": values,
        "design_field_semantics": dict(LEGACY_FIELD_SEMANTICS),
        "material_profile": dict(profile),
    }


def attach_result_metadata(
    result: Mapping[str, Any], design: Any, profile: Mapping[str, Any]
) -> dict[str, Any]:
    """Return a shallow result copy with metadata attached.

    Arrays and numerical result objects remain untouched; callers can compare
    the original and returned payloads to prove that this operation is display
    metadata only.
    """
    enriched = dict(result)
    enriched["metadata"] = design_metadata(design, profile)
    return enriched


def metadata_json_roundtrip(value: Mapping[str, Any]) -> tuple[dict[str, Any], bool]:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True)
    decoded = json.loads(encoded)
    return decoded, decoded == dict(value)


def render_material_metadata_html(records: Mapping[str, Mapping[str, Any]], path: str | Path) -> Path:
    """Render a compact report section containing both M0 and MLIT profiles."""
    cards = []
    for name, record in records.items():
        profile = record["material_profile"]
        design = record["design"]
        rows = "".join(
            f"<tr><th>{html.escape(str(key))}</th><td>{html.escape(str(value))}</td></tr>"
            for key, value in profile.items()
        )
        cards.append(
            f"<section><h2>{html.escape(str(name))}</h2>"
            "<h3>Effective material profile</h3>"
            f"<table>{rows}</table>"
            "<h3>Legacy design fields</h3>"
            f"<pre>{html.escape(json.dumps({k: design.get(k) for k in LEGACY_FIELD_SEMANTICS}, indent=2))}</pre>"
            "<p>legacy design field; not used to generate MLIT COM parameters "
            "when the effective profile is MLIT.</p></section>"
        )
    page = (
        "<!doctype html><html><head><meta charset='utf-8'><title>Material metadata</title>"
        "<style>body{font-family: sans-serif;max-width:1000px;margin:2rem auto}"
        "table{border-collapse:collapse}th,td{border:1px solid #bbb;padding:.35rem;text-align:left}"
        "section{margin-bottom:2rem}</style></head><body>"
        "<h1>Material metadata display</h1>"
        + "".join(cards)
        + "</body></html>"
    )
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    return output


__all__ = [
    "LEGACY_FIELD_SEMANTICS",
    "attach_result_metadata",
    "design_metadata",
    "material_profile_metadata",
    "metadata_json_roundtrip",
    "render_material_metadata_html",
]
