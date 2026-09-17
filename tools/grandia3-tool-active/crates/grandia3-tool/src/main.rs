mod bdf;
mod compare;
mod custom_text_scan;
mod field_ui_candidate;
mod fnt;
mod font_extension;
mod font_overlay;
mod font_resources;
mod inspect;
mod iso9660;
mod iso_candidate;
mod iso_text_scan;
mod manifest;
mod mdt;
mod mdz;
mod mdz_encode;
mod mdz_verify;
mod skj;
mod text_extract;
mod text_scan;
mod translation_draft;
mod translation_verify;

use std::env;
use std::ffi::OsString;
use std::fs;
use std::path::PathBuf;

use anyhow::{Context, Result, bail};

fn main() {
    if let Err(error) = run() {
        eprintln!("error: {error:#}");
        std::process::exit(1);
    }
}

fn run() -> Result<()> {
    let mut args = env::args_os().skip(1);
    let Some(command) = args.next() else {
        print_usage();
        bail!("missing command");
    };

    match command.to_string_lossy().as_ref() {
        "inspect" => run_inspect(args),
        "build-iso-candidate" => run_build_iso_candidate(args),
        "compare" => run_compare(args),
        "decode-mdz" => run_decode_mdz(args),
        "build-mdz-candidate" => run_build_mdz_candidate(args),
        "inspect-mdt" => run_inspect_mdt(args),
        "inspect-skj" => run_inspect_skj(args),
        "inspect-fnt" => run_inspect_fnt(args),
        "inspect-bdf" => run_inspect_bdf(args),
        "extract-font-resources" => run_extract_font_resources(args),
        "build-font-mdt-candidate" => run_build_font_mdt_candidate(args),
        "build-font-extension" => run_build_font_extension(args),
        "build-font-overlay" => run_build_font_overlay(args),
        "build-field-ui-candidate" => run_build_field_ui_candidate(args),
        "verify-mdz" => run_verify_mdz(args),
        "extract-text" => run_extract_text(args),
        "scan-mdt-text" => run_scan_mdt_text(args),
        "scan-raw-text" => run_scan_raw_text(args),
        "scan-iso-text" => run_scan_iso_text(args),
        "scan-iso-custom-text" => run_scan_iso_custom_text(args),
        "verify-translation" => run_verify_translation(args),
        "verify-translation-draft" => run_verify_translation_draft(args),
        _ => {
            print_usage();
            bail!("unsupported command: {}", command.to_string_lossy())
        }
    }
}

fn run_build_font_extension(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let input_mdt = PathBuf::from(args.next().context("missing decoded MDT path")?);
    let mut resource_plan = PathBuf::from("config/font-resources.json");
    let mut original_resources = None;
    let mut overlay_dir = None;
    let mut overlay_config = None;
    let mut output_dir = None;
    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--resource-plan" => {
                resource_plan = PathBuf::from(args.next().context("--resource-plan needs a path")?)
            }
            "--original-resources" => {
                original_resources = Some(PathBuf::from(
                    args.next().context("--original-resources needs a path")?,
                ))
            }
            "--overlay-dir" => {
                overlay_dir = Some(PathBuf::from(
                    args.next().context("--overlay-dir needs a path")?,
                ))
            }
            "--overlay-config" => {
                overlay_config = Some(PathBuf::from(
                    args.next().context("--overlay-config needs a path")?,
                ))
            }
            "--output-dir" => {
                output_dir = Some(PathBuf::from(
                    args.next().context("--output-dir needs a path")?,
                ))
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }
    let original_resources = original_resources.context("missing required --original-resources")?;
    let overlay_dir = overlay_dir.context("missing required --overlay-dir")?;
    let overlay_config = overlay_config.context("missing required --overlay-config")?;
    let output_dir = output_dir.context("missing required --output-dir")?;
    let report = font_extension::build(font_extension::Paths {
        input_mdt: &input_mdt,
        resource_plan: &resource_plan,
        original_resources: &original_resources,
        overlay_dir: &overlay_dir,
        overlay_config: &overlay_config,
        output_dir: &output_dir,
    })?;
    println!(
        "built research-only font extension: {} preserved + {} Korean = {} glyphs ({} map padding records)",
        report.original_glyph_count,
        report.korean_mapping_count,
        report.output_glyph_count,
        report.padding_map_count
    );
    println!("output: {}", output_dir.display());
    Ok(())
}

fn run_build_iso_candidate(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let source_iso = PathBuf::from(args.next().context("missing source ISO path")?);
    let mut field = None;
    let mut mdz = None;
    let mut plan = PathBuf::from("config/disc1-research-write-plan.json");
    let mut manifest = PathBuf::from("config/sources.json");
    let mut output_dir = None;
    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--field" => field = Some(PathBuf::from(args.next().context("--field needs a path")?)),
            "--mdz" => mdz = Some(PathBuf::from(args.next().context("--mdz needs a path")?)),
            "--plan" => plan = PathBuf::from(args.next().context("--plan needs a path")?),
            "--manifest" => {
                manifest = PathBuf::from(args.next().context("--manifest needs a path")?)
            }
            "--output-dir" => {
                output_dir = Some(PathBuf::from(
                    args.next().context("--output-dir needs a path")?,
                ))
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }
    let field = field.context("missing required --field path")?;
    let mdz = mdz.context("missing required --mdz path")?;
    let output_dir = output_dir.context("missing required --output-dir path")?;
    let report = iso_candidate::build(&source_iso, &field, &mdz, &plan, &manifest, &output_dir)?;
    println!(
        "built research-only Disc 1 ISO candidate: {} changed bytes, SHA-256 {}",
        report.changed_byte_count, report.output_sha256
    );
    println!("output: {}", output_dir.display());
    Ok(())
}

fn run_scan_iso_text(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let iso_path = PathBuf::from(args.next().context("missing ISO path")?);
    let mut manifest_path = PathBuf::from("config/sources.json");
    let mut json_path = None;
    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--manifest" => {
                manifest_path = PathBuf::from(args.next().context("--manifest needs a path")?);
            }
            "--json" => {
                json_path = Some(PathBuf::from(args.next().context("--json needs a path")?));
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }
    let report = iso_text_scan::scan(&iso_path, &manifest_path)?;
    println!(
        "scanned {} MDZ files ({} decoded bytes): {} strict text candidates in {} containers",
        report.mdz_count,
        report.total_decoded_bytes,
        report.candidate_count,
        report.containers_with_candidates
    );
    if let Some(path) = json_path {
        inspect::write_json_atomic(&path, &report)?;
        println!("report: {}", path.display());
    }
    Ok(())
}

fn run_scan_iso_custom_text(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let iso_path = PathBuf::from(args.next().context("missing ISO path")?);
    let mut manifest_path = PathBuf::from("config/sources.json");
    let mut codebook_path = None;
    let mut json_path = None;
    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--manifest" => {
                manifest_path = PathBuf::from(args.next().context("--manifest needs a path")?);
            }
            "--codebook" => {
                codebook_path = Some(PathBuf::from(
                    args.next().context("--codebook needs a path")?,
                ));
            }
            "--json" => {
                json_path = Some(PathBuf::from(args.next().context("--json needs a path")?));
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }
    let codebook_path = codebook_path.context("missing required --codebook path")?;
    let report = custom_text_scan::scan(&iso_path, &manifest_path, &codebook_path)?;
    println!(
        "scanned {} MDZ files ({} decoded bytes): {} custom-text clusters / {} candidates in {} containers",
        report.mdz_count,
        report.total_decoded_bytes,
        report.cluster_count,
        report.candidate_count,
        report.containers_with_clusters
    );
    if let Some(path) = json_path {
        inspect::write_json_atomic(&path, &report)?;
        println!("report: {}", path.display());
    }
    Ok(())
}

fn run_build_mdz_candidate(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let input_path = PathBuf::from(args.next().context("missing MDT input path")?);
    let mut header_template = None;
    let mut output_dir = None;
    let mut relocatable = false;
    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--header-template" => {
                header_template = Some(PathBuf::from(
                    args.next().context("--header-template needs a path")?,
                ));
            }
            "--output-dir" => {
                output_dir = Some(PathBuf::from(
                    args.next().context("--output-dir needs a path")?,
                ));
            }
            "--relocatable" => relocatable = true,
            unknown => bail!("unknown option: {unknown}"),
        }
    }
    let header_template = header_template.context("missing required --header-template path")?;
    let output_dir = output_dir.context("missing required --output-dir path")?;
    let report = mdz_encode::build(&input_path, &header_template, &output_dir, relocatable)?;
    println!(
        "built research-only GR3.MDZ candidate: {} bytes, {} commands, roundtrip verified",
        report.output_size, report.command_count
    );
    println!("output: {}", output_dir.display());
    Ok(())
}

fn run_build_font_mdt_candidate(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let input_path = PathBuf::from(args.next().context("missing decoded MDT path")?);
    let mut config_path = PathBuf::from("config/font-resources.json");
    let mut overlay_dir = None;
    let mut output_dir = None;
    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--config" => {
                config_path = PathBuf::from(args.next().context("--config needs a path")?);
            }
            "--overlay-dir" => {
                overlay_dir = Some(PathBuf::from(
                    args.next().context("--overlay-dir needs a path")?,
                ));
            }
            "--output-dir" => {
                output_dir = Some(PathBuf::from(
                    args.next().context("--output-dir needs a path")?,
                ));
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }
    let overlay_dir = overlay_dir.context("missing required --overlay-dir path")?;
    let output_dir = output_dir.context("missing required --output-dir path")?;
    let report = font_resources::repack(&input_path, &config_path, &overlay_dir, &output_dir)?;
    println!(
        "built research-only GR3.MDT font candidate: {} resources, {} changed bytes",
        report.resources.len(),
        report.changed_byte_count
    );
    println!("output: {}", output_dir.display());
    Ok(())
}

fn run_build_field_ui_candidate(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let field_bin = PathBuf::from(args.next().context("missing FIELD.BIN path")?);
    let mut draft = PathBuf::from("assets/translation/drafts/field-ui-ko-v1.json");
    let mut skj = None;
    let mut font_config = None;
    let mut output_dir = None;
    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--draft" => draft = PathBuf::from(args.next().context("--draft needs a path")?),
            "--skj" => skj = Some(PathBuf::from(args.next().context("--skj needs a path")?)),
            "--font-config" => {
                font_config = Some(PathBuf::from(
                    args.next().context("--font-config needs a path")?,
                ))
            }
            "--output-dir" => {
                output_dir = Some(PathBuf::from(
                    args.next().context("--output-dir needs a path")?,
                ))
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }
    let skj = skj.context("missing required --skj path")?;
    let font_config = font_config.context("missing required --font-config path")?;
    let output_dir = output_dir.context("missing required --output-dir path")?;
    let report = field_ui_candidate::build(field_ui_candidate::Paths {
        field_bin: &field_bin,
        draft: &draft,
        original_skj: &skj,
        font_config: &font_config,
        output_dir: &output_dir,
    })?;
    println!(
        "built research-only FIELD.BIN candidate: {} units, {} changed bytes",
        report.unit_count, report.changed_byte_count
    );
    println!("output: {}", output_dir.display());
    Ok(())
}

fn run_verify_translation_draft(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let mut draft_path = PathBuf::from("assets/translation/drafts/field-ui-ko-v1.json");
    let mut skj_path = None;
    let mut json_path = None;
    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--draft" => draft_path = PathBuf::from(args.next().context("--draft needs a path")?),
            "--skj" => skj_path = Some(PathBuf::from(args.next().context("--skj needs a path")?)),
            "--json" => {
                json_path = Some(PathBuf::from(args.next().context("--json needs a path")?))
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }
    let skj_path = skj_path.context("missing required --skj path")?;
    let report = translation_draft::verify(&draft_path, &skj_path)?;
    println!(
        "verified translation draft {}: {} units, {} Hangul syllables",
        report.draft_id, report.unit_count, report.hangul_syllable_count
    );
    if let Some(path) = json_path {
        inspect::write_json_atomic(&path, &report)?;
        println!("report: {}", path.display());
    }
    Ok(())
}

fn run_scan_raw_text(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let input_path = PathBuf::from(args.next().context("missing raw input path")?);
    let mut json_path = None;
    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--json" => {
                json_path = Some(PathBuf::from(args.next().context("--json needs a path")?))
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }
    let report = text_scan::scan_raw(&input_path)?;
    println!(
        "found {} strict Shift-JIS text candidates",
        report.candidate_count
    );
    if let Some(path) = json_path {
        inspect::write_json_atomic(&path, &report)?;
        println!("report: {}", path.display());
    }
    Ok(())
}

fn run_scan_mdt_text(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let input_path = PathBuf::from(args.next().context("missing MDT path")?);
    let mut json_path = None;
    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--json" => {
                json_path = Some(PathBuf::from(args.next().context("--json needs a path")?))
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }
    let report = text_scan::scan(&input_path)?;
    println!(
        "found {} Shift-JIS text candidates in {} chunks",
        report.candidate_count,
        report.chunks.len()
    );
    if let Some(path) = json_path {
        inspect::write_json_atomic(&path, &report)?;
        println!("report: {}", path.display());
    }
    Ok(())
}

fn run_build_font_overlay(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let input_dir = PathBuf::from(args.next().context("missing font resource directory")?);
    let mut main_bdf = None;
    let mut ruby_bdf = None;
    let mut config = None;
    let mut output_dir = None;
    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--main-bdf" => {
                main_bdf = Some(PathBuf::from(
                    args.next().context("--main-bdf needs a path")?,
                ))
            }
            "--ruby-bdf" => {
                ruby_bdf = Some(PathBuf::from(
                    args.next().context("--ruby-bdf needs a path")?,
                ))
            }
            "--config" => {
                config = Some(PathBuf::from(args.next().context("--config needs a path")?))
            }
            "--output-dir" => {
                output_dir = Some(PathBuf::from(
                    args.next().context("--output-dir needs a path")?,
                ))
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }
    let main_bdf = main_bdf.context("missing required --main-bdf")?;
    let ruby_bdf = ruby_bdf.context("missing required --ruby-bdf")?;
    let config = config.context("missing required --config")?;
    let output_dir = output_dir.context("missing required --output-dir")?;
    let report = font_overlay::build(font_overlay::Paths {
        input_dir: &input_dir,
        main_bdf: &main_bdf,
        ruby_bdf: &ruby_bdf,
        config: &config,
        output_dir: &output_dir,
    })?;
    println!(
        "built {} Korean font mappings in {}",
        report.mapping_count,
        output_dir.display()
    );
    Ok(())
}

fn run_inspect_bdf(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let input_path = PathBuf::from(args.next().context("missing BDF path")?);
    let mut expected_sha256 = None;
    let mut codepoint = None;
    let mut cell = None;
    let mut json_path = None;
    let mut pgm_path = None;
    let mut game_4bpp_path = None;

    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--sha256" => expected_sha256 = Some(args.next().context("--sha256 needs a value")?),
            "--codepoint" => codepoint = Some(args.next().context("--codepoint needs a value")?),
            "--cell" => cell = Some(args.next().context("--cell needs a value")?),
            "--json" => {
                json_path = Some(PathBuf::from(args.next().context("--json needs a path")?))
            }
            "--pgm" => pgm_path = Some(PathBuf::from(args.next().context("--pgm needs a path")?)),
            "--game-4bpp" => {
                game_4bpp_path = Some(PathBuf::from(
                    args.next().context("--game-4bpp needs a path")?,
                ))
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }

    let expected_sha256 = expected_sha256.context("missing required --sha256")?;
    let codepoint = parse_codepoint(&codepoint.context("missing required --codepoint")?)?;
    let cell = parse_cell(&cell.context("missing required --cell")?)?;
    let inspection = bdf::inspect(
        &input_path,
        &expected_sha256.to_string_lossy(),
        codepoint,
        cell,
    )?;
    println!(
        "verified BDF {} {} for {}x{} cell",
        inspection.report.family_name, inspection.report.codepoint, cell.width, cell.height
    );
    if let Some(path) = json_path {
        inspect::write_json_atomic(&path, &inspection.report)?;
        println!("report: {}", path.display());
    }
    if let Some(path) = pgm_path {
        inspect::write_bytes_atomic(&path, &inspection.pgm)?;
        println!("glyph preview: {}", path.display());
    }
    if let Some(path) = game_4bpp_path {
        inspect::write_bytes_atomic(&path, &inspection.game_4bpp)?;
        println!("game 4bpp glyph: {}", path.display());
    }
    Ok(())
}

fn parse_codepoint(value: &OsString) -> Result<u32> {
    let value = value.to_string_lossy();
    let digits = value
        .strip_prefix("U+")
        .or_else(|| value.strip_prefix("u+"))
        .context("codepoint must use U+XXXX form")?;
    u32::from_str_radix(digits, 16).context("invalid Unicode codepoint")
}

fn parse_cell(value: &OsString) -> Result<bdf::Cell> {
    let value = value.to_string_lossy();
    let (width, height) = value
        .split_once('x')
        .context("cell must use WIDTHxHEIGHT form")?;
    Ok(bdf::Cell {
        width: width.parse().context("invalid cell width")?,
        height: height.parse().context("invalid cell height")?,
    })
}

fn run_extract_font_resources(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let input_path = PathBuf::from(args.next().context("missing decoded MDT path")?);
    let mut config_path = PathBuf::from("config/font-resources.json");
    let mut output_dir = None;

    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--config" => {
                config_path = PathBuf::from(args.next().context("--config needs a path")?);
            }
            "--output-dir" => {
                output_dir = Some(PathBuf::from(
                    args.next().context("--output-dir needs a path")?,
                ));
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }

    let output_dir = output_dir.context("missing required --output-dir path")?;
    let report = font_resources::extract(&input_path, &config_path, &output_dir)?;
    println!(
        "extracted {} verified font resources to {}",
        report.resources.len(),
        output_dir.display()
    );
    Ok(())
}

fn run_inspect_fnt(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let input_path = PathBuf::from(args.next().context("missing FNT path")?);
    let mut json_path = None;
    let mut pgm_path = None;

    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--json" => {
                json_path = Some(PathBuf::from(args.next().context("--json needs a path")?));
            }
            "--pgm" => {
                pgm_path = Some(PathBuf::from(args.next().context("--pgm needs a path")?));
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }

    let report = fnt::inspect(&input_path)?;
    println!(
        "verified FNT {}: {} glyphs, {}x{} at {} bpp",
        input_path.display(),
        report.glyph_count,
        report.cell_width,
        report.cell_height,
        report.bits_per_pixel
    );
    if let Some(path) = json_path {
        inspect::write_json_atomic(&path, &report)?;
        println!("report: {}", path.display());
    }
    if let Some(path) = pgm_path {
        inspect::write_bytes_atomic(&path, &fnt::render_pgm(&input_path)?)?;
        println!("glyph atlas: {}", path.display());
    }
    Ok(())
}

fn run_inspect_skj(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let input_path = PathBuf::from(args.next().context("missing SKJ path")?);
    let mut json_path = None;

    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--json" => {
                json_path = Some(PathBuf::from(args.next().context("--json needs a path")?));
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }

    let report = skj::inspect(&input_path)?;
    println!(
        "verified SKJ {}: {} codes, {} unique",
        input_path.display(),
        report.code_count,
        report.unique_code_count
    );
    if let Some(path) = json_path {
        inspect::write_json_atomic(&path, &report)?;
        println!("report: {}", path.display());
    }
    Ok(())
}

fn run_inspect_mdt(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let input_path = PathBuf::from(args.next().context("missing MDT path")?);
    let mut json_path = None;

    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--json" => {
                json_path = Some(PathBuf::from(args.next().context("--json needs a path")?));
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }

    let report = mdt::inspect(&input_path)?;
    println!(
        "verified MDT {}: {} chunks, {} bytes",
        input_path.display(),
        report.chunk_count,
        report.file_size
    );
    if let Some(path) = json_path {
        inspect::write_json_atomic(&path, &report)?;
        println!("report: {}", path.display());
    }
    Ok(())
}

fn run_verify_translation(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let mut index_path = PathBuf::from("assets/translation/index.json");
    let mut approval_path = PathBuf::from("assets/translation/approvals/field-ui-v1.json");

    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--index" => {
                index_path = PathBuf::from(args.next().context("--index needs a path")?);
            }
            "--approval" => {
                approval_path = PathBuf::from(args.next().context("--approval needs a path")?);
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }

    let report = translation_verify::verify(&index_path, &approval_path)?;
    println!(
        "verified translation approval {}: {} segments, {} units",
        report.approval_id, report.segment_count, report.unit_count
    );
    Ok(())
}

fn run_decode_mdz(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let input_path = PathBuf::from(args.next().context("missing MDZ path")?);
    let mut output_path = None;

    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--output" => {
                output_path = Some(PathBuf::from(args.next().context("--output needs a path")?));
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }

    let output_path = output_path.context("missing required --output path")?;
    let container = fs::read(&input_path)
        .with_context(|| format!("failed to read MDZ container {}", input_path.display()))?;
    let decoded = mdz::decode(&container)
        .with_context(|| format!("failed to decode {}", input_path.display()))?;
    inspect::write_bytes_atomic(&output_path, &decoded)?;
    println!(
        "decoded {} bytes to {}",
        decoded.len(),
        output_path.display()
    );
    Ok(())
}

fn run_verify_mdz(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let iso_path = PathBuf::from(args.next().context("missing ISO path")?);
    let mut manifest_path = PathBuf::from("config/sources.json");
    let mut json_path = None;

    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--manifest" => {
                manifest_path = PathBuf::from(args.next().context("--manifest needs a path")?);
            }
            "--json" => {
                json_path = Some(PathBuf::from(args.next().context("--json needs a path")?));
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }

    let report = mdz_verify::verify(&iso_path, &manifest_path)?;
    println!(
        "verified {} MDZ containers for {}: {} decoded bytes",
        report.mdz_count, report.source_id, report.total_decoded_bytes
    );
    if let Some(path) = json_path {
        inspect::write_json_atomic(&path, &report)?;
        println!("report: {}", path.display());
    }
    Ok(())
}

fn run_extract_text(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let iso_path = PathBuf::from(args.next().context("missing ISO path")?);
    let mut manifest_path = PathBuf::from("config/sources.json");
    let mut scope_path = PathBuf::from("config/text-scopes.json");
    let mut json_path = None;

    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--manifest" => {
                manifest_path = PathBuf::from(args.next().context("--manifest needs a path")?);
            }
            "--scopes" => {
                scope_path = PathBuf::from(args.next().context("--scopes needs a path")?);
            }
            "--json" => {
                json_path = Some(PathBuf::from(args.next().context("--json needs a path")?));
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }

    let json_path = json_path.context("missing required --json path")?;
    let index = text_extract::extract(&iso_path, &manifest_path, &scope_path)?;
    inspect::write_json_atomic(&json_path, &index)?;
    println!(
        "extracted {} text units for {} to {}",
        index.unit_count,
        index.source_id,
        json_path.display()
    );
    Ok(())
}

fn run_inspect(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let iso_path = PathBuf::from(args.next().context("missing ISO path")?);
    let mut manifest_path = PathBuf::from("config/sources.json");
    let mut json_path = None;

    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--manifest" => {
                manifest_path = PathBuf::from(args.next().context("--manifest needs a path")?);
            }
            "--json" => {
                json_path = Some(PathBuf::from(args.next().context("--json needs a path")?));
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }

    let report = inspect::inspect(&iso_path, &manifest_path)?;
    println!(
        "verified {}: {} files, {} MDZ containers",
        report.source_id,
        report.file_count,
        report.mdz.len()
    );
    println!("volume: {}", report.volume_id);
    println!("serial: {}", report.serial);
    println!("sha256: {}", report.sha256);

    if let Some(path) = json_path {
        inspect::write_json_atomic(&path, &report)?;
        println!("report: {}", path.display());
    }

    Ok(())
}

fn run_compare(mut args: impl Iterator<Item = OsString>) -> Result<()> {
    let left_path = PathBuf::from(args.next().context("missing left inventory report")?);
    let right_path = PathBuf::from(args.next().context("missing right inventory report")?);
    let mut json_path = None;

    while let Some(option) = args.next() {
        match option.to_string_lossy().as_ref() {
            "--json" => {
                json_path = Some(PathBuf::from(args.next().context("--json needs a path")?));
            }
            unknown => bail!("unknown option: {unknown}"),
        }
    }

    let comparison = compare::compare_reports(&left_path, &right_path)?;
    println!(
        "compared {} to {}: {} shared files, {} identical, {} changed",
        comparison.left_source_id,
        comparison.right_source_id,
        comparison.shared_files,
        comparison.identical_files,
        comparison.changed_files.len()
    );
    println!(
        "MDZ: {} shared, {} identical, {} changed",
        comparison.shared_mdz,
        comparison.identical_mdz,
        comparison.changed_mdz_paths.len()
    );
    println!(
        "exclusive files: {} left, {} right",
        comparison.only_left.len(),
        comparison.only_right.len()
    );

    if let Some(path) = json_path {
        inspect::write_json_atomic(&path, &comparison)?;
        println!("report: {}", path.display());
    }
    Ok(())
}

fn print_usage() {
    eprintln!(
        "usage:\n  grandia3-tool inspect <iso> [--manifest config/sources.json] [--json work/report.json]\n  grandia3-tool compare <left-report.json> <right-report.json> [--json work/comparison.json]\n  grandia3-tool decode-mdz <input.MDZ> --output work/output.MDT\n  grandia3-tool build-mdz-candidate <input.MDT> --header-template <original.MDZ> --output-dir <output> [--relocatable]\n  grandia3-tool build-iso-candidate <iso> [--plan config/disc1-research-write-plan.json] --field <FIELD.BIN> --mdz <GR3.MDZ> --output-dir <output>\n  grandia3-tool inspect-mdt <input.MDT> [--json work/mdt-report.json]\n  grandia3-tool scan-mdt-text <input.MDT> [--json work/text-scan.json]\n  grandia3-tool scan-raw-text <input> [--json work/text-scan.json]\n  grandia3-tool scan-iso-text <iso> [--manifest config/sources.json] [--json work/iso-text-scan.json]\n  grandia3-tool scan-iso-custom-text <iso> --codebook <codebook.csv> [--manifest config/sources.json] [--json work/iso-custom-text-scan.json]\n  grandia3-tool extract-font-resources <input.MDT> [--config config/font-resources.json] --output-dir work/font-resources\n  grandia3-tool build-font-mdt-candidate <input.MDT> [--config config/font-resources.json] --overlay-dir <font-overlay> --output-dir <output>\n  grandia3-tool build-font-extension <input.MDT> [--resource-plan config/font-resources.json] --original-resources <font-resources> --overlay-dir <font-overlay> --overlay-config <overlay.json> --output-dir <output>\n  grandia3-tool inspect-skj <input.SKJ> [--json work/skj-report.json]\n  grandia3-tool inspect-fnt <input.FNT> [--json work/fnt-report.json] [--pgm work/glyphs.pgm]\n  grandia3-tool inspect-bdf <input.BDF> --sha256 <hex> --codepoint U+XXXX --cell WIDTHxHEIGHT [--json work/bdf.json] [--pgm work/glyph.pgm] [--game-4bpp work/glyph.bin]\n  grandia3-tool build-font-overlay <font-resources> --main-bdf <main.BDF> --ruby-bdf <ruby.BDF> --config <overlay.json> --output-dir <output>\n  grandia3-tool build-field-ui-candidate <FIELD.BIN> [--draft <draft.json>] --skj <original.SKJ> --font-config <overlay.json> --output-dir <output>\n  grandia3-tool verify-mdz <iso> [--manifest config/sources.json] [--json work/mdz-verification.json]\n  grandia3-tool extract-text <iso> [--manifest config/sources.json] [--scopes config/text-scopes.json] --json work/translation-index.json\n  grandia3-tool verify-translation [--index assets/translation/index.json] [--approval assets/translation/approvals/field-ui-v1.json]\n  grandia3-tool verify-translation-draft [--draft assets/translation/drafts/field-ui-ko-v1.json] --skj work/font-resources/RUBY.SKJ [--json work/draft-report.json]"
    );
}
