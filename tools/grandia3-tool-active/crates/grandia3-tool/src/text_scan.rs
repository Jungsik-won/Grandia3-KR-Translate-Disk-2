use std::fs;
use std::path::Path;

use anyhow::{Context, Result};
use encoding_rs::SHIFT_JIS;
use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::mdt;

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub source_size: usize,
    pub source_sha256: String,
    pub candidate_count: usize,
    pub chunks: Vec<ChunkCandidates>,
}

#[derive(Debug, Serialize)]
pub struct ChunkCandidates {
    pub chunk_index: usize,
    pub chunk_tag: String,
    pub chunk_offset: usize,
    pub candidate_count: usize,
    pub candidates: Vec<Candidate>,
}

#[derive(Debug, Serialize)]
pub struct Candidate {
    pub offset: usize,
    pub byte_length: usize,
    pub source_sha256: String,
    pub source_text: String,
    pub japanese_character_count: usize,
    pub control_tokens: Vec<String>,
}

pub(crate) fn scan_bytes(bytes: &[u8], base_offset: usize) -> Vec<Candidate> {
    scan_range(bytes, base_offset)
}

pub fn scan(path: &Path) -> Result<Report> {
    let inventory = mdt::inspect(path)?;
    let bytes = fs::read(path).with_context(|| format!("failed to read {}", path.display()))?;
    let mut chunks = Vec::new();
    for chunk in &inventory.chunks {
        let range = &bytes[chunk.offset..chunk.offset + chunk.size];
        let candidates = scan_range(range, chunk.offset);
        if !candidates.is_empty() {
            chunks.push(ChunkCandidates {
                chunk_index: chunk.index,
                chunk_tag: chunk.tag.clone(),
                chunk_offset: chunk.offset,
                candidate_count: candidates.len(),
                candidates,
            });
        }
    }
    Ok(Report {
        schema_version: 1,
        source_size: bytes.len(),
        source_sha256: format!("{:x}", Sha256::digest(&bytes)),
        candidate_count: chunks.iter().map(|chunk| chunk.candidate_count).sum(),
        chunks,
    })
}

pub fn scan_raw(path: &Path) -> Result<Report> {
    let bytes = fs::read(path).with_context(|| format!("failed to read {}", path.display()))?;
    let candidates = scan_range(&bytes, 0);
    let candidate_count = candidates.len();
    Ok(Report {
        schema_version: 1,
        source_size: bytes.len(),
        source_sha256: format!("{:x}", Sha256::digest(&bytes)),
        candidate_count,
        chunks: if candidates.is_empty() {
            Vec::new()
        } else {
            vec![ChunkCandidates {
                chunk_index: 0,
                chunk_tag: "raw".to_owned(),
                chunk_offset: 0,
                candidate_count,
                candidates,
            }]
        },
    })
}

fn scan_range(bytes: &[u8], base_offset: usize) -> Vec<Candidate> {
    let mut candidates = Vec::new();
    let mut cursor = 0;
    while cursor < bytes.len() {
        let start = cursor;
        let Some(end) = consume_text(bytes, start) else {
            cursor += 1;
            continue;
        };
        if end == start || bytes.get(end) != Some(&0) {
            cursor += 1;
            continue;
        }
        let encoded = &bytes[start..end];
        if encoded.len() >= 4
            && let Some(text) =
                SHIFT_JIS.decode_without_bom_handling_and_without_replacement(encoded)
        {
            let characters: Vec<_> = text.chars().collect();
            let japanese_character_count = characters
                .iter()
                .filter(|&&character| is_japanese(character))
                .count();
            let kana_count = characters
                .iter()
                .filter(|&&character| is_kana(character))
                .count();
            let visible_count = characters
                .iter()
                .filter(|character| !character.is_whitespace())
                .count();
            if japanese_character_count >= 3
                && kana_count > 0
                && japanese_character_count * 10 >= visible_count * 7
                && characters.iter().all(|&character| is_allowed(character))
            {
                candidates.push(Candidate {
                    offset: base_offset + start,
                    byte_length: encoded.len(),
                    source_sha256: format!("{:x}", Sha256::digest(encoded)),
                    source_text: text.into_owned(),
                    japanese_character_count,
                    control_tokens: encoded
                        .iter()
                        .filter_map(|byte| match byte {
                            b'\n' => Some("LF".to_owned()),
                            b'\r' => Some("CR".to_owned()),
                            b'\t' => Some("TAB".to_owned()),
                            _ => None,
                        })
                        .collect(),
                });
                cursor = end + 1;
                continue;
            }
        }
        cursor += 1;
    }
    candidates
}

fn consume_text(bytes: &[u8], mut cursor: usize) -> Option<usize> {
    while cursor < bytes.len() {
        let first = bytes[cursor];
        match first {
            0 => return Some(cursor),
            b'\t' | b'\n' | b'\r' | 0x20..=0x7e | 0xa1..=0xdf => cursor += 1,
            0x81..=0x9f | 0xe0..=0xef => {
                let trail = *bytes.get(cursor + 1)?;
                if (0x40..=0x7e).contains(&trail) || (0x80..=0xfc).contains(&trail) {
                    cursor += 2;
                } else {
                    return None;
                }
            }
            _ => return None,
        }
    }
    None
}

fn is_japanese(character: char) -> bool {
    matches!(
        character,
        '\u{3040}'..='\u{30ff}' | '\u{3400}'..='\u{4dbf}' | '\u{4e00}'..='\u{9fff}'
    )
}

fn is_kana(character: char) -> bool {
    matches!(character, '\u{3040}'..='\u{30ff}')
}

fn is_allowed(character: char) -> bool {
    character.is_ascii()
        || is_japanese(character)
        || matches!(character, '\u{3000}'..='\u{303f}' | '\u{ff01}'..='\u{ff60}')
}

#[cfg(test)]
mod tests {
    use super::scan_range;

    #[test]
    fn finds_a_terminated_japanese_candidate() {
        let bytes = [0xff, 0x83, 0x65, 0x83, 0x58, 0x83, 0x67, 0, 1];
        let candidates = scan_range(&bytes, 0x100);

        assert_eq!(candidates.len(), 1);
        assert_eq!(candidates[0].offset, 0x101);
        assert_eq!(candidates[0].source_text, "テスト");
    }
}
