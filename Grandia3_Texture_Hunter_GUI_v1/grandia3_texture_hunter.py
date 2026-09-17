#!/usr/bin/env python3
# Grandia III Texture Hunter
# Scans Grandia III MDT/MDZ/DAT/BIN files for GTXD/TEX1 texture resources.
# MDZ is unpacked internally. PNG output is a DIAGNOSTIC raw 4bpp preview:
# it is useful for locating images, but is not yet a lossless GTXD PS2-swizzle decoder.

from __future__ import annotations
from pathlib import Path
import argparse, csv, json, struct, sys

try:
    from PIL import Image, ImageOps, ImageDraw
except ImportError:
    raise SystemExit("Pillow is required:  pip install pillow")

# ---------------------------------------------------------------------------
# Grandia III MDZ unpacker (LZH static, dicbit=15)
# ---------------------------------------------------------------------------

NC = 510
NT = 19
CBIT = 9
TBIT = 5

class BitReader:
    def __init__(self, data: bytes):
        self.data = data
        self.bit = 0

    def get(self, n: int) -> int:
        v = 0
        for _ in range(n):
            if self.bit >= len(self.data) * 8:
                raise EOFError("unexpected end of compressed stream")
            v = (v << 1) | ((self.data[self.bit >> 3] >> (7 - (self.bit & 7))) & 1)
            self.bit += 1
        return v

    def peek(self, n: int) -> int:
        pos = self.bit
        v = self.get(n)
        self.bit = pos
        return v

def canonical(lengths):
    max_len = max(lengths) if lengths else 0
    count = [0] * (max_len + 1)
    for length in lengths:
        if length:
            count[length] += 1
    code = 0
    next_code = [0] * (max_len + 1)
    for bits in range(1, max_len + 1):
        code = (code + count[bits - 1]) << 1
        next_code[bits] = code
    mapping = {}
    for symbol, length in enumerate(lengths):
        if length:
            mapping[(length, next_code[length])] = symbol
            next_code[length] += 1
    return mapping, max_len

def decode_symbol(br, huff):
    if huff[0] == "single":
        return huff[1]
    mapping, max_len = huff[1]
    code = 0
    for length in range(1, max_len + 1):
        code = (code << 1) | br.get(1)
        symbol = mapping.get((length, code))
        if symbol is not None:
            return symbol
    raise ValueError("invalid Huffman code")

class LZHStatic:
    def __init__(self, data, dicbit=15):
        self.br = BitReader(data)
        self.dicbit = dicbit
        self.np = dicbit + 1
        self.pbit = 4 if dicbit <= 13 else 5
        self.block_remaining = 0

    def read_pt(self, nn, nbit, special):
        n = self.br.get(nbit)
        lengths = [0] * nn
        if n == 0:
            return ("single", self.br.get(nbit)), lengths
        i = 0
        while i < min(n, nn):
            c = self.br.peek(3)
            if c != 7:
                self.br.get(3)
            else:
                k = 0
                while self.br.peek(4 + k) & 1:
                    k += 1
                c = 7 + k
                self.br.get(c - 3)
            lengths[i] = c
            i += 1
            if i == special:
                zeros = self.br.get(2)
                while zeros > 0 and i < nn:
                    lengths[i] = 0
                    i += 1
                    zeros -= 1
        return ("huff", canonical(lengths)), lengths

    def read_c(self, pt):
        n = self.br.get(CBIT)
        lengths = [0] * NC
        if n == 0:
            return ("single", self.br.get(CBIT)), lengths
        i = 0
        while i < min(n, NC):
            c = decode_symbol(self.br, pt)
            if c <= 2:
                if c == 0:
                    zeros = 1
                elif c == 1:
                    zeros = self.br.get(4) + 3
                else:
                    zeros = self.br.get(CBIT) + 20
                while zeros > 0 and i < NC:
                    lengths[i] = 0
                    i += 1
                    zeros -= 1
            else:
                lengths[i] = c - 2
                i += 1
        return ("huff", canonical(lengths)), lengths

    def new_block(self):
        self.block_remaining = self.br.get(16)
        self.pt, _ = self.read_pt(NT, TBIT, 3)
        self.ch, _ = self.read_c(self.pt)
        self.ph, _ = self.read_pt(self.np, self.pbit, -1)

    def decode_c(self):
        if self.block_remaining == 0:
            self.new_block()
        self.block_remaining -= 1
        return decode_symbol(self.br, self.ch)

    def decode_p(self):
        j = decode_symbol(self.br, self.ph)
        if j:
            j = (1 << (j - 1)) + self.br.get(j - 1)
        return j

    def decompress(self, expected_size):
        out = bytearray()
        while len(out) < expected_size:
            c = self.decode_c()
            if c < 256:
                out.append(c)
            else:
                length = c - 256 + 3
                distance = self.decode_p() + 1
                for _ in range(length):
                    if len(out) >= expected_size:
                        break
                    out.append(out[-distance] if distance <= len(out) else 0x20)
        return bytes(out)

def unpack_mdz(raw: bytes) -> bytes:
    if len(raw) < 32:
        raise ValueError("MDZ too small")
    header_size = struct.unpack_from("<H", raw, 0)[0]
    packed_size = struct.unpack_from("<I", raw, 7)[0]
    original_size = struct.unpack_from("<I", raw, 11)[0]
    stream = raw[header_size:header_size + packed_size]
    return LZHStatic(stream, dicbit=15).decompress(original_size)

# ---------------------------------------------------------------------------
# Resource scan / extraction
# ---------------------------------------------------------------------------

MARKERS = (b"GTXD", b"TEX1", b"GMDL", b"GMTD", b"POF0", b"GPMT", b"gccM")

def find_all(data: bytes, marker: bytes):
    out = []
    p = 0
    while True:
        p = data.find(marker, p)
        if p < 0:
            break
        out.append(p)
        p += 1
    return out

def printable_name_near(data: bytes, off: int, radius=192):
    a = max(0, off - radius)
    b = min(len(data), off + radius)
    chunk = data[a:b]
    candidates = []
    cur = bytearray()
    for x in chunk:
        if 0x20 <= x <= 0x7E:
            cur.append(x)
        else:
            if len(cur) >= 4:
                try:
                    candidates.append(cur.decode("ascii"))
                except Exception:
                    pass
            cur.clear()
    if len(cur) >= 4:
        try:
            candidates.append(cur.decode("ascii"))
        except Exception:
            pass
    if not candidates:
        return ""
    # Favor texture-ish names.
    candidates.sort(key=lambda s: (
        not any(k in s.lower() for k in ("face", "demo", "tex", "window", "icon", "menu", "plane", "eff")),
        -len(s)
    ))
    return candidates[0][:80]

def resource_ranges(data: bytes):
    hits = []
    for marker in MARKERS:
        for off in find_all(data, marker):
            hits.append((off, marker.decode("ascii")))
    hits.sort()

    rows = []
    for i, (off, kind) in enumerate(hits):
        end = hits[i+1][0] if i+1 < len(hits) else len(data)
        # Keep a sane lower bound; false embedded markers sometimes occur.
        if end <= off:
            continue
        rows.append({
            "kind": kind,
            "offset": off,
            "end": end,
            "size": end - off,
            "near_name": printable_name_near(data, off),
        })
    return rows

def save_raw_4bpp_preview(payload: bytes, out_png: Path, width_px=256, skip=0, max_bytes=262144):
    """Diagnostic only: expand nibbles to grayscale pixels."""
    payload = payload[skip:skip+max_bytes]
    if not payload:
        return False
    pix = bytearray()
    for v in payload:
        pix.append((v & 0x0F) * 17)
        pix.append(((v >> 4) & 0x0F) * 17)
    height = len(pix) // width_px
    if height < 1:
        return False
    pix = pix[:width_px * height]
    img = Image.frombytes("L", (width_px, height), bytes(pix))
    img.save(out_png)
    return True

def make_contact_sheet(images, labels, out_path: Path):
    if not images:
        return
    thumbs = []
    for p in images:
        try:
            im = Image.open(p).convert("L")
            im.thumbnail((320, 220))
            thumbs.append(im.copy())
        except Exception:
            pass
    if not thumbs:
        return
    cols = 3
    cell_w, cell_h = 340, 260
    rows = (len(thumbs) + cols - 1) // cols
    sheet = Image.new("L", (cols*cell_w, rows*cell_h), 255)
    d = ImageDraw.Draw(sheet)
    for i, im in enumerate(thumbs):
        x = (i % cols) * cell_w + 10
        y = (i // cols) * cell_h + 26
        sheet.paste(im, (x, y))
        d.text((x, 6 + (i // cols) * cell_h), labels[i][:42], fill=0)
    sheet.save(out_path)

def process_file(path: Path, out_root: Path, dump_raw=True, previews=True):
    raw = path.read_bytes()
    was_mdz = path.suffix.lower() == ".mdz"

    if was_mdz:
        try:
            data = unpack_mdz(raw)
        except Exception as e:
            print(f"[FAIL] MDZ unpack: {path}: {e}")
            return []
    else:
        data = raw

    rel_name = path.name
    stem = path.stem
    dst = out_root / stem
    dst.mkdir(parents=True, exist_ok=True)

    if was_mdz:
        (dst / f"{stem}.MDT").write_bytes(data)

    rows = resource_ranges(data)
    texture_rows = [r for r in rows if r["kind"] in ("GTXD", "TEX1")]

    # full marker index
    with (dst / "resources.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["kind","offset_hex","end_hex","size","near_name","raw_file"])
        w.writeheader()
        for n, r in enumerate(rows):
            raw_file = ""
            if dump_raw and r["kind"] in ("GTXD","TEX1"):
                raw_file = f"{n:03d}_{r['kind']}_{r['offset']:08X}.bin"
                (dst / raw_file).write_bytes(data[r["offset"]:r["end"]])
            w.writerow({
                "kind": r["kind"],
                "offset_hex": f"0x{r['offset']:08X}",
                "end_hex": f"0x{r['end']:08X}",
                "size": r["size"],
                "near_name": r["near_name"],
                "raw_file": raw_file,
            })

    preview_paths = []
    preview_labels = []

    if previews:
        # We deliberately try several common widths and payload skips.
        # These are visual probes, not authoritative decoding.
        for idx, r in enumerate(texture_rows):
            chunk = data[r["offset"]:r["end"]]
            for skip in (0x10, 0x20, 0x40, 0x80):
                for width in (64, 128, 256, 512):
                    name = f"{idx:03d}_{r['kind']}_{r['offset']:08X}_s{skip:02X}_w{width}.png"
                    p = dst / name
                    if save_raw_4bpp_preview(chunk, p, width_px=width, skip=skip):
                        preview_paths.append(p)
                        preview_labels.append(name)

        # Contact sheet can get huge, so only first 60 previews.
        make_contact_sheet(preview_paths[:60], preview_labels[:60], dst / "_contact_sheet_first60.png")

    summary = {
        "source": str(path),
        "input_size": len(raw),
        "unpacked_size": len(data),
        "marker_counts": {m.decode("ascii"): len(find_all(data, m)) for m in MARKERS},
        "texture_count": len(texture_rows),
        "note": "PNG previews are raw 4bpp diagnostic probes, not final PS2 GTXD/TEX1 decoding."
    }
    (dst / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[OK] {path.name}: GTXD={summary['marker_counts']['GTXD']} TEX1={summary['marker_counts']['TEX1']} -> {dst}")
    return rows

def collect_inputs(inp: Path):
    if inp.is_file():
        return [inp]
    exts = {".mdz",".mdt",".dat",".bin"}
    return sorted(p for p in inp.rglob("*") if p.is_file() and p.suffix.lower() in exts)

def main():
    ap = argparse.ArgumentParser(
        description="Grandia III texture resource hunter (GTXD/TEX1 scanner + diagnostic PNG previews)"
    )
    ap.add_argument("input", help="MDZ/MDT/DAT/BIN file, or a directory")
    ap.add_argument("-o", "--output", default="texture_hunt", help="output directory")
    ap.add_argument("--no-raw", action="store_true", help="do not dump GTXD/TEX1 raw chunks")
    ap.add_argument("--no-preview", action="store_true", help="do not make diagnostic PNG previews")
    args = ap.parse_args()

    inp = Path(args.input)
    if not inp.exists():
        raise SystemExit(f"not found: {inp}")

    out_root = Path(args.output)
    out_root.mkdir(parents=True, exist_ok=True)

    inputs = collect_inputs(inp)
    if not inputs:
        raise SystemExit("No MDZ/MDT/DAT/BIN files found.")

    print(f"Scanning {len(inputs)} file(s)...")
    total = {"GTXD":0, "TEX1":0}
    for p in inputs:
        try:
            rows = process_file(p, out_root, dump_raw=not args.no_raw, previews=not args.no_preview)
            for r in rows:
                if r["kind"] in total:
                    total[r["kind"]] += 1
        except Exception as e:
            print(f"[FAIL] {p}: {e}")

    print()
    print(f"DONE: GTXD={total['GTXD']} TEX1={total['TEX1']}")
    print(f"Output: {out_root.resolve()}")
    print("Open each _contact_sheet_first60.png first.")
    print("Important: previews are diagnostic raw 4bpp views; PS2 swizzle/CLUT decoding is the next step.")

if __name__ == "__main__":
    main()
