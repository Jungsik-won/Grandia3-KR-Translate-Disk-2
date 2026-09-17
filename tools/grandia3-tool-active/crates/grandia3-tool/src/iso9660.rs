use std::collections::HashSet;
use std::fs::File;
use std::io::{Read, Seek, SeekFrom};
use std::path::Path;

use anyhow::{Context, Result, bail, ensure};
use serde::Serialize;
use sha2::{Digest, Sha256};

const SECTOR_SIZE: u64 = 2048;
const PVD_SECTOR: u64 = 16;

#[derive(Debug, Clone, Serialize)]
pub struct Entry {
    pub path: String,
    pub extent: u32,
    pub size: u32,
    pub is_dir: bool,
}

#[derive(Debug)]
pub struct Image {
    file: File,
    pub volume_id: String,
    root: Entry,
}

impl Image {
    pub fn open(path: &Path) -> Result<Self> {
        let mut file =
            File::open(path).with_context(|| format!("failed to open ISO {}", path.display()))?;
        let mut pvd = [0_u8; SECTOR_SIZE as usize];
        file.seek(SeekFrom::Start(PVD_SECTOR * SECTOR_SIZE))?;
        file.read_exact(&mut pvd)
            .context("failed to read ISO primary volume descriptor")?;

        ensure!(
            pvd[0] == 1,
            "sector 16 is not an ISO9660 primary volume descriptor"
        );
        ensure!(
            &pvd[1..6] == b"CD001",
            "ISO9660 identifier CD001 is missing"
        );
        ensure!(
            pvd[6] == 1,
            "unsupported ISO9660 descriptor version {}",
            pvd[6]
        );

        let volume_id = String::from_utf8_lossy(&pvd[40..72]).trim().to_owned();
        let root = parse_record(&pvd[156..])?.context("ISO9660 root directory is missing")?;

        Ok(Self {
            file,
            volume_id,
            root: Entry {
                path: String::new(),
                extent: root.extent,
                size: root.size,
                is_dir: true,
            },
        })
    }

    pub fn entries(&mut self) -> Result<Vec<Entry>> {
        let mut output = Vec::new();
        let mut pending = vec![self.root.clone()];
        let mut visited = HashSet::new();

        while let Some(directory) = pending.pop() {
            ensure!(
                visited.insert((directory.extent, directory.size)),
                "ISO9660 directory cycle at extent {}",
                directory.extent
            );
            let bytes = self.read_extent(directory.extent, directory.size as usize)?;
            let mut offset = 0_usize;

            while offset < bytes.len() {
                let record_len = bytes[offset] as usize;
                if record_len == 0 {
                    offset = ((offset / SECTOR_SIZE as usize) + 1) * SECTOR_SIZE as usize;
                    continue;
                }
                ensure!(
                    offset + record_len <= bytes.len(),
                    "truncated ISO9660 directory record"
                );
                let record = parse_record(&bytes[offset..offset + record_len])?
                    .context("empty ISO9660 directory record")?;
                offset += record_len;

                if record.name == "\u{0}" || record.name == "\u{1}" {
                    continue;
                }

                let name = record.name.split(';').next().unwrap_or(&record.name);
                let path = if directory.path.is_empty() {
                    name.to_owned()
                } else {
                    format!("{}/{}", directory.path, name)
                };
                let entry = Entry {
                    path,
                    extent: record.extent,
                    size: record.size,
                    is_dir: record.is_dir,
                };
                if entry.is_dir {
                    pending.push(entry.clone());
                }
                output.push(entry);
            }
        }

        output.sort_by(|left, right| left.path.cmp(&right.path));
        Ok(output)
    }

    pub fn read_entry(&mut self, entry: &Entry) -> Result<Vec<u8>> {
        ensure!(
            !entry.is_dir,
            "cannot read directory {} as a file",
            entry.path
        );
        self.read_extent(entry.extent, entry.size as usize)
    }

    pub fn read_entry_prefix(&mut self, entry: &Entry, max_len: usize) -> Result<Vec<u8>> {
        ensure!(
            !entry.is_dir,
            "cannot read directory {} as a file",
            entry.path
        );
        self.read_extent(entry.extent, (entry.size as usize).min(max_len))
    }

    pub fn hash_entry(&mut self, entry: &Entry) -> Result<String> {
        ensure!(
            !entry.is_dir,
            "cannot hash directory {} as a file",
            entry.path
        );
        let offset = u64::from(entry.extent)
            .checked_mul(SECTOR_SIZE)
            .context("ISO9660 extent offset overflow")?;
        self.file.seek(SeekFrom::Start(offset))?;

        let mut remaining = u64::from(entry.size);
        let mut buffer = vec![0_u8; 1024 * 1024];
        let mut hasher = Sha256::new();
        while remaining > 0 {
            let count = usize::try_from(remaining.min(buffer.len() as u64))?;
            self.file.read_exact(&mut buffer[..count])?;
            hasher.update(&buffer[..count]);
            remaining -= count as u64;
        }
        Ok(format!("{:x}", hasher.finalize()))
    }

    fn read_extent(&mut self, extent: u32, size: usize) -> Result<Vec<u8>> {
        let offset = u64::from(extent)
            .checked_mul(SECTOR_SIZE)
            .context("ISO9660 extent offset overflow")?;
        let mut bytes = vec![0_u8; size];
        self.file.seek(SeekFrom::Start(offset))?;
        self.file.read_exact(&mut bytes)?;
        Ok(bytes)
    }
}

#[derive(Debug)]
struct DirectoryRecord {
    extent: u32,
    size: u32,
    is_dir: bool,
    name: String,
}

fn parse_record(bytes: &[u8]) -> Result<Option<DirectoryRecord>> {
    if bytes.first().copied().unwrap_or(0) == 0 {
        return Ok(None);
    }
    let record_len = bytes[0] as usize;
    ensure!(
        record_len >= 34 && record_len <= bytes.len(),
        "invalid ISO9660 record length"
    );
    let name_len = bytes[32] as usize;
    ensure!(
        33 + name_len <= record_len,
        "invalid ISO9660 file identifier length"
    );

    let extent = little_u32(&bytes[2..6])?;
    let mirrored_extent = u32::from_be_bytes(bytes[6..10].try_into()?);
    ensure!(
        extent == mirrored_extent,
        "ISO9660 extent endian copies disagree"
    );
    let size = little_u32(&bytes[10..14])?;
    let mirrored_size = u32::from_be_bytes(bytes[14..18].try_into()?);
    ensure!(size == mirrored_size, "ISO9660 size endian copies disagree");

    Ok(Some(DirectoryRecord {
        extent,
        size,
        is_dir: bytes[25] & 0x02 != 0,
        name: String::from_utf8_lossy(&bytes[33..33 + name_len]).into_owned(),
    }))
}

fn little_u32(bytes: &[u8]) -> Result<u32> {
    if bytes.len() != 4 {
        bail!("expected four bytes");
    }
    Ok(u32::from_le_bytes(bytes.try_into()?))
}

#[cfg(test)]
mod tests {
    use super::parse_record;

    #[test]
    fn parses_directory_record_and_checks_mirrored_values() {
        let mut record = [0_u8; 40];
        record[0] = 40;
        record[2..6].copy_from_slice(&21_u32.to_le_bytes());
        record[6..10].copy_from_slice(&21_u32.to_be_bytes());
        record[10..14].copy_from_slice(&99_u32.to_le_bytes());
        record[14..18].copy_from_slice(&99_u32.to_be_bytes());
        record[25] = 2;
        record[32] = 3;
        record[33..36].copy_from_slice(b"SYS");

        let parsed = parse_record(&record).unwrap().unwrap();
        assert_eq!(parsed.extent, 21);
        assert_eq!(parsed.size, 99);
        assert!(parsed.is_dir);
        assert_eq!(parsed.name, "SYS");
    }
}
