from __future__ import annotations
import subprocess
from pathlib import Path
from typing import Optional
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("image-tools")

SUPPORTED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".tiff", ".tif", ".ico", ".avif", ".heic"}


def _resolve_path(path: str) -> Path:
    return Path(path).expanduser().resolve()


def _check_file(p: Path) -> str | None:
    if not p.exists():
        return f"ERROR: file does not exist: {p}"
    if p.suffix.lower() not in SUPPORTED_SUFFIXES:
        return f"ERROR: unsupported image format: {p.suffix}. Supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
    return None


@mcp.tool()
def image_info(image_path: str) -> str:
    """
    Get detailed information about an image file: dimensions, format, mode,
    file size, and EXIF metadata.

    Args:
        image_path: Path to the image file (png, jpg, jpeg, webp, gif, bmp, tiff, etc.)

    Returns:
        A text summary of the image properties.
    """
    from PIL import Image, ExifTags

    p = _resolve_path(image_path)
    err = _check_file(p)
    if err:
        return err

    try:
        img = Image.open(p)
    except Exception as e:
        return f"ERROR: cannot open image: {e}"

    size_bytes = p.stat().st_size

    lines = [
        f"File: {p}",
        f"Format: {img.format}",
        f"Mode: {img.mode}",
        f"Dimensions: {img.width} x {img.height}",
        f"File size: {size_bytes:,} bytes ({size_bytes / 1024:.1f} KB)",
    ]

    # EXIF
    exif = img.getexif()
    if exif:
        lines.append("\nEXIF metadata:")
        for tag_id, value in exif.items():
            tag_name = ExifTags.TAGS.get(tag_id, f"Unknown({tag_id})")
            # Skip large binary values
            if isinstance(value, bytes):
                value = f"<binary, {len(value)} bytes>"
            lines.append(f"  {tag_name}: {value}")
    else:
        lines.append("\nNo EXIF metadata found.")

    img.close()
    return "\n".join(lines)


@mcp.tool()
def convert_image(
    image_path: str,
    output_path: str,
    quality: int = 85,
) -> str:
    """
    Convert an image to a different format (e.g., png->jpg, jpg->png, etc.).

    Args:
        image_path: Path to the source image.
        output_path: Destination path. The extension determines the output format.
        quality: JPEG/WebP quality (1-100). Default 85.

    Returns:
        Status message with output path and size.
    """
    from PIL import Image

    src = _resolve_path(image_path)
    err = _check_file(src)
    if err:
        return err

    dst = _resolve_path(output_path)

    try:
        img = Image.open(src)
    except Exception as e:
        return f"ERROR: cannot open image: {e}"

    # Handle mode conversion for JPEG
    if dst.suffix.lower() in {".jpg", ".jpeg"} and img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    dst.parent.mkdir(parents=True, exist_ok=True)

    save_kwargs = {}
    if dst.suffix.lower() in {".jpg", ".jpeg"}:
        save_kwargs["quality"] = quality
        save_kwargs["optimize"] = True
    elif dst.suffix.lower() == ".webp":
        save_kwargs["quality"] = quality
    elif dst.suffix.lower() == ".png":
        save_kwargs["optimize"] = True

    try:
        img.save(str(dst), **save_kwargs)
    except Exception as e:
        img.close()
        return f"ERROR: conversion failed: {e}"

    img.close()
    dst_size = dst.stat().st_size
    src_size = src.stat().st_size

    return (
        f"OK: converted image.\n"
        f"From: {src} ({src_size:,} bytes)\n"
        f"To:   {dst} ({dst_size:,} bytes)\n"
        f"Format: {dst.suffix.upper()}"
    )


@mcp.tool()
def resize_image(
    image_path: str,
    output_path: str,
    width: Optional[int] = None,
    height: Optional[int] = None,
    keep_aspect: bool = True,
) -> str:
    """
    Resize an image to the given dimensions.

    Args:
        image_path: Path to the source image.
        output_path: Destination path.
        width: Target width in pixels.
        height: Target height in pixels.
        keep_aspect: If True, preserve aspect ratio when only one dimension is given.

    Returns:
        Status message with old and new dimensions.
    """
    from PIL import Image

    src = _resolve_path(image_path)
    err = _check_file(src)
    if err:
        return err

    if width is None and height is None:
        return "ERROR: at least one of width or height must be provided."

    try:
        img = Image.open(src)
    except Exception as e:
        return f"ERROR: cannot open image: {e}"

    old_size = (img.width, img.height)

    if keep_aspect and (width is None or height is None):
        if width is None:
            ratio = height / img.height
            width = int(img.width * ratio)
        elif height is None:
            ratio = width / img.width
            height = int(img.height * ratio)

    target = (width or img.width, height or img.height)

    try:
        resized = img.resize(target, Image.LANCZOS)
    except Exception as e:
        img.close()
        return f"ERROR: resize failed: {e}"

    dst = _resolve_path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    save_kwargs = {}
    if dst.suffix.lower() in {".jpg", ".jpeg"}:
        if resized.mode in ("RGBA", "P", "LA"):
            resized = resized.convert("RGB")
        save_kwargs["quality"] = 85
        save_kwargs["optimize"] = True
    elif dst.suffix.lower() == ".png":
        save_kwargs["optimize"] = True

    try:
        resized.save(str(dst), **save_kwargs)
    except Exception as e:
        img.close()
        return f"ERROR: save failed: {e}"

    img.close()
    return (
        f"OK: resized image.\n"
        f"Source: {old_size[0]}x{old_size[1]}\n"
        f"Result: {target[0]}x{target[1]}\n"
        f"Saved to: {dst}"
    )


@mcp.tool()
def create_thumbnail(
    image_path: str,
    output_path: str,
    size: int = 256,
) -> str:
    """
    Create a square thumbnail of the image.

    Args:
        image_path: Path to the source image.
        output_path: Destination path for the thumbnail.
        size: Max width/height in pixels. Default 256.

    Returns:
        Status message with output path and dimensions.
    """
    from PIL import Image

    src = _resolve_path(image_path)
    err = _check_file(src)
    if err:
        return err

    try:
        img = Image.open(src)
    except Exception as e:
        return f"ERROR: cannot open image: {e}"

    img.thumbnail((size, size), Image.LANCZOS)

    dst = _resolve_path(output_path)
    dst.parent.mkdir(parents=True, exist_ok=True)

    save_kwargs = {}
    if dst.suffix.lower() in {".jpg", ".jpeg"}:
        if img.mode in ("RGBA", "P", "LA"):
            img = img.convert("RGB")
        save_kwargs["quality"] = 85
        save_kwargs["optimize"] = True
    elif dst.suffix.lower() == ".png":
        save_kwargs["optimize"] = True

    try:
        img.save(str(dst), **save_kwargs)
    except Exception as e:
        img.close()
        return f"ERROR: save failed: {e}"

    img.close()
    return (
        f"OK: created thumbnail.\n"
        f"Size: {img.width}x{img.height}\n"
        f"Saved to: {dst}"
    )


@mcp.tool()
def estimate_compression(
    image_path: str,
    quality: int = 50,
) -> str:
    """
    Estimate the compressed size of an image at a given JPEG quality
    without saving to disk (uses an in-memory buffer).

    Args:
        image_path: Path to the source image.
        quality: JPEG quality (1-100). Default 50.

    Returns:
        Estimated compressed size vs original size.
    """
    from PIL import Image
    from io import BytesIO

    src = _resolve_path(image_path)
    err = _check_file(src)
    if err:
        return err

    try:
        img = Image.open(src)
    except Exception as e:
        return f"ERROR: cannot open image: {e}"

    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    buf = BytesIO()
    img.save(buf, format="JPEG", quality=quality, optimize=True)
    compressed_size = buf.tell()
    img.close()

    src_size = src.stat().st_size
    ratio = compressed_size / src_size * 100 if src_size > 0 else 0

    return (
        f"Estimation for JPEG quality={quality}:\n"
        f"Original: {src_size:,} bytes\n"
        f"Compressed: {compressed_size:,} bytes ({ratio:.1f}% of original)\n"
        f"Saved: {src_size - compressed_size:,} bytes"
    )


if __name__ == "__main__":
    mcp.run()
