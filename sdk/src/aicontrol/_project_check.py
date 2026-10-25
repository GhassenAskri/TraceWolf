"""Tell the developer, once, in the logs, that the project does not exist in AIControl.

Projects are created in the AIControl web UI. The API refuses calls for a project that does not
exist (HTTP 404 with ``X-AIControl-Error: project-not-found``). The SDK makes that visible in two
ways, neither of which can affect the application: a check made in a background thread at
``init()``, and a hook on the exporter's HTTP session that sees the refusal itself. Both report
through one ``ProjectMonitor``, which logs once per outage: if the project is created later the
calls simply start flowing (nothing to restart), and if it disappears again it is logged again.
"""

from __future__ import annotations

import logging
import re
import threading
from urllib.parse import quote

import requests

logger = logging.getLogger("aicontrol")

ERROR_HEADER = "X-AIControl-Error"
PROJECT_NOT_FOUND = "project-not-found"
EXPORTER_LOGGER = "opentelemetry.exporter.otlp.proto.http.trace_exporter"
CHECK_TIMEOUT_SECONDS = 5
# What the exporter logs for a refused batch, as formatted text because its version decides how
# the message is built: "Failed to export span batch code: 404, ..." or, from 1.45,
# "Failed to export spans batch code: 404, ..." (a template with the kind as an argument).
_REFUSED_BATCH = re.compile(r"Failed to export spans? batch code: 404\b")


class ProjectMonitor:
    """Knows whether AIControl has said the project is missing, and logs that once."""

    def __init__(self, project: str, endpoint: str) -> None:
        self.project = project
        self.endpoint = endpoint.rstrip("/")
        self._lock = threading.Lock()
        self._missing = False
        self._filter: logging.Filter | None = None

    @property
    def missing(self) -> bool:
        return self._missing

    def report_missing(self) -> None:
        with self._lock:
            if self._missing:
                return
            self._missing = True
        logger.error(
            "aicontrol: the project %r does not exist on %s. Check the slug (shown on the "
            "project's page in the AIControl UI; it is not the name) or create the project "
            "there; until then its calls are dropped (the application is not affected).",
            self.project,
            self.endpoint,
        )

    def report_found(self) -> None:
        with self._lock:
            self._missing = False

    # --- what the API told us -------------------------------------------------------------------

    def check(self) -> None:
        """Ask the API whether the project exists. Never raises; says nothing if unsure."""
        url = f"{self.endpoint}/api/projects/{quote(self.project, safe='')}"
        try:
            response = requests.get(url, timeout=CHECK_TIMEOUT_SECONDS)
        except requests.RequestException as exc:
            logger.debug("aicontrol: could not check the project at %s: %s", url, exc)
            return
        if response.status_code == 404:
            self.report_missing()
        elif response.ok:
            self.report_found()

    def session(self) -> requests.Session:
        """The HTTP session for the exporter: it notes whether each export was refused."""
        session = requests.Session()
        session.hooks["response"].append(self._on_response)
        return session

    def _on_response(self, response: requests.Response, *args: object, **kwargs: object) -> None:
        if response.status_code == 404 and response.headers.get(ERROR_HEADER) == PROJECT_NOT_FOUND:
            self.report_missing()
        elif response.ok:
            self.report_found()

    # --- wiring ---------------------------------------------------------------------------------

    def start(self) -> None:
        """Check in a background thread (``init()`` never waits) and quiet the exporter's logs."""
        self.install_log_filter()
        threading.Thread(target=self.check, name="aicontrol-project-check", daemon=True).start()

    def install_log_filter(self) -> None:
        """Drop the exporter's own "Failed to export ... 404" error while the project is known
        to be missing: it would repeat for every batch and ours already says why."""
        if self._filter is None:
            self._filter = _RefusalFilter(self)
            logging.getLogger(EXPORTER_LOGGER).addFilter(self._filter)

    def close(self) -> None:
        if self._filter is not None:
            logging.getLogger(EXPORTER_LOGGER).removeFilter(self._filter)
            self._filter = None


class _RefusalFilter(logging.Filter):
    def __init__(self, monitor: ProjectMonitor) -> None:
        super().__init__()
        self._monitor = monitor

    def filter(self, record: logging.LogRecord) -> bool:
        if not self._monitor.missing:
            return True
        try:
            text = record.getMessage()
        except Exception:  # a malformed record is not ours to judge
            return True
        return _REFUSED_BATCH.match(text) is None
