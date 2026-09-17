#!/usr/bin/env python3
"""Small PCSX2/PINE GUI for capturing Grandia III event identifiers.

The tool reads the emulated EE RAM directly through PCSX2's built-in PINE
socket.  It does not attach to the host process and never writes game memory.
"""

from __future__ import annotations

import csv
import json
import os
import re
import socket
import struct
import tkinter as tk
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk


ROOT = Path(__file__).resolve().parents[1]
EVENT_ADDRESS = 0x001F_EA20
EVENT_READ_SIZE = 32
ACTIVE_SAMPLE_PROGRESS_OFFSET = 0x10
RESOURCE_ADDRESS = 0x0020_DC00
RESOURCE_READ_SIZE = 64
REQUEST_SLOT_BASE = 0x0021_3544
REQUEST_SLOT_STRIDE = 0x8C
REQUEST_SLOT_COUNT = 2
REQUEST_SLOT_STATE_OFFSET = 0x08
REQUEST_SLOT_SAMPLE_OFFSET = 0x0C
REQUEST_SLOT_SECONDARY_OFFSET = 0x10
REQUEST_SLOT_RESOLVED_OFFSET = 0x4C
REQUEST_SLOT_PROGRESS_OFFSET = 0x64
SUBTITLE_TIMER_ADDRESS = 0x001E_8B40
SUBTITLE_TIMER_READ_SIZE = 8
DEFAULT_PINE_SLOT = 28011
READ8_OPCODE = 0
IPC_OK = 0
BATTLE_OVERLAY_SIGNATURE = bytes.fromhex("24 2F 08 0C 80 0F 62 AC")
RESOURCE_PATH_PATTERN = re.compile(
    r"^(?:DATA|BTL|SYS|MUSIC|MOVIE)/[A-Z0-9_./-]+\.(?:BIN|DAT|MDZ|MOV|STZ)$"
)


class PineError(RuntimeError):
    """Raised when PCSX2's PINE endpoint cannot satisfy a read."""


def socket_candidates(slot: int = DEFAULT_PINE_SLOT) -> list[Path]:
    names = ["pcsx2.sock"]
    if slot != DEFAULT_PINE_SLOT:
        names.insert(0, f"pcsx2.sock.{slot}")
    roots = [Path(os.environ.get("TMPDIR", "/tmp")), Path("/tmp")]
    candidates: list[Path] = []
    for root in roots:
        for name in names:
            candidate = root / name
            if candidate not in candidates:
                candidates.append(candidate)
    return candidates


def build_read8_packet(ranges: list[tuple[int, int]]) -> tuple[bytes, int]:
    commands = bytearray()
    byte_count = 0
    for address, size in ranges:
        if address < 0 or size < 0 or address + size > 0x1_0000_0000:
            raise ValueError(f"invalid EE RAM range: {address:#x}+{size:#x}")
        for offset in range(size):
            commands.extend(struct.pack("<BI", READ8_OPCODE, address + offset))
            byte_count += 1
    return struct.pack("<I", len(commands) + 4) + commands, byte_count


def recv_exact(sock: socket.socket, size: int) -> bytes:
    result = bytearray()
    while len(result) < size:
        block = sock.recv(size - len(result))
        if not block:
            raise PineError("PCSX2가 응답 도중 연결을 닫았습니다.")
        result.extend(block)
    return bytes(result)


def decode_read8_reply(reply: bytes, expected_bytes: int) -> bytes:
    if len(reply) != expected_bytes + 5:
        raise PineError(
            f"PINE 응답 크기가 다릅니다: {len(reply)} != {expected_bytes + 5}"
        )
    announced = struct.unpack_from("<I", reply, 0)[0]
    if announced != len(reply):
        raise PineError(f"PINE 응답 헤더가 다릅니다: {announced} != {len(reply)}")
    if reply[4] != IPC_OK:
        raise PineError("PCSX2에 실행 중인 게임 VM이 없습니다.")
    return reply[5:]


def pine_read_ranges(ranges: list[tuple[int, int]]) -> list[bytes]:
    packet, expected = build_read8_packet(ranges)
    last_error: Exception | None = None
    for path in socket_candidates():
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.8)
                sock.connect(str(path))
                sock.sendall(packet)
                header = recv_exact(sock, 4)
                reply_size = struct.unpack("<I", header)[0]
                if not 5 <= reply_size <= 450_000:
                    raise PineError(f"잘못된 PINE 응답 크기: {reply_size}")
                payload = decode_read8_reply(
                    header + recv_exact(sock, reply_size - 4), expected
                )
        except (FileNotFoundError, ConnectionRefusedError, socket.timeout, OSError) as error:
            last_error = error
            continue

        output: list[bytes] = []
        cursor = 0
        for _address, size in ranges:
            output.append(payload[cursor : cursor + size])
            cursor += size
        return output

    paths = ", ".join(str(path) for path in socket_candidates())
    raise PineError(
        "PCSX2 PINE 소켓에 연결할 수 없습니다. "
        f"PCSX2와 게임을 실행했는지 확인하세요. ({paths}; {last_error})"
    )


def decode_c_string(data: bytes) -> str:
    raw = data.split(b"\0", 1)[0]
    return raw.decode("ascii", errors="replace").strip()


def decode_resource_display(data: bytes) -> str:
    """Decode the field resource buffer without presenting overlay code as text."""
    if data.startswith(BATTLE_OVERLAY_SIGNATURE):
        return "전투 오버레이 활성 (현재 MDZ 없음)"
    decoded = decode_c_string(data)
    if RESOURCE_PATH_PATTERN.fullmatch(decoded):
        return decoded
    if not decoded:
        return "전환 중 (현재 MDZ 없음)"
    return "전환 중/현재 MDZ 없음"


def load_sample_stream_map() -> dict[int, int]:
    path = (
        ROOT
        / "audio/manifests/gr3_stream_inventory/gr3_event_sample_variants.csv"
    )
    if not path.exists():
        return {}
    result: dict[int, int] = {}
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            stream_key = int(row["stream_key"], 0)
            for sample in row["sample_ids"].split(";"):
                if sample:
                    result[int(sample, 0)] = stream_key
    return result


@dataclass(frozen=True)
class SampleMetadata:
    event_id: str
    stream_key: int
    scene_name: str
    resource_path: str
    duration_seconds: str
    runtime_status: str
    package_status: str
    mapping_source: str


def _sample_ids(value: str) -> list[int]:
    return [int(item, 0) for item in value.split(";") if item.strip()]


def load_sample_metadata() -> dict[int, SampleMetadata]:
    path = (
        ROOT
        / "audio/manifests/gr3_stream_inventory/gr3_rendered_event_workqueue.csv"
    )
    if not path.exists():
        return {}
    result: dict[int, SampleMetadata] = {}
    source_priority = {
        "suggested_runtime_trigger": 0,
        "confirmed_sample_ids": 1,
        "runtime_trigger_sample_ids": 2,
    }
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            stream_key = int(row["stream_key"], 0)
            groups = (
                (row.get("sample_ids", ""), "confirmed_sample_ids"),
                (
                    row.get("suggested_runtime_trigger_sample_ids", ""),
                    "suggested_runtime_trigger",
                ),
                (
                    row.get("runtime_trigger_sample_ids", ""),
                    "runtime_trigger_sample_ids",
                ),
            )
            for value, source in groups:
                for sample_id in _sample_ids(value):
                    current = result.get(sample_id)
                    # A runtime-confirmed mapping has priority over the inferred
                    # and suggested inventory rows when a sample appears twice.
                    if (
                        current
                        and source_priority[current.mapping_source]
                        >= source_priority[source]
                    ):
                        continue
                    result[sample_id] = SampleMetadata(
                        event_id=row.get("event_id", ""),
                        stream_key=stream_key,
                        scene_name=row.get("scene_name", ""),
                        resource_path=row.get("resource_path", ""),
                        duration_seconds=row.get("duration_seconds", ""),
                        runtime_status=row.get("runtime_status", ""),
                        package_status=row.get("package_status", ""),
                        mapping_source=source,
                    )
    return result


@dataclass(frozen=True)
class RequestSlot:
    index: int
    state: int
    requested_sample_id: int
    secondary_sample_id: int
    resolved_sample_id: int
    stream_key: int | None
    progress_ticks: int | None = None
    raw_bytes: bytes = b""

    @property
    def summary(self) -> str:
        stream = "미확인" if self.stream_key is None else f"0x{self.stream_key:X}"
        return (
            f"slot {self.index}: state={self.state} "
            f"req=0x{self.requested_sample_id:04X} "
            f"secondary=0x{self.secondary_sample_id:04X} "
            f"resolved=0x{self.resolved_sample_id:04X} stream={stream} "
            f"progress={self.progress_display}"
        )

    @property
    def progress_display(self) -> str:
        if self.progress_ticks is None:
            return "종료/없음"
        return f"{self.progress_ticks} ticks ({self.progress_ticks / 60.0:.3f}s)"

    def to_dict(self) -> dict[str, object]:
        return {
            "slot_index": self.index,
            "base_address": f"0x{REQUEST_SLOT_BASE + self.index * REQUEST_SLOT_STRIDE:08X}",
            "state": self.state,
            "requested_sample_id": f"0x{self.requested_sample_id:X}",
            "secondary_sample_id": f"0x{self.secondary_sample_id:X}",
            "resolved_sample_id": f"0x{self.resolved_sample_id:X}",
            "stream_key": (
                f"0x{self.stream_key:X}" if self.stream_key is not None else None
            ),
            "progress_ticks": self.progress_ticks,
            "progress_seconds": (
                round(self.progress_ticks / 60.0, 6)
                if self.progress_ticks is not None
                else None
            ),
            "raw_hex": self.raw_bytes.hex(" ").upper(),
        }


@dataclass(frozen=True)
class Capture:
    sample_id: int
    stream_key: int | None
    event_bytes: bytes
    resource_path: str
    resource_bytes: bytes
    request_slots: tuple[RequestSlot, ...]
    active_progress_ticks: int | None = None
    subtitle_timer_key: int | None = None
    subtitle_timer_ticks: int | None = None
    captured_at: str = ""

    @property
    def voice_candidate(self) -> RequestSlot | None:
        mapped = [slot for slot in self.request_slots if slot.stream_key is not None]
        same_as_visible = [
            slot for slot in mapped if slot.resolved_sample_id == self.sample_id
        ]
        if same_as_visible:
            return same_as_visible[0]
        different = [
            slot for slot in mapped if slot.resolved_sample_id != self.sample_id
        ]
        return different[0] if different else (mapped[0] if mapped else None)

    @property
    def voice_candidate_reason(self) -> str:
        candidate = self.voice_candidate
        if candidate is None:
            return "매핑된 request slot 없음"
        if candidate.resolved_sample_id == self.sample_id:
            return f"slot {candidate.index} resolved ID가 표시 ID와 일치"
        return f"slot {candidate.index}의 매핑된 resolved ID를 우선 사용"

    @property
    def timer_display(self) -> str:
        if self.subtitle_timer_key is None or self.subtitle_timer_ticks is None:
            return "미확인"
        return (
            f"stream 0x{self.subtitle_timer_key:X} / "
            f"{self.subtitle_timer_ticks} ticks "
            f"({self.subtitle_timer_ticks / 60.0:.3f}s)"
        )

    def to_dict(
        self,
        metadata: SampleMetadata | None = None,
        *,
        scene_note: str = "",
        savestate_slot: str = "",
    ) -> dict[str, object]:
        candidate = self.voice_candidate
        selected_sample = candidate.resolved_sample_id if candidate else self.sample_id
        return {
            "schema_version": 2,
            "capture_mode": "manual_pine_read_only",
            "captured_at": self.captured_at,
            "scene_note": scene_note,
            "savestate_slot": savestate_slot,
            "resource": {
                "address": f"0x{RESOURCE_ADDRESS:08X}",
                "display": self.resource_path,
                "raw_hex": self.resource_bytes.hex(" ").upper(),
            },
            "active_display": {
                "address": f"0x{EVENT_ADDRESS:08X}",
                "sample_id": f"0x{self.sample_id:X}",
                "stream_key": (
                    f"0x{self.stream_key:X}" if self.stream_key is not None else None
                ),
                "progress_ticks": self.active_progress_ticks,
                "progress_seconds": (
                    round(self.active_progress_ticks / 60.0, 6)
                    if self.active_progress_ticks is not None
                    else None
                ),
                "raw_hex": self.event_bytes.hex(" ").upper(),
            },
            "voice_candidate": {
                "sample_id": f"0x{selected_sample:X}",
                "stream_key": (
                    f"0x{candidate.stream_key:X}"
                    if candidate and candidate.stream_key is not None
                    else f"0x{self.stream_key:X}"
                    if self.stream_key is not None
                    else None
                ),
                "reason": self.voice_candidate_reason,
            },
            "subtitle_timer": {
                "address": f"0x{SUBTITLE_TIMER_ADDRESS:08X}",
                "event_key": (
                    f"0x{self.subtitle_timer_key:X}"
                    if self.subtitle_timer_key is not None
                    else None
                ),
                "ticks": self.subtitle_timer_ticks,
                "seconds": (
                    round(self.subtitle_timer_ticks / 60.0, 6)
                    if self.subtitle_timer_ticks is not None
                    else None
                ),
            },
            "request_slots": [slot.to_dict() for slot in self.request_slots],
            "workqueue_match": (
                {
                    "event_id": metadata.event_id,
                    "stream_key": f"0x{metadata.stream_key:X}",
                    "scene_name": metadata.scene_name,
                    "resource_path": metadata.resource_path,
                    "duration_seconds": metadata.duration_seconds,
                    "runtime_status": metadata.runtime_status,
                    "package_status": metadata.package_status,
                    "mapping_source": metadata.mapping_source,
                }
                if metadata
                else None
            ),
            "safety": {
                "game_memory_written": False,
                "automatic_play_tracking": False,
            },
        }

    @property
    def report(self) -> str:
        stream = "미확인" if self.stream_key is None else f"0x{self.stream_key:X}"
        raw = " ".join(f"{value:02X}" for value in self.event_bytes)
        candidate = self.voice_candidate
        voice = "미확인"
        if candidate is not None:
            voice = (
                f"sample 0x{candidate.resolved_sample_id:04X} / "
                f"GR3_STR 0x{candidate.stream_key:X}"
            )
        slot_lines = "\n".join(slot.summary for slot in self.request_slots)
        return (
            f"MDZ: {self.resource_path or '(빈 문자열)'}\n"
            f"캡처 시각: {self.captured_at or '미기록'}\n"
            f"0x001FEA20 표시 ID: 0x{self.sample_id:04X}\n"
            f"표시 ID의 GR3_STR: {stream}\n"
            f"음성 요청 후보: {voice}\n"
            f"후보 선택 근거: {self.voice_candidate_reason}\n"
            f"표시 진행 틱: {self.active_progress_ticks}\n"
            f"자막 타이머: {self.timer_display}\n"
            f"0x{EVENT_ADDRESS:08X}: {raw}\n"
            f"{slot_lines}"
        )


def parse_capture(
    event_bytes: bytes,
    resource_bytes: bytes,
    slot_bytes: list[bytes],
    timer_bytes: bytes,
    sample_stream_map: dict[int, int],
    *,
    captured_at: str = "",
) -> Capture:
    if len(event_bytes) < 4:
        raise ValueError("이벤트 메모리 블록이 너무 짧습니다.")
    if len(timer_bytes) < SUBTITLE_TIMER_READ_SIZE:
        raise ValueError("자막 타이머 블록이 너무 짧습니다.")
    if len(slot_bytes) != REQUEST_SLOT_COUNT:
        raise ValueError(f"request slot 수가 다릅니다: {len(slot_bytes)}")

    sample_id = struct.unpack_from("<I", event_bytes, 0)[0]
    active_progress = None
    if len(event_bytes) >= ACTIVE_SAMPLE_PROGRESS_OFFSET + 4:
        value = struct.unpack_from("<I", event_bytes, ACTIVE_SAMPLE_PROGRESS_OFFSET)[0]
        active_progress = None if value == 0xFFFF_FFFF else value

    slots = []
    for index, data in enumerate(slot_bytes):
        if len(data) < REQUEST_SLOT_PROGRESS_OFFSET + 4:
            raise ValueError(f"request slot {index} 블록이 너무 짧습니다.")
        state = struct.unpack_from("<I", data, REQUEST_SLOT_STATE_OFFSET)[0]
        requested = struct.unpack_from("<I", data, REQUEST_SLOT_SAMPLE_OFFSET)[0]
        secondary = struct.unpack_from("<I", data, REQUEST_SLOT_SECONDARY_OFFSET)[0]
        resolved = struct.unpack_from("<I", data, REQUEST_SLOT_RESOLVED_OFFSET)[0]
        progress_value = struct.unpack_from("<I", data, REQUEST_SLOT_PROGRESS_OFFSET)[0]
        slots.append(
            RequestSlot(
                index=index,
                state=state,
                requested_sample_id=requested,
                secondary_sample_id=secondary,
                resolved_sample_id=resolved,
                stream_key=sample_stream_map.get(resolved),
                progress_ticks=(
                    None if progress_value == 0xFFFF_FFFF else progress_value
                ),
                raw_bytes=data,
            )
        )
    timer_key, timer_ticks = struct.unpack_from("<2I", timer_bytes)
    return Capture(
        sample_id=sample_id,
        stream_key=sample_stream_map.get(sample_id),
        event_bytes=event_bytes,
        resource_path=decode_resource_display(resource_bytes),
        resource_bytes=resource_bytes,
        request_slots=tuple(slots),
        active_progress_ticks=active_progress,
        subtitle_timer_key=timer_key,
        subtitle_timer_ticks=timer_ticks,
        captured_at=captured_at or datetime.now().astimezone().isoformat(timespec="seconds"),
    )


class RuntimeProbeApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.sample_stream_map = load_sample_stream_map()
        self.sample_metadata = load_sample_metadata()
        self.last_capture: Capture | None = None
        self.after_id: str | None = None

        root.title("Grandia III 음성 이벤트 상세 추출기")
        root.geometry("980x820")
        root.minsize(860, 700)

        self.status = tk.StringVar(value="PCSX2 게임을 실행한 뒤 ‘지금 읽기’를 누르세요.")
        self.sample = tk.StringVar(value="—")
        self.stream = tk.StringVar(value="—")
        self.resource = tk.StringVar(value="—")
        self.raw = tk.StringVar(value="—")
        self.voice_sample = tk.StringVar(value="—")
        self.voice_stream = tk.StringVar(value="—")
        self.voice_reason = tk.StringVar(value="—")
        self.active_progress = tk.StringVar(value="—")
        self.subtitle_timer = tk.StringVar(value="—")
        self.request_slots = tk.StringVar(value="—")
        self.savestate_slot = tk.StringVar(value="5")
        self.scene_note = tk.StringVar(value="")
        self.auto_refresh = tk.BooleanVar(value=True)

        outer = ttk.Frame(root, padding=18)
        outer.pack(fill="both", expand=True)

        ttk.Label(
            outer,
            text="Grandia III 음성 이벤트 상세 추출기",
            font=("Helvetica", 20, "bold"),
        ).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "버튼을 누른 순간의 표시 ID·request slot·진행 틱·자막 타이머를 "
                "읽기 전용으로 한 번에 기록합니다."
            ),
        ).pack(anchor="w", pady=(2, 16))

        notebook = ttk.Notebook(outer)
        notebook.pack(fill="both", expand=True)

        summary_tab = ttk.Frame(notebook, padding=12)
        detail_tab = ttk.Frame(notebook, padding=8)
        notebook.add(summary_tab, text="요약")
        notebook.add(detail_tab, text="상세 JSON")

        values = ttk.Frame(summary_tab)
        values.pack(fill="x")
        self._value_row(values, 0, "표시 ID", f"0x{EVENT_ADDRESS:08X}", self.sample)
        self._value_row(values, 1, "표시 ID 스트림", "참고값", self.stream)
        self._value_row(values, 2, "실제 음성 후보 ID", "request slot", self.voice_sample)
        self._value_row(values, 3, "실제 음성 후보 스트림", "request slot", self.voice_stream)
        self._value_row(values, 4, "선택 근거", "판정", self.voice_reason)
        self._value_row(values, 5, "표시 진행", "+0x10", self.active_progress)
        self._value_row(values, 6, "자막 타이머", f"0x{SUBTITLE_TIMER_ADDRESS:08X}", self.subtitle_timer)
        self._value_row(values, 7, "현재 MDZ", f"0x{RESOURCE_ADDRESS:08X}", self.resource)
        self._value_row(values, 8, "원본 32바이트", "little-endian", self.raw)
        self._value_row(values, 9, "요청 슬롯", "slot 0 / slot 1", self.request_slots)
        values.columnconfigure(2, weight=1)

        self.detail_text = scrolledtext.ScrolledText(
            detail_tab,
            wrap="none",
            font=("Menlo", 11),
            undo=False,
        )
        self.detail_text.pack(fill="both", expand=True)
        self.detail_text.insert(
            "1.0",
            "‘지금 읽고 고정’을 누르면 이곳에 저장 가능한 상세 JSON이 표시됩니다.\n",
        )
        self.detail_text.configure(state="disabled")

        request = ttk.LabelFrame(outer, text="Codex 조사 요청", padding=10)
        request.pack(fill="x", pady=(12, 0))
        ttk.Label(request, text="상태저장 슬롯").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(
            request, from_=0, to=9, width=4, textvariable=self.savestate_slot
        ).grid(row=0, column=1, sticky="w", padx=(8, 20))
        ttk.Label(request, text="장면 설명").grid(row=0, column=2, sticky="w")
        ttk.Entry(request, textvariable=self.scene_note).grid(
            row=0, column=3, sticky="ew", padx=(8, 0)
        )
        request.columnconfigure(3, weight=1)

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(12, 8))
        ttk.Button(buttons, text="지금 읽고 고정", command=self.read_now).pack(side="left")
        ttk.Button(
            buttons, text="상세 조사 요청 복사", command=self.copy_report
        ).pack(side="left", padx=8)
        ttk.Button(
            buttons, text="상세 JSON 저장…", command=self.save_snapshot
        ).pack(side="left")
        ttk.Checkbutton(
            buttons,
            text="자동 갱신 (0.5초)",
            variable=self.auto_refresh,
            command=self.schedule_refresh,
        ).pack(side="left", padx=(10, 0))

        ttk.Separator(outer).pack(fill="x", pady=10)
        ttk.Label(outer, textvariable=self.status, wraplength=610).pack(anchor="w")
        ttk.Label(
            outer,
            text=(
                "자동 갱신은 화면만 바꾸며 파일을 저장하지 않습니다. 대사가 들리는 "
                "순간 ‘지금 읽고 고정’을 누른 뒤 JSON을 저장하거나 조사 요청을 복사하세요."
            ),
            foreground="#666666",
            wraplength=820,
        ).pack(anchor="w", side="bottom")

        root.bind("<Return>", lambda _event: self.read_now())
        root.bind("<Command-c>", lambda _event: self.copy_report())
        self.schedule_refresh()

    def _value_row(
        self,
        parent: ttk.Frame,
        row: int,
        label: str,
        address: str,
        variable: tk.StringVar,
    ) -> None:
        ttk.Label(parent, text=label, font=("Helvetica", 13, "bold")).grid(
            row=row, column=0, sticky="w", pady=7
        )
        ttk.Label(parent, text=address, foreground="#777777").grid(
            row=row, column=1, sticky="w", padx=(14, 18)
        )
        ttk.Label(
            parent,
            textvariable=variable,
            font=("Menlo", 13),
            wraplength=650,
        ).grid(
            row=row, column=2, sticky="w", pady=7
        )

    def _metadata_for_capture(self, capture: Capture) -> SampleMetadata | None:
        candidate = capture.voice_candidate
        sample_id = candidate.resolved_sample_id if candidate else capture.sample_id
        return self.sample_metadata.get(sample_id)

    def _snapshot_document(self) -> dict[str, object] | None:
        if self.last_capture is None:
            return None
        return self.last_capture.to_dict(
            self._metadata_for_capture(self.last_capture),
            scene_note=self.scene_note.get().strip(),
            savestate_slot=self.savestate_slot.get().strip(),
        )

    def _refresh_detail(self) -> None:
        document = self._snapshot_document()
        if document is None:
            return
        text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
        self.detail_text.configure(state="normal")
        self.detail_text.delete("1.0", "end")
        self.detail_text.insert("1.0", text)
        self.detail_text.configure(state="disabled")

    @staticmethod
    def _capture_signature(capture: Capture) -> tuple[object, ...]:
        return (
            capture.event_bytes,
            capture.resource_bytes,
            tuple(slot.raw_bytes for slot in capture.request_slots),
            capture.subtitle_timer_key,
            capture.subtitle_timer_ticks,
        )

    def read_now(self, quiet: bool = False) -> None:
        try:
            ranges = [
                (EVENT_ADDRESS, EVENT_READ_SIZE),
                (RESOURCE_ADDRESS, RESOURCE_READ_SIZE),
            ] + [
                (REQUEST_SLOT_BASE + index * REQUEST_SLOT_STRIDE, REQUEST_SLOT_STRIDE)
                for index in range(REQUEST_SLOT_COUNT)
            ] + [(SUBTITLE_TIMER_ADDRESS, SUBTITLE_TIMER_READ_SIZE)]
            values = pine_read_ranges(ranges)
            event_bytes, resource_bytes = values[:2]
            slot_bytes = values[2 : 2 + REQUEST_SLOT_COUNT]
            timer_bytes = values[-1]
            capture = parse_capture(
                event_bytes,
                resource_bytes,
                slot_bytes,
                timer_bytes,
                self.sample_stream_map,
            )
        except (PineError, ValueError) as error:
            self.status.set(str(error))
            if not quiet:
                messagebox.showerror("읽기 실패", str(error))
            return

        changed = (
            self.last_capture is None
            or self._capture_signature(capture)
            != self._capture_signature(self.last_capture)
        )
        self.last_capture = capture
        if not quiet:
            # Freeze the exact values captured while dialogue is audible.  If
            # auto-refresh keeps running, a later BGM/SE request can replace
            # the evidence before the user copies the report.
            self.auto_refresh.set(False)
            self.schedule_refresh()
        self.sample.set(f"0x{capture.sample_id:04X}")
        self.stream.set(
            "미확인" if capture.stream_key is None else f"0x{capture.stream_key:X}"
        )
        self.resource.set(capture.resource_path or "(빈 문자열)")
        self.raw.set(" ".join(f"{value:02X}" for value in capture.event_bytes))
        self.voice_reason.set(capture.voice_candidate_reason)
        self.active_progress.set(
            "종료/없음"
            if capture.active_progress_ticks is None
            else (
                f"{capture.active_progress_ticks} ticks "
                f"({capture.active_progress_ticks / 60.0:.3f}s)"
            )
        )
        self.subtitle_timer.set(capture.timer_display)
        candidate = capture.voice_candidate
        if candidate is None:
            self.voice_sample.set("미확인")
            self.voice_stream.set("미확인")
        else:
            self.voice_sample.set(f"0x{candidate.resolved_sample_id:04X}")
            self.voice_stream.set(f"0x{candidate.stream_key:X}")
        self.request_slots.set(" | ".join(slot.summary for slot in capture.request_slots))
        self._refresh_detail()
        if quiet:
            self.status.set("새 값 감지 · 결과 복사 가능" if changed else "연결됨 · 값 변화 없음")
        else:
            self.status.set("현재 값을 고정했습니다 · 상태저장 슬롯을 확인한 뒤 복사하세요.")

    def copy_report(self) -> None:
        if self.last_capture is None:
            self.read_now()
        if self.last_capture is None:
            return
        slot = self.savestate_slot.get().strip() or "미입력"
        scene = self.scene_note.get().strip() or "(장면 설명 입력 필요)"
        document = self._snapshot_document()
        assert document is not None
        report = (
            "음성 이벤트 자막 상세 조사 요청\n"
            f"상태저장 슬롯: {slot}\n"
            "저장 시점: 사람 대사가 실제로 들리는 도중\n"
            f"장면 설명: {scene}\n"
            f"{self.last_capture.report}\n"
            "상세 JSON:\n"
            f"{json.dumps(document, ensure_ascii=False, indent=2)}\n"
            "요청: 상태저장의 request slot과 SPU2 active voice를 대조해 실제 "
            "GR3 sample/stream을 확정하고, 기존 FLAC·전사·번역 큐에 연결해 주세요.\n"
            "ISO는 아직 만들지 마세요."
        )
        self.root.clipboard_clear()
        self.root.clipboard_append(report)
        self.root.update()
        self.status.set("클립보드에 복사했습니다.")

    def save_snapshot(self) -> None:
        if self.last_capture is None:
            self.read_now()
        document = self._snapshot_document()
        if document is None:
            return
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = filedialog.asksaveasfilename(
            title="상세 런타임 스냅샷 저장",
            initialdir=str(ROOT / "reports"),
            initialfile=f"gr3-runtime-capture-{stamp}.json",
            defaultextension=".json",
            filetypes=(("JSON", "*.json"), ("모든 파일", "*")),
        )
        if not path:
            return
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(document, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        self.status.set(f"상세 JSON 저장 완료: {output}")

    def schedule_refresh(self) -> None:
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
            self.after_id = None
        if self.auto_refresh.get():
            self.after_id = self.root.after(500, self._auto_refresh_tick)

    def _auto_refresh_tick(self) -> None:
        self.after_id = None
        if self.auto_refresh.get():
            self.read_now(quiet=True)
            self.schedule_refresh()


def main() -> int:
    root = tk.Tk()
    RuntimeProbeApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
