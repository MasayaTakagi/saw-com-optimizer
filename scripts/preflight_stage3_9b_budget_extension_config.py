"""Config-only, read-only launch preflight for the Stage 3.9B 16k extension."""
from sawopt.studies.audits.stage3_9b_budget_extension import preflight_main


if __name__ == "__main__":
    raise SystemExit(preflight_main())
