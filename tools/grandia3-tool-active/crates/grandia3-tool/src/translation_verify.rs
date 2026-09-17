use std::collections::HashSet;
use std::fs;
use std::path::{Component, Path, PathBuf};

use anyhow::{Context, Result, ensure};
use serde::Deserialize;
use sha2::{Digest, Sha256};

#[derive(Debug, Deserialize)]
struct ProductIndex {
    schema_version: u32,
    population_basis: PopulationBasis,
    population_status: String,
    segments: Vec<SegmentRef>,
    review: Review,
}

#[derive(Debug, Deserialize)]
struct PopulationBasis {
    scope_file: String,
    scope_file_sha256: String,
    expected_units: usize,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq)]
struct SegmentRef {
    id: String,
    path: String,
    sha256: String,
    unit_count: usize,
}

#[derive(Debug, Deserialize)]
struct Review {
    status: String,
    approval_record: String,
}

#[derive(Debug, Deserialize)]
struct Approval {
    schema_version: u32,
    approval_id: String,
    translation_index: ApprovedFile,
    scope: ApprovedScope,
    segments: Vec<SegmentRef>,
}

#[derive(Debug, Deserialize)]
struct ApprovedFile {
    path: String,
    sha256: String,
}

#[derive(Debug, Deserialize)]
struct ApprovedScope {
    path: String,
    sha256: String,
    unit_count: usize,
}

#[derive(Debug, Deserialize)]
struct ExtractedSegment {
    unit_count: usize,
    units: Vec<ExtractedUnit>,
}

#[derive(Debug, Deserialize)]
struct ExtractedUnit {
    id: String,
    byte_length: usize,
    slot_size: usize,
    max_encoded_bytes: usize,
    slot_sha256: String,
}

pub struct VerificationReport {
    pub approval_id: String,
    pub segment_count: usize,
    pub unit_count: usize,
}

pub fn verify(index_path: &Path, approval_path: &Path) -> Result<VerificationReport> {
    let index_bytes = read(index_path)?;
    let index: ProductIndex = serde_json::from_slice(&index_bytes)
        .with_context(|| format!("invalid translation index {}", index_path.display()))?;
    let approval_bytes = read(approval_path)?;
    let approval: Approval = serde_json::from_slice(&approval_bytes)
        .with_context(|| format!("invalid approval record {}", approval_path.display()))?;

    ensure!(
        index.schema_version == 1,
        "unsupported translation-index schema"
    );
    ensure!(approval.schema_version == 1, "unsupported approval schema");
    ensure!(
        index.population_status == "complete_for_declared_scope",
        "translation population is not complete"
    );
    ensure!(
        index.review.status == "approved_baseline",
        "translation baseline is not approved"
    );
    ensure!(
        index.review.approval_record == path_text(approval_path)?,
        "translation index points to a different approval record"
    );
    ensure!(
        approval.translation_index.path == path_text(index_path)?,
        "approval record points to a different translation index"
    );
    ensure_hash(
        "translation index",
        &index_bytes,
        &approval.translation_index.sha256,
    )?;
    ensure!(
        index.segments == approval.segments,
        "approved segments differ from the translation index"
    );
    ensure!(
        approval.scope.path == index.population_basis.scope_file,
        "approved scope path differs from the population basis"
    );
    ensure!(
        approval.scope.sha256 == index.population_basis.scope_file_sha256,
        "approved scope hash differs from the population basis"
    );
    ensure!(
        approval.scope.unit_count == index.population_basis.expected_units,
        "approved unit count differs from the population basis"
    );

    let scope_path = safe_project_path(&approval.scope.path)?;
    ensure_hash(
        "translation scope",
        &read(&scope_path)?,
        &approval.scope.sha256,
    )?;

    let mut total_units = 0;
    let mut ids = HashSet::new();
    for segment_ref in &index.segments {
        let segment_path = safe_project_path(&segment_ref.path)?;
        let bytes = read(&segment_path)?;
        ensure_hash(&segment_ref.id, &bytes, &segment_ref.sha256)?;
        let segment: ExtractedSegment = serde_json::from_slice(&bytes)
            .with_context(|| format!("invalid translation segment {}", segment_path.display()))?;
        ensure!(
            segment.unit_count == segment.units.len(),
            "segment {} has an inconsistent unit count",
            segment_ref.id
        );
        ensure!(
            segment.unit_count == segment_ref.unit_count,
            "segment {} unit count differs from the index",
            segment_ref.id
        );
        for unit in segment.units {
            ensure!(ids.insert(unit.id.clone()), "duplicate unit ID {}", unit.id);
            ensure!(
                unit.slot_size == unit.max_encoded_bytes + 1,
                "unit {} has inconsistent slot limits",
                unit.id
            );
            ensure!(
                unit.byte_length <= unit.max_encoded_bytes,
                "unit {} source text exceeds its slot",
                unit.id
            );
            ensure!(
                unit.slot_sha256.len() == 64,
                "unit {} has no valid slot hash",
                unit.id
            );
        }
        total_units += segment.unit_count;
    }
    ensure!(
        total_units == approval.scope.unit_count,
        "approved population has {total_units} units, expected {}",
        approval.scope.unit_count
    );

    Ok(VerificationReport {
        approval_id: approval.approval_id,
        segment_count: index.segments.len(),
        unit_count: total_units,
    })
}

fn safe_project_path(value: &str) -> Result<PathBuf> {
    let path = Path::new(value);
    ensure!(
        !path.is_absolute(),
        "product input path must be relative: {value}"
    );
    ensure!(
        path.components()
            .all(|component| matches!(component, Component::Normal(_))),
        "product input path is not normalized: {value}"
    );
    Ok(path.to_owned())
}

fn path_text(path: &Path) -> Result<String> {
    ensure!(
        !path.is_absolute(),
        "verification paths must be project-relative"
    );
    Ok(path.to_string_lossy().into_owned())
}

fn read(path: &Path) -> Result<Vec<u8>> {
    fs::read(path).with_context(|| format!("failed to read {}", path.display()))
}

fn ensure_hash(label: &str, bytes: &[u8], expected: &str) -> Result<()> {
    let actual = format!("{:x}", Sha256::digest(bytes));
    ensure!(
        actual.eq_ignore_ascii_case(expected),
        "{label} hash differs: expected {expected}, got {actual}"
    );
    Ok(())
}
