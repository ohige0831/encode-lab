"""Main application window — layout, signal wiring, and worker lifecycle."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from logic.compatibility import check_compatibility
from logic.converter import ConversionJob, ConversionSettings, build_ffmpeg_command
from logic.environment import check_environment
from logic.ffprobe_reader import MediaInfo
from logic.presets import PRESETS, get_preset_names
from logic.probe_worker import ProbeWorker
from logic.size_estimator import estimate_output_size
from logic.worker import ConversionWorker
from ui.advanced_panel import AdvancedPanel
from ui.drop_zone import DropZone
from ui.file_list import FileListWidget, JobStatus
from ui.log_panel import LogPanel


class MainWindow(QMainWindow):
    """Top-level window for EncodeLab.

    Responsibilities
    ----------------
    - Assemble child widgets into the final layout.
    - Collect UI state and delegate work to ``logic/`` modules.
    - Manage the ``ConversionWorker`` lifecycle (create → start → discard).
    - Run environment checks and surface problems before any job starts.
    """

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("EncodeLab")
        self.setMinimumSize(720, 700)
        self._worker: ConversionWorker | None = None
        self._probe_workers: set[ProbeWorker] = set()
        # Probe results keyed by str(path); populated by _on_file_probed.
        self._media_info: dict[str, MediaInfo] = {}
        # Per-run counters updated by worker-signal slots.
        self._total_jobs: int = 0
        self._current_job_index: int = 0
        # Cached at startup; re-read on each conversion attempt.
        self._env = check_environment()
        self._build_ui()
        self._connect_signals()
        first_preset = self._preset_combo.currentText()
        self._sync_advanced_panel(first_preset)
        self._sync_preset_description(first_preset)
        self._check_environment_on_startup()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)

        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # 1. Drop zone
        self._drop_zone = DropZone()
        root.addWidget(self._drop_zone)

        # 2. File list
        self._file_list = FileListWidget()
        self._file_list.setMinimumHeight(150)
        root.addWidget(self._file_list)

        # 3. Preset + audio row
        root.addWidget(self._build_preset_row())

        # 4. Divider
        root.addWidget(self._make_divider())

        # 5. Advanced settings (collapsible)
        self._advanced_panel = AdvancedPanel()
        root.addWidget(self._advanced_panel)

        # 6. Log panel
        self._log_panel = LogPanel()
        self._log_panel.setMinimumHeight(120)
        root.addWidget(self._log_panel)

        # 7. Progress bar (hidden until a run starts)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.setTextVisible(True)
        self._progress_bar.hide()
        root.addWidget(self._progress_bar)

        # 8. Convert + Cancel button row
        root.addWidget(self._build_action_row())

        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_bar.showMessage("Ready")

    def _build_preset_row(self) -> QWidget:
        """Return a widget containing the preset combo, audio checkbox,
        and a read-only description label beneath the combo."""
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(4)

        # — Controls row (combo + audio checkbox) —
        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.addWidget(QLabel("Preset:"))

        self._preset_combo = QComboBox()
        self._preset_combo.addItems(get_preset_names())
        self._preset_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        controls.addWidget(self._preset_combo)
        controls.addSpacing(16)

        self._audio_checkbox = QCheckBox("Include audio")
        self._audio_checkbox.setChecked(True)
        controls.addWidget(self._audio_checkbox)
        vbox.addLayout(controls)

        # — Description label (updated on every preset change) —
        self._preset_desc_label = QLabel()
        self._preset_desc_label.setWordWrap(True)
        self._preset_desc_label.setStyleSheet(
            "color: #888; font-size: 11px; padding-left: 2px;"
        )
        vbox.addWidget(self._preset_desc_label)

        # — Size estimate label (updated when files, preset, or bitrate change) —
        self._size_estimate_label = QLabel("Estimated size: \u2014")
        self._size_estimate_label.setStyleSheet(
            "color: #666; font-size: 11px; padding-left: 2px;"
        )
        vbox.addWidget(self._size_estimate_label)

        return container

    def _build_action_row(self) -> QWidget:
        """Convert and Cancel buttons side by side.

        Cancel is hidden at startup and shown only while a run is in progress.
        It becomes the user's handle for the (currently between-job) cancel
        mechanism.
        """
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._convert_btn = QPushButton("Convert")
        self._convert_btn.setFixedHeight(42)
        self._convert_btn.setStyleSheet("font-size: 15px; font-weight: bold;")
        self._convert_btn.setEnabled(False)
        layout.addWidget(self._convert_btn, stretch=3)

        self._cancel_btn = QPushButton("Cancel")
        self._cancel_btn.setFixedHeight(42)
        self._cancel_btn.setStyleSheet("font-size: 13px;")
        self._cancel_btn.hide()
        layout.addWidget(self._cancel_btn, stretch=1)

        return row

    @staticmethod
    def _make_divider() -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        return line

    # ------------------------------------------------------------------
    # Signal wiring
    # ------------------------------------------------------------------

    def _connect_signals(self) -> None:
        self._drop_zone.files_dropped.connect(self._on_files_dropped)
        self._convert_btn.clicked.connect(self._on_convert_clicked)
        self._cancel_btn.clicked.connect(self._on_cancel_clicked)
        self._preset_combo.currentIndexChanged.connect(self._on_preset_changed)
        self._audio_checkbox.toggled.connect(self._on_audio_toggled)
        self._advanced_panel.settings_changed.connect(self._update_size_estimate)

    def _connect_worker(self, worker: ConversionWorker) -> None:
        """Wire worker signals to UI slots.  Called once per run."""
        worker.job_started.connect(self._on_job_started)
        worker.job_progress.connect(self._on_job_progress)
        worker.job_finished.connect(self._on_job_finished)
        worker.job_failed.connect(self._on_job_failed)
        worker.cancelled.connect(self._on_worker_cancelled)
        worker.all_done.connect(self._on_all_done)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _sync_advanced_panel(self, preset_name: str) -> None:
        config = PRESETS[preset_name]
        self._advanced_panel.apply_preset_defaults(config)

    def _sync_preset_description(self, preset_name: str) -> None:
        """Refresh the description label to match the currently selected preset.

        For GPU presets the label also shows whether the encoder is available
        on this machine, using the cached ``_env`` result from startup.
        """
        config = PRESETS[preset_name]
        badge = "\u26a1 GPU  \u2014  " if config.uses_gpu else ""
        desc  = f"{badge}{config.description}"
        if config.quality_mode:
            desc = f"{desc}  \u2014  {config.quality_mode}"

        if config.uses_gpu:
            if self._env.gpu_encoder_available(config.video_codec):
                avail_tag = "  \u2714 encoder available"
                self._preset_desc_label.setStyleSheet(
                    "color: #888; font-size: 11px; padding-left: 2px;"
                )
            else:
                avail_tag = "  \u2718 encoder not available on this machine"
                self._preset_desc_label.setStyleSheet(
                    "color: #c0392b; font-size: 11px; padding-left: 2px;"
                )
            desc = f"{desc}{avail_tag}"
        elif config.is_recommended:
            # Highlight the recommended preset in accent blue instead of grey.
            self._preset_desc_label.setStyleSheet(
                "color: #4499dd; font-size: 11px; padding-left: 2px;"
            )
        else:
            self._preset_desc_label.setStyleSheet(
                "color: #888; font-size: 11px; padding-left: 2px;"
            )

        self._preset_desc_label.setText(desc)

    def _update_size_estimate(self) -> None:
        """Recompute and display the estimated output size for the current queue.

        Shows ``"—"`` when no files are queued.  Otherwise delegates to
        ``estimate_output_size`` with the sum of all known file durations so
        the label reflects the total batch output, not just one file.
        """
        paths = self._file_list.get_all_paths()
        if not paths:
            self._size_estimate_label.setText("Estimated size: \u2014")
            return

        total_duration: float | None = None
        for p in paths:
            info = self._media_info.get(str(p))
            if info is not None and info.duration_sec is not None:
                total_duration = (total_duration or 0.0) + info.duration_sec

        settings = self._collect_settings()
        config   = PRESETS[settings.preset]
        self._size_estimate_label.setText(
            estimate_output_size(settings, config, total_duration)
        )

    def _collect_settings(self) -> ConversionSettings:
        return ConversionSettings(
            preset=self._preset_combo.currentText(),
            audio_enabled=self._audio_checkbox.isChecked(),
            crf=self._advanced_panel.crf,
            bitrate=self._advanced_panel.bitrate,
            resolution=self._advanced_panel.resolution,
            extra_flags=self._advanced_panel.extra_flags,
            output_dir=self._advanced_panel.output_dir,
        )

    def _set_running_state(self, running: bool) -> None:
        """Toggle controls between idle and in-progress states."""
        self._convert_btn.setVisible(not running)
        self._cancel_btn.setVisible(running)
        self._cancel_btn.setEnabled(running)
        self._preset_combo.setEnabled(not running)
        self._audio_checkbox.setEnabled(not running)

    def _check_environment_on_startup(self) -> None:
        """Warn in the log and status bar if tools are missing at launch.

        Also logs which GPU encoders were detected (or notes their absence)
        so users can see at a glance whether NVENC presets will work.
        """
        env = self._env
        if not env.all_ok:
            for tool in env.missing():
                self._log_panel.append_warning(f"{tool} not found on PATH")
            self._log_panel.append_warning(env.user_message())
            self._status_bar.showMessage(
                "Missing tools: " + ", ".join(env.missing()) + " \u2014 see log for details"
            )
            return

        if env.available_gpu_encoders:
            encoders_str = ", ".join(sorted(env.available_gpu_encoders))
            self._log_panel.append_info(f"GPU encoders detected: {encoders_str}")
        else:
            self._log_panel.append_info(
                "No NVENC GPU encoders detected \u2014 GPU presets will be unavailable"
            )

        self._status_bar.showMessage(
            f"Ready  |  ffmpeg: {env.ffmpeg_path}  |  ffprobe: {env.ffprobe_path}"
        )

    def _run_environment_check(self) -> bool:
        """Return ``True`` if all requirements are met; log errors and return
        ``False`` otherwise.

        Refreshes the cached ``_env`` on every call so that a user who installs
        ffmpeg after launch and retries will get an up-to-date result.

        Checks performed (in order):
        1. ffmpeg and ffprobe must be on PATH.
        2. If the selected preset is GPU-based, the required encoder must be
           present in the installed ffmpeg build.
        """
        self._env = check_environment()
        env = self._env

        # Refresh description label in case GPU availability changed.
        self._sync_preset_description(self._preset_combo.currentText())

        if not env.all_ok:
            for tool in env.missing():
                self._log_panel.append_error(f"{tool} not found on PATH")
            self._log_panel.append_error(env.user_message())
            self._status_bar.showMessage(
                "Cannot convert: " + ", ".join(env.missing()) + " missing"
            )
            return False

        preset_name = self._preset_combo.currentText()
        config = PRESETS[preset_name]
        if config.uses_gpu and not env.gpu_encoder_available(config.video_codec):
            self._log_panel.append_error(
                f"GPU encoder \u2018{config.video_codec}\u2019 is not available in your "
                f"ffmpeg build.  Choose a CPU preset or install an ffmpeg build "
                f"with NVENC support."
            )
            self._status_bar.showMessage(
                f"Cannot convert: {config.video_codec} not available"
            )
            return False

        return True

    # ------------------------------------------------------------------
    # UI-event slots
    # ------------------------------------------------------------------

    def _on_files_dropped(self, paths: list[Path]) -> None:
        # Determine which paths are genuinely new before adding them so we
        # only probe files that aren't already in the queue.
        existing = {str(p) for p in self._file_list.get_all_paths()}
        new_paths = [p for p in paths if str(p) not in existing]

        self._file_list.add_files(paths)
        count = self._file_list.file_count()
        self._convert_btn.setEnabled(count > 0)
        self._status_bar.showMessage(f"{count} file(s) queued")
        self._update_size_estimate()

        if new_paths:
            self._start_probe(new_paths)

    def _start_probe(self, paths: list[Path]) -> None:
        """Launch a ``ProbeWorker`` for *paths* and track it until finished."""
        worker = ProbeWorker(paths)
        worker.file_probed.connect(self._on_file_probed)
        # Remove worker from the tracking set when the thread finishes so it
        # can be garbage-collected.  Use a default-arg capture to avoid the
        # classic late-binding closure pitfall.
        worker.finished.connect(lambda w=worker: self._probe_workers.discard(w))
        self._probe_workers.add(worker)
        worker.start()

    def _on_convert_clicked(self) -> None:
        paths = self._file_list.get_all_paths()
        if not paths:
            return

        # Gate: abort early if ffmpeg/ffprobe are not on PATH.
        self._log_panel.clear()
        if not self._run_environment_check():
            return

        settings = self._collect_settings()

        # Build jobs, attaching duration from cached probe results so that
        # stream_job can compute progress percentages.
        jobs: list[ConversionJob] = []
        for p in paths:
            info = self._media_info.get(str(p))
            jobs.append(ConversionJob(
                input_path=p,
                settings=settings,
                duration_sec=info.duration_sec if info is not None else None,
                has_audio=info.has_audio_stream if info is not None else None,
            ))

        self._total_jobs = len(jobs)
        self._current_job_index = 0

        self._file_list.reset_all_statuses()
        self._log_panel.append_info(
            f"Starting {len(jobs)} job(s) \u2014 preset: {settings.preset}"
        )

        # Log each planned command so the user can see exactly what will run.
        for job in jobs:
            self._log_panel.append_command(build_ffmpeg_command(job))

        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)
        self._progress_bar.show()
        self._set_running_state(True)
        self._status_bar.showMessage(f"Job 0 / {len(jobs)}\u2026")

        self._worker = ConversionWorker(jobs)
        self._connect_worker(self._worker)
        self._worker.start()

    def _on_cancel_clicked(self) -> None:
        """Request cancellation and disable the button to prevent double-clicks."""
        if self._worker is not None:
            self._cancel_btn.setEnabled(False)
            self._cancel_btn.setText("Cancelling\u2026")
            self._worker.request_cancel()
            self._log_panel.append_warning(
                "Cancellation requested \u2014 waiting for current job to finish"
            )
            self._status_bar.showMessage("Cancelling\u2026")

    def _on_preset_changed(self, index: int) -> None:
        preset_name = self._preset_combo.itemText(index)
        self._sync_advanced_panel(preset_name)
        self._sync_preset_description(preset_name)
        self._update_size_estimate()
        self._status_bar.showMessage(f"Preset: {preset_name}")

    def _on_audio_toggled(self, enabled: bool) -> None:
        self._update_size_estimate()
        self._status_bar.showMessage("Audio " + ("enabled" if enabled else "disabled"))

    # ------------------------------------------------------------------
    # Worker-signal slots (delivered to the UI thread via Qt queued connection)
    # ------------------------------------------------------------------

    def _on_file_probed(self, path: Path, info: MediaInfo) -> None:
        """Update media-info columns, cache result, and surface compatibility warnings."""
        self._media_info[str(path)] = info
        self._file_list.set_item_media_info(path, info)
        self._update_size_estimate()
        for w in check_compatibility(info):
            self._log_panel.append_warning(f"{path.name}: {w.message}")

    def _on_job_started(self, job: ConversionJob) -> None:
        self._current_job_index += 1
        self._file_list.set_item_status(job.input_path, JobStatus.RUNNING)
        self._log_panel.append_info(
            f"\u2192 [{self._current_job_index}/{self._total_jobs}] {job.input_path.name}"
        )
        # Use an indeterminate bar when duration is unknown so the user
        # still sees activity rather than a frozen empty bar.
        if job.duration_sec:
            self._progress_bar.setRange(0, 100)
        else:
            self._progress_bar.setRange(0, 0)  # pulsing / indeterminate
        self._progress_bar.setValue(0)
        self._status_bar.showMessage(
            f"Job {self._current_job_index} / {self._total_jobs}: 0%"
        )

    def _on_job_progress(self, job: ConversionJob, percent: int) -> None:
        """Update the progress bar and status bar as ffmpeg reports progress."""
        self._progress_bar.setValue(percent)
        self._status_bar.showMessage(
            f"Job {self._current_job_index} / {self._total_jobs}: {percent}%"
        )

    def _on_job_finished(self, job: ConversionJob) -> None:
        self._file_list.set_item_status(job.input_path, JobStatus.DONE)
        self._log_panel.append_success(f"\u2713 {job.output_path.name}")
        # Snap bar to 100 in case the last progress update was slightly under.
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(100)

    def _on_job_failed(self, job: ConversionJob, error_message: str) -> None:
        self._file_list.set_item_status(job.input_path, JobStatus.FAILED)
        self._log_panel.append_error(f"\u2717 {job.input_path.name}")
        self._log_panel.append_error(error_message)
        self._progress_bar.setRange(0, 100)
        self._progress_bar.setValue(0)

    def _on_worker_cancelled(self, completed: int, total: int) -> None:
        remaining = total - completed
        self._log_panel.append_warning(
            f"Cancelled \u2014 {completed} job(s) ran, {remaining} skipped"
        )

    def _on_all_done(self, successes: int, failures: int) -> None:
        total   = successes + failures
        summary = f"Done \u2014 {successes}/{total} succeeded"
        if failures:
            summary += f", {failures} failed"
        self._log_panel.append_info(summary)
        self._status_bar.showMessage(summary)
        # Reset cancel button text in case it was clicked this run
        self._cancel_btn.setText("Cancel")
        self._set_running_state(False)
        # Re-enable Convert only if there are still files in the queue
        self._convert_btn.setEnabled(self._file_list.file_count() > 0)
        # TODO: offer "Open output folder" shortcut when all jobs succeeded
        self._worker = None  # allow GC; thread has already exited
