use std::collections::{BTreeSet, HashSet};
use std::path::Path;

use anyhow::{Context, Result, ensure};
use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::inspect;
use crate::iso9660::Image;
use crate::mdz;
use crate::text_scan::{self, Candidate};

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub source_id: String,
    pub disc: u8,
    pub input_size: u64,
    pub input_sha256: String,
    pub mdz_count: usize,
    pub total_decoded_bytes: u64,
    pub containers_with_candidates: usize,
    pub candidate_count: usize,
    pub unique_text_count: usize,
    pub unique_sjis_codes: Vec<String>,
    pub unique_japanese_characters: String,
    pub entries: Vec<Entry>,
}

#[derive(Debug, Serialize)]
pub struct Entry {
    pub path: String,
    pub container_size: u32,
    pub decoded_size: usize,
    pub decoded_sha256: String,
    pub candidate_count: usize,
    pub candidates: Vec<Candidate>,
}

pub fn scan(iso_path: &Path, manifest_path: &Path) -> Result<Report> {
    let identity = inspect::validate_source(iso_path, manifest_path)?;
    let mut image = Image::open(iso_path)?;
    let mdz_entries: Vec<_> = identity
        .entries
        .iter()
        .filter(|entry| !entry.is_dir && entry.path.to_ascii_uppercase().ends_with(".MDZ"))
        .collect();
    ensure!(!mdz_entries.is_empty(), "source ISO contains no MDZ files");

    let mut entries = Vec::with_capacity(mdz_entries.len());
    let mut unique_text = HashSet::new();
    let mut unique_codes = BTreeSet::new();
    let mut unique_japanese = BTreeSet::new();
    let mut total_decoded_bytes = 0_u64;
    for iso_entry in mdz_entries {
        let container = image
            .read_entry(iso_entry)
            .with_context(|| format!("failed to read {}", iso_entry.path))?;
        let decoded = mdz::decode(&container)
            .with_context(|| format!("failed to decode {}", iso_entry.path))?;
        total_decoded_bytes = total_decoded_bytes
            .checked_add(decoded.len() as u64)
            .context("decoded byte total overflow")?;
        let candidates = text_scan::scan_bytes(&decoded, 0);
        for candidate in &candidates {
            unique_text.insert(candidate.source_text.clone());
            unique_japanese.extend(
                candidate
                    .source_text
                    .chars()
                    .filter(|&character| is_japanese(character)),
            );
            let end = candidate
                .offset
                .checked_add(candidate.byte_length)
                .context("text candidate range overflow")?;
            let encoded = decoded
                .get(candidate.offset..end)
                .context("text candidate exceeds decoded container")?;
            collect_codes(encoded, &mut unique_codes)?;
        }
        entries.push(Entry {
            path: iso_entry.path.clone(),
            container_size: iso_entry.size,
            decoded_size: decoded.len(),
            decoded_sha256: format!("{:x}", Sha256::digest(&decoded)),
            candidate_count: candidates.len(),
            candidates,
        });
    }

    let candidate_count = entries.iter().map(|entry| entry.candidate_count).sum();
    let containers_with_candidates = entries
        .iter()
        .filter(|entry| entry.candidate_count != 0)
        .count();
    Ok(Report {
        schema_version: 1,
        source_id: identity.source_id,
        disc: identity.disc,
        input_size: identity.input_size,
        input_sha256: identity.sha256,
        mdz_count: entries.len(),
        total_decoded_bytes,
        containers_with_candidates,
        candidate_count,
        unique_text_count: unique_text.len(),
        unique_sjis_codes: unique_codes
            .into_iter()
            .map(|code| format!("0x{code:04x}"))
            .collect(),
        unique_japanese_characters: unique_japanese.into_iter().collect(),
        entries,
    })
}

fn collect_codes(bytes: &[u8], output: &mut BTreeSet<u16>) -> Result<()> {
    let mut cursor = 0;
    while cursor < bytes.len() {
        let first = bytes[cursor];
        if matches!(first, 0x81..=0x9f | 0xe0..=0xef) {
            let second = *bytes.get(cursor + 1).context("truncated Shift-JIS code")?;
            output.insert((u16::from(first) << 8) | u16::from(second));
            cursor += 2;
        } else {
            if !matches!(first, b'\t' | b'\n' | b'\r' | b' ') {
                output.insert(u16::from(first));
            }
            cursor += 1;
        }
    }
    Ok(())
}

fn is_japanese(character: char) -> bool {
    matches!(
        character,
        '\u{3040}'..='\u{30ff}' | '\u{3400}'..='\u{4dbf}' | '\u{4e00}'..='\u{9fff}'
    )
}

#[cfg(test)]
mod tests {
    use std::collections::BTreeSet;

    use super::collect_codes;

    #[test]
    fn collects_single_and_double_byte_codes() {
        let mut codes = BTreeSet::new();
        collect_codes(&[b'A', b' ', 0x83, 0x65], &mut codes).unwrap();

        assert_eq!(codes, BTreeSet::from([0x0041, 0x8365]));
    }
}
