"""List models that back the queue and history views."""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Qt, Slot

from .core.history import history
from .core.logging_setup import get as get_logger
from .core.util import human_duration, human_size

log = get_logger("models")


def _role_map(names: list[str]) -> dict[int, QByteArray]:
    return {Qt.UserRole + index: QByteArray(name.encode()) for index, name in enumerate(names)}


class DictListModel(QAbstractListModel):
    """A list of dicts exposed with one role per key.

    Rows are replaced wholesale on refresh and patched individually on update,
    which keeps a four hundred item queue from rebuilding on every progress tick.
    """

    FIELDS: list[str] = []

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._rows: list[dict[str, Any]] = []
        self._roles = _role_map(self.FIELDS)
        self._index_by_role = {
            role: bytes(name).decode() for role, name in self._roles.items()
        }

    def roleNames(self) -> dict[int, QByteArray]:
        return self._roles

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole) -> Any:
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        key = self._index_by_role.get(role)
        if key is None:
            return None
        if key == "row":
            # One role carrying the whole record. Delegates are components that
            # already own properties called `name`, `status` and so on, and
            # redeclaring those as required roles shadows the component's real
            # properties: the model fills the shadow and the component renders
            # its own empty one. Passing a single record avoids that entirely.
            return dict(self._rows[index.row()])
        return self._rows[index.row()].get(key)

    @Slot(int, result="QVariant")
    def get(self, row: int) -> dict[str, Any]:
        if 0 <= row < len(self._rows):
            return dict(self._rows[row])
        return {}

    def replace(self, rows: list[dict[str, Any]]) -> None:
        self.beginResetModel()
        self._rows = [self._decorate(dict(row)) for row in rows]
        self.endResetModel()

    def patch(self, key_field: str, key_value: Any, row: dict[str, Any]) -> bool:
        for position, existing in enumerate(self._rows):
            if existing.get(key_field) == key_value:
                self._rows[position] = self._decorate(dict(row))
                model_index = self.index(position, 0)
                self.dataChanged.emit(model_index, model_index, list(self._roles.keys()))
                return True
        return False

    def _decorate(self, row: dict[str, Any]) -> dict[str, Any]:
        return row

    def rows(self) -> list[dict[str, Any]]:
        return list(self._rows)


class QueueModel(DictListModel):
    FIELDS = [
        "id", "name", "path", "kind", "status", "phase", "detail", "progress",
        "error", "printer", "pages", "sheets", "dpi", "size_text", "duration",
        "notes", "statusLabel", "busy", "row",
    ]

    LABELS = {
        "pending": "Waiting",
        "running": "Printing",
        "done": "Printed",
        "failed": "Failed",
        "cancelled": "Cancelled",
        "skipped": "Skipped",
    }

    def _decorate(self, row: dict[str, Any]) -> dict[str, Any]:
        status = row.get("status", "pending")
        phase = row.get("phase") or ""
        label = self.LABELS.get(status, status.title())
        if status == "running" and phase:
            label = phase.title()
        row["statusLabel"] = label
        row["busy"] = status == "running"
        if not row.get("size_text"):
            size = row.get("size") or 0
            row["size_text"] = human_size(size) if size else ""
        return row

    def bind(self, runner) -> None:
        runner.jobsChanged.connect(lambda: self.replace(runner.jobs()))
        runner.jobUpdated.connect(lambda job_id, job: self._on_update(runner, job_id, job))
        self.replace(runner.jobs())

    def _on_update(self, runner, job_id: str, job: dict[str, Any]) -> None:
        if not self.patch("id", job_id, job):
            # The row is not here yet, so fall back to a full refresh.
            self.replace(runner.jobs())


class HistoryModel(DictListModel):
    FIELDS = [
        "id", "name", "path", "kind", "printer", "pages", "sheets", "copies",
        "status", "error", "started", "duration", "options", "whenText",
        "durationText", "detail", "row",
    ]

    def _decorate(self, row: dict[str, Any]) -> dict[str, Any]:
        import time

        started = float(row.get("started") or 0)
        if started:
            row["whenText"] = time.strftime("%d %b %H:%M", time.localtime(started))
        else:
            row["whenText"] = ""
        row["durationText"] = human_duration(float(row.get("duration") or 0))
        sheets = int(row.get("sheets") or 0)
        pages = int(row.get("pages") or 0)
        if row.get("status") == "done":
            row["detail"] = (
                f"{sheets} sheet{'s' if sheets != 1 else ''}"
                + (f", {pages} page{'s' if pages != 1 else ''}" if pages != sheets else "")
                + f" in {row['durationText']}"
            )
        else:
            row["detail"] = row.get("error") or row.get("status", "")
        return row

    @Slot()
    @Slot(str, str)
    def refresh(self, search: str = "", status: str = "all") -> None:
        self.replace(history.recent(400, search, status))
