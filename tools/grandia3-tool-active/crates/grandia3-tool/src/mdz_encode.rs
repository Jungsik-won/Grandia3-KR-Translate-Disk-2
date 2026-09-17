use std::cmp::Reverse;
use std::collections::BinaryHeap;
use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};

use anyhow::{Context, Result, ensure};
use serde::Serialize;
use sha2::{Digest, Sha256};

use crate::mdz::{self, Header};

const HISTORY_SIZE: usize = 1 << 15;
const MAX_COPY: usize = 256;
const MAX_BLOCK_COMMANDS: usize = 4_096;
const HASH_SIZE: usize = 1 << 16;
const MAX_CHAIN_SEARCH: usize = 16384;

#[derive(Debug, Serialize)]
pub struct Report {
    pub schema_version: u32,
    pub status: &'static str,
    pub source_mdt_size: usize,
    pub source_mdt_sha256: String,
    pub header_template_size: usize,
    pub header_template_sha256: String,
    pub allocation_limit: usize,
    pub relocatable: bool,
    pub relocation_required: bool,
    pub encoded_payload_size: usize,
    pub payload_size: usize,
    pub padding_size: usize,
    pub output_size: usize,
    pub output_sha256: String,
    pub command_count: usize,
    pub literal_count: usize,
    pub copy_count: usize,
    pub roundtrip_verified: bool,
}

#[derive(Clone, Copy, Debug)]
enum Command {
    Literal(u8),
    Copy { length: usize, distance: usize },
}

pub fn build(
    input_mdt: &Path,
    header_template: &Path,
    output_dir: &Path,
    relocatable: bool,
) -> Result<Report> {
    ensure!(
        !output_dir.exists(),
        "output directory already exists: {}",
        output_dir.display()
    );
    let source = fs::read(input_mdt)
        .with_context(|| format!("failed to read MDT input {}", input_mdt.display()))?;
    ensure!(!source.is_empty(), "cannot encode an empty MDT");
    ensure!(
        source.len() <= 0x00ff_ffff,
        "MDT decoded size exceeds the MDZ 24-bit field"
    );
    let template = fs::read(header_template).with_context(|| {
        format!(
            "failed to read MDZ header template {}",
            header_template.display()
        )
    })?;
    let template_size = u32::try_from(template.len()).context("MDZ template exceeds 4 GiB")?;
    let header = Header::parse(&template, template_size)?;
    ensure!(header.header_size >= 21, "MDZ template has no decoder mode");
    ensure!(
        template[0x14] == 2,
        "MDZ template does not use decoder mode 2"
    );

    let commands = tokenize(&source);
    let payload = encode_payload(&commands)?;
    ensure!(
        payload.len() <= 0x00ff_ffff,
        "encoded MDZ payload exceeds the 24-bit size field"
    );
    let encoded_output_size = header.header_size as usize + payload.len();
    if !relocatable {
        ensure!(
            encoded_output_size <= template.len(),
            "encoded MDZ is {encoded_output_size} bytes, exceeding the {}-byte source allocation",
            template.len()
        );
    }
    let declared_payload_size = if relocatable {
        payload.len()
    } else {
        template.len() - header.header_size as usize
    };
    let padding_size = declared_payload_size - payload.len();

    let mut output = template[..header.header_size as usize - 1].to_vec();
    write_u24(&mut output[7..10], declared_payload_size)?;
    write_u24(&mut output[11..14], source.len())?;
    output.extend_from_slice(&payload);
    output.resize(header.header_size as usize - 1 + declared_payload_size, 0);
    output.push(0);
    ensure!(
        output.len() == header.header_size as usize + declared_payload_size,
        "MDZ output size composition error"
    );
    let decoded = mdz::decode(&output)?;
    if decoded != source {
        let mismatch = decoded
            .iter()
            .zip(&source)
            .position(|(actual, expected)| actual != expected)
            .unwrap_or(decoded.len().min(source.len()));
        let mut cursor = 0;
        let mut source_command = None;
        for (index, &command) in commands.iter().enumerate() {
            let length = match command {
                Command::Literal(_) => 1,
                Command::Copy { length, .. } => length,
            };
            if (cursor..cursor + length).contains(&mismatch) {
                source_command = Some((index, cursor, command));
                break;
            }
            cursor += length;
        }
        anyhow::bail!(
            "encoded MDZ first differs from source at offset {mismatch:#x}; source command {source_command:?}; expected {:02x?}, decoded {:02x?}",
            &source[mismatch..(mismatch + 8).min(source.len())],
            &decoded[mismatch..(mismatch + 8).min(decoded.len())]
        );
    }

    let literal_count = commands
        .iter()
        .filter(|command| matches!(command, Command::Literal(_)))
        .count();
    let copy_count = commands.len() - literal_count;
    let report = Report {
        schema_version: 1,
        status: "research_only_not_product_input",
        source_mdt_size: source.len(),
        source_mdt_sha256: sha256(&source),
        header_template_size: template.len(),
        header_template_sha256: sha256(&template),
        allocation_limit: template.len(),
        relocatable,
        relocation_required: output.len() > template.len(),
        encoded_payload_size: payload.len(),
        payload_size: declared_payload_size,
        padding_size,
        output_size: output.len(),
        output_sha256: sha256(&output),
        command_count: commands.len(),
        literal_count,
        copy_count,
        roundtrip_verified: true,
    };
    publish(output_dir, &output, &report)?;
    Ok(report)
}

fn tokenize(input: &[u8]) -> Vec<Command> {
    let mut heads = vec![usize::MAX; HASH_SIZE];
    let mut previous = vec![usize::MAX; input.len()];
    let mut commands = Vec::new();
    let mut position = 0;
    while position < input.len() {
        let (length, distance) = find_match(input, position, &heads, &previous);
        if length >= 3 {
            insert_position(input, position, &mut heads, &mut previous);
            let next_length = find_match(input, position + 1, &heads, &previous).0;
            if next_length > length + 1 {
                commands.push(Command::Literal(input[position]));
                position += 1;
                continue;
            }
            commands.push(Command::Copy { length, distance });
            let end = position + length;
            position += 1;
            while position < end {
                insert_position(input, position, &mut heads, &mut previous);
                position += 1;
            }
        } else {
            commands.push(Command::Literal(input[position]));
            insert_position(input, position, &mut heads, &mut previous);
            position += 1;
        }
    }
    commands
}

fn find_match(
    input: &[u8],
    position: usize,
    heads: &[usize],
    previous: &[usize],
) -> (usize, usize) {
    if position + 3 > input.len() {
        return (0, 0);
    }
    let max_length = MAX_COPY.min(input.len() - position);
    let mut candidate = heads[hash3(&input[position..position + 3])];
    let mut best_length = 0;
    let mut best_distance = 0;
    let mut searched = 0;
    while candidate != usize::MAX
        && position - candidate <= HISTORY_SIZE
        && searched < MAX_CHAIN_SEARCH
    {
        let mut length = 0;
        while length < max_length && input[candidate + length] == input[position + length] {
            length += 1;
        }
        if length > best_length {
            best_length = length;
            best_distance = position - candidate;
            if length == max_length {
                break;
            }
        }
        candidate = previous[candidate];
        searched += 1;
    }
    (best_length, best_distance)
}

fn insert_position(input: &[u8], position: usize, heads: &mut [usize], previous: &mut [usize]) {
    if position + 3 > input.len() {
        return;
    }
    let hash = hash3(&input[position..position + 3]);
    previous[position] = heads[hash];
    heads[hash] = position;
}

fn hash3(bytes: &[u8]) -> usize {
    ((usize::from(bytes[0]) * 251 + usize::from(bytes[1])) * 251 + usize::from(bytes[2]))
        & (HASH_SIZE - 1)
}

fn encode_payload(commands: &[Command]) -> Result<Vec<u8>> {
    let mut bits = BitWriter::default();
    for block in commands.chunks(MAX_BLOCK_COMMANDS) {
        bits.write(block.len(), 16)?;
        let mut command_frequencies = vec![0_u64; 510];
        let mut offset_frequencies = vec![0_u64; 16];
        for &command in block {
            match command {
                Command::Literal(byte) => command_frequencies[usize::from(byte)] += 1,
                Command::Copy { length, distance } => {
                    command_frequencies[256 + length - 3] += 1;
                    offset_frequencies[offset_width(distance)] += 1;
                }
            }
        }
        if offset_frequencies.iter().all(|&frequency| frequency == 0) {
            offset_frequencies[0] = 1;
        }
        let command_codes = Codebook::from_frequencies(&command_frequencies)?;
        let offset_codes = Codebook::from_frequencies(&offset_frequencies)?;
        write_tables(&mut bits, &command_codes, &offset_codes)?;
        for &command in block {
            match command {
                Command::Literal(byte) => command_codes.write(&mut bits, usize::from(byte))?,
                Command::Copy { length, distance } => {
                    ensure!((3..=MAX_COPY).contains(&length), "invalid copy length");
                    ensure!(
                        (1..=HISTORY_SIZE).contains(&distance),
                        "invalid copy distance"
                    );
                    command_codes.write(&mut bits, 256 + length - 3)?;
                    write_offset(&mut bits, &offset_codes, distance)?;
                }
            }
        }
    }
    Ok(bits.finish())
}

fn write_tables(
    bits: &mut BitWriter,
    command_codes: &Codebook,
    offset_codes: &Codebook,
) -> Result<()> {
    // A complete fixed temporary tree keeps table serialization simple:
    // symbols 0..12 use four bits and 13..18 use five bits.
    bits.write(19, 5)?;
    for symbol in 0..19 {
        write_length(bits, if symbol < 13 { 4 } else { 5 })?;
        if symbol == 2 {
            bits.write(0, 2)?;
        }
    }

    if let Some(symbol) = command_codes.single_symbol {
        bits.write(0, 9)?;
        bits.write(symbol, 9)?;
    } else {
        let count = last_nonzero(&command_codes.lengths) + 1;
        bits.write(count, 9)?;
        write_code_lengths(bits, &command_codes.lengths[..count])?;
    }

    if let Some(symbol) = offset_codes.single_symbol {
        bits.write(0, 5)?;
        bits.write(symbol, 5)?;
    } else {
        let count = last_nonzero(&offset_codes.lengths) + 1;
        bits.write(count, 5)?;
        for &length in &offset_codes.lengths[..count] {
            write_length(bits, length)?;
        }
    }
    Ok(())
}

fn write_code_lengths(bits: &mut BitWriter, lengths: &[u8]) -> Result<()> {
    let mut index = 0;
    while index < lengths.len() {
        if lengths[index] != 0 {
            write_temp_code(bits, usize::from(lengths[index]) + 2)?;
            index += 1;
            continue;
        }
        let mut run = 1;
        while index + run < lengths.len() && lengths[index + run] == 0 {
            run += 1;
        }
        let mut remaining = run;
        while remaining >= 20 {
            let count = remaining.min(531);
            write_temp_code(bits, 2)?;
            bits.write(count - 20, 9)?;
            remaining -= count;
        }
        if remaining >= 3 {
            let count = remaining.min(18);
            write_temp_code(bits, 1)?;
            bits.write(count - 3, 4)?;
            remaining -= count;
        }
        for _ in 0..remaining {
            write_temp_code(bits, 0)?;
        }
        index += run;
    }
    Ok(())
}

fn write_temp_code(bits: &mut BitWriter, symbol: usize) -> Result<()> {
    ensure!(symbol < 19, "temporary Huffman symbol is out of range");
    if symbol < 13 {
        bits.write(symbol, 4)
    } else {
        bits.write(symbol + 13, 5)
    }
}

fn write_length(bits: &mut BitWriter, length: u8) -> Result<()> {
    ensure!(length <= 16, "Huffman length exceeds 16 bits");
    if length < 7 {
        bits.write(usize::from(length), 3)
    } else {
        bits.write(7, 3)?;
        for _ in 7..length {
            bits.write(1, 1)?;
        }
        bits.write(0, 1)
    }
}

fn write_offset(bits: &mut BitWriter, codes: &Codebook, distance: usize) -> Result<()> {
    let offset = distance - 1;
    if offset == 0 {
        return codes.write(bits, 0);
    }
    let width = offset_width(distance);
    ensure!(width <= 15, "copy offset exceeds the history width");
    codes.write(bits, width)?;
    bits.write(offset - (1 << (width - 1)), width - 1)
}

fn offset_width(distance: usize) -> usize {
    let offset = distance - 1;
    if offset == 0 {
        0
    } else {
        usize::BITS as usize - offset.leading_zeros() as usize
    }
}

fn last_nonzero(lengths: &[u8]) -> usize {
    lengths.iter().rposition(|&length| length != 0).unwrap()
}

struct Codebook {
    lengths: Vec<u8>,
    codes: Vec<Option<(usize, usize)>>,
    single_symbol: Option<usize>,
}

impl Codebook {
    fn from_frequencies(frequencies: &[u64]) -> Result<Self> {
        let used: Vec<usize> = frequencies
            .iter()
            .enumerate()
            .filter_map(|(symbol, &frequency)| (frequency != 0).then_some(symbol))
            .collect();
        ensure!(!used.is_empty(), "Huffman alphabet has no used symbols");
        if used.len() == 1 {
            return Ok(Self {
                lengths: vec![0; frequencies.len()],
                codes: vec![None; frequencies.len()],
                single_symbol: Some(used[0]),
            });
        }

        let mut parents = vec![usize::MAX; frequencies.len() + used.len() - 1];
        let mut heap = BinaryHeap::new();
        for &symbol in &used {
            heap.push(Reverse((frequencies[symbol], symbol)));
        }
        let mut next_node = frequencies.len();
        while heap.len() > 1 {
            let Reverse((left_weight, left)) = heap.pop().unwrap();
            let Reverse((right_weight, right)) = heap.pop().unwrap();
            parents[left] = next_node;
            parents[right] = next_node;
            heap.push(Reverse((left_weight + right_weight, next_node)));
            next_node += 1;
        }

        let mut raw_lengths = vec![0_usize; frequencies.len()];
        for &symbol in &used {
            let mut node = symbol;
            while parents[node] != usize::MAX {
                raw_lengths[symbol] += 1;
                node = parents[node];
            }
        }
        let mut counts = [0_usize; 17];
        let mut overflow = 0_usize;
        for &symbol in &used {
            let length = raw_lengths[symbol].min(16);
            counts[length] += 1;
            if raw_lengths[symbol] > 16 {
                overflow += 1;
            }
        }
        while overflow > 0 {
            let mut width = 15;
            while counts[width] == 0 {
                width -= 1;
            }
            counts[width] -= 1;
            counts[width + 1] += 2;
            counts[16] -= 1;
            overflow -= 2;
        }

        let mut by_frequency = used.clone();
        by_frequency.sort_by_key(|&symbol| (frequencies[symbol], symbol));
        let mut lengths = vec![0_u8; frequencies.len()];
        let mut cursor = 0;
        for width in (1..=16).rev() {
            for _ in 0..counts[width] {
                let symbol = by_frequency[cursor];
                lengths[symbol] = width as u8;
                cursor += 1;
            }
        }
        ensure!(cursor == used.len(), "Huffman length assignment mismatch");
        let codes = canonical_codes(&lengths)?;
        Ok(Self {
            lengths,
            codes,
            single_symbol: None,
        })
    }

    fn write(&self, bits: &mut BitWriter, symbol: usize) -> Result<()> {
        if self.single_symbol == Some(symbol) {
            return Ok(());
        }
        let (code, width) = self
            .codes
            .get(symbol)
            .and_then(|entry| *entry)
            .context("missing Huffman code for used symbol")?;
        bits.write(code, width)
    }
}

fn canonical_codes(lengths: &[u8]) -> Result<Vec<Option<(usize, usize)>>> {
    let max_length = usize::from(lengths.iter().copied().max().unwrap_or(0));
    ensure!(max_length > 0, "Huffman table has no lengths");
    let mut counts = vec![0_usize; max_length + 1];
    for &length in lengths {
        if length != 0 {
            counts[usize::from(length)] += 1;
        }
    }
    let mut next_codes = vec![0_usize; max_length + 1];
    let mut code = 0;
    for width in 1..=max_length {
        code = (code + counts[width - 1]) << 1;
        ensure!(code + counts[width] <= 1 << width, "oversubscribed tree");
        next_codes[width] = code;
    }
    ensure!(
        code + counts[max_length] == 1 << max_length,
        "incomplete tree"
    );
    let mut result = vec![None; lengths.len()];
    for (symbol, &length) in lengths.iter().enumerate() {
        if length == 0 {
            continue;
        }
        let width = usize::from(length);
        result[symbol] = Some((next_codes[width], width));
        next_codes[width] += 1;
    }
    Ok(result)
}

#[derive(Default)]
struct BitWriter {
    bytes: Vec<u8>,
    bit_pos: usize,
}

impl BitWriter {
    fn write(&mut self, value: usize, width: usize) -> Result<()> {
        ensure!(width <= 16, "cannot write more than 16 bits at once");
        ensure!(
            width == usize::BITS as usize || value < (1_usize << width),
            "value does not fit requested bit width"
        );
        for shift in (0..width).rev() {
            if self.bit_pos.is_multiple_of(8) {
                self.bytes.push(0);
            }
            let bit = ((value >> shift) & 1) as u8;
            let byte_index = self.bit_pos / 8;
            self.bytes[byte_index] |= bit << (7 - self.bit_pos % 8);
            self.bit_pos += 1;
        }
        Ok(())
    }

    fn finish(self) -> Vec<u8> {
        self.bytes
    }
}

fn write_u24(bytes: &mut [u8], value: usize) -> Result<()> {
    ensure!(bytes.len() == 3, "u24 destination has the wrong size");
    ensure!(value <= 0x00ff_ffff, "value exceeds 24 bits");
    bytes[0] = value as u8;
    bytes[1] = (value >> 8) as u8;
    bytes[2] = (value >> 16) as u8;
    Ok(())
}

fn publish(output_dir: &Path, output: &[u8], report: &Report) -> Result<()> {
    let staging_dir = staging_path(output_dir)?;
    ensure!(
        !staging_dir.exists(),
        "staging directory already exists: {}",
        staging_dir.display()
    );
    let result = (|| -> Result<()> {
        fs::create_dir_all(&staging_dir)?;
        write_synced(&staging_dir.join("GR3.MDZ"), output)?;
        let mut manifest = serde_json::to_vec_pretty(report)?;
        manifest.push(b'\n');
        write_synced(&staging_dir.join("manifest.json"), &manifest)?;
        fs::rename(&staging_dir, output_dir)
            .with_context(|| format!("failed to publish MDZ candidate {}", output_dir.display()))?;
        Ok(())
    })();
    if result.is_err() {
        let _ = fs::remove_dir_all(&staging_dir);
    }
    result
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

fn sha256(bytes: &[u8]) -> String {
    format!("{:x}", Sha256::digest(bytes))
}

#[cfg(test)]
mod tests {
    use super::{encode_payload, tokenize};
    use crate::mdz;

    #[test]
    fn roundtrips_literals_and_back_references() {
        let mut source: Vec<u8> = (0..=255).collect();
        source.extend_from_slice(&vec![0_u8; 2048]);
        source.extend_from_slice(b"Grandia III Grandia III Grandia III");
        let payload = encode_payload(&tokenize(&source)).unwrap();
        let mut container = vec![0_u8; 23];
        container[0] = 23;
        container[2..6].copy_from_slice(b"MDZ\0");
        let payload_len = payload.len();
        container[7] = payload_len as u8;
        container[8] = (payload_len >> 8) as u8;
        container[9] = (payload_len >> 16) as u8;
        container[11] = source.len() as u8;
        container[12] = (source.len() >> 8) as u8;
        container[13] = (source.len() >> 16) as u8;
        container[20] = 2;
        container.extend_from_slice(&payload);
        container.push(0);

        assert_eq!(mdz::decode(&container).unwrap(), source);
    }
}
