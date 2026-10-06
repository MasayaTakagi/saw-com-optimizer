# Windows reference fixture for WSL2 core qualification

This directory contains the compact, committed numerical reference used by the
WSL2 core qualification scripts. It is a software-parity fixture, not a
production filter result or an accepted scientific finding.

The fixture was captured on 2026-10-06 UTC from project source commit
`65e1815db1cc18d74ff0dcee20ffd5e9098709df`, using the existing Windows project
virtual environment. It records a fixed P_D evaluator input and its frequency
grid, S11/S21 arrays, metrics, and constraints. It also records a 270-unique-
evaluation checkpoint/resume smoke with seed `20261022`, interrupted at 250 and
270 evaluations and compared with an uninterrupted run using the same seed.
The local raw runs and full environment log remain in the ignored
`artifacts/wsl-qualification/` directory and are not part of this fixture.

Machine-specific absolute paths, raw output paths, and runtime measurements
were removed. Numerical arrays and dependency versions remain so a Linux run
can compare the same inputs and calculations. The fixture does not claim that
Windows and Linux are bitwise identical for every workload; the declared
tolerances and any mismatch are handled by the qualification report.
