#!/usr/bin/env python3
"""Prepare an image as a black-and-white e-ink asset."""

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from home_companian.image_processing import (  # noqa: E402
    DEFAULT_SIZE,
    process_file,
)


def parse_size(value: str) -> tuple[int, int]:
    try:
        width_text, height_text = value.lower().split("x", 1)
        width, height = int(width_text), int(height_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("size must use WIDTHxHEIGHT") from exc
    if width <= 0 or height <= 0:
        raise argparse.ArgumentTypeError("size must be positive")
    return width, height


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert an image to a slot-sized 1-bit PNG for the e-ink display."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument(
        "--size",
        type=parse_size,
        default=DEFAULT_SIZE,
        metavar="WIDTHxHEIGHT",
        help="output size (default: 792x228)",
    )
    parser.add_argument(
        "--fit",
        choices=("cover", "contain"),
        default="cover",
        help="crop to fill or preserve the whole image (default: cover)",
    )
    parser.add_argument(
        "--binarize",
        choices=("dither", "threshold", "grayscale"),
        default="dither",
        help="photo dithering, hard threshold, or processed grayscale master (default: dither)",
    )
    parser.add_argument("--threshold", type=int, default=180)
    parser.add_argument("--autocontrast", action="store_true")
    parser.add_argument("--invert", action="store_true")
    parser.add_argument(
        "--trim",
        type=int,
        default=0,
        metavar="PIXELS",
        help="crop this many pixels from every input edge",
    )
    parser.add_argument(
        "--content-scale",
        type=float,
        default=1.0,
        metavar="RATIO",
        help="scale content within the output canvas (0 < ratio <= 1)",
    )
    args = parser.parse_args()
    try:
        processed = process_file(
            args.input,
            args.output,
            size=args.size,
            fit=args.fit,
            binarize=args.binarize,
            threshold=args.threshold,
            autocontrast=args.autocontrast,
            invert=args.invert,
            trim=args.trim,
            content_scale=args.content_scale,
        )
    except ValueError as exc:
        parser.error(str(exc))
    print(
        f"Wrote {args.output} "
        f"({processed.width}x{processed.height}, {processed.mode} PNG)"
    )


if __name__ == "__main__":
    main()
