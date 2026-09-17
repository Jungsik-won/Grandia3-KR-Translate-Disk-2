use std::collections::HashMap;
use std::fs;
use std::path::Path;

use anyhow::{Context, Result, ensure};
use encoding_rs::SHIFT_JIS;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::inspect;
use crate::iso9660::Image;

#[derive(Debug, Deserialize)]
struct ScopeFile {
    schema_version: u32,
    scopes: Vec<Scope>,
}

#[derive(Debug, Deserialize)]
struct Scope {
    id: String,
    source_path: String,
    source_sha256: String,
    start: usize,
    end: usize,
    encoding: String,
    expected_units: usize,
}

#[derive(Debug, Serialize)]
pub struct TranslationIndex {
    pub schema_version: u32,
    pub source_id: String,
    pub scope_file_sha256: String,
    pub unit_count: usize,
    pub units: Vec<Unit>,
}

#[derive(Debug, Serialize)]
pub struct Unit {
    pub id: String,
    pub scope_id: String,
    pub source_path: String,
    pub offset: usize,
    pub byte_length: usize,
    pub source_sha256: String,
    pub slot_size: usize,
    pub max_encoded_bytes: usize,
    pub slot_sha256: String,
    pub source_text: String,
    pub control_tokens: Vec<String>,
    pub translation: String,
    pub status: String,
}

pub fn extract(
    iso_path: &Path,
    manifest_path: &Path,
    scope_path: &Path,
) -> Result<TranslationIndex> {
    let inventory = inspect::inspect(iso_path, manifest_path)?;
    let scope_bytes = fs::read(scope_path)
        .with_context(|| format!("failed to read text scope {}", scope_path.display()))?;
    let scopes: ScopeFile = serde_json::from_slice(&scope_bytes)
        .with_context(|| format!("invalid text scope {}", scope_path.display()))?;
    ensure!(scopes.schema_version == 1, "unsupported text-scope schema");
    ensure!(!scopes.scopes.is_empty(), "text scope has no entries");

    let mut image = Image::open(iso_path)?;
    let iso_entries = image.entries()?;
    let mut sources = HashMap::new();
    let mut units = Vec::new();

    for scope in &scopes.scopes {
        ensure!(scope.encoding == "shift_jis", "unsupported text encoding");
        if !sources.contains_key(&scope.source_path) {
            let entry = iso_entries
                .iter()
                .find(|entry| entry.path == scope.source_path)
                .with_context(|| format!("text source {} is missing", scope.source_path))?;
            sources.insert(scope.source_path.clone(), image.read_entry(entry)?);
        }
        let source = &sources[&scope.source_path];
        let source_sha256 = format!("{:x}", Sha256::digest(source));
        ensure!(
            source_sha256.eq_ignore_ascii_case(&scope.source_sha256),
            "text source {} hash differs from scope",
            scope.source_path
        );
        ensure!(
            scope.start < scope.end && scope.end <= source.len(),
            "text scope {} is outside {}",
            scope.id,
            scope.source_path
        );

        let first_unit = units.len();
        let mut segment_start = scope.start;
        for segment_end in scope.start..scope.end {
            if source[segment_end] != 0 {
                continue;
            }
            if segment_start < segment_end
                && let Some(unit) = decode_unit(scope, source, segment_start, segment_end)
            {
                units.push(unit);
            }
            segment_start = segment_end + 1;
        }
        ensure!(
            segment_start == scope.end || source[segment_start..scope.end].iter().all(|&b| b == 0),
            "text scope {} ends inside a nonterminated string",
            scope.id
        );
        let extracted = units.len() - first_unit;
        ensure!(
            extracted == scope.expected_units,
            "text scope {} produced {extracted} units, expected {}",
            scope.id,
            scope.expected_units
        );
        finalize_slots(scope, source, &mut units[first_unit..])?;
    }

    Ok(TranslationIndex {
        schema_version: 1,
        source_id: inventory.source_id,
        scope_file_sha256: format!("{:x}", Sha256::digest(&scope_bytes)),
        unit_count: units.len(),
        units,
    })
}

fn finalize_slots(scope: &Scope, source: &[u8], units: &mut [Unit]) -> Result<()> {
    for index in 0..units.len() {
        let slot_start = units[index].offset;
        let text_end = slot_start + units[index].byte_length;
        let slot_end = units.get(index + 1).map_or(scope.end, |unit| unit.offset);

        ensure!(
            text_end < slot_end,
            "text unit {} has no NUL terminator in its slot",
            units[index].id
        );
        ensure!(
            source[text_end..slot_end].iter().all(|&byte| byte == 0),
            "text unit {} has nonzero data after its string",
            units[index].id
        );

        let slot = &source[slot_start..slot_end];
        units[index].slot_size = slot.len();
        units[index].max_encoded_bytes = slot.len() - 1;
        units[index].slot_sha256 = format!("{:x}", Sha256::digest(slot));
    }
    Ok(())
}

fn decode_unit(scope: &Scope, source: &[u8], start: usize, end: usize) -> Option<Unit> {
    let bytes = &source[start..end];
    let text = SHIFT_JIS.decode_without_bom_handling_and_without_replacement(bytes)?;
    if text.is_ascii()
        || text
            .chars()
            .any(|character| character.is_control() && !matches!(character, '\n' | '\r' | '\t'))
    {
        return None;
    }

    let control_tokens = text
        .chars()
        .filter_map(|character| match character {
            '\n' => Some("LF".to_owned()),
            '\r' => Some("CR".to_owned()),
            '\t' => Some("TAB".to_owned()),
            _ => None,
        })
        .collect();

    Some(Unit {
        id: format!("{}-{start:08x}", scope.id),
        scope_id: scope.id.clone(),
        source_path: scope.source_path.clone(),
        offset: start,
        byte_length: bytes.len(),
        source_sha256: format!("{:x}", Sha256::digest(bytes)),
        slot_size: 0,
        max_encoded_bytes: 0,
        slot_sha256: String::new(),
        source_text: text.into_owned(),
        control_tokens,
        translation: String::new(),
        status: "untranslated".to_owned(),
    })
}

#[cfg(test)]
mod tests {
    use super::{Scope, decode_unit, finalize_slots};

    fn scope() -> Scope {
        Scope {
            id: "test".to_owned(),
            source_path: "FIELD.BIN".to_owned(),
            source_sha256: String::new(),
            start: 0,
            end: 0,
            encoding: "shift_jis".to_owned(),
            expected_units: 0,
        }
    }

    #[test]
    fn extracts_shift_jis_with_stable_offset_id() {
        let bytes = [0x83, 0x65, 0x83, 0x58, 0x83, 0x67];
        let unit = decode_unit(&scope(), &bytes, 0, bytes.len()).unwrap();
        assert_eq!(unit.id, "test-00000000");
        assert_eq!(unit.source_text, "テスト");
        assert_eq!(unit.byte_length, 6);
    }

    #[test]
    fn rejects_ascii_and_invalid_sequences() {
        assert!(decode_unit(&scope(), b"DEBUG", 0, 5).is_none());
        assert!(decode_unit(&scope(), &[0x82], 0, 1).is_none());
    }

    #[test]
    fn binds_units_to_zero_padded_slots() {
        let source = [0x83, 0x65, 0, 0, 0x83, 0x58, 0, 0];
        let mut scope = scope();
        scope.end = source.len();
        let mut units = vec![
            decode_unit(&scope, &source, 0, 2).unwrap(),
            decode_unit(&scope, &source, 4, 6).unwrap(),
        ];

        finalize_slots(&scope, &source, &mut units).unwrap();

        assert_eq!(units[0].slot_size, 4);
        assert_eq!(units[0].max_encoded_bytes, 3);
        assert_eq!(units[1].slot_size, 4);
        assert!(!units[0].slot_sha256.is_empty());
    }

    #[test]
    fn rejects_nonzero_data_inside_a_slot() {
        let source = [0x83, 0x65, 0, b'X', 0];
        let mut scope = scope();
        scope.end = source.len();
        let mut units = vec![decode_unit(&scope, &source, 0, 2).unwrap()];

        assert!(finalize_slots(&scope, &source, &mut units).is_err());
    }
}
