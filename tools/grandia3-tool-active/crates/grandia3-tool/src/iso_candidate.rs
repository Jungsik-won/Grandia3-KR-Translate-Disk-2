use std::fs::{self, File};
use std::io::{BufReader, BufWriter, Read, Seek, SeekFrom, Write};
use std::ops::Range;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::inspect;
use crate::iso9660::{Entry, Image};
use crate::mdz;

const SECTOR_SIZE: u64 = 2048;
const BUFFER_SIZE: usize = 4 * 1024 * 1024;
const OUTPUT_NAME: &str = "disc1-research.iso";

#[derive(Debug, Deserialize)]
struct Plan {
    schema_version: u32,
    status: String,
    source_id: String,
    sector_size: u64,
    field: FilePlan,
    mdz: FilePlan,
    directory_record: DirectoryRecordPlan,
    relocation: RelocationPlan,
}

#[derive(Debug, Deserialize)]
struct FilePlan {
    path: String,
    extent: u32,
    size: u32,
    sha256: String,
}

#[derive(Debug, Deserialize)]
struct DirectoryRecordPlan {
    offset: u64,
    size: usize,
    sha256: String,
    identifier: String,
}

#[derive(Debug, Deserialize)]
struct RelocationPlan {
    extent: u32,
    zero_extent_end: u32,
}

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub status: &'static str,
    pub source_id: String,
    pub source_size: u64,
    pub source_sha256: String,
    pub plan_sha256: String,
    pub output_size: u64,
    pub output_sha256: String,
    pub changed_byte_count: u64,
    pub field_sha256: String,
    pub mdz_sha256: String,
    pub decoded_mdt_size: usize,
    pub decoded_mdt_sha256: String,
    pub relocated_extent: u32,
    pub relocated_allocation_sectors: u32,
    pub writes: Vec<WriteReport>,
    pub staged_iso9660_verified: bool,
}

#[derive(Debug, Serialize)]
pub struct WriteReport {
    pub label: String,
    pub offset: u64,
    pub size: usize,
    pub changed_byte_count: usize,
}

struct DeclaredWrite {
    label: &'static str,
    offset: u64,
    bytes: Vec<u8>,
}

impl DeclaredWrite {
    fn range(&self) -> Range<u64> {
        self.offset..self.offset + self.bytes.len() as u64
    }
}

pub fn build(
    source_iso: &Path,
    field_candidate: &Path,
    mdz_candidate: &Path,
    plan_path: &Path,
    manifest_path: &Path,
    output_dir: &Path,
) -> Result<Report> {
    ensure!(
        !output_dir.exists(),
        "output directory already exists: {}",
        output_dir.display()
    );
    let plan_bytes = fs::read(plan_path)
        .with_context(|| format!("failed to read write plan {}", plan_path.display()))?;
    let plan: Plan = serde_json::from_slice(&plan_bytes)
        .with_context(|| format!("invalid write plan {}", plan_path.display()))?;
    ensure!(plan.schema_version == 1, "unsupported write plan schema");
    ensure!(
        plan.status == "research_only_not_product_input",
        "write plan is not marked research-only"
    );
    ensure!(plan.sector_size == SECTOR_SIZE, "sector size mismatch");

    let identity = inspect::validate_source(source_iso, manifest_path)?;
    ensure!(
        identity.source_id == plan.source_id,
        "write plan source ID mismatch"
    );
    let source_size = fs::metadata(source_iso)?.len();
    let mut image = Image::open(source_iso)?;
    validate_file_plan(&mut image, &identity.entries, &plan.field)?;
    validate_file_plan(&mut image, &identity.entries, &plan.mdz)?;

    let field = fs::read(field_candidate)
        .with_context(|| format!("failed to read {}", field_candidate.display()))?;
    ensure!(
        field.len() == plan.field.size as usize,
        "FIELD.BIN candidate size mismatch"
    );
    let field_sha256 = sha256(&field);

    let mdz_bytes = fs::read(mdz_candidate)
        .with_context(|| format!("failed to read {}", mdz_candidate.display()))?;
    ensure!(!mdz_bytes.is_empty(), "GR3.MDZ candidate is empty");
    let mdz_sha256 = sha256(&mdz_bytes);
    let decoded_mdt = mdz::decode(&mdz_bytes).context("candidate GR3.MDZ failed to decode")?;
    let decoded_mdt_sha256 = sha256(&decoded_mdt);

    let original_record = read_exact_at(
        source_iso,
        plan.directory_record.offset,
        plan.directory_record.size,
    )?;
    ensure_hash(
        &original_record,
        &plan.directory_record.sha256,
        "directory record",
    )?;
    validate_directory_record(&original_record, &plan)?;

    let allocation_sectors = u32::try_from((mdz_bytes.len() as u64).div_ceil(SECTOR_SIZE))
        .context("relocated MDZ sector count overflow")?;
    let relocation_end = plan
        .relocation
        .extent
        .checked_add(allocation_sectors)
        .context("relocation extent overflow")?;
    ensure!(
        relocation_end <= plan.relocation.zero_extent_end,
        "candidate MDZ exceeds declared zero extent range"
    );
    ensure_relocation_unallocated(&identity.entries, plan.relocation.extent, relocation_end)?;
    let relocation_offset = u64::from(plan.relocation.extent) * SECTOR_SIZE;
    let allocation_size = u64::from(allocation_sectors) * SECTOR_SIZE;
    ensure!(
        relocation_offset + allocation_size <= source_size,
        "relocation allocation exceeds source image"
    );
    ensure_zero_region(source_iso, relocation_offset, allocation_size)?;

    let mut updated_record = original_record.clone();
    write_both_endian_u32(&mut updated_record, 2, plan.relocation.extent)?;
    write_both_endian_u32(
        &mut updated_record,
        10,
        u32::try_from(mdz_bytes.len()).context("candidate MDZ exceeds ISO size field")?,
    )?;
    let mut writes = vec![
        DeclaredWrite {
            label: "ISO directory record for SYS/GR3.MDZ",
            offset: plan.directory_record.offset,
            bytes: updated_record,
        },
        DeclaredWrite {
            label: "FIELD.BIN candidate",
            offset: u64::from(plan.field.extent) * SECTOR_SIZE,
            bytes: field,
        },
        DeclaredWrite {
            label: "relocated SYS/GR3.MDZ candidate",
            offset: relocation_offset,
            bytes: mdz_bytes,
        },
    ];
    writes.sort_by_key(|write| write.offset);
    validate_writes(&writes, source_size)?;

    let staging_dir = staging_path(output_dir)?;
    ensure!(
        !staging_dir.exists(),
        "staging directory already exists: {}",
        staging_dir.display()
    );
    let result = (|| -> Result<Report> {
        fs::create_dir_all(&staging_dir)?;
        let staged_iso = staging_dir.join(OUTPUT_NAME);
        let (output_sha256, changed_byte_count, write_reports) =
            compose_iso(source_iso, &staged_iso, &writes, &identity.sha256)?;
        verify_staged(
            &staged_iso,
            &plan,
            &field_sha256,
            &mdz_sha256,
            &decoded_mdt_sha256,
        )?;
        let report = Report {
            schema_version: 1,
            status: "research_only_not_product_input",
            source_id: identity.source_id,
            source_size,
            source_sha256: identity.sha256,
            plan_sha256: sha256(&plan_bytes),
            output_size: source_size,
            output_sha256,
            changed_byte_count,
            field_sha256,
            mdz_sha256,
            decoded_mdt_size: decoded_mdt.len(),
            decoded_mdt_sha256,
            relocated_extent: plan.relocation.extent,
            relocated_allocation_sectors: allocation_sectors,
            writes: write_reports,
            staged_iso9660_verified: true,
        };
        let mut manifest = serde_json::to_vec_pretty(&report)?;
        manifest.push(b'\n');
        write_synced(&staging_dir.join("manifest.json"), &manifest)?;
        fs::rename(&staging_dir, output_dir)
            .with_context(|| format!("failed to publish ISO candidate {}", output_dir.display()))?;
        Ok(report)
    })();
    if result.is_err() {
        let _ = fs::remove_dir_all(&staging_dir);
    }
    result
}

fn validate_file_plan(image: &mut Image, entries: &[Entry], plan: &FilePlan) -> Result<()> {
    let entry = find_entry(entries, &plan.path)?;
    ensure!(entry.extent == plan.extent, "{} extent mismatch", plan.path);
    ensure!(entry.size == plan.size, "{} size mismatch", plan.path);
    let actual = image.hash_entry(entry)?;
    ensure!(
        actual.eq_ignore_ascii_case(&plan.sha256),
        "{} SHA-256 mismatch",
        plan.path
    );
    Ok(())
}

fn find_entry<'a>(entries: &'a [Entry], path: &str) -> Result<&'a Entry> {
    entries
        .iter()
        .find(|entry| !entry.is_dir && entry.path.eq_ignore_ascii_case(path))
        .with_context(|| format!("ISO entry {path} is missing"))
}

fn validate_directory_record(bytes: &[u8], plan: &Plan) -> Result<()> {
    ensure!(
        bytes.len() == plan.directory_record.size,
        "record size mismatch"
    );
    ensure!(
        usize::from(bytes[0]) == bytes.len(),
        "record length mismatch"
    );
    ensure!(
        read_both_endian_u32(bytes, 2)? == plan.mdz.extent,
        "record extent mismatch"
    );
    ensure!(
        read_both_endian_u32(bytes, 10)? == plan.mdz.size,
        "record file size mismatch"
    );
    let name_len = usize::from(bytes[32]);
    let name = bytes
        .get(33..33 + name_len)
        .context("record name truncated")?;
    ensure!(
        name == plan.directory_record.identifier.as_bytes(),
        "record identifier mismatch"
    );
    Ok(())
}

fn ensure_relocation_unallocated(entries: &[Entry], start: u32, end: u32) -> Result<()> {
    for entry in entries {
        let entry_sectors = u32::try_from(u64::from(entry.size).div_ceil(SECTOR_SIZE))?;
        let entry_end = entry
            .extent
            .checked_add(entry_sectors)
            .context("entry extent overflow")?;
        ensure!(
            end <= entry.extent || start >= entry_end,
            "relocation overlaps ISO entry {}",
            entry.path
        );
    }
    Ok(())
}

fn ensure_zero_region(path: &Path, offset: u64, size: u64) -> Result<()> {
    let mut file = File::open(path)?;
    file.seek(SeekFrom::Start(offset))?;
    let mut remaining = size;
    let mut buffer = vec![0_u8; BUFFER_SIZE];
    let mut cursor = offset;
    while remaining != 0 {
        let count = usize::try_from(remaining.min(buffer.len() as u64))?;
        file.read_exact(&mut buffer[..count])?;
        if let Some(index) = buffer[..count].iter().position(|&byte| byte != 0) {
            anyhow::bail!(
                "relocation region is nonzero at offset {:#x}",
                cursor + index as u64
            );
        }
        cursor += count as u64;
        remaining -= count as u64;
    }
    Ok(())
}

fn validate_writes(writes: &[DeclaredWrite], source_size: u64) -> Result<()> {
    ensure!(!writes.is_empty(), "write plan is empty");
    for write in writes {
        ensure!(!write.bytes.is_empty(), "declared write is empty");
        ensure!(
            write.range().end <= source_size,
            "declared write exceeds ISO"
        );
    }
    for pair in writes.windows(2) {
        ensure!(
            pair[0].range().end <= pair[1].range().start,
            "declared ISO writes overlap"
        );
    }
    Ok(())
}

fn compose_iso(
    source_path: &Path,
    output_path: &Path,
    writes: &[DeclaredWrite],
    expected_source_sha256: &str,
) -> Result<(String, u64, Vec<WriteReport>)> {
    let source = File::open(source_path)?;
    let mut reader = BufReader::with_capacity(BUFFER_SIZE, source);
    let output = File::create(output_path)?;
    let mut writer = BufWriter::with_capacity(BUFFER_SIZE, output);
    let mut source_hasher = Sha256::new();
    let mut output_hasher = Sha256::new();
    let mut buffer = vec![0_u8; BUFFER_SIZE];
    let mut position = 0_u64;
    let mut changed_counts = vec![0_usize; writes.len()];
    loop {
        let count = reader.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        source_hasher.update(&buffer[..count]);
        let original = buffer[..count].to_vec();
        apply_to_chunk(&mut buffer[..count], position, writes)?;
        for (index, write) in writes.iter().enumerate() {
            let chunk = position..position + count as u64;
            let overlap_start = chunk.start.max(write.range().start);
            let overlap_end = chunk.end.min(write.range().end);
            if overlap_start < overlap_end {
                let start = usize::try_from(overlap_start - position)?;
                let end = usize::try_from(overlap_end - position)?;
                changed_counts[index] += original[start..end]
                    .iter()
                    .zip(&buffer[start..end])
                    .filter(|(left, right)| left != right)
                    .count();
            }
        }
        output_hasher.update(&buffer[..count]);
        writer.write_all(&buffer[..count])?;
        position += count as u64;
    }
    writer.flush()?;
    writer.get_ref().sync_all()?;
    let source_sha256 = format!("{:x}", source_hasher.finalize());
    ensure!(
        source_sha256.eq_ignore_ascii_case(expected_source_sha256),
        "source ISO changed while composing output"
    );
    let write_reports: Vec<_> = writes
        .iter()
        .zip(changed_counts)
        .map(|(write, changed_byte_count)| WriteReport {
            label: write.label.to_owned(),
            offset: write.offset,
            size: write.bytes.len(),
            changed_byte_count,
        })
        .collect();
    let changed_byte_count = write_reports
        .iter()
        .map(|write| write.changed_byte_count as u64)
        .sum();
    Ok((
        format!("{:x}", output_hasher.finalize()),
        changed_byte_count,
        write_reports,
    ))
}

fn apply_to_chunk(chunk: &mut [u8], chunk_offset: u64, writes: &[DeclaredWrite]) -> Result<()> {
    let chunk_end = chunk_offset + chunk.len() as u64;
    for write in writes {
        let start = chunk_offset.max(write.range().start);
        let end = chunk_end.min(write.range().end);
        if start >= end {
            continue;
        }
        let chunk_start = usize::try_from(start - chunk_offset)?;
        let chunk_end = usize::try_from(end - chunk_offset)?;
        let write_start = usize::try_from(start - write.offset)?;
        let write_end = write_start + (chunk_end - chunk_start);
        chunk[chunk_start..chunk_end].copy_from_slice(&write.bytes[write_start..write_end]);
    }
    Ok(())
}

fn verify_staged(
    path: &Path,
    plan: &Plan,
    field_sha256: &str,
    mdz_sha256: &str,
    decoded_mdt_sha256: &str,
) -> Result<()> {
    let mut image = Image::open(path)?;
    let entries = image.entries()?;
    let field = find_entry(&entries, &plan.field.path)?;
    ensure!(
        field.extent == plan.field.extent,
        "staged FIELD extent changed"
    );
    ensure!(
        image.hash_entry(field)? == field_sha256,
        "staged FIELD hash mismatch"
    );
    let mdz_entry = find_entry(&entries, &plan.mdz.path)?;
    ensure!(
        mdz_entry.extent == plan.relocation.extent,
        "staged MDZ extent mismatch"
    );
    ensure!(
        mdz_entry.size as usize > plan.mdz.size as usize,
        "staged MDZ was not expanded"
    );
    ensure!(
        image.hash_entry(mdz_entry)? == mdz_sha256,
        "staged MDZ hash mismatch"
    );
    let container = image.read_entry(mdz_entry)?;
    let decoded = mdz::decode(&container)?;
    ensure!(
        sha256(&decoded) == decoded_mdt_sha256,
        "staged MDZ decoded hash mismatch"
    );
    Ok(())
}

fn read_exact_at(path: &Path, offset: u64, size: usize) -> Result<Vec<u8>> {
    let mut file = File::open(path)?;
    file.seek(SeekFrom::Start(offset))?;
    let mut bytes = vec![0_u8; size];
    file.read_exact(&mut bytes)?;
    Ok(bytes)
}

fn read_both_endian_u32(bytes: &[u8], offset: usize) -> Result<u32> {
    let little = u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .context("LE u32 truncated")?
            .try_into()?,
    );
    let big = u32::from_be_bytes(
        bytes
            .get(offset + 4..offset + 8)
            .context("BE u32 truncated")?
            .try_into()?,
    );
    ensure!(little == big, "both-endian integer copies disagree");
    Ok(little)
}

fn write_both_endian_u32(bytes: &mut [u8], offset: usize, value: u32) -> Result<()> {
    bytes
        .get_mut(offset..offset + 4)
        .context("LE u32 truncated")?
        .copy_from_slice(&value.to_le_bytes());
    bytes
        .get_mut(offset + 4..offset + 8)
        .context("BE u32 truncated")?
        .copy_from_slice(&value.to_be_bytes());
    Ok(())
}

fn ensure_hash(bytes: &[u8], expected: &str, label: &str) -> Result<()> {
    let actual = sha256(bytes);
    ensure!(
        actual.eq_ignore_ascii_case(expected),
        "{label} SHA-256 mismatch"
    );
    Ok(())
}

fn staging_path(output_dir: &Path) -> Result<PathBuf> {
    let name = output_dir
        .file_name()
        .context("output directory has no final component")?;
    let mut staging_name = name.to_os_string();
    staging_name.push(format!(".tmp-{}", std::process::id()));
    Ok(output_dir.with_file_name(staging_name))
}

fn write_synced(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut file = File::create(path)?;
    file.write_all(bytes)?;
    file.sync_all()?;
    Ok(())
}

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[cfg(test)]
mod tests {
    use super::{DeclaredWrite, apply_to_chunk, validate_writes};

    #[test]
    fn applies_only_overlapping_write_bytes() {
        let writes = [DeclaredWrite {
            label: "test",
            offset: 3,
            bytes: vec![9, 8, 7, 6],
        }];
        let mut chunk = [0_u8; 4];

        apply_to_chunk(&mut chunk, 5, &writes).unwrap();

        assert_eq!(chunk, [7, 6, 0, 0]);
    }

    #[test]
    fn rejects_overlapping_writes() {
        let writes = [
            DeclaredWrite {
                label: "left",
                offset: 2,
                bytes: vec![1; 4],
            },
            DeclaredWrite {
                label: "right",
                offset: 5,
                bytes: vec![2; 4],
            },
        ];

        assert!(validate_writes(&writes, 16).is_err());
    }
}
