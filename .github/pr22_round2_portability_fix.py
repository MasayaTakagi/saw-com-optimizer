from pathlib import Path
import re

path = Path('src/sawopt/studies/hybrid_stage4c.py')
text = path.read_text(encoding='utf-8')
text = text.replace('from pathlib import Path\n', 'from pathlib import Path, PureWindowsPath\n', 1)
text = text.replace(
    'if not raw.get("persistent_run_root") or not Path(raw["persistent_run_root"]).is_absolute():',
    'if not raw.get("persistent_run_root") or not _is_absolute_path(raw["persistent_run_root"]):',
    1,
)
pattern = re.compile(
    r'def _is_within\(candidate: str \| Path, parent: str \| Path\) -> bool:\n.*?\n\n\ndef _atomic_json',
    re.S,
)
replacement = '''def _is_absolute_path(candidate: str | Path) -> bool:\n    """Recognize native absolute paths and frozen Windows paths during portable review/tests."""\n    value = str(candidate)\n    return Path(value).is_absolute() or PureWindowsPath(value).is_absolute()\n\n\ndef _is_within(candidate: str | Path, parent: str | Path) -> bool:\n    """Compare path components without accepting textual prefixes, including Windows paths on POSIX CI."""\n    candidate_text, parent_text = str(candidate), str(parent)\n    if PureWindowsPath(parent_text).is_absolute():\n        try:\n            PureWindowsPath(candidate_text).relative_to(PureWindowsPath(parent_text))\n        except ValueError:\n            return False\n        return True\n    try:\n        Path(candidate).resolve(strict=False).relative_to(Path(parent).resolve(strict=False))\n    except (OSError, RuntimeError, ValueError):\n        return False\n    return True\n\n\ndef _atomic_json'''
text, count = pattern.subn(replacement, text, count=1)
if count != 1:
    raise SystemExit(f'expected one _is_within function, got {count}')
path.write_text(text, encoding='utf-8', newline='\n')
