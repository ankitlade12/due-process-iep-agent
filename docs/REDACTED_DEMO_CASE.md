# Redacted live-demo case

This bundled case exercises the same upload path available to a user. It is a
fully synthetic, de-identified demonstration record: it contains no real student,
family, provider, school, or district information.

## Case setup

- Student label: `Student R-104`
- School label: `Cedar Grove Elementary`
- District label: `Harbor Unified District`
- Instructional periods: `12`
- Review window: `2025-09-02` through `2025-11-20`
- IEP commitment: `Speech-Language Therapy: 2 sessions per week, 30 minutes per
  session, individual, pull-out.`

The app pre-fills these values after **Upload redacted case** is selected. Open
the **Redacted demo case kit** panel, download the bundled CSV and supporting
provider note, upload the CSV, confirm the de-identification attestation, and
select **Start Qwen review**.

## Expected demonstration

The case contains 24 scheduled rows:

- 16 delivered sessions / 480 delivered minutes;
- 3 clearly excused missed sessions / 90 minutes;
- 4 clearly unexcused missed sessions / 120 minutes; and
- 1 deliberately ambiguous entry: `See provider note`.

Qwen should route the unclear entry to the human checkpoint. The reviewer then
opens `redacted-provider-note-r104.txt`, which states that the provider was
reassigned by the school and no substitute was available, and classifies the row
as unexcused. The deterministic ledger shows a 150-minute unexcused gap out of
720 required minutes (20.8%). The threshold is a screening signal, not a legal
finding.

The `SLP-07` provider value is a synthetic role label, not a person.
