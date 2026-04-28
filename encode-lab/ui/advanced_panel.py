"""Collapsible advanced-settings panel."""

from __future__ import annotations

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from logic.presets import PresetConfig


class AdvancedPanel(QWidget):
    """A toggle-able panel that exposes fine-grained encoding controls.

    The panel collapses/expands with an animated height transition.  When
    collapsed the widget occupies zero vertical space so the surrounding
    layout reflows cleanly.

    Signals
    -------
    settings_changed
        Emitted whenever the user edits the video bitrate or CRF fields.
        ``MainWindow`` connects this to its size-estimate update slot so the
        estimate refreshes in real time.
    """

    settings_changed: Signal = Signal()

    _COLLAPSED_HEIGHT: int = 0
    _EXPANDED_HEIGHT: int = 210  # approx; adjust when more fields are added

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._expanded: bool = False
        self._build_ui()
        self._setup_animation()
        self._connect_internal_signals()
        # Start collapsed
        self._content.setMaximumHeight(self._COLLAPSED_HEIGHT)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # Toggle button
        self._toggle_btn = QPushButton("▶  Advanced settings")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setFlat(True)
        self._toggle_btn.setStyleSheet(
            "text-align: left; padding: 4px 2px; font-weight: bold;"
        )
        self._toggle_btn.toggled.connect(self._on_toggle)
        outer.addWidget(self._toggle_btn)

        # Collapsible content area
        self._content = QFrame()
        self._content.setFrameShape(QFrame.Shape.StyledPanel)
        self._content.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        outer.addWidget(self._content)

        form_layout = QFormLayout(self._content)
        form_layout.setContentsMargins(8, 8, 8, 8)
        form_layout.setSpacing(8)

        # CRF / quality
        self._crf_spin = QSpinBox()
        self._crf_spin.setRange(0, 63)
        self._crf_spin.setValue(23)
        self._crf_spin.setToolTip("Constant Rate Factor (lower = better quality)")
        form_layout.addRow("CRF:", self._crf_spin)
        # TODO: hide/show CRF vs bitrate depending on selected preset codec

        # Bitrate override
        self._bitrate_edit = QLineEdit()
        self._bitrate_edit.setPlaceholderText("e.g. 4000k  (leave blank for CRF)")
        form_layout.addRow("Video bitrate:", self._bitrate_edit)
        # TODO: validate bitrate string format before passing to ffmpeg

        # Resolution
        self._resolution_edit = QLineEdit()
        self._resolution_edit.setPlaceholderText("e.g. 1920x1080  (leave blank to keep)")
        form_layout.addRow("Resolution:", self._resolution_edit)
        # TODO: offer a drop-down of common resolutions as an alternative

        # Extra ffmpeg flags
        self._extra_flags_edit = QLineEdit()
        self._extra_flags_edit.setPlaceholderText(
            "Raw ffmpeg flags appended verbatim (advanced)"
        )
        form_layout.addRow("Extra flags:", self._extra_flags_edit)
        # TODO: warn user when extra flags conflict with preset settings

        # Output directory — line edit + Browse button side by side
        output_row = QWidget()
        output_layout = QHBoxLayout(output_row)
        output_layout.setContentsMargins(0, 0, 0, 0)
        output_layout.setSpacing(4)

        self._output_dir_edit = QLineEdit()
        self._output_dir_edit.setPlaceholderText("Same folder as source (default)")
        output_layout.addWidget(self._output_dir_edit)

        self._browse_btn = QPushButton("Browse\u2026")
        self._browse_btn.setFixedWidth(72)
        self._browse_btn.clicked.connect(self._on_browse_clicked)
        output_layout.addWidget(self._browse_btn)

        form_layout.addRow("Output dir:", output_row)

    # ------------------------------------------------------------------
    # Animation setup
    # ------------------------------------------------------------------

    def _setup_animation(self) -> None:
        self._anim = QPropertyAnimation(self._content, b"maximumHeight")
        self._anim.setDuration(200)
        self._anim.setEasingCurve(QEasingCurve.Type.InOutCubic)

    # ------------------------------------------------------------------
    # Internal signal wiring
    # ------------------------------------------------------------------

    def _connect_internal_signals(self) -> None:
        """Emit ``settings_changed`` when fields that affect the size estimate change."""
        self._bitrate_edit.textChanged.connect(self.settings_changed)
        self._crf_spin.valueChanged.connect(self.settings_changed)

    # ------------------------------------------------------------------
    # Slots
    # ------------------------------------------------------------------

    def _on_toggle(self, checked: bool) -> None:
        self._expanded = checked
        arrow = "▼" if checked else "▶"
        self._toggle_btn.setText(f"{arrow}  Advanced settings")

        start = self._COLLAPSED_HEIGHT if checked else self._EXPANDED_HEIGHT
        end = self._EXPANDED_HEIGHT if checked else self._COLLAPSED_HEIGHT
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.start()

    def _on_browse_clicked(self) -> None:
        """Open a native directory picker and write the chosen path to the field."""
        start_dir = self._output_dir_edit.text().strip() or ""
        chosen = QFileDialog.getExistingDirectory(
            self,
            "Select Output Directory",
            start_dir,
        )
        if chosen:
            self._output_dir_edit.setText(chosen)

    # ------------------------------------------------------------------
    # Public API — values read by the conversion controller
    # ------------------------------------------------------------------

    def apply_preset_defaults(self, config: PresetConfig) -> None:
        """Push *config*'s baseline values into the panel fields.

        Only the CRF spinner is updated; user-entered bitrate, resolution,
        and extra flags are intentionally left alone so that manual overrides
        survive a preset switch.

        Called by MainWindow._on_preset_changed whenever the user picks a
        different preset from the combo box.
        """
        if config.crf > 0:
            self._crf_spin.setValue(config.crf)
            self._crf_spin.setEnabled(True)
            self._crf_spin.setToolTip(
                "Constant Rate Factor — lower = better quality, larger file"
            )
        else:
            self._crf_spin.setEnabled(False)
            if config.uses_gpu:
                self._crf_spin.setToolTip(
                    "CRF is not used by GPU (NVENC) encoders.\n"
                    "Quality is set by -cq in the preset's extra flags.\n"
                    "To change it, add e.g. \"-cq 18\" in the Extra flags field."
                )
            else:
                self._crf_spin.setToolTip(
                    "CRF is not applicable for this codec.\n"
                    "Quality is fixed by the format (e.g. ProRes, GIF)."
                )
        # TODO: hide the CRF row entirely when codec doesn't support it

    # ------------------------------------------------------------------
    # Read-only property accessors — called by MainWindow to build
    # ConversionSettings before handing off to the converter.
    # ------------------------------------------------------------------

    @property
    def crf(self) -> int:
        return self._crf_spin.value()

    @property
    def bitrate(self) -> str:
        return self._bitrate_edit.text().strip()

    @property
    def resolution(self) -> str:
        return self._resolution_edit.text().strip()

    @property
    def extra_flags(self) -> str:
        return self._extra_flags_edit.text().strip()

    @property
    def output_dir(self) -> str:
        return self._output_dir_edit.text().strip()
