use std::fs;
use std::path::Path;

use anyhow::{Context, Result, ensure};
use serde::Serialize;
use sha2::{Digest, Sha256};

const MDT_HEADER_SIZE: usize = 0x80;
const CHUNK_ALIGNMENT: usize = 0x80;

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub file_size: usize,
    pub sha256: String,
    pub chunk_count: usize,
    pub root_instance_count: u32,
    pub chunks: Vec<Chunk>,
}

#[derive(Debug, Serialize)]
pub struct Chunk {
    pub index: usize,
    pub offset: usize,
    pub tag: String,
    pub size: usize,
    pub instance_count: u32,
    pub sha256: String,
    pub markers: Vec<Marker>,
}

#[derive(Debug, Serialize)]
pub struct Marker {
    pub offset: usize,
    pub text: String,
}

pub fn inspect(path: &Path) -> Result<Report> {
    let bytes = fs::read(path).with_context(|| format!("failed to read {}", path.display()))?;
    parse(&bytes).with_context(|| format!("invalid MDT structure in {}", path.display()))
}

pub(crate) fn parse(bytes: &[u8]) -> Result<Report> {
    ensure!(
        bytes.len() >= MDT_HEADER_SIZE,
        "MDT is smaller than its header"
    );
    ensure!(
        bytes[8..MDT_HEADER_SIZE].iter().all(|&byte| byte == 0),
        "MDT reserved header bytes are nonzero"
    );
    let chunk_count = read_u32(bytes, 0)? as usize;
    let root_instance_count = read_u32(bytes, 4)?;
    ensure!(
        (1..=4096).contains(&chunk_count),
        "invalid MDT chunk count {chunk_count}"
    );

    let mut chunks = Vec::with_capacity(chunk_count);
    let mut offset = MDT_HEADER_SIZE;
    for index in 0..chunk_count {
        ensure!(
            offset.is_multiple_of(CHUNK_ALIGNMENT),
            "chunk {index} is not aligned"
        );
        ensure!(
            offset + MDT_HEADER_SIZE <= bytes.len(),
            "chunk {index} header exceeds the MDT"
        );
        let tag = read_u32(bytes, offset)?;
        let size = read_u32(bytes, offset + 4)? as usize;
        let instance_count = read_u32(bytes, offset + 12)?;
        ensure!(
            size >= MDT_HEADER_SIZE,
            "chunk {index} is smaller than its header"
        );
        ensure!(
            size.is_multiple_of(CHUNK_ALIGNMENT),
            "chunk {index} size is not aligned"
        );
        let end = offset
            .checked_add(size)
            .context("MDT chunk size overflow")?;
        ensure!(end <= bytes.len(), "chunk {index} exceeds the MDT");
        let chunk_bytes = &bytes[offset..end];
        chunks.push(Chunk {
            index,
            offset,
            tag: format!("0x{tag:08x}"),
            size,
            instance_count,
            sha256: format!("{:x}", Sha256::digest(chunk_bytes)),
            markers: find_markers(chunk_bytes),
        });
        offset = end;
    }
    ensure!(
        offset == bytes.len(),
        "{} trailing bytes follow the final MDT chunk",
        bytes.len() - offset
    );

    Ok(Report {
        schema_version: 1,
        file_size: bytes.len(),
        sha256: format!("{:x}", Sha256::digest(bytes)),
        chunk_count,
        root_instance_count,
        chunks,
    })
}

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32> {
    let value = bytes
        .get(offset..offset + 4)
        .context("truncated MDT integer")?;
    Ok(u32::from_le_bytes(value.try_into().unwrap()))
}

fn find_markers(chunk: &[u8]) -> Vec<Marker> {
    let mut markers = Vec::new();
    for (needle, text) in [(b"GTXD".as_slice(), "GTXD"), (b"PTB\0".as_slice(), "PTB")] {
        let mut cursor = 0;
        while let Some(relative) = chunk[cursor..]
            .windows(needle.len())
            .position(|window| window == needle)
        {
            let offset = cursor + relative;
            markers.push(Marker {
                offset,
                text: text.to_owned(),
            });
            cursor = offset + needle.len();
        }
    }
    markers.sort_by_key(|marker| marker.offset);
    markers
}

#[cfg(test)]
mod tests {
    use super::{CHUNK_ALIGNMENT, MDT_HEADER_SIZE, parse};

    #[test]
    fn parses_size_delimited_chunks() {
        let mut bytes = vec![0; MDT_HEADER_SIZE + CHUNK_ALIGNMENT * 2];
        bytes[0..4].copy_from_slice(&2_u32.to_le_bytes());
        bytes[4..8].copy_from_slice(&1_u32.to_le_bytes());
        for (index, tag) in [0xa000_1000_u32, 0xb000_2000].into_iter().enumerate() {
            let offset = MDT_HEADER_SIZE + index * CHUNK_ALIGNMENT;
            bytes[offset..offset + 4].copy_from_slice(&tag.to_le_bytes());
            bytes[offset + 4..offset + 8].copy_from_slice(&(CHUNK_ALIGNMENT as u32).to_le_bytes());
            bytes[offset + 12..offset + 16].copy_from_slice(&1_u32.to_le_bytes());
        }

        let report = parse(&bytes).unwrap();

        assert_eq!(report.chunk_count, 2);
        assert_eq!(report.chunks[1].offset, 0x100);
        assert_eq!(report.chunks[1].tag, "0xb0002000");
    }

    #[test]
    fn rejects_trailing_or_misaligned_data() {
        let mut bytes = vec![0; MDT_HEADER_SIZE + CHUNK_ALIGNMENT + 1];
        bytes[0..4].copy_from_slice(&1_u32.to_le_bytes());
        bytes[MDT_HEADER_SIZE..MDT_HEADER_SIZE + 4].copy_from_slice(&0xa000_1000_u32.to_le_bytes());
        bytes[MDT_HEADER_SIZE + 4..MDT_HEADER_SIZE + 8]
            .copy_from_slice(&(CHUNK_ALIGNMENT as u32).to_le_bytes());

        assert!(parse(&bytes).is_err());
    }
}
