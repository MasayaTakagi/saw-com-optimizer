from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_repository_does_not_reintroduce_project_local_agent_hooks_or_c2c_config():
    # A removed hook configuration must not return as an empty or disabled
    # project-local container that could later activate retired utilities.
    assert not (ROOT / ".codex").exists()
    assert not (ROOT / ".c2cignore").exists()

    # Keep the retired state probe out of executable source and wrappers too;
    # historical documentation and evidence are intentionally not scanned.
    for relative_root in ("src", "scripts"):
        root = ROOT / relative_root
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            assert "c2c_state_access_preflight" not in text, path
            assert ".codex/hooks" not in text, path
