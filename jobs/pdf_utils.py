"""Minimal PDF writer (no extra packages)."""

from pathlib import Path


def _escape_pdf_text(text: str) -> str:
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_simple_pdf(filepath: Path, title: str, content: str) -> Path:
    """Create a simple one-page PDF with title + content lines."""
    filepath = Path(filepath)
    filepath.parent.mkdir(parents=True, exist_ok=True)

    lines = [title, ""] + (content or "").splitlines()
    y = 750
    ops = ["BT", "/F1 14 Tf", f"50 {y} Td"]
    first = True
    for line in lines:
        safe = _escape_pdf_text(line[:100])
        if first:
            ops.append(f"({safe}) Tj")
            first = False
        else:
            ops.append("0 -18 Td")
            ops.append(f"({safe}) Tj")
    ops.append("ET")
    stream = "\n".join(ops).encode("latin-1", errors="replace")

    objects = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(
        b"4 0 obj<< /Length "
        + str(len(stream)).encode()
        + b" >>stream\n"
        + stream
        + b"\nendstream\nendobj\n"
    )
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")

    pdf = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(pdf))
        pdf.extend(obj)

    xref_pos = len(pdf)
    pdf.extend(f"xref\n0 {len(offsets)}\n".encode())
    pdf.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        pdf.extend(f"{off:010d} 00000 n \n".encode())
    pdf.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\n"
        f"startxref\n{xref_pos}\n%%EOF\n".encode()
    )

    filepath.write_bytes(pdf)
    return filepath
