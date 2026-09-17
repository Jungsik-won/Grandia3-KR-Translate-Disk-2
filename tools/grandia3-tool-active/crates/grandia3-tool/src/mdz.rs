use anyhow::{Context, Result, bail, ensure};
use serde::{Deserialize, Serialize};

const COPY_THRESHOLD: usize = 3;
const HISTORY_BITS: usize = 15;
const HISTORY_SIZE: usize = 1 << HISTORY_BITS;
const NUM_CODES: usize = 510;
const NUM_TEMP_CODES: usize = 19;
const NUM_OFFSET_CODES: usize = 16;

#[derive(Clone, Debug, Deserialize, Eq, PartialEq, Serialize)]
pub struct Header {
    pub header_size: u32,
    pub compressed_size: u32,
    pub decoded_size_field: u32,
    pub field_0f: u32,
    pub embedded_name: Option<String>,
}

impl Header {
    pub fn parse(prefix: &[u8], file_size: u32) -> Result<Self> {
        ensure!(prefix.len() >= 18, "MDZ header is shorter than 18 bytes");
        ensure!(&prefix[2..6] == b"MDZ\0", "MDZ magic is missing");

        let header_size = u32::from(prefix[0]) + 1;
        ensure!(header_size >= 18, "invalid MDZ header size {header_size}");
        ensure!(
            prefix.len() >= header_size as usize,
            "MDZ prefix does not include full header"
        );
        ensure!(
            prefix[6] == 0,
            "unsupported nonzero MDZ field prefix at 0x06"
        );
        ensure!(
            prefix[10] == 0,
            "unsupported nonzero MDZ field prefix at 0x0A"
        );
        ensure!(
            prefix[14] == 0,
            "unsupported nonzero MDZ field prefix at 0x0E"
        );
        let compressed_size = read_u24(&prefix[7..10]);
        ensure!(
            u64::from(header_size) + u64::from(compressed_size) == u64::from(file_size),
            "MDZ header ({header_size}) + payload ({compressed_size}) != file size ({file_size})"
        );

        let header_bytes = &prefix[..header_size as usize];
        Ok(Self {
            header_size,
            compressed_size,
            decoded_size_field: read_u24(&prefix[11..14]),
            field_0f: read_u24(&prefix[15..18]),
            embedded_name: find_embedded_mdt_name(header_bytes),
        })
    }
}

pub fn decode(container: &[u8]) -> Result<Vec<u8>> {
    let file_size = u32::try_from(container.len()).context("MDZ container exceeds 4 GiB")?;
    let header = Header::parse(container, file_size)?;
    ensure!(
        header.header_size >= 21,
        "MDZ header does not contain a decoder mode"
    );
    ensure!(
        container[0x14] == 2,
        "unsupported MDZ decoder mode {}",
        container[0x14]
    );

    // The game seeds its bit reader with the final header byte, then consumes
    // the declared compressed byte count from that overlapping position.
    let stream_start = header.header_size as usize - 1;
    let stream_end = stream_start + header.compressed_size as usize;
    let payload = &container[stream_start..stream_end];
    let mut decoder = Decoder::new(payload, header.decoded_size_field as usize);
    decoder.decode()
}

struct Decoder<'a> {
    bits: BitReader<'a>,
    history: Vec<u8>,
    history_pos: usize,
    output: Vec<u8>,
    decoded_size: usize,
    block_remaining: usize,
    code_tree: Huffman,
    offset_tree: Huffman,
}

impl<'a> Decoder<'a> {
    fn new(payload: &'a [u8], decoded_size: usize) -> Self {
        Self {
            bits: BitReader::new(payload),
            history: vec![b' '; HISTORY_SIZE],
            history_pos: 0,
            output: Vec::with_capacity(decoded_size),
            decoded_size,
            block_remaining: 0,
            code_tree: Huffman::Single(0),
            offset_tree: Huffman::Single(0),
        }
    }

    fn decode(&mut self) -> Result<Vec<u8>> {
        while self.output.len() < self.decoded_size {
            if self.block_remaining == 0 {
                self.start_block()?;
                ensure!(
                    self.block_remaining > 0,
                    "MDZ contains an empty command block"
                );
            }
            self.block_remaining -= 1;

            let code = self.code_tree.read(&mut self.bits)?;
            ensure!(code < NUM_CODES, "MDZ command code {code} is out of range");
            if code < 256 {
                self.output_byte(code as u8);
            } else {
                let count = code - 256 + COPY_THRESHOLD;
                ensure!(
                    self.output.len() + count <= self.decoded_size,
                    "MDZ back-reference exceeds declared decoded size"
                );
                self.copy_from_history(count)?;
            }
        }

        Ok(std::mem::take(&mut self.output))
    }

    fn start_block(&mut self) -> Result<()> {
        self.block_remaining = self.bits.read(16)?;
        let temp_tree = read_table(&mut self.bits, NUM_TEMP_CODES, 5, Some(3))?;
        self.code_tree = read_code_table(&mut self.bits, &temp_tree)?;
        self.offset_tree = read_table(&mut self.bits, NUM_OFFSET_CODES, 5, None)?;
        Ok(())
    }

    fn output_byte(&mut self, byte: u8) {
        self.output.push(byte);
        self.history[self.history_pos] = byte;
        self.history_pos = (self.history_pos + 1) & (HISTORY_SIZE - 1);
    }

    fn copy_from_history(&mut self, count: usize) -> Result<()> {
        let offset_bits = self.offset_tree.read(&mut self.bits)?;
        ensure!(
            offset_bits <= HISTORY_BITS,
            "MDZ offset code {offset_bits} exceeds the history width"
        );
        let offset = if offset_bits == 0 {
            0
        } else {
            (1 << (offset_bits - 1)) + self.bits.read(offset_bits - 1)?
        };
        ensure!(offset < HISTORY_SIZE, "MDZ history offset is out of range");

        let start = self
            .history_pos
            .wrapping_add(HISTORY_SIZE)
            .wrapping_sub(offset)
            .wrapping_sub(1);
        for index in 0..count {
            let byte = self.history[(start + index) & (HISTORY_SIZE - 1)];
            self.output_byte(byte);
        }
        Ok(())
    }
}

fn read_table(
    bits: &mut BitReader<'_>,
    symbol_count: usize,
    count_bits: usize,
    zero_run_after: Option<usize>,
) -> Result<Huffman> {
    let count = bits.read(count_bits)?;
    if count == 0 {
        let symbol = bits.read(count_bits)?;
        ensure!(
            symbol < symbol_count,
            "single Huffman symbol is out of range"
        );
        return Ok(Huffman::Single(symbol));
    }
    ensure!(
        count <= symbol_count,
        "Huffman table declares {count} symbols, maximum is {symbol_count}"
    );

    let mut lengths = vec![0_u8; symbol_count];
    let mut index = 0;
    while index < count {
        lengths[index] = read_length(bits)?;
        index += 1;
        if zero_run_after == Some(index) {
            let zeros = bits.read(2)?;
            ensure!(
                index + zeros <= count,
                "Huffman zero run exceeds declared symbol count"
            );
            index += zeros;
        }
    }
    Huffman::from_lengths(&lengths)
}

fn read_code_table(bits: &mut BitReader<'_>, temp_tree: &Huffman) -> Result<Huffman> {
    let count = bits.read(9)?;
    if count == 0 {
        let symbol = bits.read(9)?;
        ensure!(symbol < NUM_CODES, "single command symbol is out of range");
        return Ok(Huffman::Single(symbol));
    }
    ensure!(
        count <= NUM_CODES,
        "command table declares {count} symbols, maximum is {NUM_CODES}"
    );

    let mut lengths = vec![0_u8; NUM_CODES];
    let mut index = 0;
    while index < count {
        let code = temp_tree.read(bits)?;
        if code <= 2 {
            let zeros = match code {
                0 => 1,
                1 => bits.read(4)? + 3,
                2 => bits.read(9)? + 20,
                _ => unreachable!(),
            };
            ensure!(
                index + zeros <= count,
                "command-table zero run exceeds declared symbol count"
            );
            index += zeros;
        } else {
            lengths[index] = u8::try_from(code - 2).context("Huffman length overflow")?;
            index += 1;
        }
    }
    Huffman::from_lengths(&lengths)
}

fn read_length(bits: &mut BitReader<'_>) -> Result<u8> {
    let mut length = bits.read(3)?;
    if length == 7 {
        while bits.read(1)? != 0 {
            length += 1;
            ensure!(length <= 16, "Huffman code length exceeds 16 bits");
        }
    }
    Ok(length as u8)
}

struct BitReader<'a> {
    bytes: &'a [u8],
    bit_pos: usize,
}

impl<'a> BitReader<'a> {
    fn new(bytes: &'a [u8]) -> Self {
        Self { bytes, bit_pos: 0 }
    }

    fn read(&mut self, count: usize) -> Result<usize> {
        ensure!(count <= 16, "cannot read more than 16 bits at once");
        ensure!(
            self.bit_pos + count <= self.bytes.len() * 8,
            "unexpected end of MDZ compressed payload"
        );
        let mut value = 0;
        for _ in 0..count {
            let byte = self.bytes[self.bit_pos / 8];
            let bit = (byte >> (7 - self.bit_pos % 8)) & 1;
            value = (value << 1) | usize::from(bit);
            self.bit_pos += 1;
        }
        Ok(value)
    }
}

enum Huffman {
    Single(usize),
    Tree(Vec<Node>),
}

#[derive(Clone, Copy, Default)]
struct Node {
    children: [Option<usize>; 2],
    symbol: Option<usize>,
}

impl Huffman {
    fn from_lengths(lengths: &[u8]) -> Result<Self> {
        let max_length = lengths.iter().copied().max().unwrap_or(0) as usize;
        ensure!(max_length > 0, "Huffman table has no symbols");
        ensure!(max_length <= 16, "Huffman code length exceeds 16 bits");

        let mut counts = vec![0_usize; max_length + 1];
        for &length in lengths {
            if length != 0 {
                counts[length as usize] += 1;
            }
        }

        let mut next_codes = vec![0_usize; max_length + 1];
        let mut code = 0_usize;
        for width in 1..=max_length {
            code = (code + counts[width - 1]) << 1;
            ensure!(
                code + counts[width] <= 1 << width,
                "oversubscribed Huffman table"
            );
            next_codes[width] = code;
        }
        ensure!(
            code + counts[max_length] == 1 << max_length,
            "incomplete Huffman table"
        );

        let mut nodes = vec![Node::default()];
        for (symbol, &length) in lengths.iter().enumerate() {
            if length == 0 {
                continue;
            }
            let width = length as usize;
            let symbol_code = next_codes[width];
            next_codes[width] += 1;
            let mut node_index = 0;
            for shift in (0..width).rev() {
                ensure!(
                    nodes[node_index].symbol.is_none(),
                    "Huffman code extends through a leaf"
                );
                let branch = (symbol_code >> shift) & 1;
                let child = match nodes[node_index].children[branch] {
                    Some(child) => child,
                    None => {
                        let child = nodes.len();
                        nodes.push(Node::default());
                        nodes[node_index].children[branch] = Some(child);
                        child
                    }
                };
                node_index = child;
            }
            ensure!(
                nodes[node_index].symbol.is_none() && nodes[node_index].children == [None, None],
                "duplicate or prefix-conflicting Huffman code"
            );
            nodes[node_index].symbol = Some(symbol);
        }
        Ok(Self::Tree(nodes))
    }

    fn read(&self, bits: &mut BitReader<'_>) -> Result<usize> {
        match self {
            Self::Single(symbol) => Ok(*symbol),
            Self::Tree(nodes) => {
                let mut node_index = 0;
                for _ in 0..=16 {
                    if let Some(symbol) = nodes[node_index].symbol {
                        return Ok(symbol);
                    }
                    let branch = bits.read(1)?;
                    node_index = nodes[node_index].children[branch]
                        .context("compressed bit sequence is absent from Huffman table")?;
                }
                bail!("Huffman code exceeds 16 bits")
            }
        }
    }
}

fn read_u24(bytes: &[u8]) -> u32 {
    u32::from(bytes[0]) | (u32::from(bytes[1]) << 8) | (u32::from(bytes[2]) << 16)
}

fn find_embedded_mdt_name(bytes: &[u8]) -> Option<String> {
    for end in 4..=bytes.len() {
        if !bytes[end - 4..end].eq_ignore_ascii_case(b".MDT") {
            continue;
        }
        let mut start = end - 4;
        while start > 0 && bytes[start - 1].is_ascii_graphic() {
            start -= 1;
        }
        let candidate = &bytes[start..end];
        if candidate.iter().all(u8::is_ascii_graphic) {
            return Some(String::from_utf8_lossy(candidate).into_owned());
        }
    }
    None
}

#[cfg(test)]
mod tests {
    use super::{BitReader, Header, Huffman, decode};

    #[test]
    fn parses_observed_container_shape() {
        let mut bytes = vec![0_u8; 32];
        bytes[0] = 23;
        bytes[2..6].copy_from_slice(b"MDZ\0");
        bytes[7] = 8;
        bytes[11] = 64;
        bytes[16..24].copy_from_slice(b"TEST.MDT");

        let header = Header::parse(&bytes, 32).unwrap();
        assert_eq!(header.header_size, 24);
        assert_eq!(header.compressed_size, 8);
        assert_eq!(header.decoded_size_field, 64);
        assert_eq!(header.embedded_name.as_deref(), Some("TEST.MDT"));
    }

    #[test]
    fn rejects_payload_length_mismatch() {
        let mut bytes = vec![0_u8; 24];
        bytes[0] = 23;
        bytes[2..6].copy_from_slice(b"MDZ\0");
        bytes[7] = 7;
        assert!(Header::parse(&bytes, 32).is_err());
    }

    #[test]
    fn reads_bits_most_significant_first() {
        let mut reader = BitReader::new(&[0b1011_0010, 0b0110_0000]);
        assert_eq!(reader.read(3).unwrap(), 0b101);
        assert_eq!(reader.read(6).unwrap(), 0b100100);
        assert_eq!(reader.read(3).unwrap(), 0b110);
    }

    #[test]
    fn decodes_canonical_huffman_codes() {
        let tree = Huffman::from_lengths(&[1, 2, 2]).unwrap();
        let mut reader = BitReader::new(&[0b0101_1000]);
        assert_eq!(tree.read(&mut reader).unwrap(), 0);
        assert_eq!(tree.read(&mut reader).unwrap(), 1);
        assert_eq!(tree.read(&mut reader).unwrap(), 2);
    }

    #[test]
    fn rejects_incomplete_huffman_table() {
        assert!(Huffman::from_lengths(&[2, 2]).is_err());
    }

    #[test]
    fn decodes_single_literal_block() {
        let stream = pack_bits(&[
            (512, 16),
            (0, 5),
            (0, 5),
            (0, 9),
            (b'A' as usize, 9),
            (0, 5),
            (0, 5),
        ]);
        assert_eq!(stream[0], 2);

        let mut container = vec![0_u8; 21 + stream.len()];
        container[0] = 20;
        container[2..6].copy_from_slice(b"MDZ\0");
        write_u24(&mut container[7..10], stream.len());
        write_u24(&mut container[11..14], 512);
        container[20..20 + stream.len()].copy_from_slice(&stream);

        assert_eq!(decode(&container).unwrap(), vec![b'A'; 512]);
    }

    fn pack_bits(fields: &[(usize, usize)]) -> Vec<u8> {
        let bit_count: usize = fields.iter().map(|(_, width)| width).sum();
        let mut bytes = vec![0_u8; bit_count.div_ceil(8)];
        let mut bit_pos = 0;
        for &(value, width) in fields {
            for shift in (0..width).rev() {
                bytes[bit_pos / 8] |= ((value >> shift) as u8 & 1) << (7 - bit_pos % 8);
                bit_pos += 1;
            }
        }
        bytes
    }

    fn write_u24(bytes: &mut [u8], value: usize) {
        bytes[0] = value as u8;
        bytes[1] = (value >> 8) as u8;
        bytes[2] = (value >> 16) as u8;
    }
}
