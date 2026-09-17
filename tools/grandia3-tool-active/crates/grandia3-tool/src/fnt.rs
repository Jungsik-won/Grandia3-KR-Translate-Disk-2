use std::fs;
use std::path::Path;

use anyhow::{Context, Result, ensure};
use serde::Serialize;
use sha2::{Digest, Sha256};

const HEADER_SIZE: usize = 0x20;
const BITS_PER_PIXEL: usize = 4;
const ATLAS_COLUMNS: usize = 64;
const ATLAS_GUTTER: usize = 1;

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub file_size: usize,
    pub sha256: String,
    pub bitmap_offset: usize,
    pub metadata_offset: usize,
    pub glyph_count: usize,
    pub field_0a: u16,
    pub field_0c: u16,
    pub field_0e: u16,
    pub cell_width: usize,
    pub cell_height: usize,
    pub field_12: u8,
    pub field_13: u8,
    pub bits_per_pixel: usize,
    pub bytes_per_glyph: usize,
    pub metadata_sha256: String,
    pub bitmap_sha256: String,
}

struct Parsed {
    bytes: Vec<u8>,
    report: Report,
}

pub fn inspect(path: &Path) -> Result<Report> {
    Ok(parse_file(path)?.report)
}

pub fn render_pgm(path: &Path) -> Result<Vec<u8>> {
    let parsed = parse_file(path)?;
    let report = &parsed.report;
    let columns = ATLAS_COLUMNS.min(report.glyph_count);
    let rows = report.glyph_count.div_ceil(columns);
    let width = columns * (report.cell_width + ATLAS_GUTTER) - ATLAS_GUTTER;
    let height = rows * (report.cell_height + ATLAS_GUTTER) - ATLAS_GUTTER;
    let mut pixels = vec![0_u8; width * height];
    let bitmap = &parsed.bytes[report.bitmap_offset..];

    for glyph_index in 0..report.glyph_count {
        let glyph_offset = glyph_index * report.bytes_per_glyph;
        let glyph = &bitmap[glyph_offset..glyph_offset + report.bytes_per_glyph];
        let origin_x = (glyph_index % columns) * (report.cell_width + ATLAS_GUTTER);
        let origin_y = (glyph_index / columns) * (report.cell_height + ATLAS_GUTTER);
        for pixel_index in 0..report.cell_width * report.cell_height {
            let packed = glyph[pixel_index / 2];
            let value = if pixel_index.is_multiple_of(2) {
                packed & 0x0f
            } else {
                packed >> 4
            };
            let x = origin_x + pixel_index % report.cell_width;
            let y = origin_y + pixel_index / report.cell_width;
            pixels[y * width + x] = value * 17;
        }
    }

    let mut pgm = format!("P5\n{width} {height}\n255\n").into_bytes();
    pgm.extend_from_slice(&pixels);
    Ok(pgm)
}

fn parse_file(path: &Path) -> Result<Parsed> {
    let bytes = fs::read(path).with_context(|| format!("failed to read {}", path.display()))?;
    parse(bytes).with_context(|| format!("invalid FNT structure in {}", path.display()))
}

fn parse(bytes: Vec<u8>) -> Result<Parsed> {
    ensure!(bytes.len() >= HEADER_SIZE, "FNT is smaller than its header");
    let bitmap_offset = read_u32(&bytes, 0)? as usize;
    let metadata_offset = read_u32(&bytes, 4)? as usize;
    let glyph_count = read_u16(&bytes, 8)? as usize;
    let field_0a = read_u16(&bytes, 10)?;
    let field_0c = read_u16(&bytes, 12)?;
    let field_0e = read_u16(&bytes, 14)?;
    let cell_width = usize::from(bytes[16]);
    let cell_height = usize::from(bytes[17]);
    let field_12 = bytes[18];
    let field_13 = bytes[19];

    ensure!(
        metadata_offset == HEADER_SIZE,
        "unexpected FNT metadata offset"
    );
    ensure!(glyph_count > 0, "FNT has no glyphs");
    ensure!(cell_width > 0 && cell_height > 0, "FNT has an empty cell");
    ensure!(
        (cell_width * cell_height).is_multiple_of(2),
        "FNT 4bpp cell has a fractional byte"
    );
    ensure!(
        bitmap_offset == metadata_offset + glyph_count * 2,
        "FNT bitmap offset differs from the glyph metadata boundary"
    );
    let bytes_per_glyph = cell_width * cell_height * BITS_PER_PIXEL / 8;
    ensure!(
        bytes.len() == bitmap_offset + glyph_count * bytes_per_glyph,
        "FNT bitmap length differs from its glyph geometry"
    );

    let report = Report {
        schema_version: 1,
        file_size: bytes.len(),
        sha256: format!("{:x}", Sha256::digest(&bytes)),
        bitmap_offset,
        metadata_offset,
        glyph_count,
        field_0a,
        field_0c,
        field_0e,
        cell_width,
        cell_height,
        field_12,
        field_13,
        bits_per_pixel: BITS_PER_PIXEL,
        bytes_per_glyph,
        metadata_sha256: format!(
            "{:x}",
            Sha256::digest(&bytes[metadata_offset..bitmap_offset])
        ),
        bitmap_sha256: format!("{:x}", Sha256::digest(&bytes[bitmap_offset..])),
    };
    Ok(Parsed { bytes, report })
}

fn read_u16(bytes: &[u8], offset: usize) -> Result<u16> {
    let value = bytes
        .get(offset..offset + 2)
        .context("truncated FNT integer")?;
    Ok(u16::from_le_bytes(value.try_into().unwrap()))
}

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32> {
    let value = bytes
        .get(offset..offset + 4)
        .context("truncated FNT integer")?;
    Ok(u32::from_le_bytes(value.try_into().unwrap()))
}

#[cfg(test)]
mod tests {
    use super::{HEADER_SIZE, parse};

    #[test]
    fn parses_exact_four_bit_glyph_storage() {
        let glyph_count = 2_u16;
        let bitmap_offset = HEADER_SIZE + usize::from(glyph_count) * 2;
        let mut bytes = vec![0; bitmap_offset + 4];
        bytes[0..4].copy_from_slice(&(bitmap_offset as u32).to_le_bytes());
        bytes[4..8].copy_from_slice(&(HEADER_SIZE as u32).to_le_bytes());
        bytes[8..10].copy_from_slice(&glyph_count.to_le_bytes());
        bytes[16] = 2;
        bytes[17] = 2;

        let parsed = parse(bytes).unwrap();

        assert_eq!(parsed.report.glyph_count, 2);
        assert_eq!(parsed.report.bytes_per_glyph, 2);
    }

    #[test]
    fn rejects_bitmap_length_mismatch() {
        let mut bytes = vec![0; HEADER_SIZE];
        bytes[0..4].copy_from_slice(&(HEADER_SIZE as u32).to_le_bytes());
        bytes[4..8].copy_from_slice(&(HEADER_SIZE as u32).to_le_bytes());
        bytes[8..10].copy_from_slice(&1_u16.to_le_bytes());
        bytes[16] = 8;
        bytes[17] = 8;

        assert!(parse(bytes).is_err());
    }
}
