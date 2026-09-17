use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::fs;
use std::path::{Component, Path, PathBuf};

use anyhow::{Context, Result, ensure};
use encoding_rs::SHIFT_JIS;
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::skj;

#[derive(Debug, Deserialize)]
struct Draft {
    schema_version: u32,
    draft_id: String,
    status: String,
    rule: FileRef,
    rule_approval: String,
    source_segment: SegmentRef,
    glossary_exceptions: Vec<GlossaryException>,
    translations: BTreeMap<String, String>,
}

#[derive(Debug, Deserialize)]
struct FileRef {
    path: String,
    sha256: String,
}

#[derive(Debug, Deserialize)]
struct SegmentRef {
    path: String,
    sha256: String,
    unit_count: usize,
}

#[derive(Debug, Deserialize)]
struct GlossaryException {
    unit_id: String,
    source: String,
    translation: String,
    reason: String,
}

#[derive(Debug, Deserialize)]
struct Approval {
    schema_version: u32,
    approval_id: String,
    rule: FileRef,
    translation_index: FileRef,
    scope: ApprovedScope,
    segments: Vec<ApprovedSegment>,
}

#[derive(Debug, Deserialize)]
struct ApprovedScope {
    path: String,
    sha256: String,
    unit_count: usize,
}

#[derive(Debug, Deserialize)]
struct ApprovedSegment {
    id: String,
    path: String,
    sha256: String,
    unit_count: usize,
}

#[derive(Debug, Deserialize)]
struct Rule {
    schema_version: u32,
    rule_id: String,
    scope: RuleScope,
    glossary: Vec<GlossaryEntry>,
}

#[derive(Debug, Deserialize)]
struct RuleScope {
    unit_count: usize,
    segment_path: String,
    segment_sha256: String,
}

#[derive(Debug, Deserialize)]
struct GlossaryEntry {
    source: String,
    target: String,
}

#[derive(Debug, Deserialize)]
struct SourceSegment {
    unit_count: usize,
    units: Vec<SourceUnit>,
}

#[derive(Debug, Deserialize)]
struct SourceUnit {
    id: String,
    max_encoded_bytes: usize,
    source_text: String,
    control_tokens: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub draft_id: String,
    pub unit_count: usize,
    pub translated_draft_count: usize,
    pub source_segment_sha256: String,
    pub draft_sha256: String,
    pub existing_character_count: usize,
    pub hangul_syllable_count: usize,
    pub hangul_syllables: Vec<String>,
    pub maximum_encoded_bytes_used: usize,
    pub glossary_exception_count: usize,
}

pub fn verify(draft_path: &Path, skj_path: &Path) -> Result<Report> {
    let draft_bytes = read(draft_path)?;
    let draft: Draft = serde_json::from_slice(&draft_bytes)
        .with_context(|| format!("invalid translation draft {}", draft_path.display()))?;
    ensure!(draft.schema_version == 1, "unsupported draft schema");
    ensure!(
        draft.status == "translated_draft",
        "draft is not marked translated_draft"
    );

    let rule_path = safe_project_path(&draft.rule.path)?;
    let rule_bytes = read(&rule_path)?;
    ensure_hash("translation rule", &rule_bytes, &draft.rule.sha256)?;
    let rule: Rule = serde_json::from_slice(&rule_bytes)
        .with_context(|| format!("invalid translation rule {}", rule_path.display()))?;
    ensure!(rule.schema_version == 1, "unsupported rule schema");
    ensure!(rule.rule_id == draft.draft_id, "draft and rule IDs differ");

    let approval_path = safe_project_path(&draft.rule_approval)?;
    let approval: Approval = serde_json::from_slice(&read(&approval_path)?)
        .with_context(|| format!("invalid rule approval {}", approval_path.display()))?;
    ensure!(approval.schema_version == 1, "unsupported approval schema");
    ensure!(
        approval.approval_id == draft.draft_id,
        "draft and approval IDs differ"
    );
    ensure!(
        approval.rule.path == draft.rule.path && approval.rule.sha256 == draft.rule.sha256,
        "rule approval does not bind the draft rule"
    );
    ensure_hash(
        "approved translation index",
        &read(&safe_project_path(&approval.translation_index.path)?)?,
        &approval.translation_index.sha256,
    )?;
    ensure_hash(
        "approved translation scope",
        &read(&safe_project_path(&approval.scope.path)?)?,
        &approval.scope.sha256,
    )?;
    ensure!(
        approval.scope.unit_count == rule.scope.unit_count,
        "approved scope unit count differs from the rule"
    );

    let segment_path = safe_project_path(&draft.source_segment.path)?;
    let segment_bytes = read(&segment_path)?;
    ensure_hash(
        "draft source segment",
        &segment_bytes,
        &draft.source_segment.sha256,
    )?;
    ensure!(
        draft.source_segment.path == rule.scope.segment_path
            && draft.source_segment.sha256 == rule.scope.segment_sha256,
        "draft source segment differs from the rule"
    );
    ensure!(
        approval.segments.iter().any(|segment| {
            segment.path == draft.source_segment.path
                && segment.sha256 == draft.source_segment.sha256
                && segment.unit_count == draft.source_segment.unit_count
                && !segment.id.is_empty()
        }),
        "rule approval does not bind the draft source segment"
    );
    let segment: SourceSegment = serde_json::from_slice(&segment_bytes)
        .with_context(|| format!("invalid source segment {}", segment_path.display()))?;
    ensure!(
        segment.unit_count == segment.units.len()
            && segment.unit_count == draft.source_segment.unit_count
            && segment.unit_count == rule.scope.unit_count,
        "draft unit populations differ"
    );
    ensure!(
        draft.translations.len() == segment.unit_count,
        "draft translation count differs from the source population"
    );

    let records = skj::records(skj_path)?;
    let existing_codes: HashSet<_> = records.iter().map(|record| record.code).collect();
    let source_ids: HashSet<_> = segment.units.iter().map(|unit| unit.id.as_str()).collect();
    ensure!(
        draft
            .translations
            .keys()
            .all(|id| source_ids.contains(id.as_str())),
        "draft contains an unknown unit ID"
    );

    let mut exceptions = BTreeMap::new();
    for exception in &draft.glossary_exceptions {
        ensure!(
            !exception.reason.trim().is_empty(),
            "empty glossary exception reason"
        );
        ensure!(
            exceptions.insert(&exception.unit_id, exception).is_none(),
            "duplicate glossary exception"
        );
    }

    let mut hangul = BTreeSet::new();
    let mut existing_characters = BTreeSet::new();
    let mut maximum_encoded_bytes_used = 0;
    for unit in &segment.units {
        let translation = draft
            .translations
            .get(&unit.id)
            .with_context(|| format!("missing translation for {}", unit.id))?;
        ensure!(!translation.is_empty(), "empty translation for {}", unit.id);
        let translated_tokens: Vec<_> = translation
            .chars()
            .filter_map(|character| match character {
                '\n' => Some("LF"),
                '\r' => Some("CR"),
                '\t' => Some("TAB"),
                _ => None,
            })
            .collect();
        ensure!(
            translated_tokens == unit.control_tokens,
            "control tokens differ for {}",
            unit.id
        );

        let encoded_size = encoded_size(
            translation,
            &existing_codes,
            &mut hangul,
            &mut existing_characters,
        )
        .with_context(|| format!("translation {} is not encodable", unit.id))?;
        ensure!(
            encoded_size <= unit.max_encoded_bytes,
            "translation {} needs {} bytes but its slot permits {}",
            unit.id,
            encoded_size,
            unit.max_encoded_bytes
        );
        maximum_encoded_bytes_used = maximum_encoded_bytes_used.max(encoded_size);

        for entry in &rule.glossary {
            if !unit.source_text.contains(&entry.source) {
                continue;
            }
            if translation.contains(&normalize_game_ascii(&entry.target)) {
                continue;
            }
            let exception = exceptions
                .get(&unit.id)
                .with_context(|| format!("{} violates glossary term {}", unit.id, entry.source))?;
            ensure!(
                exception.source == entry.source && exception.translation == *translation,
                "glossary exception does not match {}",
                unit.id
            );
        }
    }
    ensure!(
        exceptions.keys().all(|id| source_ids.contains(id.as_str())),
        "glossary exception names an unknown unit"
    );

    Ok(Report {
        schema_version: 1,
        draft_id: draft.draft_id,
        unit_count: segment.unit_count,
        translated_draft_count: draft.translations.len(),
        source_segment_sha256: sha256(&segment_bytes),
        draft_sha256: sha256(&draft_bytes),
        existing_character_count: existing_characters.len(),
        hangul_syllable_count: hangul.len(),
        hangul_syllables: hangul
            .into_iter()
            .map(|character| character.to_string())
            .collect(),
        maximum_encoded_bytes_used,
        glossary_exception_count: exceptions.len(),
    })
}

fn normalize_game_ascii(value: &str) -> String {
    value
        .chars()
        .map(|character| match character {
            ' ' => '\u{3000}',
            '!'..='~' => char::from_u32(character as u32 + 0xfee0).unwrap(),
            _ => character,
        })
        .collect()
}

fn encoded_size(
    text: &str,
    existing_codes: &HashSet<u16>,
    hangul: &mut BTreeSet<char>,
    existing_characters: &mut BTreeSet<char>,
) -> Result<usize> {
    let mut size = 0;
    for character in text.chars() {
        if ('\u{ac00}'..='\u{d7a3}').contains(&character)
            || ('\u{3130}'..='\u{318f}').contains(&character)
        {
            hangul.insert(character);
            size += 2;
            continue;
        }
        let source = character.to_string();
        let (encoded, _, had_errors) = SHIFT_JIS.encode(&source);
        ensure!(
            !had_errors,
            "unsupported character U+{:04X}",
            character as u32
        );
        let code = match encoded.as_ref() {
            [single] => u16::from(*single),
            [lead, trail] => u16::from_be_bytes([*lead, *trail]),
            _ => anyhow::bail!("unsupported encoded width for U+{:04X}", character as u32),
        };
        ensure!(
            existing_codes.contains(&code),
            "character U+{:04X} has unmapped game code 0x{code:04x}",
            character as u32
        );
        existing_characters.insert(character);
        size += encoded.len();
    }
    Ok(size)
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
