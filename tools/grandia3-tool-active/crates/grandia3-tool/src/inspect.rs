use std::fs::{self, File, OpenOptions};
use std::io::{BufReader, Read, Write};
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};
use sha2::{Digest, Sha256};

use crate::iso9660::{Entry, Image};
use crate::manifest::SourceManifest;
use crate::mdz::Header;

#[derive(Debug, Deserialize, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub source_id: String,
    pub game: String,
    pub region: String,
    pub disc: u8,
    pub input_size: u64,
    pub sha256: String,
    pub volume_id: String,
    pub serial: String,
    pub executable: String,
    pub file_count: usize,
    pub directory_count: usize,
    pub total_file_bytes: u64,
    pub files: Vec<FileEntry>,
    pub mdz: Vec<MdzEntry>,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct FileEntry {
    pub path: String,
    pub size: u32,
    pub sha256: String,
}

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct MdzEntry {
    pub path: String,
    pub file_size: u32,
    #[serde(flatten)]
    pub header: Header,
}

#[derive(Debug)]
pub struct SourceIdentity {
    pub source_id: String,
    pub game: String,
    pub region: String,
    pub disc: u8,
    pub input_size: u64,
    pub sha256: String,
    pub volume_id: String,
    pub serial: String,
    pub executable: String,
    pub entries: Vec<Entry>,
}

pub fn inspect(iso_path: &Path, manifest_path: &Path) -> Result<Report> {
    let identity = validate_source(iso_path, manifest_path)?;
    let mut image = Image::open(iso_path)?;

    let mut mdz = Vec::new();
    for entry in identity
        .entries
        .iter()
        .filter(|entry| !entry.is_dir && entry.path.to_ascii_uppercase().ends_with(".MDZ"))
    {
        let prefix = image.read_entry_prefix(entry, 512)?;
        let header = Header::parse(&prefix, entry.size)
            .with_context(|| format!("invalid MDZ container {}", entry.path))?;
        mdz.push(MdzEntry {
            path: entry.path.clone(),
            file_size: entry.size,
            header,
        });
    }

    let mut files = Vec::new();
    for entry in identity.entries.iter().filter(|entry| !entry.is_dir) {
        files.push(FileEntry {
            path: entry.path.clone(),
            size: entry.size,
            sha256: image
                .hash_entry(entry)
                .with_context(|| format!("failed to hash ISO file {}", entry.path))?,
        });
    }

    Ok(Report {
        schema_version: 2,
        source_id: identity.source_id,
        game: identity.game,
        region: identity.region,
        disc: identity.disc,
        input_size: identity.input_size,
        sha256: identity.sha256,
        volume_id: identity.volume_id,
        serial: identity.serial,
        executable: identity.executable,
        file_count: identity
            .entries
            .iter()
            .filter(|entry| !entry.is_dir)
            .count(),
        directory_count: identity.entries.iter().filter(|entry| entry.is_dir).count(),
        total_file_bytes: identity
            .entries
            .iter()
            .filter(|entry| !entry.is_dir)
            .map(|entry| u64::from(entry.size))
            .sum(),
        files,
        mdz,
    })
}

pub fn validate_source(iso_path: &Path, manifest_path: &Path) -> Result<SourceIdentity> {
    let input_size = fs::metadata(iso_path)
        .with_context(|| format!("failed to stat input {}", iso_path.display()))?
        .len();
    let sha256 = hash_file(iso_path)?;
    let manifest = SourceManifest::load(manifest_path)?;
    let source = manifest.exact_match(input_size, &sha256).with_context(|| {
        format!("unsupported source: size {input_size}, SHA-256 {sha256}; no exact manifest match")
    })?;

    let mut image = Image::open(iso_path)?;
    let volume_id = image.volume_id.clone();
    let entries = image.entries()?;
    let system_cnf = find_file(&entries, "SYSTEM.CNF")?;
    let system_cnf_bytes = image.read_entry(system_cnf)?;
    let serial_file = parse_boot_executable(&system_cnf_bytes)?;
    let serial = canonical_serial(&serial_file)?;
    ensure!(
        serial.eq_ignore_ascii_case(&source.serial),
        "source serial {serial} differs from manifest serial {}",
        source.serial
    );
    ensure!(
        serial_file.eq_ignore_ascii_case(&source.executable),
        "boot executable {serial_file} differs from manifest executable {}",
        source.executable
    );

    Ok(SourceIdentity {
        source_id: source.id.clone(),
        game: source.game.clone(),
        region: source.region.clone(),
        disc: source.disc,
        input_size,
        sha256,
        volume_id,
        serial,
        executable: serial_file,
        entries,
    })
}

pub fn write_json_atomic<T: Serialize>(path: &Path, value: &T) -> Result<()> {
    let bytes = serde_json::to_vec_pretty(value)?;
    let mut bytes_with_newline = bytes;
    bytes_with_newline.push(b'\n');
    write_bytes_atomic(path, &bytes_with_newline)
}

pub fn write_bytes_atomic(path: &Path, bytes: &[u8]) -> Result<()> {
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent)
        .with_context(|| format!("failed to create output directory {}", parent.display()))?;
    let temp_path = temporary_path(path)?;

    let write_result = (|| -> Result<()> {
        let mut file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temp_path)
            .with_context(|| {
                format!("failed to create temporary report {}", temp_path.display())
            })?;
        file.write_all(bytes)?;
        file.sync_all()?;
        fs::rename(&temp_path, path).with_context(|| {
            format!(
                "failed to publish output {} from {}",
                path.display(),
                temp_path.display()
            )
        })?;
        Ok(())
    })();

    if write_result.is_err() {
        let _ = fs::remove_file(&temp_path);
    }
    write_result
}

fn hash_file(path: &Path) -> Result<String> {
    let file = File::open(path)?;
    let mut reader = BufReader::with_capacity(1024 * 1024, file);
    let mut hasher = Sha256::new();
    let mut buffer = vec![0_u8; 1024 * 1024];
    loop {
        let count = reader.read(&mut buffer)?;
        if count == 0 {
            break;
        }
        hasher.update(&buffer[..count]);
    }
    Ok(format!("{:x}", hasher.finalize()))
}

fn find_file<'a>(entries: &'a [Entry], path: &str) -> Result<&'a Entry> {
    entries
        .iter()
        .find(|entry| !entry.is_dir && entry.path.eq_ignore_ascii_case(path))
        .with_context(|| format!("required ISO file {path} is missing"))
}

fn parse_boot_executable(system_cnf: &[u8]) -> Result<String> {
    let text = String::from_utf8_lossy(system_cnf);
    let boot_line = text
        .lines()
        .find(|line| line.trim_start().to_ascii_uppercase().starts_with("BOOT2"))
        .context("SYSTEM.CNF has no BOOT2 line")?;
    let after_slash = boot_line
        .rsplit_once('\\')
        .map(|(_, value)| value)
        .context("BOOT2 line has no cdrom path separator")?;
    let executable = after_slash.split(';').next().unwrap_or(after_slash).trim();
    ensure!(!executable.is_empty(), "BOOT2 executable is empty");
    Ok(executable.to_owned())
}

fn canonical_serial(executable: &str) -> Result<String> {
    let (prefix, suffix) = executable
        .split_once('_')
        .context("boot executable does not contain a serial separator")?;
    let digits: String = suffix.chars().filter(char::is_ascii_digit).collect();
    if prefix.len() != 4 || digits.len() != 5 {
        bail!("unsupported boot executable serial shape: {executable}");
    }
    Ok(format!("{}-{}", prefix.to_ascii_uppercase(), digits))
}

fn temporary_path(path: &Path) -> Result<PathBuf> {
    let file_name = path.file_name().context("report path has no file name")?;
    let mut temp_name = file_name.to_os_string();
    temp_name.push(format!(".tmp-{}", std::process::id()));
    Ok(path.with_file_name(temp_name))
}

#[cfg(test)]
mod tests {
    use super::{canonical_serial, parse_boot_executable};

    #[test]
    fn parses_grandia_boot_line() {
        for (line, expected_executable, expected_serial) in [
            (
                b"BOOT2 = cdrom0:\\SLPM_659.76;1\r\nVER = 1.01\r\n".as_slice(),
                "SLPM_659.76",
                "SLPM-65976",
            ),
            (
                b"BOOT2 = cdrom0:\\SLPM_659.77;1\r\nVER = 1.01\r\n".as_slice(),
                "SLPM_659.77",
                "SLPM-65977",
            ),
        ] {
            let executable = parse_boot_executable(line).unwrap();
            assert_eq!(executable, expected_executable);
            assert_eq!(canonical_serial(&executable).unwrap(), expected_serial);
        }
    }
}
