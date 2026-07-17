"""Pure file-parsing and text-chunking helpers for uploaded notes.

This module has no HTTP or database dependency: it turns raw uploaded bytes
into extracted text, and splits long text into overlapping chunks for later
consumption by an LLM (ticket 06). All failure modes are distinct, typed
exceptions so callers can surface a specific, actionable message instead of a
single generic error.

See tickets/05-upload-and-parse/decisions.md for the locked design.
"""

from io import BytesIO

from pypdf import PdfReader
from pypdf.errors import PdfReadError

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MiB

SUPPORTED_FILE_TYPES = frozenset({"pdf", "md", "txt"})

DEFAULT_MAX_CHARS = 100_000
DEFAULT_OVERLAP_CHARS = 500


class ParsingError(Exception):
    """Base class for all typed parsing failures raised by :func:`parse_file`."""


class UnsupportedFileType(ParsingError):
    """Raised when ``file_type`` is not one of the supported extensions."""


class FileTooLarge(ParsingError):
    """Raised when the uploaded bytes exceed :data:`MAX_FILE_SIZE_BYTES`."""


class NoExtractableText(ParsingError):
    """Raised when the file parses successfully but yields no usable text.

    Distinct from :class:`UnreadableFile`: this means the file was read
    without error, but stripping the extracted text left nothing (e.g. a
    scanned/image PDF with no text layer).
    """


class UnreadableFile(ParsingError):
    """Raised when the file itself could not be parsed at all (e.g. corrupt PDF).

    Distinct from :class:`NoExtractableText`: this means parsing failed
    outright, before any text could be extracted.
    """


def parse_file(data: bytes, file_type: str) -> str:
    """Extract text from raw uploaded file bytes.

    Args:
        data: The raw file contents.
        file_type: The file's extension, case-insensitive, without a leading
            dot (e.g. ``"pdf"``, ``"md"``, ``"txt"``).

    Returns:
        The extracted, non-empty (after stripping) text.

    Raises:
        UnsupportedFileType: ``file_type`` is not ``pdf``, ``md``, or ``txt``.
        FileTooLarge: ``data`` exceeds :data:`MAX_FILE_SIZE_BYTES`.
        UnreadableFile: a PDF's bytes could not be parsed at all.
        NoExtractableText: parsing succeeded but produced no usable text.
    """
    normalized_type = file_type.lower().lstrip(".")

    if normalized_type not in SUPPORTED_FILE_TYPES:
        raise UnsupportedFileType(
            f"unsupported file type: '{file_type}' (expected one of: pdf, md, txt)"
        )

    if len(data) > MAX_FILE_SIZE_BYTES:
        raise FileTooLarge(
            f"file too large: {len(data)} bytes exceeds the {MAX_FILE_SIZE_BYTES}-byte cap"
        )

    if normalized_type == "pdf":
        text = _extract_pdf_text(data)
    else:
        text = data.decode("utf-8", errors="replace")

    if not text.strip():
        raise NoExtractableText("no extractable text — likely a scanned/image PDF or an empty file")

    return text


def _extract_pdf_text(data: bytes) -> str:
    """Extract and concatenate text across all pages of a PDF.

    Raises:
        UnreadableFile: the PDF could not be parsed at all.
    """
    try:
        reader = PdfReader(BytesIO(data))
        pages_text = [page.extract_text() or "" for page in reader.pages]
    except PdfReadError as exc:
        # PdfReadError is pypdf's base parse-failure exception; subclasses
        # like PdfStreamError (truncated/malformed streams) are caught here
        # too.
        raise UnreadableFile(f"could not read this PDF: {exc}") from exc

    return "\n".join(pages_text)


def chunk_text(
    text: str,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap_chars: int = DEFAULT_OVERLAP_CHARS,
) -> list[str]:
    """Split ``text`` into overlapping character-based chunks.

    Returns ``[text]`` unchanged (a single chunk) when ``len(text) <=
    max_chars``. Otherwise splits into consecutive chunks of at most
    ``max_chars`` characters, each overlapping the previous chunk's tail by
    ``overlap_chars`` characters, so a later multi-chunk LLM call (ticket 06)
    doesn't lose context at a chunk boundary.

    This is a plain, stateless helper: it does not persist anything and does
    no NLP-aware (sentence/paragraph) splitting.

    Args:
        text: The text to split.
        max_chars: Maximum characters per chunk.
        overlap_chars: Number of characters each chunk overlaps with the
            previous one.

    Raises:
        ValueError: if ``max_chars`` is not positive, or ``overlap_chars`` is
            negative or is not smaller than ``max_chars``.
    """
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0:
        raise ValueError("overlap_chars must not be negative")
    if overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be smaller than max_chars")

    if len(text) <= max_chars:
        return [text]

    chunks: list[str] = []
    step = max_chars - overlap_chars
    start = 0
    text_len = len(text)
    while start < text_len:
        end = min(start + max_chars, text_len)
        chunks.append(text[start:end])
        if end == text_len:
            break
        start += step

    return chunks
