use std::collections::{BTreeMap, HashMap};
use std::fs;
use std::path::Path;

use anyhow::{Context, Result, ensure};
use serde::Serialize;

use crate::inspect;
use crate::iso9660::Image;
use crate::{mdt, mdz};

const MIN_BYTES: usize = 3;
const MAX_BYTES: usize = 512;
const MIN_KNOWN_RATIO: f64 = 0.65;

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub source_id: String,
    pub disc: u8,
    pub mdz_count: usize,
    pub total_decoded_bytes: u64,
    pub containers_with_clusters: usize,
    pub cluster_count: usize,
    pub candidate_count: usize,
    pub chunk_tag_inventory: BTreeMap<String, ChunkTagInventory>,
    pub tag_summary: BTreeMap<String, TagSummary>,
    pub entries: Vec<Entry>,
}

#[derive(Debug, Default, Serialize)]
pub struct ChunkTagInventory {
    pub container_count: usize,
    pub chunk_count: usize,
    pub total_bytes: u64,
    pub max_chunk_size: usize,
    pub max_chunk_path: String,
}

#[derive(Debug, Default, Serialize)]
pub struct TagSummary {
    pub container_count: usize,
    pub chunk_count: usize,
    pub cluster_count: usize,
    pub candidate_count: usize,
}

#[derive(Debug, Serialize)]
pub struct Entry {
    pub path: String,
    pub decoded_size: usize,
    pub chunks: Vec<ChunkEntry>,
}

#[derive(Debug, Serialize)]
pub struct ChunkEntry {
    pub chunk_index: usize,
    pub chunk_offset: usize,
    pub chunk_tag: String,
    pub chunk_size: usize,
    pub clusters: Vec<Cluster>,
}

#[derive(Debug, Serialize)]
pub struct Cluster {
    pub start_offset: usize,
    pub end_offset: usize,
    pub chunk_relative_offset: usize,
    pub byte_span: usize,
    pub string_count: usize,
    pub known_character_ratio: f64,
    pub candidates: Vec<Candidate>,
}

#[derive(Debug, Serialize)]
pub struct Candidate {
    pub offset: usize,
    pub chunk_relative_offset: usize,
    pub byte_length: usize,
    pub character_count: usize,
    pub known_character_count: usize,
    pub unknown_pair_count: usize,
    pub text: String,
}

struct Codebook {
    one: HashMap<u8, String>,
    two: HashMap<(u8, u8), String>,
}

pub fn scan(iso_path: &Path, manifest_path: &Path, codebook_path: &Path) -> Result<Report> {
    let identity = inspect::validate_source(iso_path, manifest_path)?;
    let codebook = Codebook::load(codebook_path)?;
    let mut image = Image::open(iso_path)?;
    let mdz_entries: Vec<_> = identity
        .entries
        .iter()
        .filter(|entry| !entry.is_dir && entry.path.to_ascii_uppercase().ends_with(".MDZ"))
        .collect();
    ensure!(!mdz_entries.is_empty(), "source ISO contains no MDZ files");

    let mut entries = Vec::new();
    let mut chunk_tag_inventory: BTreeMap<String, ChunkTagInventory> = BTreeMap::new();
    let mut tag_summary: BTreeMap<String, TagSummary> = BTreeMap::new();
    let mut total_decoded_bytes = 0_u64;
    for iso_entry in &mdz_entries {
        let container = image
            .read_entry(iso_entry)
            .with_context(|| format!("failed to read {}", iso_entry.path))?;
        let decoded = mdz::decode(&container)
            .with_context(|| format!("failed to decode {}", iso_entry.path))?;
        total_decoded_bytes = total_decoded_bytes
            .checked_add(decoded.len() as u64)
            .context("decoded byte total overflow")?;
        let structure = mdt::parse(&decoded)
            .with_context(|| format!("invalid decoded MDT {}", iso_entry.path))?;
        let mut chunks = Vec::new();
        let mut container_tags = std::collections::BTreeSet::new();
        for chunk in structure.chunks {
            container_tags.insert(chunk.tag.clone());
            let inventory = chunk_tag_inventory.entry(chunk.tag.clone()).or_default();
            inventory.chunk_count += 1;
            inventory.total_bytes += chunk.size as u64;
            if chunk.size > inventory.max_chunk_size {
                inventory.max_chunk_size = chunk.size;
                inventory.max_chunk_path = iso_entry.path.clone();
            }
            let bytes = &decoded[chunk.offset..chunk.offset + chunk.size];
            let clusters = scan_chunk(bytes, chunk.offset, &codebook);
            if clusters.is_empty() {
                continue;
            }
            let summary = tag_summary.entry(chunk.tag.clone()).or_default();
            summary.chunk_count += 1;
            summary.cluster_count += clusters.len();
            summary.candidate_count += clusters
                .iter()
                .map(|cluster| cluster.string_count)
                .sum::<usize>();
            chunks.push(ChunkEntry {
                chunk_index: chunk.index,
                chunk_offset: chunk.offset,
                chunk_tag: chunk.tag,
                chunk_size: chunk.size,
                clusters,
            });
        }
        for tag in container_tags {
            chunk_tag_inventory.get_mut(&tag).unwrap().container_count += 1;
        }
        if !chunks.is_empty() {
            for tag in chunks
                .iter()
                .map(|chunk| chunk.chunk_tag.as_str())
                .collect::<std::collections::BTreeSet<_>>()
            {
                tag_summary.get_mut(tag).unwrap().container_count += 1;
            }
            entries.push(Entry {
                path: iso_entry.path.clone(),
                decoded_size: decoded.len(),
                chunks,
            });
        }
    }

    let cluster_count = entries
        .iter()
        .flat_map(|entry| &entry.chunks)
        .map(|chunk| chunk.clusters.len())
        .sum();
    let candidate_count = entries
        .iter()
        .flat_map(|entry| &entry.chunks)
        .flat_map(|chunk| &chunk.clusters)
        .map(|cluster| cluster.string_count)
        .sum();
    Ok(Report {
        schema_version: 1,
        source_id: identity.source_id,
        disc: identity.disc,
        mdz_count: mdz_entries.len(),
        total_decoded_bytes,
        containers_with_clusters: entries.len(),
        cluster_count,
        candidate_count,
        chunk_tag_inventory,
        tag_summary,
        entries,
    })
}

fn scan_chunk(bytes: &[u8], chunk_offset: usize, codebook: &Codebook) -> Vec<Cluster> {
    let mut candidates = Vec::new();
    let mut start = 0;
    while start < bytes.len() {
        let Some(relative_end) = bytes[start..].iter().position(|&byte| byte == 0) else {
            break;
        };
        let end = start + relative_end;
        let segment = &bytes[start..end];
        if (MIN_BYTES..=MAX_BYTES).contains(&segment.len()) {
            if let Some(decoded) = codebook.decode(segment) {
                if decoded.character_count >= 3
                    && decoded.known_character_count as f64 / decoded.character_count as f64
                        >= MIN_KNOWN_RATIO
                    && decoded.japanese_character_count >= 2
                {
                    candidates.push(Candidate {
                        offset: chunk_offset + start,
                        chunk_relative_offset: start,
                        byte_length: segment.len(),
                        character_count: decoded.character_count,
                        known_character_count: decoded.known_character_count,
                        unknown_pair_count: decoded.unknown_pair_count,
                        text: decoded.text,
                    });
                }
            }
        }
        start = end + 1;
    }

    let mut groups: Vec<Vec<Candidate>> = Vec::new();
    for candidate in candidates {
        let contiguous = groups
            .last()
            .and_then(|group| group.last())
            .is_some_and(|previous| candidate.offset == previous.offset + previous.byte_length + 1);
        if !contiguous {
            groups.push(Vec::new());
        }
        groups.last_mut().unwrap().push(candidate);
    }

    groups
        .into_iter()
        .filter(|group| {
            let bytes = group.last().unwrap().offset + group.last().unwrap().byte_length + 1
                - group.first().unwrap().offset;
            (group.len() >= 3 && bytes >= 16)
                || (group.len() == 1
                    && group[0].character_count >= 20
                    && group[0].known_character_count * 10 >= group[0].character_count * 8)
        })
        .map(|group| {
            let start_offset = group.first().unwrap().offset;
            let end_offset = group.last().unwrap().offset + group.last().unwrap().byte_length + 1;
            let known: usize = group.iter().map(|item| item.known_character_count).sum();
            let total: usize = group.iter().map(|item| item.character_count).sum();
            Cluster {
                start_offset,
                end_offset,
                chunk_relative_offset: start_offset - chunk_offset,
                byte_span: end_offset - start_offset,
                string_count: group.len(),
                known_character_ratio: known as f64 / total as f64,
                candidates: group,
            }
        })
        .collect()
}

struct Decoded {
    text: String,
    character_count: usize,
    known_character_count: usize,
    japanese_character_count: usize,
    unknown_pair_count: usize,
}

impl Codebook {
    fn load(path: &Path) -> Result<Self> {
        let source = fs::read_to_string(path)
            .with_context(|| format!("failed to read codebook {}", path.display()))?;
        let mut one = HashMap::new();
        let mut two = HashMap::new();
        for (index, raw_line) in source.lines().enumerate().skip(1) {
            let line = raw_line.trim();
            if line.is_empty() {
                continue;
            }
            let mut columns = line.splitn(3, ',');
            let encoded = columns.next().context("missing encoded_hex")?.trim();
            let character = columns.next().context("missing character")?.to_owned();
            let bytes = encoded
                .split_ascii_whitespace()
                .map(|value| u8::from_str_radix(value, 16))
                .collect::<std::result::Result<Vec<_>, _>>()
                .with_context(|| format!("invalid codebook hex on line {}", index + 1))?;
            match bytes.as_slice() {
                [value] => {
                    one.insert(*value, character);
                }
                [first, second] => {
                    two.insert((*first, *second), character);
                }
                _ => anyhow::bail!("unsupported code width on line {}", index + 1),
            }
        }
        ensure!(!one.is_empty() && !two.is_empty(), "codebook is empty");
        Ok(Self { one, two })
    }

    fn decode(&self, bytes: &[u8]) -> Option<Decoded> {
        let mut text = String::new();
        let mut cursor = 0;
        let mut character_count = 0;
        let mut known_character_count = 0;
        let mut japanese_character_count = 0;
        let mut unknown_pair_count = 0;
        while cursor < bytes.len() {
            let first = bytes[cursor];
            if cursor + 1 < bytes.len() && (0xf0..=0xf9).contains(&bytes[cursor + 1]) {
                let second = bytes[cursor + 1];
                if let Some(character) = self.two.get(&(first, second)) {
                    text.push_str(character);
                    known_character_count += 1;
                    japanese_character_count +=
                        character.chars().filter(|&c| is_japanese(c)).count();
                } else {
                    text.push_str(&format!("<{first:02X}{second:02X}>"));
                    unknown_pair_count += 1;
                }
                cursor += 2;
            } else {
                let character = self.one.get(&first)?;
                text.push_str(character);
                known_character_count += 1;
                japanese_character_count += character.chars().filter(|&c| is_japanese(c)).count();
                cursor += 1;
            }
            character_count += 1;
        }
        Some(Decoded {
            text,
            character_count,
            known_character_count,
            japanese_character_count,
            unknown_pair_count,
        })
    }
}

fn is_japanese(character: char) -> bool {
    matches!(
        character,
        '\u{3040}'..='\u{30ff}' | '\u{3400}'..='\u{4dbf}' | '\u{4e00}'..='\u{9fff}'
    )
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use super::{Codebook, scan_chunk};

    #[test]
    fn finds_contiguous_custom_encoded_strings() {
        let codebook = Codebook {
            one: HashMap::from([
                (0x59, "う".to_owned()),
                (0x62, "く".to_owned()),
                (0x70, "そ".to_owned()),
                (0x96, "や".to_owned()),
            ]),
            two: HashMap::from([((0x36, 0xf0), "攻".to_owned())]),
        };
        let bytes = [
            0x96, 0x62, 0x70, 0x59, 0, 0x96, 0x62, 0x70, 0x59, 0, 0x36, 0xf0, 0x96, 0x62, 0, 0x96,
            0x62, 0x70, 0x59, 0,
        ];

        let clusters = scan_chunk(&bytes, 0x800, &codebook);

        assert_eq!(clusters.len(), 1);
        assert_eq!(clusters[0].string_count, 4);
        assert_eq!(clusters[0].candidates[0].text, "やくそう");
        assert_eq!(clusters[0].candidates[2].text, "攻やく");
    }
}
