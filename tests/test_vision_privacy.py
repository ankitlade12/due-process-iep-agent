"""Privacy boundary for cloud vision inputs."""

import pytest

from due_process.ingest import read_iep_image
from due_process.llm.client import LLMResult


class _VisionClient:
    def complete_vision(self, prompt, image_b64, *, mime):
        assert image_b64
        return LLMResult(
            text="Speech therapy: 1 x 30 minutes per week.", model="fake")


def test_cloud_vision_refuses_unattested_image(tmp_path):
    image = tmp_path / "iep.png"
    image.write_bytes(b"not-a-real-image")
    with pytest.raises(ValueError, match="disabled for unredacted"):
        read_iep_image(str(image), _VisionClient())


def test_cloud_vision_accepts_explicit_synthetic_attestation(tmp_path):
    image = tmp_path / "synthetic.png"
    image.write_bytes(b"synthetic-image")
    text = read_iep_image(
        str(image), _VisionClient(), image_is_redacted_or_synthetic=True)
    assert "Speech therapy" in text
