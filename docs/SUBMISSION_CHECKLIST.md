# Qwen hackathon submission checklist

The official rules control; re-check them immediately before submitting.

## Eligibility and timing

- [ ] Confirm every team member's residence is eligible under the official rules.
- [ ] Submit before **July 20, 2026 at 2:00 PM Pacific Time**; do not rely on a
  local-time assumption.
- [ ] Identify **Track 4: Autopilot Agent** consistently in the form and video.

## Required proof

- [ ] Public, judge-accessible repository with an open-source license.
- [ ] Public testable application that remains available through judging.
- [ ] Qwen Cloud usage visible in code and in actual-call provenance.
- [ ] Backend deployed on Alibaba Cloud.
- [ ] Architecture diagram included.
- [ ] Public demo video under three minutes.
- [ ] Code/repository link added to the submission.
- [ ] Alibaba Cloud Workbench screenshot clearly showing the deployed resource.
- [ ] Slide deck attached if the submission form requests it.

The organizer's July update says missing code-link or Workbench proof can make an
entry ineligible. Capture the screenshot after the final deployment and ensure no
credential or student record is visible.

## Quality gate

- [ ] Rotate every credential exposed during development; review usage logs.
- [ ] `uv run --extra dev pytest` passes on a clean checkout.
- [ ] `python -m due_process.evaluation.run_eval --offline` matches README metrics.
- [ ] Live Qwen path is recorded once; fallback is labeled honestly if it occurs.
- [ ] Authenticated synthetic request produces an OSS receipt.
- [ ] Demo uses synthetic/de-identified data only.
- [ ] Accessibility smoke check: keyboard navigation, contrast, captions, readable
  zoom, and no meaning conveyed by color alone.
- [ ] Claims avoid “only,” guaranteed legal outcomes, and compliance guarantees.
- [ ] All public links work in a signed-out browser.

## Official references

- [Hackathon rules](https://qwen3-hackathon.devpost.com/rules)
- [Hackathon page and submission flow](https://qwen3-hackathon.devpost.com/)
