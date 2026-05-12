import base64

from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Optional
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("pdf-tools")


def _resolve_path(path: str) -> Path:
    return Path(path).expanduser().resolve()


@mcp.tool()
def pdf_to_text(
    pdf_path: str,
    output_path: Optional[str] = None,
    layout: bool = True,
) -> str:
    """
    Convert a PDF file to a text file using pdftotext.

    Args:
        pdf_path: Path to the PDF file.
        output_path: Optional output .txt path. If omitted, a .txt file will be created next to the PDF.
        layout: Whether to preserve layout with pdftotext -layout.

    Returns:
        The output text file path and a short preview.
    """
    pdf = _resolve_path(pdf_path)

    if not pdf.exists():
        return f"ERROR: PDF file does not exist: {pdf}"

    if pdf.suffix.lower() != ".pdf":
        return f"ERROR: Input file is not a PDF: {pdf}"

    if output_path:
        out = _resolve_path(output_path)
    else:
        out = pdf.with_suffix(".txt")

    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["pdftotext"]
    if layout:
        cmd.append("-layout")
    cmd.extend([str(pdf), str(out)])

    try:
        result = subprocess.run(
            cmd,
            check=False,
            text=True,
            capture_output=True,
        )
    except FileNotFoundError:
        return "ERROR: pdftotext is not installed. Install it with: sudo apt install -y poppler-utils"

    if result.returncode != 0:
        return (
            "ERROR: pdftotext failed.\n"
            f"Command: {' '.join(cmd)}\n"
            f"stderr:\n{result.stderr}"
        )

    try:
        preview = out.read_text(encoding="utf-8", errors="ignore")[:2000]
    except Exception as e:
        preview = f"Could not read output preview: {e}"

    return (
        f"OK: converted PDF to text.\n"
        f"PDF: {pdf}\n"
        f"TXT: {out}\n\n"
        f"Preview:\n{preview}"
    )


@mcp.tool()
def read_text_preview(path: str, max_chars: int = 4000) -> str:
    """
    Read the beginning of a text/markdown file.

    Args:
        path: Path to a text-like file.
        max_chars: Maximum number of characters to return.

    Returns:
        A preview of the file content.
    """
    p = _resolve_path(path)

    if not p.exists():
        return f"ERROR: file does not exist: {p}"

    if max_chars <= 0:
        max_chars = 4000

    text = p.read_text(encoding="utf-8", errors="ignore")
    return text[:max_chars]

if __name__ == "__main__":
    mcp.run()
