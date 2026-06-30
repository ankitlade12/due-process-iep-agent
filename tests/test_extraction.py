"""Tests for IEP commitment extraction (offline regex path)."""

from due_process.llm.extraction import extract_commitments
from due_process.models import (
    DeliverySetting,
    FrequencyPeriod,
    ServiceLocation,
    ServiceType,
)


def test_extract_speech_line():
    text = "Speech-Language Therapy: 3 x 30 minutes per week, individual, pull-out."
    extracted = extract_commitments(text)
    assert len(extracted) == 1
    e = extracted[0]
    assert e.needs_confirmation is True  # always confirmed by a human
    c = e.commitment
    assert c.service_type == ServiceType.SPEECH_LANGUAGE
    assert c.frequency_count == 3
    assert c.frequency_period == FrequencyPeriod.WEEK
    assert c.duration_minutes == 30
    assert c.setting == DeliverySetting.INDIVIDUAL
    assert c.location == ServiceLocation.PULL_OUT


def test_extract_group_ot_line():
    text = "Occupational Therapy: 2 sessions per week, 45 min, group of 3, push-in"
    extracted = extract_commitments(text)
    assert len(extracted) == 1
    c = extracted[0].commitment
    assert c.service_type == ServiceType.OCCUPATIONAL_THERAPY
    assert c.frequency_count == 2
    assert c.duration_minutes == 45
    assert c.setting == DeliverySetting.GROUP
    assert c.group_size_max == 3
    assert c.location == ServiceLocation.PUSH_IN


def test_multiple_services():
    text = (
        "Speech-Language Therapy: 3 x 30 minutes per week, individual.\n"
        "Physical Therapy: 1 x 30 min per week, individual, pull-out.\n"
    )
    extracted = extract_commitments(text)
    assert len(extracted) == 2
    assert {e.commitment.service_type for e in extracted} == {
        ServiceType.SPEECH_LANGUAGE, ServiceType.PHYSICAL_THERAPY}


def test_non_service_text_yields_nothing():
    assert extract_commitments("The student is making good progress.") == []


def test_source_ref_attached():
    text = "Speech-Language Therapy: 3 x 30 minutes per week, individual."
    e = extract_commitments(text, source_uri="oss://iep.pdf")[0]
    assert e.commitment.source_ref is not None
    assert e.commitment.source_ref.uri == "oss://iep.pdf"
