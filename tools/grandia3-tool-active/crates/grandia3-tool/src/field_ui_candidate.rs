use std::collections::{BTreeMap, HashMap, HashSet};
use std::fs::{self, File};
use std::io::Write;
use std::ops::Range;
use std::path::{Component, Path, PathBuf};

use anyhow::{Context, Result, ensure};
use encoding_rs::SHIFT_JIS;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::translation_draft;

#[derive(Debug, Deserialize)]
struct Draft {
    draft_id: String,
    rule_approval: String,
    source_segment: SegmentRef,
    translations: BTreeMap<String, String>,
}

#[derive(Debug, Deserialize)]
struct SegmentRef {
    path: String,
    sha256: String,
}

#[derive(Debug, Deserialize)]
struct Approval {
    scope: ApprovedScope,
}

#[derive(Debug, Deserialize)]
struct ApprovedScope {
    path: String,
}

#[derive(Debug, Deserialize)]
struct TextScopes {
    schema_version: u32,
    scopes: Vec<TextScope>,
}

#[derive(Debug, Deserialize)]
struct TextScope {
    source_path: String,
    source_sha256: String,
    start: usize,
    end: usize,
}

#[derive(Debug, Deserialize)]
struct Segment {
    unit_count: usize,
    units: Vec<Unit>,
}

#[derive(Debug, Deserialize)]
struct Unit {
    id: String,
    source_path: String,
    offset: usize,
    byte_length: usize,
    source_sha256: String,
    slot_size: usize,
    max_encoded_bytes: usize,
    slot_sha256: String,
}

#[derive(Debug, Deserialize)]
struct FontConfig {
    schema_version: u32,
    inputs: FontInputs,
    mappings: Vec<FontMapping>,
}

#[derive(Debug, Deserialize)]
struct FontInputs {
    skj_sha256: String,
}

#[derive(Debug, Deserialize)]
struct FontMapping {
    character: String,
    code: String,
}

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub status: String,
    pub limitation: String,
    pub draft_id: String,
    pub draft_sha256: String,
    pub font_config_sha256: String,
    pub original: FileHash,
    pub output: FileHash,
    pub unit_count: usize,
    pub changed_unit_count: usize,
    pub declared_write_count: usize,
    pub changed_byte_count: usize,
    pub writes: Vec<WriteRecord>,
}

#[derive(Debug, Serialize)]
pub struct FileHash {
    pub file_name: String,
    pub size: usize,
    pub sha256: String,
}

#[derive(Debug, Serialize)]
pub struct WriteRecord {
    pub unit_id: String,
    pub offset: usize,
    pub slot_size: usize,
    pub encoded_size: usize,
    pub original_slot_sha256: String,
    pub output_slot_sha256: String,
    pub changed_bytes: usize,
}

pub struct Paths<'a> {
    pub field_bin: &'a Path,
    pub draft: &'a Path,
    pub original_skj: &'a Path,
    pub font_config: &'a Path,
    pub output_dir: &'a Path,
}

pub fn build(paths: Paths<'_>) -> Result<Report> {
    ensure!(
        !paths.output_dir.exists(),
        "output directory already exists: {}",
        paths.output_dir.display()
    );
    let draft_report = translation_draft::verify(paths.draft, paths.original_skj)?;
    let draft_bytes = read(paths.draft)?;
    let draft: Draft = serde_json::from_slice(&draft_bytes)
        .with_context(|| format!("invalid translation draft {}", paths.draft.display()))?;
    ensure!(
        draft.draft_id == draft_report.draft_id,
        "draft verification ID mismatch"
    );

    let approval_path = safe_project_path(&draft.rule_approval)?;
    let approval: Approval = serde_json::from_slice(&read(&approval_path)?)
        .with_context(|| format!("invalid rule approval {}", approval_path.display()))?;
    let scopes_path = safe_project_path(&approval.scope.path)?;
    let scopes: TextScopes = serde_json::from_slice(&read(&scopes_path)?)
        .with_context(|| format!("invalid text scopes {}", scopes_path.display()))?;
    ensure!(scopes.schema_version == 1, "unsupported text-scope schema");
    let field_scopes: Vec<_> = scopes
        .scopes
        .iter()
        .filter(|scope| scope.source_path == "FIELD.BIN")
        .collect();
    ensure!(!field_scopes.is_empty(), "no FIELD.BIN text scopes");
    let expected_source_hash = &field_scopes[0].source_sha256;
    ensure!(
        field_scopes
            .iter()
            .all(|scope| scope.source_sha256 == *expected_source_hash),
        "FIELD.BIN scopes disagree on the source hash"
    );

    let original = read(paths.field_bin)?;
    ensure_hash("FIELD.BIN", &original, expected_source_hash)?;
    let mut output = original.clone();

    let segment_path = safe_project_path(&draft.source_segment.path)?;
    let segment_bytes = read(&segment_path)?;
    ensure_hash(
        "source segment",
        &segment_bytes,
        &draft.source_segment.sha256,
    )?;
    let segment: Segment = serde_json::from_slice(&segment_bytes)
        .with_context(|| format!("invalid source segment {}", segment_path.display()))?;
    ensure!(
        segment.unit_count == segment.units.len() && segment.unit_count == draft.translations.len(),
        "candidate unit populations differ"
    );

    let font_config_bytes = read(paths.font_config)?;
    let font_config: FontConfig = serde_json::from_slice(&font_config_bytes)
        .with_context(|| format!("invalid font config {}", paths.font_config.display()))?;
    ensure!(
        font_config.schema_version == 1,
        "unsupported font config schema"
    );
    ensure_hash(
        "original SKJ",
        &read(paths.original_skj)?,
        &font_config.inputs.skj_sha256,
    )?;
    let hangul_codes = hangul_codes(&font_config.mappings)?;
    let expected_hangul: HashSet<_> = draft_report
        .hangul_syllables
        .iter()
        .map(|value| value.chars().next().unwrap())
        .collect();
    ensure!(
        hangul_codes.keys().copied().collect::<HashSet<_>>() == expected_hangul,
        "font config Hangul population differs from the translation draft"
    );

    let mut writes = Vec::with_capacity(segment.unit_count);
    let mut ranges = Vec::with_capacity(segment.unit_count);
    for unit in &segment.units {
        ensure!(
            unit.source_path == "FIELD.BIN",
            "unexpected unit source path"
        );
        let range = unit.offset..unit.offset + unit.slot_size;
        ensure!(
            range.end <= original.len(),
            "unit {} exceeds FIELD.BIN",
            unit.id
        );
        ensure!(
            field_scopes
                .iter()
                .any(|scope| scope.start <= range.start && range.end <= scope.end),
            "unit {} is outside the approved text scopes",
            unit.id
        );
        ensure_hash("source slot", &original[range.clone()], &unit.slot_sha256)
            .with_context(|| format!("unit {} slot differs", unit.id))?;
        ensure_hash(
            "source text",
            &original[unit.offset..unit.offset + unit.byte_length],
            &unit.source_sha256,
        )
        .with_context(|| format!("unit {} source text differs", unit.id))?;
        let translation = &draft.translations[&unit.id];
        let encoded = encode(translation, &hangul_codes)
            .with_context(|| format!("failed to encode unit {}", unit.id))?;
        ensure!(
            encoded.len() <= unit.max_encoded_bytes,
            "unit {} exceeds its encoded slot",
            unit.id
        );
        let mut slot = vec![0; unit.slot_size];
        slot[..encoded.len()].copy_from_slice(&encoded);
        output[range.clone()].copy_from_slice(&slot);
        let changed_bytes = original[range.clone()]
            .iter()
            .zip(&slot)
            .filter(|(before, after)| before != after)
            .count();
        writes.push(WriteRecord {
            unit_id: unit.id.clone(),
            offset: unit.offset,
            slot_size: unit.slot_size,
            encoded_size: encoded.len(),
            original_slot_sha256: unit.slot_sha256.clone(),
            output_slot_sha256: sha256(&slot),
            changed_bytes,
        });
        ranges.push(range);
    }
    ranges.sort_by_key(|range| range.start);
    for pair in ranges.windows(2) {
        ensure!(pair[0].end <= pair[1].start, "FIELD.BIN writes overlap");
    }
    verify_declared_diff(&original, &output, &ranges)?;

    let changed_byte_count = writes.iter().map(|write| write.changed_bytes).sum();
    let changed_unit_count = writes
        .iter()
        .filter(|write| write.changed_bytes > 0)
        .count();
    let report = Report {
        schema_version: 1,
        status: "research_only_not_product_input".to_owned(),
        limitation: "Font slots protect only the declared FIELD.BIN source population; undiscovered story dialogue remains out of scope.".to_owned(),
        draft_id: draft.draft_id,
        draft_sha256: sha256(&draft_bytes),
        font_config_sha256: sha256(&font_config_bytes),
        original: file_hash("FIELD.BIN", &original),
        output: file_hash("FIELD.BIN", &output),
        unit_count: writes.len(),
        changed_unit_count,
        declared_write_count: ranges.len(),
        changed_byte_count,
        writes,
    };
    publish(paths.output_dir, &output, &report)?;
    Ok(report)
}

fn hangul_codes(mappings: &[FontMapping]) -> Result<HashMap<char, u16>> {
    let mut result = HashMap::with_capacity(mappings.len());
    let mut codes = HashSet::new();
    for mapping in mappings {
        let mut characters = mapping.character.chars();
        let character = characters.next().context("empty font mapping character")?;
        ensure!(
            characters.next().is_none()
                && (('\u{ac00}'..='\u{d7a3}').contains(&character)
                    || ('\u{3130}'..='\u{318f}').contains(&character)),
            "font mapping is not one supported Korean glyph"
        );
        let digits = mapping
            .code
            .strip_prefix("0x")
            .context("font mapping code must begin with 0x")?;
        let code = u16::from_str_radix(digits, 16).context("invalid font mapping code")?;
        ensure!(
            result.insert(character, code).is_none(),
            "duplicate Hangul mapping"
        );
        ensure!(codes.insert(code), "duplicate font mapping code");
    }
    Ok(result)
}

fn encode(text: &str, hangul_codes: &HashMap<char, u16>) -> Result<Vec<u8>> {
    let mut output = Vec::with_capacity(text.len() * 2);
    for character in text.chars() {
        if ('\u{ac00}'..='\u{d7a3}').contains(&character)
            || ('\u{3130}'..='\u{318f}').contains(&character)
        {
            let code = hangul_codes
                .get(&character)
                .with_context(|| format!("unmapped Hangul U+{:04X}", character as u32))?;
            output.extend_from_slice(&code.to_be_bytes());
            continue;
        }
        let source = character.to_string();
        let (encoded, _, had_errors) = SHIFT_JIS.encode(&source);
        ensure!(
            !had_errors,
            "unencodable character U+{:04X}",
            character as u32
        );
        ensure!(!encoded.contains(&0), "encoded text contains NUL");
        output.extend_from_slice(&encoded);
    }
    Ok(output)
}

fn verify_declared_diff(original: &[u8], output: &[u8], ranges: &[Range<usize>]) -> Result<()> {
    ensure!(original.len() == output.len(), "FIELD.BIN size changed");
    for (offset, (before, after)) in original.iter().zip(output).enumerate() {
        if before != after {
            ensure!(
                ranges
                    .iter()
                    .any(|range| range.start <= offset && offset < range.end),
                "undeclared FIELD.BIN change at offset {offset:#x}"
            );
        }
    }
    Ok(())
}

fn publish(output_dir: &Path, field_bin: &[u8], report: &Report) -> Result<()> {
    let staging = staging_path(output_dir)?;
    ensure!(
        !staging.exists(),
        "candidate staging directory already exists"
    );
    let result = (|| -> Result<()> {
        fs::create_dir_all(&staging)?;
        write_synced(&staging.join("FIELD.BIN"), field_bin)?;
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

fn safe_project_path(value: &str) -> Result<PathBuf> {
    let path = Path::new(value);
    ensure!(
        !path.is_absolute(),
        "project path must be relative: {value}"
    );
    ensure!(
        path.components()
            .all(|component| matches!(component, Component::Normal(_))),
        "project path is not normalized: {value}"
    );
    Ok(path.to_owned())
}

fn file_hash(file_name: &str, bytes: &[u8]) -> FileHash {
    FileHash {
        file_name: file_name.to_owned(),
        size: bytes.len(),
        sha256: sha256(bytes),
    }
}

fn read(path: &Path) -> Result<Vec<u8>> {
    fs::read(path).with_context(|| format!("failed to read {}", path.display()))
}

fn ensure_hash(label: &str, bytes: &[u8], expected: &str) -> Result<()> {
    let actual = sha256(bytes);
    ensure!(
        actual.eq_ignore_ascii_case(expected),
        "{label} hash differs: expected {expected}, got {actual}"
    );
    Ok(())
}

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use super::{encode, verify_declared_diff};

    #[test]
    fn encodes_custom_hangul_codes_in_big_endian_order() {
        let mappings = HashMap::from([('가', 0xa040)]);

        let encoded = encode("가！\n", &mappings).unwrap();

        assert_eq!(encoded, [0xa0, 0x40, 0x81, 0x49, 0x0a]);
    }

    #[test]
    fn rejects_missing_hangul_mapping() {
        assert!(encode("가", &HashMap::new()).is_err());
    }

    #[test]
    fn rejects_undeclared_field_change() {
        let original = [0_u8; 8];
        let mut output = original;
        output[6] = 1;

        assert!(verify_declared_diff(&original, &output, &[1..4, 4..6]).is_err());
    }
}
