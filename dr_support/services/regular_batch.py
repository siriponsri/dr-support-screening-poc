"""Daily AI batch for one review app on the shared regular Model API (owner-approved 2026-10-31).

A batch is a durable list of admitted images in this workspace. A background
worker runs each image's grader stage through the existing ``infer`` path (one
image at a time; the shared queue adds fairness between workstations). PRISM
stays clinician-armed: its stage is shown as waiting for Review until a PRISM
result is saved. Batch files live under the app's local state directory, never
in the case store, so the batch adds no schema and no case revisions.

No automatic resend: a call refused by the queue before sending (outside AI
hours, daily limit, queue wait) is deferred and tried again later; any other
failure, and any stage interrupted while it may have been sent, needs action.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
from typing import Callable
from uuid import uuid4

SCHEMA = "dr-regular-batch.v1"
IMAGE_ID = re.compile(r"[A-Za-z0-9_-]{1,80}")
MAX_IMAGES = 500
GRADER_MODELS = {"CFP": "retfound-aptos5", "UWF": "uspec-uwf-grading"}
LABELS = {
    "PENDING": "Waiting", "RUNNING": "Analysing", "SAVED": "AI grade saved", "NEEDS_ACTION": "Needs action",
    "NEEDS_CONFIRM_IMAGE": "Needs Confirm Image", "CANCELLED": "Cancelled",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BatchDeferred(Exception):
    """Nothing was sent; the stage stays waiting."""


class BatchStore:
    """One JSON file per batch, replaced atomically."""

    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()

    def _path(self, batch_id):
        if not re.fullmatch(r"batch_[a-f0-9]{16}", batch_id or ""):
            raise KeyError(batch_id)
        return self.directory / f"{batch_id}.json"

    def save(self, batch):
        with self.lock:
            path = self._path(batch["batch_id"])
            temporary = path.with_suffix(".tmp")
            with open(temporary, "w", encoding="utf-8") as handle:
                json.dump(batch, handle, sort_keys=True)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)

    def load(self, batch_id):
        with self.lock:
            return json.loads(self._path(batch_id).read_text(encoding="utf-8"))

    def all(self):
        with self.lock:
            batches = []
            for path in sorted(self.directory.glob("batch_*.json")):
                try:
                    batch = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if batch.get("schema") == SCHEMA:
                    batches.append(batch)
            return sorted(batches, key=lambda item: item["created_utc"])


class BatchRunner:
    """Runs grader stages for this app's batches on one background thread."""

    def __init__(self, store: BatchStore, *, workspace_id: str, stage_for: Callable[[str], tuple[str, str] | None],
                 has_result: Callable[[str, str], bool], run_grader: Callable[[str, str, str, str], None],
                 queue_open: Callable[[], bool], deferred_details: set[str], idle_seconds: float = 1.0,
                 deferred_seconds: float = 30.0):
        # Clinician wording of refusals that happen before anything is sent: safe to try again later.
        self.deferred_details = frozenset(deferred_details)
        self.store, self.workspace_id = store, workspace_id
        self.stage_for, self.has_result, self.run_grader = stage_for, has_result, run_grader
        self.queue_open = queue_open
        self.idle_seconds, self.deferred_seconds = idle_seconds, deferred_seconds
        self.stop_event, self.wake = threading.Event(), threading.Event()
        self.thread = None
        self.deferred_note = None
        self._recover()

    def _recover(self):
        # A stage interrupted while running may have been sent: never resent automatically.
        for batch in self.store.all():
            changed = False
            for image_id, item in batch["items"].items():
                if item["grader"]["state"] == "RUNNING":
                    saved = self.has_result(image_id, "global")
                    item["grader"] = {"state": "SAVED" if saved else "NEEDS_ACTION", "updated_utc": _now(),
                                      "detail": None if saved else
                                      "Analysis was interrupted. Check the image and run AI again if needed."}
                    changed = True
            if changed:
                self.store.save(batch)

    def create(self, image_ids):
        unique = list(dict.fromkeys(image_ids))
        if not unique or len(unique) > MAX_IMAGES or not all(isinstance(item, str) and IMAGE_ID.fullmatch(item)
                                                             for item in unique):
            raise ValueError("Choose between 1 and 500 admitted images.")
        items = {}
        for image_id in unique:
            stage = self.stage_for(image_id)
            if self.has_result(image_id, "global"):
                state, detail = "SAVED", None
            elif stage is None:
                state, detail = "NEEDS_CONFIRM_IMAGE", "Confirm the image type before AI analysis."
            else:
                state, detail = "PENDING", None
            items[image_id] = {"grader": {"state": state, "detail": detail, "updated_utc": _now()}}
        batch = {"schema": SCHEMA, "batch_id": "batch_" + uuid4().hex[:16], "workspace_id": self.workspace_id,
                 "created_utc": _now(), "cancelled": False, "order": unique, "items": items}
        self.store.save(batch)
        self.wake.set()
        return self.summary(batch)

    def cancel(self, batch_id):
        batch = self.store.load(batch_id)
        batch["cancelled"] = True
        for item in batch["items"].values():
            if item["grader"]["state"] == "PENDING":
                item["grader"] = {"state": "CANCELLED", "detail": None, "updated_utc": _now()}
        self.store.save(batch)
        return self.summary(batch)

    def summary(self, batch):
        counts = {}
        rows = []
        for image_id in batch["order"]:
            grader = batch["items"][image_id]["grader"]
            prism_done = self.has_result(image_id, "lesion-roi")
            counts[grader["state"]] = counts.get(grader["state"], 0) + 1
            counts["PRISM_SAVED"] = counts.get("PRISM_SAVED", 0) + int(prism_done)
            rows.append({"image_id": image_id, "grader": grader["state"], "grader_label": LABELS[grader["state"]],
                         "detail": grader.get("detail"),
                         "prism": "SAVED" if prism_done else "WAITING_FOR_REVIEW",
                         "prism_label": "PRISM saved" if prism_done else "PRISM in Review"})
        return {"batch_id": batch["batch_id"], "created_utc": batch["created_utc"], "cancelled": batch["cancelled"],
                "total": len(batch["order"]), "counts": counts, "items": rows,
                "active": not batch["cancelled"] and counts.get("PENDING", 0) + counts.get("RUNNING", 0) > 0,
                "note": self.deferred_note if counts.get("PENDING") else None}

    def list(self):
        return [self.summary(batch) for batch in self.store.all() if batch["workspace_id"] == self.workspace_id]

    def _next(self):
        for batch in self.store.all():
            if batch["workspace_id"] != self.workspace_id or batch["cancelled"]:
                continue
            for image_id in batch["order"]:
                if batch["items"][image_id]["grader"]["state"] == "PENDING":
                    return batch, image_id
        return None, None

    def _set(self, batch_id, image_id, state, detail=None):
        batch = self.store.load(batch_id)
        batch["items"][image_id]["grader"] = {"state": state, "detail": detail, "updated_utc": _now()}
        self.store.save(batch)

    def step(self) -> bool:
        """Run at most one grader stage. Returns True when work was attempted."""
        batch, image_id = self._next()
        if batch is None:
            return False
        if not self.queue_open():
            self.deferred_note = "Waiting for AI hours or today's limit; the batch continues automatically."
            raise BatchDeferred()
        stage = self.stage_for(image_id)
        if stage is None:
            self._set(batch["batch_id"], image_id, "NEEDS_CONFIRM_IMAGE", "Confirm the image type before AI analysis.")
            return True
        if self.has_result(image_id, "global"):
            self._set(batch["batch_id"], image_id, "SAVED")
            return True
        model_id, modality = stage
        self._set(batch["batch_id"], image_id, "RUNNING")
        try:
            self.run_grader(image_id, model_id, modality, f"regular-{batch['batch_id']}-{image_id}")
        except Exception as error:
            detail = getattr(error, "detail", None)
            if isinstance(detail, str) and detail in self.deferred_details:
                self._set(batch["batch_id"], image_id, "PENDING")
                self.deferred_note = detail
                raise BatchDeferred() from None
            self._set(batch["batch_id"], image_id, "NEEDS_ACTION", detail if isinstance(detail, str) else
                      "AI analysis did not complete. Nothing is resent automatically.")
            return True
        # Trusted readback: the saved case must now hold this grader result.
        saved = self.has_result(image_id, "global")
        self._set(batch["batch_id"], image_id, "SAVED" if saved else "NEEDS_ACTION",
                  None if saved else "The AI result could not be confirmed as saved.")
        self.deferred_note = None
        return True

    def start(self):
        if self.thread is not None:
            return
        def loop():
            while not self.stop_event.is_set():
                try:
                    worked = self.step()
                    wait = 0 if worked else self.idle_seconds
                except BatchDeferred:
                    wait = self.deferred_seconds
                except Exception:
                    wait = self.deferred_seconds  # Never a hot loop; the next pass reports state.
                if wait:
                    self.wake.wait(wait)
                    self.wake.clear()
        self.thread = threading.Thread(target=loop, name="regular-batch", daemon=True)
        self.thread.start()

    def stop(self):
        self.stop_event.set()
        self.wake.set()
        if self.thread is not None:
            self.thread.join(timeout=5)
