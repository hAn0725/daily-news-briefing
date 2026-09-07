from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_hidden_launcher_waits_and_propagates_exit_code():
    script = (ROOT / "run_scheduled.vbs").read_text(encoding="utf-8")

    assert "sh.Run(command, 0, True)" in script
    assert "WScript.Quit exitCode" in script
    assert "scheduler.log" in script
    assert "LAUNCH_ERROR" in script


def test_batch_runner_quotes_python_and_logs_lifecycle():
    script = (ROOT / "run_daily.bat").read_text(encoding="utf-8")

    assert '"%PY_EXE%" %PY_ARGS% -m news_crawler.main --wait-net' in script
    assert "scheduled launcher started" in script
    assert "scheduled launcher finished rc=%RC%" in script
