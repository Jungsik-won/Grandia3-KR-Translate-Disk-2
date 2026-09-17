use std::path::Path;

use anyhow::{Context, Result, ensure};
use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::inspect;
use crate::iso9660::Image;
use crate::mdz;

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub source_id: String,
    pub mdz_count: usize,
    pub total_decoded_bytes: u64,
    pub entries: Vec<Entry>,
}

#[derive(Debug, Serialize)]
pub struct Entry {
    pub path: String,
    pub container_size: u32,
    pub decoded_size: usize,
    pub decoded_sha256: String,
}

pub fn verify(iso_path: &Path, manifest_path: &Path) -> Result<Report> {
    let inventory = inspect::inspect(iso_path, manifest_path)?;
    let mut image = Image::open(iso_path)?;
    let iso_entries = image.entries()?;
    let mut entries = Vec::with_capacity(inventory.mdz.len());

    for expected in &inventory.mdz {
        let iso_entry = iso_entries
            .iter()
            .find(|entry| entry.path == expected.path)
            .with_context(|| format!("inventory MDZ {} is missing from ISO", expected.path))?;
        let container = image
            .read_entry(iso_entry)
            .with_context(|| format!("failed to read {}", expected.path))?;
        let decoded = mdz::decode(&container)
            .with_context(|| format!("failed to decode {}", expected.path))?;
        ensure!(
            decoded.len() == expected.header.decoded_size_field as usize,
            "decoded size of {} differs from its inventory header",
            expected.path
        );
        entries.push(Entry {
            path: expected.path.clone(),
            container_size: expected.file_size,
            decoded_size: decoded.len(),
            decoded_sha256: format!("{:x}", Sha256::digest(&decoded)),
        });
    }

    Ok(Report {
        schema_version: 1,
        source_id: inventory.source_id,
        mdz_count: entries.len(),
        total_decoded_bytes: entries.iter().map(|entry| entry.decoded_size as u64).sum(),
        entries,
    })
}
