use std::collections::BTreeMap;
use std::fs;
use std::path::Path;

use anyhow::{Context, Result, ensure};
use serde::Serialize;

use crate::inspect::{FileEntry, Report};

#[derive(Debug, Serialize)]
pub struct Comparison {
    pub schema_version: u32,
    pub left_source_id: String,
    pub right_source_id: String,
    pub shared_files: usize,
    pub identical_files: usize,
    pub changed_files: Vec<ChangedFile>,
    pub only_left: Vec<FileEntry>,
    pub only_right: Vec<FileEntry>,
    pub shared_mdz: usize,
    pub identical_mdz: usize,
    pub changed_mdz_paths: Vec<String>,
    pub only_left_mdz_paths: Vec<String>,
    pub only_right_mdz_paths: Vec<String>,
}

#[derive(Debug, Serialize)]
pub struct ChangedFile {
    pub path: String,
    pub left_size: u32,
    pub right_size: u32,
    pub left_sha256: String,
    pub right_sha256: String,
}

pub fn compare_reports(left_path: &Path, right_path: &Path) -> Result<Comparison> {
    let left = load_report(left_path)?;
    let right = load_report(right_path)?;
    compare(left, right)
}

fn compare(left: Report, right: Report) -> Result<Comparison> {
    ensure!(
        left.schema_version == 2 && right.schema_version == 2,
        "compare requires schema version 2 inventory reports"
    );
    ensure!(left.game == right.game, "inventory games differ");
    ensure!(left.region == right.region, "inventory regions differ");
    ensure!(
        left.source_id != right.source_id,
        "cannot compare a source report with itself"
    );

    let left_files = left
        .files
        .iter()
        .map(|entry| (entry.path.as_str(), entry))
        .collect::<BTreeMap<_, _>>();
    let right_files = right
        .files
        .iter()
        .map(|entry| (entry.path.as_str(), entry))
        .collect::<BTreeMap<_, _>>();

    let mut shared_files = 0;
    let mut identical_files = 0;
    let mut changed_files = Vec::new();
    let mut only_left = Vec::new();
    let mut only_right = Vec::new();

    for (path, left_entry) in &left_files {
        let Some(right_entry) = right_files.get(path) else {
            only_left.push((*left_entry).clone());
            continue;
        };
        shared_files += 1;
        if left_entry.size == right_entry.size && left_entry.sha256 == right_entry.sha256 {
            identical_files += 1;
        } else {
            changed_files.push(ChangedFile {
                path: (*path).to_owned(),
                left_size: left_entry.size,
                right_size: right_entry.size,
                left_sha256: left_entry.sha256.clone(),
                right_sha256: right_entry.sha256.clone(),
            });
        }
    }
    for (path, right_entry) in &right_files {
        if !left_files.contains_key(path) {
            only_right.push((*right_entry).clone());
        }
    }

    let left_mdz = left
        .mdz
        .iter()
        .map(|entry| (entry.path.as_str(), entry))
        .collect::<BTreeMap<_, _>>();
    let right_mdz = right
        .mdz
        .iter()
        .map(|entry| (entry.path.as_str(), entry))
        .collect::<BTreeMap<_, _>>();
    let mut shared_mdz = 0;
    let mut identical_mdz = 0;
    let mut changed_mdz_paths = Vec::new();
    let mut only_left_mdz_paths = Vec::new();
    let mut only_right_mdz_paths = Vec::new();

    for (path, left_entry) in &left_mdz {
        let Some(right_entry) = right_mdz.get(path) else {
            only_left_mdz_paths.push((*path).to_owned());
            continue;
        };
        shared_mdz += 1;
        let left_hash = &left_files
            .get(path)
            .with_context(|| format!("MDZ {path} is missing from the left file inventory"))?
            .sha256;
        let right_hash = &right_files
            .get(path)
            .with_context(|| format!("MDZ {path} is missing from the right file inventory"))?
            .sha256;
        if left_entry == right_entry && left_hash == right_hash {
            identical_mdz += 1;
        } else {
            changed_mdz_paths.push((*path).to_owned());
        }
    }
    for path in right_mdz.keys() {
        if !left_mdz.contains_key(path) {
            only_right_mdz_paths.push((*path).to_owned());
        }
    }

    Ok(Comparison {
        schema_version: 1,
        left_source_id: left.source_id,
        right_source_id: right.source_id,
        shared_files,
        identical_files,
        changed_files,
        only_left,
        only_right,
        shared_mdz,
        identical_mdz,
        changed_mdz_paths,
        only_left_mdz_paths,
        only_right_mdz_paths,
    })
}

fn load_report(path: &Path) -> Result<Report> {
    let bytes = fs::read(path)
        .with_context(|| format!("failed to read inventory report {}", path.display()))?;
    serde_json::from_slice(&bytes)
        .with_context(|| format!("failed to parse inventory report {}", path.display()))
}

#[cfg(test)]
mod tests {
    use super::compare;
    use crate::inspect::{FileEntry, MdzEntry, Report};
    use crate::mdz::Header;

    #[test]
    fn compares_files_by_content_hash() {
        let shared = file("DATA/SHARED.MDZ", 32, "same");
        let left = report(
            "disc1",
            1,
            vec![shared.clone(), file("SYSTEM.INI", 10, "left")],
            vec![mdz("DATA/SHARED.MDZ")],
        );
        let right = report(
            "disc2",
            2,
            vec![shared, file("SYSTEM.INI", 10, "right")],
            vec![mdz("DATA/SHARED.MDZ")],
        );

        let result = compare(left, right).unwrap();
        assert_eq!(result.shared_files, 2);
        assert_eq!(result.identical_files, 1);
        assert_eq!(result.changed_files.len(), 1);
        assert_eq!(result.identical_mdz, 1);
    }

    fn file(path: &str, size: u32, sha256: &str) -> FileEntry {
        FileEntry {
            path: path.to_owned(),
            size,
            sha256: sha256.to_owned(),
        }
    }

    fn mdz(path: &str) -> MdzEntry {
        MdzEntry {
            path: path.to_owned(),
            file_size: 32,
            header: Header {
                header_size: 24,
                compressed_size: 8,
                decoded_size_field: 64,
                field_0f: 0,
                embedded_name: Some("SHARED.MDT".to_owned()),
            },
        }
    }

    fn report(id: &str, disc: u8, files: Vec<FileEntry>, mdz: Vec<MdzEntry>) -> Report {
        Report {
            schema_version: 2,
            source_id: id.to_owned(),
            game: "Grandia III".to_owned(),
            region: "Japan".to_owned(),
            disc,
            input_size: 0,
            sha256: String::new(),
            volume_id: String::new(),
            serial: String::new(),
            executable: String::new(),
            file_count: files.len(),
            directory_count: 0,
            total_file_bytes: files.iter().map(|entry| u64::from(entry.size)).sum(),
            files,
            mdz,
        }
    }
}
