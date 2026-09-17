use std::collections::{HashMap, HashSet};
use std::fs::{self, File};
use std::io::Write;
use std::ops::Range;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::bdf::{self, Cell};
use crate::{fnt, skj};

const METADATA_RECORD_SIZE: usize = 2;
const SKJ_LOGICAL_BASE: usize = 32;

#[derive(Debug, Deserialize)]
struct Config {
    schema_version: u32,
    inputs: InputHashes,
    bdf: BdfSources,
    mappings: Vec<MappingConfig>,
    #[serde(default)]
    preserve_skj_codes: bool,
}

#[derive(Debug, Deserialize)]
struct InputHashes {
    main_fnt_sha256: String,
    ruby_fnt_sha256: String,
    skj_sha256: String,
    metrics_sha256: String,
}

#[derive(Debug, Deserialize)]
struct BdfSources {
    main_sha256: String,
    ruby_sha256: String,
}

#[derive(Debug, Deserialize)]
struct MappingConfig {
    character: String,
    code: String,
    glyph_index: usize,
    expected_original_code: String,
    metric_donor_index: usize,
}

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub mapping_count: usize,
    pub preserve_skj_codes: bool,
    pub inputs: Vec<FileHash>,
    pub outputs: Vec<FileHash>,
    pub mappings: Vec<AppliedMapping>,
    pub declared_writes: Vec<DeclaredWrite>,
}

#[derive(Debug, Serialize)]
pub struct DeclaredWrite {
    pub file_name: String,
    pub offset: usize,
    pub size: usize,
    pub purpose: String,
}

#[derive(Debug, Serialize)]
pub struct FileHash {
    pub file_name: String,
    pub size: usize,
    pub sha256: String,
}

#[derive(Debug, Serialize)]
pub struct AppliedMapping {
    pub character: String,
    pub unicode: String,
    pub code: String,
    pub glyph_index: usize,
    pub original_code: String,
    pub metric_donor_index: usize,
    pub main_glyph_sha256: String,
    pub ruby_glyph_sha256: String,
}

pub struct Paths<'a> {
    pub input_dir: &'a Path,
    pub main_bdf: &'a Path,
    pub ruby_bdf: &'a Path,
    pub config: &'a Path,
    pub output_dir: &'a Path,
}

pub fn build(paths: Paths<'_>) -> Result<Report> {
    ensure!(
        !paths.output_dir.exists(),
        "output directory already exists: {}",
        paths.output_dir.display()
    );
    let config_bytes = fs::read(paths.config)
        .with_context(|| format!("failed to read overlay config {}", paths.config.display()))?;
    let config: Config = serde_json::from_slice(&config_bytes)
        .with_context(|| format!("invalid overlay config {}", paths.config.display()))?;
    ensure!(
        config.schema_version == 1,
        "unsupported overlay config schema"
    );
    ensure!(!config.mappings.is_empty(), "font overlay has no mappings");

    let main_path = paths.input_dir.join("GR3BACK.FNT");
    let ruby_path = paths.input_dir.join("RUBY.FNT");
    let skj_path = paths.input_dir.join("RUBY.SKJ");
    let metrics_path = paths.input_dir.join("RUBY.METRICS");
    let mut main = read_exact(&main_path, &config.inputs.main_fnt_sha256)?;
    let mut ruby = read_exact(&ruby_path, &config.inputs.ruby_fnt_sha256)?;
    let mut skj_bytes = read_exact(&skj_path, &config.inputs.skj_sha256)?;
    let mut metrics = read_exact(&metrics_path, &config.inputs.metrics_sha256)?;
    let original_main = main.clone();
    let original_ruby = ruby.clone();
    let original_skj = skj_bytes.clone();
    let original_metrics = metrics.clone();
    let input_hashes = file_hashes(&[
        ("GR3BACK.FNT", &main),
        ("RUBY.FNT", &ruby),
        ("RUBY.SKJ", &skj_bytes),
        ("RUBY.METRICS", &metrics),
    ]);

    let main_report = fnt::inspect(&main_path)?;
    let ruby_report = fnt::inspect(&ruby_path)?;
    ensure!(
        main_report.glyph_count == ruby_report.glyph_count,
        "main and ruby glyph populations differ"
    );
    ensure!(
        metrics.len() == main_report.glyph_count * METADATA_RECORD_SIZE,
        "metric population differs from FNT glyph population"
    );
    let records = skj::records(&skj_path)?;
    ensure!(
        records.len() >= main_report.glyph_count,
        "SKJ has fewer records than the FNT population"
    );

    let mut selected_slots = HashSet::new();
    let mut selected_codes = HashSet::new();
    let mut parsed = Vec::with_capacity(config.mappings.len());
    for mapping in &config.mappings {
        let character = single_hangul(&mapping.character)?;
        let code = parse_korean_code(&mapping.code)?;
        let expected_original_code = parse_hex_u16(&mapping.expected_original_code)?;
        ensure!(
            mapping.glyph_index >= 32 && mapping.glyph_index < main_report.glyph_count,
            "glyph index {} is not a replaceable FNT slot",
            mapping.glyph_index
        );
        ensure!(
            mapping.metric_donor_index < main_report.glyph_count,
            "metric donor index is outside the FNT population"
        );
        ensure!(
            records
                .get(mapping.glyph_index + SKJ_LOGICAL_BASE)
                .is_some_and(|record| record.code == expected_original_code),
            "slot {} original code mismatch",
            mapping.glyph_index
        );
        ensure!(
            selected_slots.insert(mapping.glyph_index),
            "duplicate glyph slot"
        );
        ensure!(selected_codes.insert(code), "duplicate Korean code");
        parsed.push((mapping, character, code, expected_original_code));
    }

    if !config.preserve_skj_codes {
        let selected_record_indices: HashSet<_> = selected_slots
            .iter()
            .map(|index| index + SKJ_LOGICAL_BASE)
            .collect();
        let occupied: HashMap<_, _> = records
            .iter()
            .filter(|record| !selected_record_indices.contains(&record.index))
            .map(|record| (record.code, record.index))
            .collect();
        for (_, _, code, _) in &parsed {
            ensure!(
                !occupied.contains_key(code),
                "Korean code 0x{code:04x} collides with the retained map"
            );
        }
    }

    let codepoints: Vec<_> = parsed
        .iter()
        .map(|(_, character, _, _)| *character as u32)
        .collect();
    let main_glyphs = bdf::render_game_4bpp_many(
        paths.main_bdf,
        &config.bdf.main_sha256,
        &codepoints,
        Cell {
            width: main_report.cell_width,
            height: main_report.cell_height,
        },
    )?;
    let ruby_glyphs = bdf::render_game_4bpp_many(
        paths.ruby_bdf,
        &config.bdf.ruby_sha256,
        &codepoints,
        Cell {
            width: ruby_report.cell_width,
            height: ruby_report.cell_height,
        },
    )?;

    let mut applied = Vec::with_capacity(parsed.len());
    let mut declared_writes = Vec::with_capacity(parsed.len() * 7);
    for (mapping, character, code, original_code) in parsed {
        let main_glyph = &main_glyphs[&(character as u32)];
        let ruby_glyph = &ruby_glyphs[&(character as u32)];
        replace_glyph(&mut main, &main_report, mapping.glyph_index, main_glyph)?;
        replace_glyph(&mut ruby, &ruby_report, mapping.glyph_index, ruby_glyph)?;
        copy_record(
            &mut main,
            main_report.metadata_offset,
            mapping.metric_donor_index,
            mapping.glyph_index,
        )?;
        copy_record(
            &mut ruby,
            ruby_report.metadata_offset,
            mapping.metric_donor_index,
            mapping.glyph_index,
        )?;
        copy_record(
            &mut metrics,
            0,
            mapping.metric_donor_index,
            mapping.glyph_index,
        )?;
        let offset = records[mapping.glyph_index + SKJ_LOGICAL_BASE].file_offset;
        if !config.preserve_skj_codes {
            skj_bytes[offset..offset + 2].copy_from_slice(&code.to_be_bytes());
        }
        declare_mapping_writes(
            &mut declared_writes,
            mapping.glyph_index,
            offset,
            &main_report,
            &ruby_report,
            config.preserve_skj_codes,
        );
        applied.push(AppliedMapping {
            character: character.to_string(),
            unicode: format!("U+{:04X}", character as u32),
            code: format!("0x{code:04x}"),
            glyph_index: mapping.glyph_index,
            original_code: format!("0x{original_code:04x}"),
            metric_donor_index: mapping.metric_donor_index,
            main_glyph_sha256: sha256(main_glyph),
            ruby_glyph_sha256: sha256(ruby_glyph),
        });
    }

    verify_declared_diff(&original_main, &main, &declared_writes, "GR3BACK.FNT")?;
    verify_declared_diff(&original_ruby, &ruby, &declared_writes, "RUBY.FNT")?;
    verify_declared_diff(&original_skj, &skj_bytes, &declared_writes, "RUBY.SKJ")?;
    verify_declared_diff(
        &original_metrics,
        &metrics,
        &declared_writes,
        "RUBY.METRICS",
    )?;

    let output_hashes = file_hashes(&[
        ("GR3BACK.FNT", &main),
        ("RUBY.FNT", &ruby),
        ("RUBY.SKJ", &skj_bytes),
        ("RUBY.METRICS", &metrics),
    ]);
    let report = Report {
        schema_version: 1,
        mapping_count: applied.len(),
        preserve_skj_codes: config.preserve_skj_codes,
        inputs: input_hashes,
        outputs: output_hashes,
        mappings: applied,
        declared_writes,
    };
    publish(
        paths.output_dir,
        &main,
        &ruby,
        &skj_bytes,
        &metrics,
        &report,
    )?;
    Ok(report)
}

fn declare_mapping_writes(
    writes: &mut Vec<DeclaredWrite>,
    index: usize,
    skj_offset: usize,
    main: &fnt::Report,
    ruby: &fnt::Report,
    preserve_skj_codes: bool,
) {
    let mut mapping_writes = vec![
        (
            "GR3BACK.FNT",
            main.metadata_offset + index * 2,
            2,
            "main glyph metadata",
        ),
        (
            "GR3BACK.FNT",
            main.bitmap_offset + index * main.bytes_per_glyph,
            main.bytes_per_glyph,
            "main glyph bitmap",
        ),
        (
            "RUBY.FNT",
            ruby.metadata_offset + index * 2,
            2,
            "ruby glyph metadata",
        ),
        (
            "RUBY.FNT",
            ruby.bitmap_offset + index * ruby.bytes_per_glyph,
            ruby.bytes_per_glyph,
            "ruby glyph bitmap",
        ),
        ("RUBY.METRICS", index * 2, 2, "paired glyph metrics"),
    ];
    if !preserve_skj_codes {
        mapping_writes.push(("RUBY.SKJ", skj_offset, 2, "character code record"));
    }
    for (file_name, offset, size, purpose) in mapping_writes {
        writes.push(DeclaredWrite {
            file_name: file_name.to_owned(),
            offset,
            size,
            purpose: purpose.to_owned(),
        });
    }
}

fn verify_declared_diff(
    original: &[u8],
    output: &[u8],
    writes: &[DeclaredWrite],
    file_name: &str,
) -> Result<()> {
    ensure!(original.len() == output.len(), "{file_name} size changed");
    let mut ranges: Vec<Range<usize>> = writes
        .iter()
        .filter(|write| write.file_name == file_name)
        .map(|write| write.offset..write.offset + write.size)
        .collect();
    ranges.sort_by_key(|range| range.start);
    for pair in ranges.windows(2) {
        ensure!(pair[0].end <= pair[1].start, "{file_name} writes overlap");
    }
    for (offset, (before, after)) in original.iter().zip(output).enumerate() {
        if before != after {
            ensure!(
                ranges
                    .iter()
                    .any(|range| range.start <= offset && offset < range.end),
                "undeclared {file_name} change at offset {offset:#x}"
            );
        }
    }
    Ok(())
}

fn replace_glyph(bytes: &mut [u8], report: &fnt::Report, index: usize, glyph: &[u8]) -> Result<()> {
    ensure!(
        glyph.len() == report.bytes_per_glyph,
        "packed glyph size mismatch"
    );
    let start = report.bitmap_offset + index * report.bytes_per_glyph;
    bytes[start..start + glyph.len()].copy_from_slice(glyph);
    Ok(())
}

fn copy_record(bytes: &mut [u8], base: usize, donor: usize, target: usize) -> Result<()> {
    let donor_start = base + donor * METADATA_RECORD_SIZE;
    let target_start = base + target * METADATA_RECORD_SIZE;
    let value: [u8; METADATA_RECORD_SIZE] = bytes[donor_start..donor_start + 2]
        .try_into()
        .context("metric donor exceeds input")?;
    bytes
        .get_mut(target_start..target_start + 2)
        .context("metric target exceeds input")?
        .copy_from_slice(&value);
    Ok(())
}

fn single_hangul(value: &str) -> Result<char> {
    let mut chars = value.chars();
    let character = chars.next().context("empty Korean character")?;
    ensure!(chars.next().is_none(), "mapping must contain one character");
    ensure!(
        ('\u{ac00}'..='\u{d7a3}').contains(&character)
            || ('\u{3130}'..='\u{318f}').contains(&character),
        "mapping character is not a supported Korean glyph"
    );
    Ok(character)
}

fn parse_korean_code(value: &str) -> Result<u16> {
    let code = parse_hex_u16(value)?;
    let [lead, trail] = code.to_be_bytes();
    ensure!(
        (0xa0..=0xdf).contains(&lead),
        "Korean code lead is outside 0xa0..0xdf"
    );
    ensure!(
        (0x40..=0x7e).contains(&trail) || (0x80..=0xfc).contains(&trail),
        "Korean code trail is outside the approved candidate set"
    );
    Ok(code)
}

fn parse_hex_u16(value: &str) -> Result<u16> {
    let digits = value
        .strip_prefix("0x")
        .context("code must begin with 0x")?;
    u16::from_str_radix(digits, 16).context("invalid mapping code")
}

fn read_exact(path: &Path, expected_sha256: &str) -> Result<Vec<u8>> {
    let bytes = fs::read(path).with_context(|| format!("failed to read {}", path.display()))?;
    ensure!(
        sha256(&bytes).eq_ignore_ascii_case(expected_sha256),
        "input SHA-256 mismatch for {}",
        path.display()
    );
    Ok(bytes)
}

fn file_hashes(files: &[(&str, &[u8])]) -> Vec<FileHash> {
    files
        .iter()
        .map(|(file_name, bytes)| FileHash {
            file_name: (*file_name).to_owned(),
            size: bytes.len(),
            sha256: sha256(bytes),
        })
        .collect()
}

fn publish(
    output_dir: &Path,
    main: &[u8],
    ruby: &[u8],
    skj: &[u8],
    metrics: &[u8],
    report: &Report,
) -> Result<()> {
    let staging = staging_path(output_dir)?;
    ensure!(
        !staging.exists(),
        "overlay staging directory already exists"
    );
    let result = (|| -> Result<()> {
        fs::create_dir_all(&staging)?;
        for (name, bytes) in [
            ("GR3BACK.FNT", main),
            ("RUBY.FNT", ruby),
            ("RUBY.SKJ", skj),
            ("RUBY.METRICS", metrics),
        ] {
            write_synced(&staging.join(name), bytes)?;
        }
        let mut manifest = serde_json::to_vec_pretty(report)?;
        manifest.push(b'\n');
        write_synced(&staging.join("manifest.json"), &manifest)?;
        fs::rename(&staging, output_dir)?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_dir_all(&staging);
    }
    result
}

fn write_synced(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut file = File::create(path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    Ok(())
}

fn staging_path(path: &Path) -> Result<PathBuf> {
    let name = path.file_name().context("output directory has no name")?;
    let mut staging = name.to_os_string();
    staging.push(format!(".tmp-{}", std::process::id()));
    Ok(path.with_file_name(staging))
}

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[cfg(test)]
mod tests {
    use super::{DeclaredWrite, verify_declared_diff};

    fn write(offset: usize, size: usize) -> DeclaredWrite {
        DeclaredWrite {
            file_name: "test.bin".to_owned(),
            offset,
            size,
            purpose: "test".to_owned(),
        }
    }

    #[test]
    fn rejects_an_undeclared_output_change() {
        let original = [0_u8; 4];
        let output = [0, 0, 0, 1];

        assert!(verify_declared_diff(&original, &output, &[write(1, 1)], "test.bin").is_err());
    }

    #[test]
    fn rejects_overlapping_declared_writes() {
        let bytes = [0_u8; 4];

        assert!(
            verify_declared_diff(&bytes, &bytes, &[write(1, 2), write(2, 1)], "test.bin").is_err()
        );
    }
}
