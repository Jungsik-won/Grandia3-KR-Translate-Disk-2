use std::collections::HashSet;
use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, ensure};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::{fnt, mdt, skj};

const ALIGNMENT: usize = 0x80;
const RECORD_SIZE: usize = 2;
const LOGICAL_GLYPH_BASE: usize = 32;

#[derive(Debug, Deserialize)]
struct ResourcePlan {
    schema_version: u32,
    decoded_size: usize,
    decoded_sha256: String,
    chunk: ChunkPlan,
    bundle: BundlePlan,
    resources: Vec<ResourceSpec>,
}

#[derive(Debug, Deserialize)]
struct ChunkPlan {
    offset: usize,
    tag: String,
    size: usize,
}

#[derive(Debug, Deserialize)]
struct BundlePlan {
    offset: usize,
    tag: String,
    size: usize,
    member_table_offset: usize,
    member_data_offset: usize,
}

#[derive(Debug, Deserialize)]
struct ResourceSpec {
    file_name: String,
    size: usize,
    sha256: String,
}

#[derive(Debug, Deserialize)]
struct OverlayConfig {
    schema_version: u32,
    mappings: Vec<Mapping>,
}

#[derive(Debug, Deserialize)]
struct Mapping {
    character: String,
    code: String,
    glyph_index: usize,
    metric_donor_index: usize,
}

#[derive(Debug, Deserialize)]
struct OverlayManifest {
    schema_version: u32,
    mapping_count: usize,
    outputs: Vec<FileHash>,
    mappings: Vec<OverlayMapping>,
}

#[derive(Debug, Deserialize)]
struct FileHash {
    file_name: String,
    size: usize,
    sha256: String,
}

#[derive(Debug, Deserialize)]
struct OverlayMapping {
    character: String,
    code: String,
    glyph_index: usize,
}

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub status: &'static str,
    pub original_mdt_size: usize,
    pub original_mdt_sha256: String,
    pub output_mdt_size: usize,
    pub output_mdt_sha256: String,
    pub added_mdt_bytes: usize,
    pub original_glyph_count: usize,
    pub logical_glyph_base: usize,
    pub padding_map_count: usize,
    pub korean_mapping_count: usize,
    pub output_glyph_count: usize,
    pub output_map_count: usize,
    pub overlay_config_sha256: String,
    pub overlay_manifest_sha256: String,
    pub resources: Vec<OutputResource>,
    pub original_font_prefixes_verified: bool,
    pub mdt_structure_verified: bool,
}

#[derive(Debug, Serialize)]
pub struct OutputResource {
    pub file_name: String,
    pub original_size: usize,
    pub output_size: usize,
    pub output_sha256: String,
}

pub struct Paths<'a> {
    pub input_mdt: &'a Path,
    pub resource_plan: &'a Path,
    pub original_resources: &'a Path,
    pub overlay_dir: &'a Path,
    pub overlay_config: &'a Path,
    pub output_dir: &'a Path,
}

pub fn build(paths: Paths<'_>) -> Result<Report> {
    ensure!(
        !paths.output_dir.exists(),
        "output directory already exists: {}",
        paths.output_dir.display()
    );
    let original_mdt = fs::read(paths.input_mdt)
        .with_context(|| format!("failed to read {}", paths.input_mdt.display()))?;
    let resource_plan_bytes = fs::read(paths.resource_plan)
        .with_context(|| format!("failed to read {}", paths.resource_plan.display()))?;
    let resource_plan: ResourcePlan = serde_json::from_slice(&resource_plan_bytes)?;
    validate_mdt(&original_mdt, &resource_plan)?;

    let overlay_config_bytes = fs::read(paths.overlay_config)
        .with_context(|| format!("failed to read {}", paths.overlay_config.display()))?;
    let overlay_config: OverlayConfig = serde_json::from_slice(&overlay_config_bytes)?;
    ensure!(
        overlay_config.schema_version == 1,
        "unsupported overlay config schema"
    );
    ensure!(
        !overlay_config.mappings.is_empty(),
        "overlay mapping list is empty"
    );
    let overlay_manifest_path = paths.overlay_dir.join("manifest.json");
    let overlay_manifest_bytes = fs::read(&overlay_manifest_path)
        .with_context(|| format!("failed to read {}", overlay_manifest_path.display()))?;
    let overlay_manifest: OverlayManifest = serde_json::from_slice(&overlay_manifest_bytes)?;
    validate_overlay(&overlay_config, &overlay_manifest)?;

    ensure!(
        resource_plan.resources.len() == 4,
        "font extension requires exactly four resources"
    );
    let expected_names = ["GR3BACK.FNT", "RUBY.FNT", "RUBY.SKJ", "RUBY.METRICS"];
    for (resource, expected_name) in resource_plan.resources.iter().zip(expected_names) {
        ensure!(
            resource.file_name == expected_name,
            "font resource order mismatch"
        );
    }

    let originals = read_original_resources(paths.original_resources, &resource_plan.resources)?;
    validate_embedded_resources(&original_mdt, &resource_plan, &originals)?;
    let overlays = read_overlay_resources(paths.overlay_dir, &overlay_manifest.outputs)?;
    let original_main_report = fnt::inspect(&paths.original_resources.join("GR3BACK.FNT"))?;
    let original_ruby_report = fnt::inspect(&paths.original_resources.join("RUBY.FNT"))?;
    let overlay_main_report = fnt::inspect(&paths.overlay_dir.join("GR3BACK.FNT"))?;
    let overlay_ruby_report = fnt::inspect(&paths.overlay_dir.join("RUBY.FNT"))?;
    ensure!(
        original_main_report.glyph_count == original_ruby_report.glyph_count,
        "original FNT glyph populations differ"
    );
    ensure!(
        overlay_main_report.glyph_count == original_main_report.glyph_count
            && overlay_ruby_report.glyph_count == original_ruby_report.glyph_count,
        "overlay FNT population differs from original"
    );
    ensure!(
        originals[3].len() == original_main_report.glyph_count * RECORD_SIZE,
        "original metrics population mismatch"
    );
    let map_records = skj::records(&paths.original_resources.join("RUBY.SKJ"))?;
    ensure!(
        map_records.len() >= LOGICAL_GLYPH_BASE,
        "SKJ population is smaller than the logical glyph base"
    );
    let original_logical_capacity = original_main_report
        .glyph_count
        .checked_add(LOGICAL_GLYPH_BASE)
        .context("original logical glyph capacity overflow")?;
    ensure!(
        map_records.len() <= original_logical_capacity,
        "SKJ population exceeds the original FNT logical capacity"
    );
    let padding_map_count = original_logical_capacity - map_records.len();

    let original_codes: HashSet<_> = map_records.iter().map(|record| record.code).collect();
    let mut mapping_slots = HashSet::new();
    for mapping in &overlay_config.mappings {
        let code = parse_korean_code(&mapping.code)?;
        ensure!(
            !original_codes.contains(&code),
            "Korean code 0x{code:04x} collides with the original map"
        );
        ensure!(
            mapping_slots.insert(mapping.glyph_index),
            "duplicate overlay glyph index"
        );
    }

    let donor_index = overlay_config.mappings[0].metric_donor_index;
    ensure!(
        donor_index < original_main_report.glyph_count,
        "metric donor index exceeds original glyph population"
    );
    ensure!(
        overlay_config
            .mappings
            .iter()
            .all(|mapping| mapping.metric_donor_index == donor_index),
        "font extension requires one reviewed metric donor"
    );
    let output_glyph_count = original_main_report
        .glyph_count
        .checked_add(overlay_config.mappings.len())
        .context("expanded glyph population overflow")?;
    ensure!(
        output_glyph_count <= u16::MAX as usize,
        "expanded glyph population exceeds FNT field"
    );

    let main = expand_fnt(
        &originals[0],
        &overlays[0],
        &original_main_report,
        &overlay_config.mappings,
        donor_index,
    )?;
    let ruby = expand_fnt(
        &originals[1],
        &overlays[1],
        &original_ruby_report,
        &overlay_config.mappings,
        donor_index,
    )?;
    let mut map = originals[2].clone();
    let padding_codes = padding_codes(
        padding_map_count,
        &original_codes,
        &overlay_config
            .mappings
            .iter()
            .map(|mapping| parse_korean_code(&mapping.code))
            .collect::<Result<HashSet<_>>>()?,
    )?;
    for code in padding_codes {
        map.extend_from_slice(&code.to_be_bytes());
    }
    for mapping in &overlay_config.mappings {
        map.extend_from_slice(&parse_korean_code(&mapping.code)?.to_be_bytes());
    }
    let mut metrics = originals[3].clone();
    let donor_metric = originals[3]
        .get(donor_index * RECORD_SIZE..(donor_index + 1) * RECORD_SIZE)
        .context("metric donor range vanished")?
        .to_vec();
    for _ in 0..overlay_config.mappings.len() {
        metrics.extend_from_slice(&donor_metric);
    }
    let output_resources = vec![main, ruby, map, metrics];

    verify_preserved_prefixes(
        &originals,
        &output_resources,
        &original_main_report,
        &original_ruby_report,
    )?;
    let output_mdt = rebuild_mdt(&original_mdt, &resource_plan, &output_resources)?;
    let staging_dir = staging_path(paths.output_dir)?;
    ensure!(
        !staging_dir.exists(),
        "staging directory already exists: {}",
        staging_dir.display()
    );
    let result = (|| -> Result<Report> {
        fs::create_dir_all(&staging_dir)?;
        for (name, bytes) in expected_names.iter().zip(&output_resources) {
            write_synced(&staging_dir.join(name), bytes)?;
        }
        write_synced(&staging_dir.join("GR3.MDT"), &output_mdt)?;
        let output_main_report = fnt::inspect(&staging_dir.join("GR3BACK.FNT"))?;
        let output_ruby_report = fnt::inspect(&staging_dir.join("RUBY.FNT"))?;
        let output_map = skj::records(&staging_dir.join("RUBY.SKJ"))?;
        ensure!(
            output_main_report.glyph_count == output_glyph_count
                && output_ruby_report.glyph_count == output_glyph_count
                && output_map.len() == output_glyph_count + LOGICAL_GLYPH_BASE,
            "expanded font populations differ"
        );
        let inventory = mdt::inspect(&staging_dir.join("GR3.MDT"))?;
        ensure!(
            inventory.chunks.len() == 19,
            "expanded MDT chunk count changed"
        );
        let resources: Vec<_> = expected_names
            .iter()
            .zip(&originals)
            .zip(&output_resources)
            .map(|((name, original), output)| OutputResource {
                file_name: (*name).to_owned(),
                original_size: original.len(),
                output_size: output.len(),
                output_sha256: sha256(output),
            })
            .collect();
        let report = Report {
            schema_version: 1,
            status: "research_only_not_product_input",
            original_mdt_size: original_mdt.len(),
            original_mdt_sha256: sha256(&original_mdt),
            output_mdt_size: output_mdt.len(),
            output_mdt_sha256: sha256(&output_mdt),
            added_mdt_bytes: output_mdt.len() - original_mdt.len(),
            original_glyph_count: original_main_report.glyph_count,
            logical_glyph_base: LOGICAL_GLYPH_BASE,
            padding_map_count,
            korean_mapping_count: overlay_config.mappings.len(),
            output_glyph_count,
            output_map_count: output_map.len(),
            overlay_config_sha256: sha256(&overlay_config_bytes),
            overlay_manifest_sha256: sha256(&overlay_manifest_bytes),
            resources,
            original_font_prefixes_verified: true,
            mdt_structure_verified: true,
        };
        let mut manifest = serde_json::to_vec_pretty(&report)?;
        manifest.push(b'\n');
        write_synced(&staging_dir.join("manifest.json"), &manifest)?;
        fs::rename(&staging_dir, paths.output_dir).with_context(|| {
            format!(
                "failed to publish font extension {}",
                paths.output_dir.display()
            )
        })?;
        Ok(report)
    })();
    if result.is_err() {
        let _ = fs::remove_dir_all(&staging_dir);
    }
    result
}

fn validate_overlay(config: &OverlayConfig, manifest: &OverlayManifest) -> Result<()> {
    ensure!(
        manifest.schema_version == 1,
        "unsupported overlay manifest schema"
    );
    ensure!(
        manifest.mapping_count == config.mappings.len(),
        "overlay mapping count mismatch"
    );
    ensure!(
        manifest.mappings.len() == config.mappings.len(),
        "overlay manifest mapping mismatch"
    );
    let mut characters = HashSet::new();
    let mut codes = HashSet::new();
    for (expected, actual) in config.mappings.iter().zip(&manifest.mappings) {
        ensure!(
            expected.character == actual.character
                && expected.code.eq_ignore_ascii_case(&actual.code)
                && expected.glyph_index == actual.glyph_index,
            "overlay mapping differs from config"
        );
        ensure!(
            expected.character.chars().count() == 1,
            "mapping is not one character"
        );
        ensure!(
            characters.insert(&expected.character),
            "duplicate mapped character"
        );
        ensure!(
            codes.insert(parse_hex_u16(&expected.code)?),
            "duplicate mapped code"
        );
    }
    Ok(())
}

fn read_original_resources(dir: &Path, specs: &[ResourceSpec]) -> Result<Vec<Vec<u8>>> {
    specs
        .iter()
        .map(|spec| {
            let bytes = fs::read(dir.join(&spec.file_name))?;
            ensure!(bytes.len() == spec.size, "{} size mismatch", spec.file_name);
            ensure_hash(&bytes, &spec.sha256, &spec.file_name)?;
            Ok(bytes)
        })
        .collect()
}

fn read_overlay_resources(dir: &Path, specs: &[FileHash]) -> Result<Vec<Vec<u8>>> {
    let expected_names = ["GR3BACK.FNT", "RUBY.FNT", "RUBY.SKJ", "RUBY.METRICS"];
    expected_names
        .iter()
        .map(|name| {
            let spec = specs
                .iter()
                .find(|spec| spec.file_name == *name)
                .with_context(|| format!("overlay manifest is missing {name}"))?;
            let bytes = fs::read(dir.join(name))?;
            ensure!(bytes.len() == spec.size, "overlay {name} size mismatch");
            ensure_hash(&bytes, &spec.sha256, &format!("overlay {name}"))?;
            Ok(bytes)
        })
        .collect()
}

fn validate_mdt(bytes: &[u8], plan: &ResourcePlan) -> Result<()> {
    ensure!(plan.schema_version == 1, "unsupported resource plan schema");
    ensure!(
        bytes.len() == plan.decoded_size,
        "decoded MDT size mismatch"
    );
    ensure_hash(bytes, &plan.decoded_sha256, "decoded MDT")?;
    ensure!(
        read_u32(bytes, plan.chunk.offset)? == parse_hex_u32(&plan.chunk.tag)?,
        "font chunk tag mismatch"
    );
    ensure!(
        read_u32(bytes, plan.chunk.offset + 4)? as usize == plan.chunk.size,
        "font chunk size mismatch"
    );
    ensure!(
        read_u32(bytes, plan.bundle.offset)? == parse_hex_u32(&plan.bundle.tag)?,
        "font bundle tag mismatch"
    );
    ensure!(
        read_u32(bytes, plan.bundle.offset + 4)? as usize == plan.bundle.size,
        "font bundle size mismatch"
    );
    ensure!(
        plan.bundle.offset == plan.chunk.offset + ALIGNMENT,
        "bundle offset mismatch"
    );
    ensure!(
        plan.bundle.member_data_offset.is_multiple_of(ALIGNMENT),
        "bundle data is unaligned"
    );
    Ok(())
}

fn validate_embedded_resources(
    mdt: &[u8],
    plan: &ResourcePlan,
    originals: &[Vec<u8>],
) -> Result<()> {
    let table = plan.bundle.offset + plan.bundle.member_table_offset;
    let mut cursor = plan.bundle.offset + plan.bundle.member_data_offset;
    for (index, ((spec, original), declared)) in plan
        .resources
        .iter()
        .zip(originals)
        .zip((0..plan.resources.len()).map(|i| read_u32(mdt, table + i * 4)))
        .enumerate()
    {
        ensure!(
            declared? as usize == spec.size,
            "member {index} table size mismatch"
        );
        let end = cursor
            .checked_add(spec.size)
            .context("member range overflow")?;
        ensure!(
            mdt.get(cursor..end) == Some(original),
            "member {index} differs from extracted resource"
        );
        cursor = align_up(end, ALIGNMENT)?;
    }
    ensure!(
        cursor == plan.chunk.offset + plan.chunk.size,
        "font members do not fill chunk"
    );
    Ok(())
}

fn expand_fnt(
    original: &[u8],
    overlay: &[u8],
    report: &fnt::Report,
    mappings: &[Mapping],
    donor_index: usize,
) -> Result<Vec<u8>> {
    ensure!(original.len() == overlay.len(), "overlay FNT size changed");
    let new_count = report.glyph_count + mappings.len();
    let new_bitmap_offset = report.metadata_offset + new_count * RECORD_SIZE;
    let mut output = original[..report.metadata_offset].to_vec();
    output[0..4].copy_from_slice(&u32::try_from(new_bitmap_offset)?.to_le_bytes());
    output[8..10].copy_from_slice(&u16::try_from(new_count)?.to_le_bytes());
    let metadata = &original[report.metadata_offset..report.bitmap_offset];
    let donor_metadata = &metadata[donor_index * RECORD_SIZE..(donor_index + 1) * RECORD_SIZE];
    output.extend_from_slice(metadata);
    for _ in 0..mappings.len() {
        output.extend_from_slice(donor_metadata);
    }
    let bitmap = &original[report.bitmap_offset..];
    output.extend_from_slice(bitmap);
    for mapping in mappings {
        ensure!(
            mapping.glyph_index < report.glyph_count,
            "overlay glyph index exceeds source FNT"
        );
        let start = report.bitmap_offset + mapping.glyph_index * report.bytes_per_glyph;
        output.extend_from_slice(&overlay[start..start + report.bytes_per_glyph]);
    }
    Ok(output)
}

fn verify_preserved_prefixes(
    originals: &[Vec<u8>],
    outputs: &[Vec<u8>],
    main: &fnt::Report,
    ruby: &fnt::Report,
) -> Result<()> {
    for (original, output, report) in [
        (&originals[0], &outputs[0], main),
        (&originals[1], &outputs[1], ruby),
    ] {
        let new_bitmap_offset = read_u32(output, 0)? as usize;
        ensure!(
            output[report.metadata_offset..report.bitmap_offset]
                == original[report.metadata_offset..report.bitmap_offset],
            "original FNT metadata changed"
        );
        ensure!(
            output[new_bitmap_offset..new_bitmap_offset + original.len() - report.bitmap_offset]
                == original[report.bitmap_offset..],
            "original FNT bitmap changed"
        );
    }
    ensure!(
        outputs[2].starts_with(&originals[2]),
        "original SKJ bytes changed"
    );
    ensure!(
        outputs[3].starts_with(&originals[3]),
        "original metrics changed"
    );
    Ok(())
}

fn rebuild_mdt(original: &[u8], plan: &ResourcePlan, resources: &[Vec<u8>]) -> Result<Vec<u8>> {
    let old_chunk_end = plan.chunk.offset + plan.chunk.size;
    let first_member = plan.bundle.offset + plan.bundle.member_data_offset;
    let mut new_chunk = original[plan.chunk.offset..first_member].to_vec();
    let table_in_chunk = plan.bundle.offset - plan.chunk.offset + plan.bundle.member_table_offset;
    for (index, resource) in resources.iter().enumerate() {
        let size = u32::try_from(resource.len())?;
        new_chunk[table_in_chunk + index * 4..table_in_chunk + index * 4 + 4]
            .copy_from_slice(&size.to_le_bytes());
    }
    for resource in resources {
        new_chunk.extend_from_slice(resource);
        new_chunk.resize(align_up(new_chunk.len(), ALIGNMENT)?, 0);
    }
    let bundle_size = new_chunk.len() - (plan.bundle.offset - plan.chunk.offset);
    let chunk_size = new_chunk.len();
    new_chunk[4..8].copy_from_slice(&u32::try_from(chunk_size)?.to_le_bytes());
    let bundle_size_offset = plan.bundle.offset - plan.chunk.offset + 4;
    new_chunk[bundle_size_offset..bundle_size_offset + 4]
        .copy_from_slice(&u32::try_from(bundle_size)?.to_le_bytes());
    let mut output = Vec::with_capacity(original.len() + chunk_size - plan.chunk.size);
    output.extend_from_slice(&original[..plan.chunk.offset]);
    output.extend_from_slice(&new_chunk);
    output.extend_from_slice(&original[old_chunk_end..]);
    ensure!(
        output[..plan.chunk.offset] == original[..plan.chunk.offset]
            && output[plan.chunk.offset + chunk_size..] == original[old_chunk_end..],
        "MDT data outside font chunk changed"
    );
    Ok(output)
}

fn parse_hex_u16(value: &str) -> Result<u16> {
    let digits = value
        .strip_prefix("0x")
        .or_else(|| value.strip_prefix("0X"))
        .context("expected hex code")?;
    u16::from_str_radix(digits, 16).context("invalid hex code")
}

fn parse_korean_code(value: &str) -> Result<u16> {
    let code = parse_hex_u16(value)?;
    let [lead, trail] = code.to_be_bytes();
    ensure!(
        (0xa0..=0xdf).contains(&lead),
        "Korean code lead is outside 0xa0..0xdf"
    );
    ensure!(
        (0x40..=0x7e).contains(&trail) || (0x80..=0xfc).contains(&trail),
        "Korean code trail is outside the approved candidate set"
    );
    Ok(code)
}

fn padding_codes(
    count: usize,
    original_codes: &HashSet<u16>,
    korean_codes: &HashSet<u16>,
) -> Result<Vec<u16>> {
    let mut codes = Vec::with_capacity(count);
    for lead in (0xa0_u16..=0xdf).rev() {
        for trail in (0x80_u16..=0xfc).rev().chain((0x40_u16..=0x7e).rev()) {
            let code = lead << 8 | trail;
            if !original_codes.contains(&code) && !korean_codes.contains(&code) {
                codes.push(code);
                if codes.len() == count {
                    codes.sort_unstable();
                    return Ok(codes);
                }
            }
        }
    }
    ensure!(count == 0, "not enough unused codes for SKJ padding");
    Ok(codes)
}

fn parse_hex_u32(value: &str) -> Result<u32> {
    let digits = value
        .strip_prefix("0x")
        .or_else(|| value.strip_prefix("0X"))
        .context("expected hex value")?;
    u32::from_str_radix(digits, 16).context("invalid hex value")
}

fn read_u32(bytes: &[u8], offset: usize) -> Result<u32> {
    Ok(u32::from_le_bytes(
        bytes
            .get(offset..offset + 4)
            .context("truncated u32")?
            .try_into()?,
    ))
}

fn align_up(value: usize, alignment: usize) -> Result<usize> {
    value
        .checked_add(alignment - 1)
        .context("alignment overflow")
        .map(|value| value / alignment * alignment)
}

fn ensure_hash(bytes: &[u8], expected: &str, label: &str) -> Result<()> {
    ensure!(
        sha256(bytes).eq_ignore_ascii_case(expected),
        "{label} SHA-256 mismatch"
    );
    Ok(())
}

fn write_synced(path: &Path, bytes: &[u8]) -> Result<()> {
    let mut file = File::create(path)?;
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

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[cfg(test)]
mod tests {
    use std::collections::HashSet;

    use super::{align_up, padding_codes};

    #[test]
    fn aligns_resource_boundaries() {
        assert_eq!(align_up(0x101, 0x80).unwrap(), 0x180);
        assert_eq!(align_up(0x180, 0x80).unwrap(), 0x180);
    }

    #[test]
    fn chooses_distinct_padding_codes_outside_korean_mappings() {
        let korean = HashSet::from([0xdffc]);
        let padding = padding_codes(2, &HashSet::new(), &korean).unwrap();

        assert_eq!(padding, [0xdffa, 0xdffb]);
    }
}
