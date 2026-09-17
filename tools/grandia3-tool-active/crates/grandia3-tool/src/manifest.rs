use std::fs;
use std::path::Path;

use anyhow::{Context, Result};
use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct SourceManifest {
    pub sources: Vec<Source>,
}

#[derive(Clone, Debug, Deserialize)]
pub struct Source {
    pub id: String,
    pub game: String,
    pub region: String,
    pub disc: u8,
    pub serial: String,
    pub executable: String,
    pub size: u64,
    pub sha256: String,
}

impl SourceManifest {
    pub fn load(path: &Path) -> Result<Self> {
        let bytes = fs::read(path)
            .with_context(|| format!("failed to read source manifest {}", path.display()))?;
        serde_json::from_slice(&bytes)
            .with_context(|| format!("invalid source manifest {}", path.display()))
    }

    pub fn exact_match(&self, size: u64, sha256: &str) -> Option<&Source> {
        self.sources
            .iter()
            .find(|source| source.size == size && source.sha256.eq_ignore_ascii_case(sha256))
    }
}
