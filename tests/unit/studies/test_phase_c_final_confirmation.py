from sawopt.io.config import load_experiment_config
from sawopt.studies.convergence import normalize_convergence_config
from sawopt.studies.phase_c_final_confirmation import (
    CURVE_BUDGETS,
    SEEDS,
    _aggregate_curve,
    _arm_cfg,
)


def _row(seed, optimizer, budget, value):
    return {
        "seed": seed,
        "optimizer": optimizer,
        "checkpoint_budget": budget,
        "feasible": False,
        "max_violation": value,
        "sum_violation": value,
        "worst_il_db": 5.0,
    }


def test_curve_reports_confirmed_interval_and_seed_wins():
    rows = []
    for budget in CURVE_BUDGETS:
        legacy_value, lshade_value = (0.70, 0.71) if budget == 4000 else (0.70, 0.60)
        for seed in SEEDS:
            rows.extend([
                _row(seed, "Legacy-DE", budget, legacy_value),
                _row(seed, "L-SHADE", budget, lshade_value),
            ])
    result = _aggregate_curve(rows)
    assert result["first_observed_lshade_better_budget"] == 8000
    assert result["confirmed_crossover_interval"] == "(4k, 8k]"
    assert result["crossover_reproduced"] is True
    assert result["median_by_budget"]["4000"]["legacy_seed_wins"] == 4
    assert result["median_by_budget"]["8000"]["lshade_seed_wins"] == 4


def test_diagnostic_lshade_keeps_terminal_horizon_separate():
    base = normalize_convergence_config(load_experiment_config(
        "configs/studies/stage3_5_phase_c_final_confirmation.yaml"
    ))
    import yaml
    s1 = yaml.safe_load(open(
        "artifacts/stage3_5/phase_a_revised/search_space_s1.yaml", encoding="utf-8"
    ))
    cfg = _arm_cfg(base, s1, optimizer="lshade", seeds=SEEDS, budgets=[4000, 8000])
    assert cfg["stage3_5_arm"]["diagnostic_stop"] == 8000
    assert cfg["stage3_3"]["lshade"]["population_schedule_terminal_budget"] == 64000
    assert cfg["stage3_3"]["lshade"]["hard_max_budget"] == 64000
