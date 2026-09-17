#!/usr/bin/env python3
# Grandia III Texture Hunter GUI
# Windows/macOS/Linux Tkinter front-end.

from __future__ import annotations
import os
import sys
import threading
import subprocess
import queue
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "Grandia III Texture Hunter"

try:
    from PIL import Image, ImageTk
    PIL_OK = True
except Exception:
    PIL_OK = False

# Import the core scanner living next to this file.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
try:
    import grandia3_texture_hunter as hunter
except Exception as e:
    hunter = None
    IMPORT_ERROR = e
else:
    IMPORT_ERROR = None


class Redirector:
    def __init__(self, q):
        self.q = q
    def write(self, s):
        if s:
            self.q.put(s)
    def flush(self):
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("980x720")
        self.minsize(860, 620)

        self.msgq = queue.Queue()
        self.worker = None

        self.input_var = tk.StringVar()
        self.output_var = tk.StringVar(value=str((HERE / "texture_hunt").resolve()))
        self.raw_var = tk.BooleanVar(value=True)
        self.preview_var = tk.BooleanVar(value=True)
        self.open_after_var = tk.BooleanVar(value=True)

        self._build_ui()
        self.after(100, self._drain_queue)

        if hunter is None:
            messagebox.showerror(
                APP_TITLE,
                f"코어 스크립트를 불러오지 못했습니다.\n\n{IMPORT_ERROR}"
            )
        elif not PIL_OK:
            messagebox.showwarning(
                APP_TITLE,
                "Pillow가 설치되어 있지 않습니다.\n\n"
                "미리보기 PNG 기능을 쓰려면 아래 명령을 한 번 실행하세요:\n"
                "pip install pillow"
            )

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=10)

        ttk.Label(top, text="입력 파일 / 폴더").grid(row=0, column=0, sticky="w", **pad)
        ent_in = ttk.Entry(top, textvariable=self.input_var)
        ent_in.grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(top, text="파일 선택", command=self.pick_file).grid(row=0, column=2, **pad)
        ttk.Button(top, text="폴더 선택", command=self.pick_folder).grid(row=0, column=3, **pad)

        ttk.Label(top, text="출력 폴더").grid(row=1, column=0, sticky="w", **pad)
        ent_out = ttk.Entry(top, textvariable=self.output_var)
        ent_out.grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(top, text="출력 선택", command=self.pick_output).grid(row=1, column=2, **pad)
        ttk.Button(top, text="열기", command=self.open_output).grid(row=1, column=3, **pad)

        top.columnconfigure(1, weight=1)

        opts = ttk.LabelFrame(self, text="옵션")
        opts.pack(fill="x", padx=12, pady=(0, 8))

        ttk.Checkbutton(opts, text="GTXD / TEX1 원본 조각도 저장", variable=self.raw_var).pack(side="left", padx=12, pady=8)
        ttk.Checkbutton(opts, text="진단용 PNG 미리보기 생성", variable=self.preview_var).pack(side="left", padx=12, pady=8)
        ttk.Checkbutton(opts, text="완료 후 출력 폴더 열기", variable=self.open_after_var).pack(side="left", padx=12, pady=8)

        action = ttk.Frame(self)
        action.pack(fill="x", padx=12, pady=4)

        self.run_btn = ttk.Button(action, text="🔍 이미지 리소스 찾기", command=self.start_scan)
        self.run_btn.pack(side="left")

        self.progress = ttk.Progressbar(action, mode="indeterminate", length=220)
        self.progress.pack(side="left", padx=12)

        self.status_var = tk.StringVar(value="대기 중")
        ttk.Label(action, textvariable=self.status_var).pack(side="left", padx=6)

        main = ttk.Panedwindow(self, orient="vertical")
        main.pack(fill="both", expand=True, padx=12, pady=8)

        log_frame = ttk.LabelFrame(main, text="작업 로그")
        self.log = tk.Text(log_frame, wrap="word", height=15)
        self.log.pack(fill="both", expand=True, padx=6, pady=6)
        self.log.configure(state="disabled")
        main.add(log_frame, weight=3)

        help_frame = ttk.LabelFrame(main, text="빠른 사용법")
        help_text = (
            "1) FACE.MDZ / SYSWIN0.MDZ 같은 파일 하나를 고르거나 SYS / DATA 폴더 전체를 선택\n"
            "2) [이미지 리소스 찾기] 클릭\n"
            "3) 출력 폴더 안의 각 하위 폴더에서 _contact_sheet_first60.png 먼저 확인\n"
            "4) resources.csv 에서 GTXD/TEX1 오프셋과 주변 리소스명 확인\n\n"
            "추천 순서: FACE.MDZ → SYSWIN0.MDZ → PARTY*.MDZ / PLAYER*.MDZ → DATA 폴더\n\n"
            "※ 현재 PNG는 '찾기용 진단 미리보기'입니다. PS2 GTXD의 CLUT/swizzle까지 완전 복원한 "
            "최종 PNG 디코더는 아닙니다."
        )
        lbl = ttk.Label(help_frame, text=help_text, justify="left", anchor="nw")
        lbl.pack(fill="both", expand=True, padx=10, pady=8)
        main.add(help_frame, weight=1)

    def pick_file(self):
        p = filedialog.askopenfilename(
            title="Grandia III 리소스 파일 선택",
            filetypes=[
                ("Grandia III resources", "*.mdz *.mdt *.dat *.bin"),
                ("MDZ", "*.mdz"),
                ("MDT", "*.mdt"),
                ("DAT", "*.dat"),
                ("BIN", "*.bin"),
                ("All files", "*.*"),
            ],
        )
        if p:
            self.input_var.set(p)

    def pick_folder(self):
        p = filedialog.askdirectory(title="Grandia III 리소스 폴더 선택")
        if p:
            self.input_var.set(p)

    def pick_output(self):
        p = filedialog.askdirectory(title="출력 폴더 선택")
        if p:
            self.output_var.set(p)

    def append_log(self, s):
        self.log.configure(state="normal")
        self.log.insert("end", s)
        self.log.see("end")
        self.log.configure(state="disabled")

    def start_scan(self):
        if self.worker and self.worker.is_alive():
            return
        if hunter is None:
            messagebox.showerror(APP_TITLE, f"코어 로드 실패:\n{IMPORT_ERROR}")
            return

        inp = Path(self.input_var.get().strip().strip('"'))
        out = Path(self.output_var.get().strip().strip('"'))

        if not inp.exists():
            messagebox.showerror(APP_TITLE, "입력 파일 또는 폴더를 선택해주세요.")
            return

        out.mkdir(parents=True, exist_ok=True)

        self.run_btn.configure(state="disabled")
        self.progress.start(10)
        self.status_var.set("분석 중...")
        self.append_log("\n" + "="*70 + "\n")
        self.append_log(f"입력: {inp}\n출력: {out}\n\n")

        self.worker = threading.Thread(
            target=self._run_scan,
            args=(inp, out, self.raw_var.get(), self.preview_var.get()),
            daemon=True
        )
        self.worker.start()

    def _run_scan(self, inp, out, dump_raw, previews):
        old_out, old_err = sys.stdout, sys.stderr
        sys.stdout = Redirector(self.msgq)
        sys.stderr = Redirector(self.msgq)

        ok = True
        err = None
        try:
            inputs = hunter.collect_inputs(inp)
            print(f"스캔 대상: {len(inputs)}개 파일")
            if not inputs:
                raise RuntimeError("MDZ/MDT/DAT/BIN 파일을 찾지 못했습니다.")

            totals = {"GTXD": 0, "TEX1": 0}
            for n, p in enumerate(inputs, 1):
                print(f"\n[{n}/{len(inputs)}] {p}")
                rows = hunter.process_file(
                    p, out,
                    dump_raw=dump_raw,
                    previews=previews
                )
                for r in rows:
                    if r["kind"] in totals:
                        totals[r["kind"]] += 1

            print("\n" + "-"*70)
            print(f"완료! GTXD={totals['GTXD']} / TEX1={totals['TEX1']}")
            print(f"출력 폴더: {out}")
        except Exception as e:
            ok = False
            err = e
            print(f"\n[ERROR] {type(e).__name__}: {e}")
        finally:
            sys.stdout, sys.stderr = old_out, old_err
            self.msgq.put(("DONE", ok, str(err) if err else "", str(out)))

    def _drain_queue(self):
        try:
            while True:
                item = self.msgq.get_nowait()
                if isinstance(item, tuple) and item and item[0] == "DONE":
                    _, ok, err, out = item
                    self.progress.stop()
                    self.run_btn.configure(state="normal")
                    if ok:
                        self.status_var.set("완료")
                        if self.open_after_var.get():
                            self._open_path(Path(out))
                        messagebox.showinfo(
                            APP_TITLE,
                            "분석이 끝났습니다.\n\n"
                            "출력 폴더에서 _contact_sheet_first60.png 를 먼저 확인하세요."
                        )
                    else:
                        self.status_var.set("오류")
                        messagebox.showerror(APP_TITLE, f"작업 중 오류가 발생했습니다.\n\n{err}")
                else:
                    self.append_log(str(item))
        except queue.Empty:
            pass
        self.after(100, self._drain_queue)

    def open_output(self):
        p = Path(self.output_var.get().strip().strip('"'))
        p.mkdir(parents=True, exist_ok=True)
        self._open_path(p)

    def _open_path(self, p: Path):
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(p))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(p)])
            else:
                subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            messagebox.showerror(APP_TITLE, f"폴더를 열지 못했습니다.\n{e}")


if __name__ == "__main__":
    App().mainloop()
