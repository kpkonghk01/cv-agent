"""Text-layer denoising: strip watermark junk, keep real content."""

from __future__ import annotations

from cv_agent.ocr import denoise_text_layer


def test_drops_single_char_watermark_fragments():
    out = denoise_text_layer("李玉婷\n~\nw\nh\n2\n求职意向：AI全栈")
    assert "李玉婷" in out
    assert "求职意向：AI全栈" in out
    assert out.splitlines() == ["李玉婷", "求职意向：AI全栈"]


def test_drops_long_random_watermark_token():
    wm = "16b1c7817ab01d181HN-3dW6GVpTxYy3VfidWOKrnv_YPhhl2w~"
    out = denoise_text_layer(f"{wm}\n李玉婷")
    assert wm not in out
    assert "李玉婷" in out


def test_keeps_email_phone_and_tech_terms():
    out = denoise_text_layer("729682017@qq.com\n14770016941\nSpringCloudGateway\nLangGraph")
    assert "729682017@qq.com" in out
    assert "14770016941" in out       # all-digits, not flagged as a watermark token
    assert "SpringCloudGateway" in out  # long but no digits, kept
    assert "LangGraph" in out
