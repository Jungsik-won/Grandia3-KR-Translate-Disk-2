use std::collections::{HashMap, HashSet};
use std::fs;
use std::path::Path;

use anyhow::{Context, Result, bail, ensure};
use serde::Serialize;
use sha2::{Digest, Sha256};

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub file_size: usize,
    pub sha256: String,
    pub font: String,
    pub family_name: String,
    pub font_version: String,
    pub declared_glyph_count: usize,
    pub unencoded_glyph_count: usize,
    pub codepoint: String,
    pub glyph_name: String,
    pub device_width: i32,
    pub bounding_box: BoundingBox,
    pub target_cell: Cell,
    pub game_4bpp_size: usize,
    pub game_4bpp_sha256: String,
}

#[derive(Clone, Copy, Debug, Serialize)]
pub struct BoundingBox {
    pub width: usize,
    pub height: usize,
    pub x_offset: i32,
    pub y_offset: i32,
}

#[derive(Clone, Copy, Debug, Serialize)]
pub struct Cell {
    pub width: usize,
    pub height: usize,
}

pub struct Inspection {
    pub report: Report,
    pub pgm: Vec<u8>,
    pub game_4bpp: Vec<u8>,
}

struct Glyph {
    name: String,
    device_width: i32,
    bounding_box: BoundingBox,
    rows: Vec<Vec<u8>>,
}

pub fn inspect(
    path: &Path,
    expected_sha256: &str,
    codepoint: u32,
    target_cell: Cell,
) -> Result<Inspection> {
    let bytes = fs::read(path).with_context(|| format!("failed to read BDF {}", path.display()))?;
    let sha256 = format!("{:x}", Sha256::digest(&bytes));
    ensure!(
        sha256.eq_ignore_ascii_case(expected_sha256),
        "BDF SHA-256 mismatch: expected {expected_sha256}, found {sha256}"
    );
    let text = std::str::from_utf8(&bytes).context("BDF is not valid UTF-8")?;
    parse(text, bytes.len(), sha256, codepoint, target_cell)
        .with_context(|| format!("invalid BDF structure in {}", path.display()))
}

pub fn render_game_4bpp_many(
    path: &Path,
    expected_sha256: &str,
    codepoints: &[u32],
    target_cell: Cell,
) -> Result<HashMap<u32, Vec<u8>>> {
    ensure!(!codepoints.is_empty(), "no BDF codepoints requested");
    ensure!(
        target_cell.width > 0 && target_cell.height > 0,
        "empty target cell"
    );
    let requested: HashSet<_> = codepoints.iter().copied().collect();
    let bytes = fs::read(path).with_context(|| format!("failed to read BDF {}", path.display()))?;
    let sha256 = format!("{:x}", Sha256::digest(&bytes));
    ensure!(
        sha256.eq_ignore_ascii_case(expected_sha256),
        "BDF SHA-256 mismatch: expected {expected_sha256}, found {sha256}"
    );
    let text = std::str::from_utf8(&bytes).context("BDF is not valid UTF-8")?;
    let lines: Vec<_> = text.lines().collect();
    validate_document(&lines)?;

    let mut rendered = HashMap::with_capacity(requested.len());
    let mut index = 0;
    while index < lines.len() {
        let Some(name) = lines[index].strip_prefix("STARTCHAR ") else {
            index += 1;
            continue;
        };
        let start = index;
        let end = lines[start..]
            .iter()
            .position(|line| *line == "ENDCHAR")
            .map(|relative| start + relative)
            .context("BDF glyph has no ENDCHAR marker")?;
        let block = &lines[start + 1..end];
        let encoding = value_after(block, "ENCODING ")?
            .parse::<i64>()
            .context("invalid BDF ENCODING")?;
        if encoding >= 0 {
            let codepoint = encoding as u32;
            if requested.contains(&codepoint) {
                let glyph = parse_glyph(name, block)?;
                let pixels = rasterize(&glyph, target_cell)?;
                ensure!(
                    rendered
                        .insert(codepoint, pack_game_4bpp(&pixels)?)
                        .is_none(),
                    "duplicate BDF glyph for U+{codepoint:04X}"
                );
            }
        }
        index = end + 1;
    }
    for codepoint in requested {
        ensure!(
            rendered.contains_key(&codepoint),
            "BDF has no glyph for U+{codepoint:04X}"
        );
    }
    Ok(rendered)
}

fn parse(
    text: &str,
    file_size: usize,
    sha256: String,
    codepoint: u32,
    target_cell: Cell,
) -> Result<Inspection> {
    ensure!(
        target_cell.width > 0 && target_cell.height > 0,
        "empty target cell"
    );
    let lines: Vec<_> = text.lines().collect();
    let (declared_glyph_count, unencoded_glyph_count) = validate_document(&lines)?;

    let font = value_after(&lines, "FONT ")?.to_owned();
    let family_name = quoted_property(&lines, "FAMILY_NAME ")?;
    let font_version = quoted_property(&lines, "FONT_VERSION ")?;

    let glyph = find_glyph(&lines, codepoint)?;
    let pixels = rasterize(&glyph, target_cell)?;
    let game_4bpp = pack_game_4bpp(&pixels)?;
    let game_4bpp_sha256 = format!("{:x}", Sha256::digest(&game_4bpp));
    let mut pgm = format!("P5\n{} {}\n255\n", target_cell.width, target_cell.height).into_bytes();
    pgm.extend(pixels.iter().map(|&pixel| if pixel { 255 } else { 0 }));

    Ok(Inspection {
        report: Report {
            schema_version: 1,
            file_size,
            sha256,
            font,
            family_name,
            font_version,
            declared_glyph_count,
            unencoded_glyph_count,
            codepoint: format!("U+{codepoint:04X}"),
            glyph_name: glyph.name,
            device_width: glyph.device_width,
            bounding_box: glyph.bounding_box,
            target_cell,
            game_4bpp_size: game_4bpp.len(),
            game_4bpp_sha256,
        },
        pgm,
        game_4bpp,
    })
}

fn validate_document(lines: &[&str]) -> Result<(usize, usize)> {
    ensure!(
        lines.first() == Some(&"STARTFONT 2.1"),
        "unsupported BDF version"
    );
    ensure!(
        lines.last() == Some(&"ENDFONT"),
        "BDF has no ENDFONT marker"
    );

    let declared_glyph_count = value_after(lines, "CHARS ")?
        .parse::<usize>()
        .context("invalid BDF CHARS value")?;
    let startchar_count = lines
        .iter()
        .filter(|line| line.starts_with("STARTCHAR "))
        .count();
    let encodings = lines
        .iter()
        .filter_map(|line| line.strip_prefix("ENCODING "))
        .map(str::parse::<i64>)
        .collect::<std::result::Result<Vec<_>, _>>()
        .context("invalid BDF ENCODING value")?;
    ensure!(
        encodings.len() == startchar_count,
        "not every BDF glyph has one ENCODING field"
    );
    let actual_glyph_count = encodings.iter().filter(|&&encoding| encoding >= 0).count();
    let unencoded_glyph_count = encodings.len() - actual_glyph_count;
    ensure!(
        actual_glyph_count == declared_glyph_count,
        "BDF CHARS declares {declared_glyph_count}, found {actual_glyph_count} glyphs"
    );

    Ok((declared_glyph_count, unencoded_glyph_count))
}

fn find_glyph(lines: &[&str], codepoint: u32) -> Result<Glyph> {
    let mut index = 0;
    while index < lines.len() {
        let Some(name) = lines[index].strip_prefix("STARTCHAR ") else {
            index += 1;
            continue;
        };
        let start = index;
        let end = lines[start..]
            .iter()
            .position(|line| *line == "ENDCHAR")
            .map(|relative| start + relative)
            .context("BDF glyph has no ENDCHAR marker")?;
        let block = &lines[start + 1..end];
        let encoding = value_after(block, "ENCODING ")?
            .parse::<i64>()
            .context("invalid BDF ENCODING")?;
        if encoding == i64::from(codepoint) {
            return parse_glyph(name, block);
        }
        index = end + 1;
    }
    bail!("BDF has no glyph for U+{codepoint:04X}")
}

fn parse_glyph(name: &str, block: &[&str]) -> Result<Glyph> {
    let dwidth_values = parse_i32_list(value_after(block, "DWIDTH ")?, 2, "DWIDTH")?;
    ensure!(
        dwidth_values[1] == 0,
        "vertical BDF device width is unsupported"
    );
    let bbx = parse_i32_list(value_after(block, "BBX ")?, 4, "BBX")?;
    ensure!(bbx[0] >= 0 && bbx[1] >= 0, "negative BDF glyph dimensions");
    let bounding_box = BoundingBox {
        width: bbx[0] as usize,
        height: bbx[1] as usize,
        x_offset: bbx[2],
        y_offset: bbx[3],
    };
    let bitmap_index = block
        .iter()
        .position(|line| *line == "BITMAP")
        .context("BDF glyph has no BITMAP marker")?;
    let bitmap_lines = block
        .get(bitmap_index + 1..bitmap_index + 1 + bounding_box.height)
        .context("BDF glyph bitmap has too few rows")?;
    ensure!(
        bitmap_index + 1 + bounding_box.height == block.len(),
        "unexpected data follows BDF glyph bitmap"
    );
    let expected_row_bytes = bounding_box.width.div_ceil(8);
    let mut rows = Vec::with_capacity(bounding_box.height);
    for line in bitmap_lines {
        ensure!(
            line.len() == expected_row_bytes * 2,
            "BDF bitmap row width mismatch"
        );
        rows.push(decode_hex(line)?);
    }
    Ok(Glyph {
        name: name.to_owned(),
        device_width: dwidth_values[0],
        bounding_box,
        rows,
    })
}

fn rasterize(glyph: &Glyph, cell: Cell) -> Result<Vec<bool>> {
    let box_ = glyph.bounding_box;
    let origin_x = box_.x_offset;
    let origin_y = cell.height as i32 - box_.y_offset - box_.height as i32;
    ensure!(
        origin_x >= 0 && origin_y >= 0,
        "BDF glyph begins outside target cell"
    );
    ensure!(
        origin_x as usize + box_.width <= cell.width
            && origin_y as usize + box_.height <= cell.height,
        "BDF glyph exceeds target cell"
    );
    let mut pixels = vec![false; cell.width * cell.height];
    for (row_index, row) in glyph.rows.iter().enumerate() {
        for x in 0..box_.width {
            if row[x / 8] & (0x80 >> (x % 8)) != 0 {
                let target_x = origin_x as usize + x;
                let target_y = origin_y as usize + row_index;
                pixels[target_y * cell.width + target_x] = true;
            }
        }
    }
    Ok(pixels)
}

fn pack_game_4bpp(pixels: &[bool]) -> Result<Vec<u8>> {
    ensure!(
        pixels.len().is_multiple_of(2),
        "4bpp glyph has a fractional byte"
    );
    Ok(pixels
        .chunks_exact(2)
        .map(|pair| (u8::from(pair[0]) * 0x0f) | (u8::from(pair[1]) * 0xf0))
        .collect())
}

fn value_after<'a>(lines: &'a [&str], prefix: &str) -> Result<&'a str> {
    lines
        .iter()
        .find_map(|line| line.strip_prefix(prefix))
        .with_context(|| format!("missing BDF {prefix}field"))
}

fn quoted_property(lines: &[&str], prefix: &str) -> Result<String> {
    let value = value_after(lines, prefix)?;
    let value = value
        .strip_prefix('"')
        .and_then(|value| value.strip_suffix('"'))
        .with_context(|| format!("BDF {prefix}property is not quoted"))?;
    Ok(value.to_owned())
}

fn parse_i32_list(value: &str, count: usize, field: &str) -> Result<Vec<i32>> {
    let values = value
        .split_ascii_whitespace()
        .map(str::parse)
        .collect::<std::result::Result<Vec<i32>, _>>()
        .with_context(|| format!("invalid BDF {field}"))?;
    ensure!(values.len() == count, "BDF {field} field count mismatch");
    Ok(values)
}

fn decode_hex(value: &str) -> Result<Vec<u8>> {
    ensure!(value.len().is_multiple_of(2), "odd BDF bitmap hex length");
    value
        .as_bytes()
        .chunks_exact(2)
        .map(|pair| {
            let text = std::str::from_utf8(pair).unwrap();
            u8::from_str_radix(text, 16).context("invalid BDF bitmap hex")
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use std::fs;

    use sha2::Digest;

    use super::{Cell, parse, render_game_4bpp_many};

    #[test]
    fn parses_and_places_a_bdf_glyph() {
        let input = "STARTFONT 2.1\nFONT test\nFAMILY_NAME \"Test\"\nFONT_VERSION \"1\"\nCHARS 1\nSTARTCHAR U+0041\nENCODING 65\nDWIDTH 3 0\nBBX 2 2 1 0\nBITMAP\n80\nC0\nENDCHAR\nENDFONT\n";
        let inspection = parse(
            input,
            input.len(),
            "hash".to_owned(),
            65,
            Cell {
                width: 4,
                height: 4,
            },
        )
        .unwrap();

        assert_eq!(inspection.report.bounding_box.width, 2);
        assert_eq!(inspection.report.game_4bpp_size, 8);
        assert_eq!(inspection.game_4bpp, [0, 0, 0, 0, 0xf0, 0, 0xf0, 0x0f]);
        assert_eq!(
            &inspection.pgm[11..],
            &[0, 0, 0, 0, 0, 0, 0, 0, 0, 255, 0, 0, 0, 255, 255, 0]
        );
    }

    #[test]
    fn renders_multiple_requested_glyphs_in_one_pass() {
        let input = "STARTFONT 2.1\nFONT test\nFAMILY_NAME \"Test\"\nFONT_VERSION \"1\"\nCHARS 2\nSTARTCHAR U+0041\nENCODING 65\nDWIDTH 3 0\nBBX 2 2 1 0\nBITMAP\n80\nC0\nENDCHAR\nSTARTCHAR U+0042\nENCODING 66\nDWIDTH 3 0\nBBX 2 2 1 0\nBITMAP\nC0\n80\nENDCHAR\nENDFONT\n";
        let path = std::env::temp_dir().join(format!(
            "grandia3-bdf-many-{}-{}.bdf",
            std::process::id(),
            line!()
        ));
        fs::write(&path, input).unwrap();
        let hash = format!("{:x}", sha2::Sha256::digest(input));

        let rendered = render_game_4bpp_many(
            &path,
            &hash,
            &[65, 66, 65],
            Cell {
                width: 4,
                height: 4,
            },
        )
        .unwrap();
        fs::remove_file(path).unwrap();

        assert_eq!(rendered.len(), 2);
        assert_ne!(rendered[&65], rendered[&66]);
    }
}
