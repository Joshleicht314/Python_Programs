#!/usr/bin/env python3
"""
imgconvert.py - Universal image converter with auto-detected formats and batch support

Usage:
    imgconvert.py input_file target_format
    imgconvert.py file1 file2 ... target_format
    imgconvert.py formats   # show supported formats

Examples:
    imgconvert.py logo.png ico
    imgconvert.py *.png jpg
    imgconvert.py formats
"""

import sys
import os
from glob import glob
from PIL import Image

# Common multi-size set for ICO files
ICO_SIZES = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]

# Aliases for convenience
ALIASES = {
    "jpg": "jpeg",
    "icon": "ico"
}


def get_valid_formats():
    """Get a mapping of extensions -> format names supported by Pillow."""
    valid_formats = {}
    for ext, fmt in Image.registered_extensions().items():
        valid_formats[ext.lstrip(".").lower()] = fmt
    return valid_formats


def show_formats():
    exts = Image.registered_extensions()
    print("✅ Supported formats on this system:\n")
    for ext in sorted(exts.keys()):
        print(f"{ext}  ->  {exts[ext]}")


def convert_file(input_file, target_ext, valid_formats):
    """Convert a single file to the target format."""
    if not os.path.isfile(input_file):
        print(f"❌ File not found: {input_file}")
        return

    # Lowercase output extension
    base, _ = os.path.splitext(input_file)
    output_file = f"{base}.{target_ext}"

    try:
        im = Image.open(input_file)

        # JPEG requires RGB
        if target_ext == "jpeg" and im.mode in ("RGBA", "P"):
            im = im.convert("RGB")

        # ICO requires special handling
        if target_ext == "ico":
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            im.save(output_file, valid_formats[target_ext], sizes=ICO_SIZES)
        else:
            im.save(output_file, valid_formats[target_ext])

        print(f"✅ Saved: {output_file}")

    except Exception as e:
        print(f"❌ Conversion failed for {input_file}: {e}")


def main():
    if len(sys.argv) < 2:
        print("Usage: imgconvert.py input_file(s) target_format")
        print("       imgconvert.py formats")
        sys.exit(1)

    if sys.argv[1].lower() == "formats":
        show_formats()
        sys.exit(0)

    # Last argument is target format
    target_ext = sys.argv[-1].lower()

    # Normalize aliases
    if target_ext in ALIASES:
        target_ext = ALIASES[target_ext]

    valid_formats = get_valid_formats()

    if target_ext not in valid_formats:
        print(f"❌ Unsupported format: {target_ext}")
        print(f"Run `imgconvert formats` to see all supported formats.")
        sys.exit(1)

    # All preceding args are files (support wildcards)
    input_files = []
    for arg in sys.argv[1:-1]:
        input_files.extend(glob(arg))  # expand wildcards

    if not input_files:
        print("❌ No files found to convert.")
        sys.exit(1)

    for file in input_files:
        convert_file(file, target_ext, valid_formats)


if __name__ == "__main__":
    main()
