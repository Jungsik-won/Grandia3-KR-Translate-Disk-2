use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

const ALIGNMENT: usize = 0x80;

#[derive(Debug, Deserialize)]
struct Config {
    schema_version: u32,
    source_virtual_path: String,
    decoded_size: usize,
    decoded_sha256: String,
    chunk: ChunkConfig,
    bundle: BundleConfig,
    resources: Vec<ResourceConfig>,
}

#[derive(Debug, Deserialize)]
struct ChunkConfig {
    index: usize,
    offset: usize,
    tag: String,
    size: usize,
}

#[derive(Debug, Deserialize)]
struct BundleConfig {
    offset: usize,
    tag: String,
    size: usize,
    member_table_offset: usize,
    member_data_offset: usize,
}

#[derive(Debug, Deserialize)]
struct ResourceConfig {
    resource_id: String,
    file_name: String,
    size: usize,
    sha256: String,
}

#[derive(Debug, Deserialize)]
struct OverlayManifest {
    schema_version: u32,
    inputs: Vec<OverlayResource>,
    outputs: Vec<OverlayResource>,
}

#[derive(Debug, Deserialize)]
struct OverlayResource {
    file_name: String,
    size: usize,
    sha256: String,
}

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub source_virtual_path: String,
    pub decoded_size: usize,
    pub decoded_sha256: String,
    pub chunk_index: usize,
    pub chunk_offset: usize,
    pub chunk_tag: String,
    pub chunk_size: usize,
    pub resources: Vec<ExtractedResource>,
}

#[derive(Debug, Serialize)]
pub struct ExtractedResource {
    pub resource_id: String,
    pub file_name: String,
    pub offset: usize,
    pub size: usize,
    pub sha256: String,
}

#[derive(Debug, Serialize)]
pub struct RepackReport {
    pub schema_version: u32,
    pub status: &'static str,
    pub source_virtual_path: String,
    pub original_size: usize,
    pub original_sha256: String,
    pub output_size: usize,
    pub output_sha256: String,
    pub overlay_manifest_sha256: String,
    pub changed_byte_count: usize,
    pub resources: Vec<RepackedResource>,
}

#[derive(Debug, Serialize)]
pub struct RepackedResource {
    pub resource_id: String,
    pub file_name: String,
    pub offset: usize,
    pub size: usize,
    pub original_sha256: String,
    pub output_sha256: String,
    pub changed_byte_count: usize,
}

struct Validated {
    report: Report,
    ranges: Vec<(usize, usize)>,
}

pub fn extract(input_path: &Path, config_path: &Path, output_dir: &Path) -> Result<Report> {
    ensure!(
        !output_dir.exists(),
        "output directory already exists: {}",
        output_dir.display()
    );
    let input = fs::read(input_path)
        .with_context(|| format!("failed to read decoded MDT {}", input_path.display()))?;
    let config_bytes = fs::read(config_path).with_context(|| {
        format!(
            "failed to read font resource config {}",
            config_path.display()
        )
    })?;
    let config: Config = serde_json::from_slice(&config_bytes)
        .with_context(|| format!("invalid font resource config {}", config_path.display()))?;
    let validated = validate(&input, &config)?;

    let staging_dir = staging_path(output_dir)?;
    ensure!(
        !staging_dir.exists(),
        "staging directory already exists: {}",
        staging_dir.display()
    );
    let write_result = (|| -> Result<()> {
        fs::create_dir_all(&staging_dir).with_context(|| {
            format!(
                "failed to create staging directory {}",
                staging_dir.display()
            )
        })?;
        for (resource, &(start, end)) in validated.report.resources.iter().zip(&validated.ranges) {
            write_synced(
                &staging_dir.join(&resource.file_name),
                input
                    .get(start..end)
                    .context("validated font range vanished")?,
            )?;
        }
        let mut manifest = serde_json::to_vec_pretty(&validated.report)?;
        manifest.push(b'\n');
        write_synced(&staging_dir.join("manifest.json"), &manifest)?;
        fs::rename(&staging_dir, output_dir).with_context(|| {
            format!(
                "failed to publish extracted resources {}",
                output_dir.display()
            )
        })?;
        Ok(())
    })();
    if write_result.is_err() {
        let _ = fs::remove_dir_all(&staging_dir);
    }
    write_result?;
    Ok(validated.report)
}

pub fn repack(
    input_path: &Path,
    config_path: &Path,
    overlay_dir: &Path,
    output_dir: &Path,
) -> Result<RepackReport> {
    ensure!(
        !output_dir.exists(),
        "output directory already exists: {}",
        output_dir.display()
    );
    let input = fs::read(input_path)
        .with_context(|| format!("failed to read decoded MDT {}", input_path.display()))?;
    let config_bytes = fs::read(config_path).with_context(|| {
        format!(
            "failed to read font resource config {}",
            config_path.display()
        )
    })?;
    let config: Config = serde_json::from_slice(&config_bytes)
        .with_context(|| format!("invalid font resource config {}", config_path.display()))?;
    let validated = validate(&input, &config)?;

    let overlay_manifest_path = overlay_dir.join("manifest.json");
    let overlay_manifest_bytes = fs::read(&overlay_manifest_path).with_context(|| {
        format!(
            "failed to read font overlay manifest {}",
            overlay_manifest_path.display()
        )
    })?;
    let overlay_manifest: OverlayManifest = serde_json::from_slice(&overlay_manifest_bytes)
        .with_context(|| {
            format!(
                "invalid font overlay manifest {}",
                overlay_manifest_path.display()
            )
        })?;
    ensure!(
        overlay_manifest.schema_version == 1,
        "unsupported font overlay manifest schema"
    );
    validate_overlay_inputs(&config.resources, &overlay_manifest.inputs)?;
    ensure!(
        overlay_manifest.outputs.len() == config.resources.len(),
        "font overlay output count mismatch"
    );

    let mut output = input.clone();
    let mut repacked_resources = Vec::with_capacity(config.resources.len());
    for ((expected, original), &(start, end)) in config
        .resources
        .iter()
        .zip(&validated.report.resources)
        .zip(&validated.ranges)
    {
        let declared_output =
            unique_overlay_resource(&overlay_manifest.outputs, &expected.file_name)?;
        ensure!(
            declared_output.size == expected.size,
            "font overlay output size mismatch for {}",
            expected.file_name
        );
        let replacement_path = overlay_dir.join(&expected.file_name);
        let replacement = fs::read(&replacement_path).with_context(|| {
            format!(
                "failed to read font overlay output {}",
                replacement_path.display()
            )
        })?;
        ensure!(
            replacement.len() == expected.size,
            "font overlay file size mismatch for {}",
            expected.file_name
        );
        let replacement_sha256 = sha256(&replacement);
        ensure!(
            replacement_sha256.eq_ignore_ascii_case(&declared_output.sha256),
            "font overlay file SHA-256 mismatch for {}",
            expected.file_name
        );
        let original_bytes = input
            .get(start..end)
            .context("validated original font range vanished")?;
        let changed_byte_count = original_bytes
            .iter()
            .zip(&replacement)
            .filter(|(left, right)| left != right)
            .count();
        output[start..end].copy_from_slice(&replacement);
        repacked_resources.push(RepackedResource {
            resource_id: expected.resource_id.clone(),
            file_name: expected.file_name.clone(),
            offset: original.offset,
            size: expected.size,
            original_sha256: original.sha256.clone(),
            output_sha256: replacement_sha256,
            changed_byte_count,
        });
    }
    ensure_declared_diff(&input, &output, &validated.ranges)?;

    let report = RepackReport {
        schema_version: 1,
        status: "research_only_not_product_input",
        source_virtual_path: config.source_virtual_path,
        original_size: input.len(),
        original_sha256: sha256(&input),
        output_size: output.len(),
        output_sha256: sha256(&output),
        overlay_manifest_sha256: sha256(&overlay_manifest_bytes),
        changed_byte_count: input
            .iter()
            .zip(&output)
            .filter(|(left, right)| left != right)
            .count(),
        resources: repacked_resources,
    };

    publish_repack(output_dir, &output, &report)?;
    Ok(report)
}

fn validate_overlay_inputs(expected: &[ResourceConfig], actual: &[OverlayResource]) -> Result<()> {
    ensure!(
        actual.len() == expected.len(),
        "font overlay input count mismatch"
    );
    for resource in expected {
        let declared = unique_overlay_resource(actual, &resource.file_name)?;
        ensure!(
            declared.size == resource.size,
            "font overlay input size mismatch for {}",
            resource.file_name
        );
        ensure!(
            declared.sha256.eq_ignore_ascii_case(&resource.sha256),
            "font overlay input SHA-256 mismatch for {}",
            resource.file_name
        );
    }
    Ok(())
}

fn unique_overlay_resource<'a>(
    resources: &'a [OverlayResource],
    file_name: &str,
) -> Result<&'a OverlayResource> {
    let mut matches = resources
        .iter()
        .filter(|entry| entry.file_name == file_name);
    let resource = matches
        .next()
        .with_context(|| format!("font overlay manifest is missing {file_name}"))?;
    ensure!(
        matches.next().is_none(),
        "font overlay manifest repeats {file_name}"
    );
    Ok(resource)
}

fn ensure_declared_diff(original: &[u8], output: &[u8], ranges: &[(usize, usize)]) -> Result<()> {
    ensure!(original.len() == output.len(), "repacked MDT size changed");
    for (offset, (left, right)) in original.iter().zip(output).enumerate() {
        if left != right {
            ensure!(
                ranges
                    .iter()
                    .any(|&(start, end)| (start..end).contains(&offset)),
                "undeclared MDT byte changed at offset {offset:#x}"
            );
        }
    }
    Ok(())
}

fn publish_repack(output_dir: &Path, output: &[u8], report: &RepackReport) -> Result<()> {
    let staging_dir = staging_path(output_dir)?;
    ensure!(
        !staging_dir.exists(),
        "staging directory already exists: {}",
        staging_dir.display()
    );
    let write_result = (|| -> Result<()> {
        fs::create_dir_all(&staging_dir).with_context(|| {
            format!(
                "failed to create staging directory {}",
                staging_dir.display()
            )
        })?;
        write_synced(&staging_dir.join("GR3.MDT"), output)?;
        let mut manifest = serde_json::to_vec_pretty(report)?;
        manifest.push(b'\n');
        write_synced(&staging_dir.join("manifest.json"), &manifest)?;
        fs::rename(&staging_dir, output_dir).with_context(|| {
            format!(
                "failed to publish repacked font candidate {}",
                output_dir.display()
            )
        })?;
        Ok(())
    })();
    if write_result.is_err() {
        let _ = fs::remove_dir_all(&staging_dir);
    }
    write_result
}

fn validate(bytes: &[u8], config: &Config) -> Result<Validated> {
    ensure!(config.schema_version == 1, "unsupported config schema");
    ensure!(
        bytes.len() == config.decoded_size,
        "decoded MDT size mismatch"
    );
    let decoded_sha256 = sha256(bytes);
    ensure!(
        decoded_sha256.eq_ignore_ascii_case(&config.decoded_sha256),
        "decoded MDT SHA-256 mismatch"
    );
    ensure!(!config.resources.is_empty(), "font resource list is empty");

    let chunk_tag = parse_hex_u32(&config.chunk.tag)?;
    ensure!(
        read_u32(bytes, config.chunk.offset)? == chunk_tag,
        "font chunk tag mismatch"
    );
    ensure!(
        read_u32(bytes, config.chunk.offset + 4)? as usize == config.chunk.size,
        "font chunk size mismatch"
    );
    let chunk_end = checked_end(config.chunk.offset, config.chunk.size)?;
    ensure!(chunk_end <= bytes.len(), "font chunk exceeds decoded MDT");
    ensure!(
        config.bundle.offset == config.chunk.offset + ALIGNMENT,
        "font bundle is not immediately after the chunk header"
    );

    let bundle_tag = parse_hex_u32(&config.bundle.tag)?;
    ensure!(
        read_u32(bytes, config.bundle.offset)? == bundle_tag,
        "font bundle tag mismatch"
    );
    ensure!(
        read_u32(bytes, config.bundle.offset + 4)? as usize == config.bundle.size,
        "font bundle size mismatch"
    );
    ensure!(
        checked_end(config.bundle.offset, config.bundle.size)? == chunk_end,
        "font bundle does not end at the chunk boundary"
    );
    ensure!(
        read_u32(bytes, config.bundle.offset + 0x10)? as usize == config.bundle.member_table_offset,
        "font member table offset mismatch"
    );
    ensure!(
        read_u32(bytes, config.bundle.offset + 0x14)? as usize == config.resources.len(),
        "font member count mismatch"
    );
    ensure!(
        config.bundle.member_data_offset.is_multiple_of(ALIGNMENT),
        "font member data offset is not aligned"
    );

    let table_start = checked_end(config.bundle.offset, config.bundle.member_table_offset)?;
    let table_end = checked_end(table_start, config.resources.len() * 4)?;
    let data_start = checked_end(config.bundle.offset, config.bundle.member_data_offset)?;
    ensure!(
        table_end <= data_start,
        "font member table overlaps member data"
    );
    ensure!(
        bytes
            .get(table_end..data_start)
            .context("font member table padding exceeds decoded MDT")?
            .iter()
            .all(|&byte| byte == 0),
        "font member table padding is nonzero"
    );

    let mut resources = Vec::with_capacity(config.resources.len());
    let mut ranges = Vec::with_capacity(config.resources.len());
    let mut cursor = data_start;
    for (index, expected) in config.resources.iter().enumerate() {
        ensure!(
            read_u32(bytes, table_start + index * 4)? as usize == expected.size,
            "font member {index} declared size mismatch"
        );
        ensure!(
            cursor.is_multiple_of(ALIGNMENT),
            "font member {index} is unaligned"
        );
        let end = checked_end(cursor, expected.size)?;
        let member = bytes
            .get(cursor..end)
            .with_context(|| format!("font member {index} exceeds decoded MDT"))?;
        let member_sha256 = sha256(member);
        ensure!(
            member_sha256.eq_ignore_ascii_case(&expected.sha256),
            "font member {index} SHA-256 mismatch"
        );
        resources.push(ExtractedResource {
            resource_id: expected.resource_id.clone(),
            file_name: expected.file_name.clone(),
            offset: cursor,
            size: expected.size,
            sha256: member_sha256,
        });
        ranges.push((cursor, end));

        let aligned_end = align_up(end, ALIGNMENT)?;
        ensure!(
            aligned_end <= chunk_end,
            "font member alignment exceeds chunk"
        );
        ensure!(
            bytes[end..aligned_end].iter().all(|&byte| byte == 0),
            "font member {index} padding is nonzero"
        );
        cursor = aligned_end;
    }
    ensure!(
        cursor == chunk_end,
        "font members do not fill the declared bundle"
    );

    Ok(Validated {
        report: Report {
            schema_version: 1,
            source_virtual_path: config.source_virtual_path.clone(),
            decoded_size: bytes.len(),
            decoded_sha256,
            chunk_index: config.chunk.index,
            chunk_offset: config.chunk.offset,
            chunk_tag: config.chunk.tag.clone(),
            chunk_size: config.chunk.size,
            resources,
        },
        ranges,
    })
}

fn write_synced(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut file = File::create(path)
        .with_context(|| format!("failed to create staged output {}", path.display()))?;
    file.write_all(bytes)?;
    file.sync_all()?;
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

fn parse_hex_u32(value: &str) -> Result<u32> {
    let digits = value
        .strip_prefix("0x")
        .or_else(|| value.strip_prefix("0X"))
        .context("expected a hexadecimal value beginning with 0x")?;
    u32::from_str_radix(digits, 16).context("invalid hexadecimal value")
}

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32> {
    let value = bytes
        .get(offset..offset + 4)
        .context("truncated font container integer")?;
    Ok(u32::from_le_bytes(value.try_into().unwrap()))
}

fn checked_end(offset: usize, size: usize) -> Result<usize> {
    offset
        .checked_add(size)
        .context("font container size overflow")
}

fn align_up(value: usize, alignment: usize) -> Result<usize> {
    let remainder = value % alignment;
    if remainder == 0 {
        Ok(value)
    } else {
        value
            .checked_add(alignment - remainder)
            .context("font alignment overflow")
    }
}

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[cfg(test)]
mod tests {
    use super::{
        BundleConfig, ChunkConfig, Config, ResourceConfig, ensure_declared_diff, sha256, validate,
    };

    #[test]
    fn validates_declared_aligned_members() {
        let mut bytes = vec![0_u8; 0x280];
        bytes[0x80..0x84].copy_from_slice(&0xa000_0910_u32.to_le_bytes());
        bytes[0x84..0x88].copy_from_slice(&0x200_u32.to_le_bytes());
        bytes[0x100..0x104].copy_from_slice(&0x0015_0000_u32.to_le_bytes());
        bytes[0x104..0x108].copy_from_slice(&0x180_u32.to_le_bytes());
        bytes[0x110..0x114].copy_from_slice(&0x80_u32.to_le_bytes());
        bytes[0x114..0x118].copy_from_slice(&1_u32.to_le_bytes());
        bytes[0x180..0x184].copy_from_slice(&0x80_u32.to_le_bytes());
        bytes[0x200..0x280].fill(0x5a);
        let member_hash = sha256(&bytes[0x200..0x280]);
        let config = Config {
            schema_version: 1,
            source_virtual_path: "SYS/GR3.MDZ".to_owned(),
            decoded_size: bytes.len(),
            decoded_sha256: sha256(&bytes),
            chunk: ChunkConfig {
                index: 0,
                offset: 0x80,
                tag: "0xa0000910".to_owned(),
                size: 0x200,
            },
            bundle: BundleConfig {
                offset: 0x100,
                tag: "0x00150000".to_owned(),
                size: 0x180,
                member_table_offset: 0x80,
                member_data_offset: 0x100,
            },
            resources: vec![ResourceConfig {
                resource_id: "SYS/FONT/TEST.FNT".to_owned(),
                file_name: "TEST.FNT".to_owned(),
                size: 0x80,
                sha256: member_hash,
            }],
        };

        let validated = validate(&bytes, &config).unwrap();

        assert_eq!(validated.report.resources[0].offset, 0x200);
    }

    #[test]
    fn rejects_changes_outside_declared_resource_ranges() {
        let original = vec![0_u8; 16];
        let mut output = original.clone();
        output[4] = 1;
        output[12] = 1;

        let error = ensure_declared_diff(&original, &output, &[(4, 8)]).unwrap_err();

        assert!(error.to_string().contains("offset 0xc"));
    }
}
