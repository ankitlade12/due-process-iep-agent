"""Tests for state filing guidance and the evidence packet."""

from datetime import date

from due_process.analysis import analyze_commitment
from due_process.filing import export_evidence_packet, filing_instructions
from due_process.instruments.drafter import LetterContext, draft_state_complaint
from due_process.scenarios import worked_example_speech

TODAY = date(2026, 6, 30)


def _worked_analysis():
    s = worked_example_speech()
    return analyze_commitment(
        s.commitment, s.logs, window_start=s.window_start,
        window_end=s.window_end, today=TODAY,
        instructional_periods=s.instructional_periods,
        discovery_date=s.discovery_date)


def test_federal_default():
    info = filing_instructions("")
    assert "State Education Agency" in info.agency_name
    assert info.limitations_years == 1  # state complaint: 34 CFR 300.153(c)


def test_known_state():
    info = filing_instructions("CA")
    assert "California" in info.agency_name
    assert info.verify_required is True


def test_new_york_has_real_filing_address():
    info = filing_instructions("NY")
    assert "NYSED" in info.agency_name or "New York" in info.agency_name
    assert "Albany" in info.how_to_file        # the verified filing address
    assert info.url.startswith("https://www.nysed.gov")


def test_unknown_state_falls_back_to_federal():
    assert filing_instructions("ZZ").agency_name == filing_instructions("").agency_name


def test_evidence_packet_assembles():
    a = _worked_analysis()
    inst = draft_state_complaint([a], LetterContext(letter_date=TODAY))
    packet = export_evidence_packet(inst, [a], state="CA")
    assert "EVIDENCE PACKET" in packet
    assert "WHERE TO FILE" in packet
    assert "EXHIBIT INDEX" in packet
    assert "California" in packet
    assert "300.151" in packet
    # Exhibit references the actual service-log dates.
    assert "Exhibit 1" in packet


def test_evidence_packet_writes_file(tmp_path):
    a = _worked_analysis()
    inst = draft_state_complaint([a], LetterContext(letter_date=TODAY))
    out = tmp_path / "packet.txt"
    export_evidence_packet(inst, [a], filename=str(out))
    assert out.exists()
    assert "EVIDENCE PACKET" in out.read_text()
