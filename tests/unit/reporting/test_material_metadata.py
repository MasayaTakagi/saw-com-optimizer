import json
from dataclasses import dataclass

from sawopt.reporting.material_metadata import (
    attach_result_metadata,
    design_metadata,
    material_profile_metadata,
    metadata_json_roundtrip,
    render_material_metadata_html,
)


@dataclass(frozen=True)
class Design:
    metallization_ratio: float = 0.5
    thickness_over_lambda: float = 0.04


MLIT = {
    "profile_id": "LI2024_42YX_LT_METAL_UNSPECIFIED_T25",
    "substrate": "42YX-LiTaO3",
    "electrode_material": "unspecified_metal",
    "temperature_c": 25.0,
    "h_over_lambda": 0.08,
    "metallization_ratio": 0.65,
    "phase_policy": "SIGNED_REAL_TABLE_ASSUMPTION",
    "source": {"title": "source", "doi": "10.0000/source"},
    "definition_source": {"title": "definition", "doi": "10.0000/definition"},
}


def test_mlit_metadata_emits_effective_values_and_legacy_semantics():
    design = Design()
    profile = material_profile_metadata(MLIT)
    record = design_metadata(design, profile)
    assert profile["effective_h_over_lambda"] == 0.08
    assert profile["effective_duty"] == 0.65
    assert "not used to generate MLIT COM parameters" in record["design_field_semantics"]["metallization_ratio"]


def test_m0_metadata_remains_backward_compatible():
    design = Design()
    profile = material_profile_metadata(None, profile_id="M0", design=design)
    assert profile["effective_duty"] == design.metallization_ratio
    assert profile["effective_h_over_lambda"] == design.thickness_over_lambda
    result = {"metrics": {"worst_il_db": 1.2}, "design": {"metallization_ratio": 0.5}}
    enriched = attach_result_metadata(result, design, profile)
    assert enriched["metrics"] == result["metrics"]
    assert enriched["design"] == result["design"]


def test_metadata_patch_is_serializable_and_does_not_change_result_payload():
    design = Design()
    profile = material_profile_metadata(MLIT)
    result = {"metrics": {"ripple_db": 2.0}, "response": [1, 2, 3]}
    enriched = attach_result_metadata(result, design, profile)
    decoded, passed = metadata_json_roundtrip(enriched["metadata"])
    assert passed
    assert decoded["material_profile"]["effective_duty"] == 0.65
    assert enriched["metrics"] is result["metrics"]
    json.dumps(decoded)


def test_report_renders_m0_and_mlit(tmp_path):
    design = Design()
    records = {
        "M0": design_metadata(design, material_profile_metadata(None, profile_id="M0", design=design)),
        "MLIT": design_metadata(design, material_profile_metadata(MLIT)),
    }
    path = render_material_metadata_html(records, tmp_path / "report.html")
    text = path.read_text(encoding="utf-8")
    assert "Effective material profile" in text
    assert "M0" in text and "LI2024_42YX_LT_METAL_UNSPECIFIED_T25" in text
    assert "not used to generate MLIT COM parameters" in text
