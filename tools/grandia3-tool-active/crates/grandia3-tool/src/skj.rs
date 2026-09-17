use std::collections::{BTreeMap, HashSet};
use std::fs;
use std::path::Path;

use anyhow::{Context, Result, ensure};
use serde::Serialize;
use sha2::{Digest, Sha256};

const DIRECT_CONTROL_CODE_COUNT: usize = 32;

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub file_size: usize,
    pub sha256: String,
    pub code_count: usize,
    pub unique_code_count: usize,
    pub duplicate_code_values: usize,
    pub direct_control_code_count: usize,
    pub one_byte_code_count: usize,
    pub two_byte_code_count: usize,
    pub cr_count: usize,
    pub lf_count: usize,
    pub lead_bytes: Vec<LeadByte>,
}

#[derive(Debug, Serialize)]
pub struct LeadByte {
    pub value: String,
    pub code_count: usize,
}

#[derive(Clone, Debug, Eq, PartialEq)]
pub struct Record {
    pub index: usize,
    pub file_offset: usize,
    pub code: u16,
    pub direct_control: bool,
}

pub fn inspect(path: &Path) -> Result<Report> {
    let bytes = fs::read(path).with_context(|| format!("failed to read {}", path.display()))?;
    parse(&bytes).with_context(|| format!("invalid SKJ structure in {}", path.display()))
}

pub fn records(path: &Path) -> Result<Vec<Record>> {
    let bytes = fs::read(path).with_context(|| format!("failed to read {}", path.display()))?;
    parse_records(&bytes).with_context(|| format!("invalid SKJ structure in {}", path.display()))
}

fn parse(bytes: &[u8]) -> Result<Report> {
    ensure!(!bytes.is_empty(), "SKJ file is empty");
    let records = parse_records(bytes)?;
    let codes: Vec<_> = records.iter().map(|record| record.code).collect();
    let mut one_byte_code_count = 0;
    let mut two_byte_code_count = 0;
    let direct_control_code_count = records
        .iter()
        .filter(|record| record.direct_control)
        .count();
    let (cr_count, lf_count) = line_break_counts(bytes)?;
    let mut lead_counts = BTreeMap::new();

    for record in records.iter().filter(|record| !record.direct_control) {
        let first = (record.code >> 8) as u8;
        if record.code < 0x80 {
            one_byte_code_count += 1;
        } else {
            two_byte_code_count += 1;
            *lead_counts.entry(first).or_insert(0) += 1;
        }
    }

    let unique_codes: HashSet<_> = codes.iter().copied().collect();
    let duplicate_code_values = unique_codes
        .iter()
        .filter(|code| codes.iter().filter(|candidate| candidate == code).count() > 1)
        .count();

    Ok(Report {
        schema_version: 2,
        file_size: bytes.len(),
        sha256: format!("{:x}", Sha256::digest(bytes)),
        code_count: codes.len(),
        unique_code_count: unique_codes.len(),
        duplicate_code_values,
        direct_control_code_count,
        one_byte_code_count,
        two_byte_code_count,
        cr_count,
        lf_count,
        lead_bytes: lead_counts
            .into_iter()
            .map(|(value, code_count)| LeadByte {
                value: format!("0x{value:02x}"),
                code_count,
            })
            .collect(),
    })
}

fn line_break_counts(bytes: &[u8]) -> Result<(usize, usize)> {
    let mut cursor = 0;
    let mut cr_count = 0;
    let mut lf_count = 0;
    while cursor < bytes.len() {
        match bytes[cursor] {
            b'\r' => {
                cr_count += 1;
                cursor += 1;
            }
            b'\n' => {
                lf_count += 1;
                cursor += 1;
            }
            _ => {
                ensure!(cursor + 1 < bytes.len(), "truncated SKJ record");
                cursor += 2;
            }
        }
    }
    Ok((cr_count, lf_count))
}

fn parse_records(bytes: &[u8]) -> Result<Vec<Record>> {
    ensure!(!bytes.is_empty(), "SKJ file is empty");
    let mut cursor = 0;
    let mut records = Vec::new();
    while cursor < bytes.len() {
        let first = bytes[cursor];
        if matches!(first, b'\r' | b'\n') {
            cursor += 1;
            continue;
        }
        let file_offset = cursor;
        let second = *bytes
            .get(cursor + 1)
            .with_context(|| format!("truncated SKJ record at offset {:#x}", cursor + 1))?;
        let direct_control = records.len() < DIRECT_CONTROL_CODE_COUNT;
        let code = if direct_control {
            records.len() as u16
        } else if first < 0x80 {
            u16::from(first)
        } else {
            u16::from_be_bytes([first, second])
        };
        records.push(Record {
            index: records.len(),
            file_offset,
            code,
            direct_control,
        });
        cursor += 2;
    }
    Ok(records)
}

#[cfg(test)]
mod tests {
    use super::{DIRECT_CONTROL_CODE_COUNT, parse, parse_records};

    #[test]
    fn parses_game_style_codes_and_line_breaks() {
        let mut bytes = vec![0x81; DIRECT_CONTROL_CODE_COUNT * 2];
        bytes.extend_from_slice(&[b'\r', b'\n', b'A', 0, 0x82, 0xa0, 0x82, 0xa0]);
        let report = parse(&bytes).unwrap();

        assert_eq!(report.code_count, 35);
        assert_eq!(report.unique_code_count, 34);
        assert_eq!(report.duplicate_code_values, 1);
        assert_eq!(report.direct_control_code_count, 32);
        assert_eq!(report.one_byte_code_count, 1);
        assert_eq!(report.two_byte_code_count, 2);
        assert_eq!(report.cr_count, 1);
        assert_eq!(report.lf_count, 1);
        let records = parse_records(&bytes).unwrap();
        assert_eq!(records[32].file_offset, 66);
        assert_eq!(records[32].code, u16::from(b'A'));
    }

    #[test]
    fn rejects_a_truncated_record() {
        assert!(parse(&[0x82]).is_err());
    }
}
