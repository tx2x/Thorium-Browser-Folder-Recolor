#!/usr/bin/env python3
"""
Recolor the yellow bookmark folder icons in Thorium/Chromium .pak files to blue.

The script does not depend on resource IDs (which change between versions).
It parses the .pak files (formats v4 and v5), finds small PNG images that are
mostly yellow, and shifts their hue to a muted light blue. Because detection is
color-based, you can simply run it again after every browser update.

Requirements:  pip install pillow numpy

Examples:
  python recolor_folders.py --list   "C:\\Users\\Me\\AppData\\Local\\Thorium\\Application\\156.0.8078.28"
  python recolor_folders.py --export preview "C:\\...\\156.0.8078.28"
  python recolor_folders.py "C:\\...\\156.0.8078.28"
  python recolor_folders.py --restore "C:\\...\\156.0.8078.28"

Close Thorium completely (including background processes) before running.
"""
import argparse
import io
import os
import shutil
import struct
import sys

import numpy as np
from PIL import Image

PNG_SIG = b"\x89PNG\r\n\x1a\n"
PAK_FILES = ("chrome_100_percent.pak", "chrome_200_percent.pak")


# --------------------------------------------------------------------------- #
#  .pak handling
# --------------------------------------------------------------------------- #
class Pak:
    def __init__(self, path):
        with open(path, "rb") as f:
            self.raw = f.read()
        raw = self.raw
        self.version = struct.unpack_from("<I", raw, 0)[0]
        if self.version == 5:
            self.encoding = raw[4]
            count, alias_count = struct.unpack_from("<HH", raw, 8)
            pos = 12
        elif self.version == 4:
            count = struct.unpack_from("<I", raw, 4)[0]
            self.encoding = raw[8]
            alias_count = 0
            pos = 9
        else:
            raise ValueError(f"Unsupported .pak version: {self.version}")

        # count + 1 entries (the last one is a sentinel marking the end of data)
        entries = []
        for i in range(count + 1):
            rid, off = struct.unpack_from("<HI", raw, pos + i * 6)
            entries.append((rid, off))
        pos += (count + 1) * 6

        self.aliases = []
        for i in range(alias_count):
            self.aliases.append(struct.unpack_from("<HH", raw, pos + i * 4))

        self.ids = [e[0] for e in entries[:-1]]
        self.data = [raw[entries[i][1]:entries[i + 1][1]] for i in range(count)]

    def save(self, path):
        count = len(self.ids)
        out = bytearray()
        if self.version == 5:
            out += struct.pack("<I", 5)
            out += bytes([self.encoding, 0, 0, 0])
            out += struct.pack("<HH", count, len(self.aliases))
            header_size = 12
        else:
            out += struct.pack("<I", 4)
            out += struct.pack("<I", count)
            out += bytes([self.encoding])
            header_size = 9

        data_start = header_size + (count + 1) * 6 + len(self.aliases) * 4
        offset = data_start
        table = bytearray()
        for rid, blob in zip(self.ids, self.data):
            table += struct.pack("<HI", rid, offset)
            offset += len(blob)
        table += struct.pack("<HI", 0, offset)  # sentinel

        out += table
        for a in self.aliases:
            out += struct.pack("<HH", *a)
        for blob in self.data:
            out += blob

        tmp = path + ".tmp"
        with open(tmp, "wb") as f:
            f.write(out)
        os.replace(tmp, path)


# --------------------------------------------------------------------------- #
#  Color handling
# --------------------------------------------------------------------------- #
def rgb_to_hsv_arr(rgb):
    """rgb: float [0..1], shape (..., 3) -> h, s, v in [0..1]"""
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    mx = rgb.max(-1)
    mn = rgb.min(-1)
    d = mx - mn
    nz = d > 1e-9
    safe_d = np.where(nz, d, 1)
    rc = np.where(nz, (mx - r) / safe_d, 0)
    gc = np.where(nz, (mx - g) / safe_d, 0)
    bc = np.where(nz, (mx - b) / safe_d, 0)
    h = np.where(mx == r, bc - gc, np.where(mx == g, 2.0 + rc - bc, 4.0 + gc - rc))
    h = (h / 6.0) % 1.0
    h = np.where(nz, h, 0)
    s = np.where(mx > 1e-9, d / np.where(mx > 1e-9, mx, 1), 0)
    return h, s, mx


def hsv_to_rgb_arr(h, s, v):
    i = np.floor(h * 6).astype(int) % 6
    f = h * 6 - np.floor(h * 6)
    p = v * (1 - s)
    q = v * (1 - f * s)
    t = v * (1 - (1 - f) * s)
    r = np.choose(i, [v, q, p, p, t, v])
    g = np.choose(i, [t, v, v, q, p, p])
    b = np.choose(i, [p, p, t, v, v, q])
    return np.stack([r, g, b], -1)


def yellow_mask(h, s, v, hue_min, hue_max, min_sat):
    deg = h * 360.0
    return (deg >= hue_min) & (deg <= hue_max) & (s >= min_sat) & (v >= 0.3)


def analyze(png_bytes, args):
    """Return (img, arr, hsv, mask, share), or None if the image doesn't qualify."""
    try:
        img = Image.open(io.BytesIO(png_bytes))
        img.load()
    except Exception:
        return None
    if max(img.size) > args.max_size or min(img.size) < args.min_size:
        return None
    img = img.convert("RGBA")
    arr = np.asarray(img).astype(np.float32) / 255.0
    opaque = arr[..., 3] > 0.1
    if opaque.sum() < 20:
        return None
    h, s, v = rgb_to_hsv_arr(arr[..., :3])
    ym = yellow_mask(h, s, v, args.hue_min, args.hue_max, args.min_sat) & opaque
    share = ym.sum() / opaque.sum()
    if share < args.min_share:
        return None
    return img, arr, (h, s, v), ym, share


def recolor(arr, hsv, mask, args):
    h, s, v = hsv
    nh = np.where(mask, args.target_hue / 360.0, h)
    ns = np.where(mask, np.clip(s * args.sat_scale, 0, 1), s)
    nv = np.where(mask, np.clip(v * args.val_scale, 0, 1), v)
    rgb = hsv_to_rgb_arr(nh, ns, nv)
    out = np.concatenate([rgb, arr[..., 3:4]], -1)
    out = (np.clip(out, 0, 1) * 255 + 0.5).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def to_png(img):
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
#  Main logic
# --------------------------------------------------------------------------- #
def find_app_dir(path):
    """Accept the folder containing the .pak files, or a parent folder
    (in which case the newest matching subfolder is used)."""
    if os.path.isfile(os.path.join(path, PAK_FILES[0])):
        return path
    best = None
    for root, _dirs, files in os.walk(path):
        if PAK_FILES[0] in files:
            best = root if best is None or root > best else best
    return best


def process(pak_path, args):
    pak = Pak(pak_path)
    only = set(args.only) if args.only else None
    skip = set(args.skip) if args.skip else set()
    hits = []
    for idx, (rid, blob) in enumerate(zip(pak.ids, pak.data)):
        if not blob.startswith(PNG_SIG):
            continue
        if only is not None and rid not in only:
            continue
        if rid in skip:
            continue
        res = analyze(blob, args)
        if res is None:
            continue
        img, arr, hsv, ym, share = res
        hits.append((idx, rid, img, arr, hsv, ym, share))

    name = os.path.basename(pak_path)
    print(f"\n== {name}: candidates found: {len(hits)}")
    for idx, rid, img, arr, hsv, ym, share in hits:
        print(f"   id={rid:<6} {img.size[0]}x{img.size[1]:<4} yellow: {share:5.0%}")

    if args.export:
        os.makedirs(args.export, exist_ok=True)
        base = os.path.splitext(name)[0]
        for idx, rid, img, arr, hsv, ym, share in hits:
            img.save(os.path.join(args.export, f"{base}_{rid}_orig.png"))
            recolor(arr, hsv, ym, args).save(
                os.path.join(args.export, f"{base}_{rid}_new.png"))
        print(f"   previews saved to: {args.export}")

    if args.list or args.export or not hits:
        return 0

    # Backup (the original is never overwritten once it exists)
    bak = pak_path + ".orig"
    if not os.path.exists(bak):
        shutil.copy2(pak_path, bak)
        print(f"   backup: {bak}")

    for idx, rid, img, arr, hsv, ym, share in hits:
        pak.data[idx] = to_png(recolor(arr, hsv, ym, args))
    pak.save(pak_path)
    print(f"   written: {pak_path}")
    return len(hits)


def restore(app_dir):
    for n in PAK_FILES:
        p = os.path.join(app_dir, n)
        bak = p + ".orig"
        if os.path.exists(bak):
            shutil.copy2(bak, p)
            print(f"restored {n}")
        else:
            print(f"no backup for {n}")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path", help="Thorium folder containing the .pak files (or a parent folder)")
    ap.add_argument("--list", action="store_true",
                    help="only list the icons that would be changed; modify nothing")
    ap.add_argument("--export", metavar="DIR",
                    help="save before/after previews to DIR; do not modify .pak files")
    ap.add_argument("--restore", action="store_true",
                    help="restore the original .pak files from their *.orig backups")
    ap.add_argument("--only", type=int, nargs="*", help="process only these resource IDs")
    ap.add_argument("--skip", type=int, nargs="*", help="skip these resource IDs")
    # detection parameters
    ap.add_argument("--hue-min", type=float, default=35, help="min yellow hue, degrees (35)")
    ap.add_argument("--hue-max", type=float, default=65, help="max yellow hue, degrees (65)")
    ap.add_argument("--min-sat", type=float, default=0.35, help="min saturation (0.35)")
    ap.add_argument("--min-share", type=float, default=0.6,
                    help="min fraction of yellow pixels in an image (0.6)")
    ap.add_argument("--max-size", type=int, default=40,
                    help="max image side in px (40: covers 16 px and 32 px folders)")
    ap.add_argument("--min-size", type=int, default=12, help="min image side in px (12)")
    # result parameters
    ap.add_argument("--target-hue", type=float, default=212, help="target hue, degrees (212)")
    ap.add_argument("--sat-scale", type=float, default=0.55,
                    help="saturation multiplier; lower = paler (0.55)")
    ap.add_argument("--val-scale", type=float, default=0.95, help="brightness multiplier (0.95)")
    args = ap.parse_args()

    app_dir = find_app_dir(args.path)
    if not app_dir:
        sys.exit(f"{PAK_FILES[0]} not found in {args.path}")
    print(f"Browser folder: {app_dir}")

    if args.restore:
        restore(app_dir)
        return

    total = 0
    for n in PAK_FILES:
        p = os.path.join(app_dir, n)
        if os.path.isfile(p):
            total += process(p, args)
        else:
            print(f"{n}: not found, skipping")
    if not (args.list or args.export):
        print(f"\nDone. Icons recolored: {total}. Restart Thorium.")


if __name__ == "__main__":
    main()
