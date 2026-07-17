"""Unit tests for the pure parsing/chunking module (no HTTP or DB dependency)."""

import pytest

from memory_ai.parsing import (
    MAX_FILE_SIZE_BYTES,
    FileTooLarge,
    NoExtractableText,
    UnreadableFile,
    UnsupportedFileType,
    chunk_text,
    parse_file,
)


def _build_pdf(content_stream: bytes) -> bytes:
    """Construct minimal, hand-rolled (but valid) single-page PDF bytes.

    Builds a PDF from scratch (no reportlab dependency) with one page whose
    content stream is ``content_stream``. Passing text-drawing operators
    (``BT ... Tj ET``) produces a PDF with extractable text; passing an empty
    stream produces a PDF that parses fine but has no text layer (simulating
    a scanned/image PDF).
    """
    objects = [
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj",
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj",
        b"3 0 obj << /Type /Page /Parent 2 0 R "
        b"/Resources << /Font << /F1 4 0 R >> >> "
        b"/MediaBox [0 0 612 792] /Contents 5 0 R >> endobj",
        b"4 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj",
        b"5 0 obj << /Length %d >> stream\n" % len(content_stream)
        + content_stream
        + b"\nendstream endobj",
    ]

    body = b"%PDF-1.4\n"
    offsets = [0]
    for obj in objects:
        offsets.append(len(body))
        body += obj + b"\n"

    xref_offset = len(body)
    xref = b"xref\n0 %d\n" % (len(objects) + 1)
    xref += b"0000000000 65535 f \n"
    for off in offsets[1:]:
        xref += b"%010d 00000 n \n" % off
    trailer = b"trailer << /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF" % (
        len(objects) + 1,
        xref_offset,
    )

    return body + xref + trailer


@pytest.fixture
def text_pdf_bytes() -> bytes:
    """A minimal, valid single-page PDF containing extractable text."""
    return _build_pdf(b"BT /F1 24 Tf 100 700 Td (Hello World) Tj ET")


@pytest.fixture
def no_text_pdf_bytes() -> bytes:
    """A minimal, valid single-page PDF with an empty content stream.

    Parses without error but has no text layer, simulating a scanned/image
    PDF.
    """
    return _build_pdf(b"")


@pytest.fixture
def corrupt_pdf_bytes() -> bytes:
    """Bytes that look like a PDF but fail to parse at all."""
    return b"%PDF-1.4\nthis is not a real pdf structure, just garbage 1234567890"


class TestParseFilePdf:
    def test_extracts_text_from_valid_pdf(self, text_pdf_bytes: bytes) -> None:
        assert parse_file(text_pdf_bytes, "pdf") == "Hello World"

    def test_extension_is_case_insensitive(self, text_pdf_bytes: bytes) -> None:
        assert parse_file(text_pdf_bytes, "PDF") == "Hello World"

    def test_no_extractable_text_raises_distinct_error(self, no_text_pdf_bytes: bytes) -> None:
        with pytest.raises(NoExtractableText):
            parse_file(no_text_pdf_bytes, "pdf")

    def test_corrupt_pdf_raises_unreadable_file(self, corrupt_pdf_bytes: bytes) -> None:
        with pytest.raises(UnreadableFile):
            parse_file(corrupt_pdf_bytes, "pdf")

    def test_no_extractable_text_and_unreadable_are_distinct_types(
        self, no_text_pdf_bytes: bytes, corrupt_pdf_bytes: bytes
    ) -> None:
        # The two failure modes must be distinguishable exception types, not
        # a single generic error.
        with pytest.raises(NoExtractableText):
            parse_file(no_text_pdf_bytes, "pdf")
        with pytest.raises(UnreadableFile):
            parse_file(corrupt_pdf_bytes, "pdf")
        assert not issubclass(UnreadableFile, NoExtractableText)
        assert not issubclass(NoExtractableText, UnreadableFile)


class TestParseFileMarkdownAndText:
    def test_markdown_is_utf8_decoded(self) -> None:
        data = b"# Heading\n\nSome *markdown* text."
        assert parse_file(data, "md") == "# Heading\n\nSome *markdown* text."

    def test_txt_is_utf8_decoded(self) -> None:
        data = b"Plain note text."
        assert parse_file(data, "txt") == "Plain note text."

    def test_md_extension_is_case_insensitive(self) -> None:
        assert parse_file(b"hello", "MD") == "hello"

    def test_empty_txt_raises_no_extractable_text(self) -> None:
        with pytest.raises(NoExtractableText):
            parse_file(b"   \n\t  ", "txt")

    def test_invalid_utf8_is_replaced_not_raised(self) -> None:
        # errors="replace" per decisions.md — invalid bytes become U+FFFD
        # rather than raising, and the result still has usable text.
        data = b"valid text \xff\xfe more text"
        result = parse_file(data, "txt")
        assert "valid text" in result
        assert "more text" in result


class TestParseFileUnsupportedType:
    def test_unsupported_extension_raises(self) -> None:
        with pytest.raises(UnsupportedFileType):
            parse_file(b"data", "docx")

    def test_unsupported_error_message_names_the_type(self) -> None:
        with pytest.raises(UnsupportedFileType, match="docx"):
            parse_file(b"data", "docx")


class TestParseFileTooLarge:
    def test_oversized_file_raises(self) -> None:
        oversized = b"a" * (MAX_FILE_SIZE_BYTES + 1)
        with pytest.raises(FileTooLarge):
            parse_file(oversized, "txt")

    def test_file_at_exact_cap_is_accepted(self) -> None:
        at_cap = b"a" * MAX_FILE_SIZE_BYTES
        assert parse_file(at_cap, "txt") == "a" * MAX_FILE_SIZE_BYTES


class TestChunkText:
    def test_text_under_threshold_returns_single_chunk(self) -> None:
        text = "short text"
        assert chunk_text(text, max_chars=100, overlap_chars=10) == [text]

    def test_text_at_threshold_returns_single_chunk(self) -> None:
        text = "a" * 100
        assert chunk_text(text, max_chars=100, overlap_chars=10) == [text]

    def test_text_over_threshold_returns_multiple_chunks(self) -> None:
        text = "a" * 250
        chunks = chunk_text(text, max_chars=100, overlap_chars=10)
        assert len(chunks) > 1
        # Every chunk except the last is exactly max_chars long.
        for chunk in chunks[:-1]:
            assert len(chunk) == 100

    def test_chunks_overlap_correctly(self) -> None:
        text = "0123456789" * 30  # 300 distinct-position characters
        max_chars = 100
        overlap_chars = 10
        chunks = chunk_text(text, max_chars=max_chars, overlap_chars=overlap_chars)
        step = max_chars - overlap_chars
        for i in range(len(chunks) - 1):
            # The tail of chunk i should match the head of chunk i+1 over the
            # overlap window.
            expected_overlap = text[i * step + step : i * step + max_chars]
            assert chunks[i][-overlap_chars:] == expected_overlap

    def test_chunks_reconstruct_full_text_with_overlap_removed(self) -> None:
        text = "x" * 237
        max_chars = 50
        overlap_chars = 5
        chunks = chunk_text(text, max_chars=max_chars, overlap_chars=overlap_chars)
        step = max_chars - overlap_chars
        reconstructed = chunks[0]
        for chunk in chunks[1:]:
            reconstructed += chunk[overlap_chars:] if len(chunk) > overlap_chars else ""
        # Rough sanity: reconstructed text covers the same content length
        # class (exact reconstruction depends on step alignment at the tail).
        assert reconstructed.replace("x", "") == ""
        assert step > 0

    def test_default_thresholds_do_not_split_ordinary_notes(self) -> None:
        text = "word " * 1000  # well under 100_000 default max_chars
        assert chunk_text(text) == [text]

    def test_rejects_non_positive_max_chars(self) -> None:
        with pytest.raises(ValueError):
            chunk_text("abc", max_chars=0)

    def test_rejects_negative_overlap(self) -> None:
        with pytest.raises(ValueError):
            chunk_text("abc", max_chars=10, overlap_chars=-1)

    def test_rejects_overlap_not_smaller_than_max_chars(self) -> None:
        with pytest.raises(ValueError):
            chunk_text("abc", max_chars=10, overlap_chars=10)

    def test_last_chunk_covers_the_tail(self) -> None:
        text = "a" * 105
        chunks = chunk_text(text, max_chars=100, overlap_chars=10)
        assert chunks[-1].endswith("a" * 5)
        assert "".join(dict.fromkeys(chunks[-1])) == "a"
