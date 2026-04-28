"""Background conversion worker.

``ConversionWorker`` is a ``QThread`` subclass that runs a list of
``ConversionJob`` objects sequentially on a dedicated thread, emitting Qt
signals as each job changes state.

Progress
--------
``stream_job`` is a generator that yields integer progress values (0–100) as
ffmpeg writes ``time=`` lines to stderr.  The worker emits ``job_progress``
for every yielded value so the UI progress bar updates in real time.

Cancellation
------------
Call ``request_cancel()`` from the UI thread at any time.  The worker checks
the flag **between** jobs.  The current job runs to completion because the
``Popen`` handle is owned by ``stream_job``'s generator frame, not by this
class.

TODO: to cancel mid-job, ``stream_job`` needs to expose its ``Popen`` handle
so ``request_cancel()`` can call ``proc.terminate()``.  The architecture is
ready for this: the worker already breaks out of the progress loop when
cancelled, which triggers the generator's ``finally`` block (terminate +
wait) automatically — the only missing piece is the terminate call inside
``stream_job`` itself when ``proc.poll() is None`` on ``GeneratorExit``.
"""

from __future__ import annotations

from PySide6.QtCore import QThread, Signal

from logic.converter import ConversionError, ConversionJob, stream_job


_STDERR_TAIL_LINES: int = 8


class ConversionWorker(QThread):
    """Runs ``ConversionJob`` items one after another on a background thread.

    Signals
    -------
    job_started(job)
        Emitted immediately before the ffmpeg process is spawned for *job*.
    job_progress(job, percent)
        Emitted each time ffmpeg writes a parseable progress line.
        *percent* is an integer in ``[0, 100]``.
    job_finished(job)
        Emitted after *job* completes successfully (ffmpeg exit code 0).
    job_failed(job, error_message)
        Emitted when *job* raises ``ConversionError``.  *error_message* is a
        trimmed excerpt of ffmpeg's stderr, safe to display in the log panel.
    cancelled(completed, total)
        Emitted when the run is cut short by ``request_cancel()``.
        *completed* is the number of jobs that ran before cancellation;
        *total* is the full queue length.
    all_done(success_count, failure_count)
        Emitted once after every attempted job — including after cancellation
        so the UI can always rely on this signal for cleanup.
    """

    job_started:  Signal = Signal(object)       # ConversionJob
    job_progress: Signal = Signal(object, int)  # ConversionJob, percent
    job_finished: Signal = Signal(object)       # ConversionJob
    job_failed:   Signal = Signal(object, str)  # ConversionJob, error_message
    cancelled:    Signal = Signal(int, int)     # completed_count, total_count
    all_done:     Signal = Signal(int, int)     # success_count, failure_count

    def __init__(self, jobs: list[ConversionJob]) -> None:
        super().__init__()
        self._jobs: list[ConversionJob] = list(jobs)  # defensive copy
        self._cancel_requested: bool = False

    # ------------------------------------------------------------------
    # Cancellation API (called from the UI thread)
    # ------------------------------------------------------------------

    def request_cancel(self) -> None:
        """Ask the worker to stop after the current job finishes.

        Thread-safe: ``bool`` assignment is atomic under CPython's GIL.

        Current behaviour
        -----------------
        The flag is checked between jobs, so the job already running
        continues to completion before the worker exits.

        Future behaviour (TODO)
        -----------------------
        When ``stream_job`` exposes its ``Popen`` handle, calling
        ``proc.terminate()`` here will interrupt ffmpeg immediately.
        The generator's ``finally`` block already calls ``proc.wait()``
        on ``GeneratorExit``, so the teardown path is already correct —
        only the ``terminate()`` call is missing from ``stream_job``.
        """
        self._cancel_requested = True

    # ------------------------------------------------------------------
    # QThread entry point
    # ------------------------------------------------------------------

    def run(self) -> None:  # type: ignore[override]
        """Execute all jobs sequentially, streaming progress for each one.

        Called automatically by Qt on the worker thread when ``start()`` is
        invoked from the UI thread.  Never call this directly.
        """
        successes = 0
        failures  = 0
        completed = 0

        for job in self._jobs:
            # --- cancellation guard (between jobs) ------------------------
            if self._cancel_requested:
                self.cancelled.emit(completed, len(self._jobs))
                self.all_done.emit(successes, failures)
                return

            self.job_started.emit(job)
            try:
                for percent in stream_job(job):
                    self.job_progress.emit(job, percent)
                    # Check cancel flag inside the progress loop so the worker
                    # can break out as soon as the current stderr line is read.
                    # This triggers GeneratorExit → stream_job's finally block
                    # (terminate + wait), giving near-immediate stop once
                    # proc.terminate() is wired up in stream_job.
                    if self._cancel_requested:
                        break
                else:
                    # Normal loop completion (no break): job succeeded.
                    successes += 1
                    self.job_finished.emit(job)
                    completed += 1
                    continue

                # Reached only via break (cancel was requested mid-job).
                # Treat the interrupted job as neither success nor failure;
                # the cancelled signal will be emitted at the top of the
                # next iteration.
                completed += 1

            except ConversionError as exc:
                failures += 1
                completed += 1
                message = _trim_stderr(str(exc))
                self.job_failed.emit(job, message)

        self.all_done.emit(successes, failures)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _trim_stderr(stderr: str, max_lines: int = _STDERR_TAIL_LINES) -> str:
    """Return the last *max_lines* non-empty lines of *stderr*.

    ffmpeg writes codec info and progress lines before the actual error, so
    the relevant message is almost always at the tail of the stream.
    """
    lines = [ln for ln in stderr.splitlines() if ln.strip()]
    tail  = lines[-max_lines:] if len(lines) > max_lines else lines
    return "\n".join(tail) if tail else "(no error output captured)"
