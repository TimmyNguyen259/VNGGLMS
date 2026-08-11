"""Unit tests cho _render_lesson_media — không cần Flask, chỉ test hàm thuần."""
import pytest
from modules.lms.enrollment import _render_lesson_media as render


@pytest.mark.parametrize("url,expected_substring", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "youtube-nocookie.com/embed/dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ", "youtube-nocookie.com/embed/dQw4w9WgXcQ"),
    ("https://www.youtube.com/embed/dQw4w9WgXcQ", "youtube-nocookie.com/embed/dQw4w9WgXcQ"),
    ("https://youtube.com/watch?v=abc123&t=42", "youtube-nocookie.com/embed/abc123"),
    ("https://m.youtube.com/watch?v=xyzXYZ_012", "youtube-nocookie.com/embed/xyzXYZ_012"),
])
def test_youtube_variants_produce_iframe(url, expected_substring):
    html = render("video", url)
    assert expected_substring in html
    assert "<iframe" in html


def test_vimeo_produces_iframe():
    html = render("video", "https://vimeo.com/76979871")
    assert "player.vimeo.com/video/76979871" in html
    assert "<iframe" in html


def test_pdf_url_produces_iframe():
    html = render("pdf", "https://example.com/notes.pdf")
    assert 'iframe src="https://example.com/notes.pdf"' in html


def test_video_content_type_but_pdf_url_still_embeds_as_pdf():
    """URL ends in .pdf -> pdf viewer even nếu admin chọn content_type=video."""
    html = render("video", "https://example.com/handout.pdf")
    assert 'iframe src="https://example.com/handout.pdf"' in html


def test_unknown_video_url_falls_back_to_link():
    html = render("video", "https://example.com/somefile.mp4")
    assert "btn btn-blue" in html
    assert "target=\"_blank\"" in html


def test_javascript_scheme_blocked():
    assert render("video", "javascript:alert(1)") == ""


def test_ftp_scheme_blocked():
    assert render("pdf", "ftp://internal/handout.pdf") == ""


def test_empty_url_returns_empty():
    assert render("video", "") == ""
    assert render("video", None) == ""


def test_url_attribute_is_html_escaped():
    """Admin có thể inject " vào URL — phải escape."""
    malicious = 'https://x.com/"><script>alert(1)</script>'
    html = render("pdf", malicious)
    # Attacker string không được thoát ra ngoài attribute
    assert "<script>" not in html
    assert "&quot;" in html or "&#" in html
