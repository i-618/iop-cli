import sys

from iop.runner import ResolvedStep, run


def _py(code: str) -> tuple:
    return (sys.executable, "-c", code)


def test_run_returns_zero_when_all_steps_succeed():
    steps = [
        ResolvedStep(argv=_py("pass"), shell_command=None, ok_fail=False),
        ResolvedStep(argv=_py("pass"), shell_command=None, ok_fail=False),
    ]
    assert run(steps) == 0


def test_run_stops_at_the_failing_step_and_propagates_its_code(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    marker = tmp_path / "should_not_run.txt"
    steps = [
        ResolvedStep(argv=_py("import sys; sys.exit(0)"), shell_command=None, ok_fail=False),
        ResolvedStep(argv=_py("import sys; sys.exit(7)"), shell_command=None, ok_fail=False),
        ResolvedStep(
            argv=(sys.executable, "-c", f"import pathlib; pathlib.Path(r'{marker}').write_text('x')"),
            shell_command=None,
            ok_fail=False,
        ),
    ]
    assert run(steps) == 7
    assert not marker.exists()  # step 3 must never have run


def test_run_continues_past_an_ok_fail_step(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    marker = tmp_path / "reached.txt"
    steps = [
        ResolvedStep(argv=_py("import sys; sys.exit(1)"), shell_command=None, ok_fail=True),
        ResolvedStep(
            argv=(sys.executable, "-c", f"import pathlib; pathlib.Path(r'{marker}').write_text('x')"),
            shell_command=None,
            ok_fail=False,
        ),
    ]
    assert run(steps) == 0
    assert marker.exists()


def test_run_maps_a_missing_executable_to_127():
    steps = [
        ResolvedStep(
            argv=("definitely-not-a-real-binary-xyz",),
            shell_command=None,
            ok_fail=False,
        )
    ]
    assert run(steps) == 127
