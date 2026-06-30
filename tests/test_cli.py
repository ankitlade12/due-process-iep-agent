"""Smoke tests for the CLI entry point (offline)."""

from due_process.cli import main

_LOGS_CSV = """Date,Minutes,Status,Reason
2025-09-02,30,Delivered,
2025-09-04,0,Missed,Provider absent no substitute
2025-09-06,30,Delivered,
2025-09-09,0,Missed,Provider absent no substitute
2025-09-11,30,Delivered,
2025-09-13,0,Missed,Provider absent no substitute
"""

_DEFICIENT_PWN = """The district proposes to change placement. This is because of
new evaluation data, based on the assessment and reports. You have procedural
safeguards and may request a copy. Contact the parent center for assistance.
"""


def test_version(capsys):
    assert main(["version"]) == 0
    assert "due-process" in capsys.readouterr().out


def test_worked_example_runs(capsys):
    assert main(["worked-example"]) == 0
    assert "720" in capsys.readouterr().out


def test_analyze_from_csv(tmp_path, capsys):
    csv_path = tmp_path / "logs.csv"
    csv_path.write_text(_LOGS_CSV)
    rc = main(["analyze", "--logs", str(csv_path), "--service", "speech",
               "--freq", "3", "--duration", "30", "--periods", "2",
               "--today", "2026-06-30", "--state", "NY"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "Material failure: True" in out
    assert "State-complaint deadline" in out
    assert "New York" in out  # filing instructions localized


def test_analyze_draft_and_packet(tmp_path, capsys):
    csv_path = tmp_path / "logs.csv"
    csv_path.write_text(_LOGS_CSV)
    packet = tmp_path / "packet.txt"
    rc = main(["analyze", "--logs", str(csv_path), "--service", "speech",
               "--freq", "3", "--duration", "30", "--periods", "2",
               "--today", "2026-06-30", "--draft", "--packet", str(packet)])
    assert rc == 0
    assert "STATE COMPLAINT" in capsys.readouterr().out
    assert packet.exists() and "EVIDENCE PACKET" in packet.read_text()


def test_pwn_check(tmp_path, capsys):
    pwn_path = tmp_path / "pwn.txt"
    pwn_path.write_text(_DEFICIENT_PWN)
    rc = main(["pwn", "--file", str(pwn_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "MISSING" in out
    assert "300.503" in out


def test_unknown_service_errors(tmp_path):
    csv_path = tmp_path / "logs.csv"
    csv_path.write_text(_LOGS_CSV)
    assert main(["analyze", "--logs", str(csv_path), "--service", "nonsense"]) == 2
