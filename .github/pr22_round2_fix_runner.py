from pathlib import Path

script_path = Path('.github/pr22_round2_fix.py')
source = script_path.read_text(encoding='utf-8')
target = 'stream.write("\\\\n")'
replacement = 'stream.write("\\\\\\\\n")'
if source.count(target) != 1:
    raise SystemExit(f'expected one newline-escape target, got {source.count(target)}')
source = source.replace(target, replacement, 1)
exec(compile(source, str(script_path), 'exec'), {'__name__': '__main__'})
