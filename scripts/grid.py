#!/usr/bin/env python3
"""Tile test stills into one labelled contact sheet for quick review:
   ../scripts/grid.py tests/grid.png tests/a.png tests/b.png ... [--cols N] [--width W]"""
import argparse, os
from PIL import Image, ImageDraw

ap = argparse.ArgumentParser()
ap.add_argument("out")
ap.add_argument("images", nargs="+")
ap.add_argument("--cols", type=int, default=2)
ap.add_argument("--width", type=int, default=640, help="width of each tile")
args = ap.parse_args()

tiles = []
for p in args.images:
    im = Image.open(p).convert("RGB")
    im = im.resize((args.width, round(im.height * args.width / im.width)))
    ImageDraw.Draw(im).text((8, 8), os.path.basename(p), fill=(255, 255, 0))
    tiles.append(im)
h = max(t.height for t in tiles)
rows = -(-len(tiles) // args.cols)
sheet = Image.new("RGB", (args.cols * args.width, rows * h))
for i, t in enumerate(tiles):
    sheet.paste(t, ((i % args.cols) * args.width, (i // args.cols) * h))
sheet.save(args.out)
print(args.out, sheet.size)
