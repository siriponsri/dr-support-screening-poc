"""Daily two-stage AI batch for one review app on the shared regular Model API (owner-approved 2026-10-31).

A batch is a durable list of admitted images in this workspace. For every image a
background worker runs two stages, each with its own state:

1. the grader for its confirmed image type (CFP: RETFound, UWF: USPEC) through the
   existing ``infer`` path;
2. PRISM through the existing preview receipt path (prepare a one-use receipt for
   the current case revision, then submit exactly that receipt).

Before each stage the image's source rights and confirmed type are checked here
and again by the existing paths, and the shared queue checks AI hours and the
daily allowance before anything is sent. An image is complete only when both
stages are saved; a PRISM precondition that fails is shown with its reason and
the image is not labelled complete.

No automatic resend: a refusal that happens before sending (outside AI hours,
daily limit, queue wait, PRISM server not loaded, case changed before the
receipt was used) leaves the stage waiting; any other failure, and a stage
interrupted while it may have been sent, needs action. Saving goes through the
existing validation and raw history; the clinician's grade and findings are
never changed here. Batch files live in the app's private local state, never in
the case store.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import threading
import time
from typing import Callable
from uuid import uuid4

SCHEMA = "dr-regular-batch.v2"
IMAGE_ID = re.compile(r"[A-Za-z0-9_-]{1,80}")
MAX_IMAGES = 500
MAX_DEFERRALS = 10  # About 5 minutes of waiting (server loading, case changing) before asking for action.
GRADER_MODELS = {"CFP": "retfound-aptos5", "UWF": "uspec-uwf-grading"}
STAGES = ("grader", "prism")
TERMINAL = {"SAVED", "NEEDS_ACTION", "NOT_ELIGIBLE", "NEEDS_CONFIRM_IMAGE", "CANCELLED"}
LABELS = {
    "grader": {"PENDING": "Grade waiting", "RUNNING": "Grading", "SAVED": "AI grade saved",
               "NEEDS_ACTION": "Grade needs action", "NEEDS_CONFIRM_IMAGE": "Needs Confirm Image",
               "NOT_ELIGIBLE": "Grade not run", "CANCELLED": "Cancelled"},
    "prism": {"PENDING": "PRISM waiting", "RUNNING": "PRISM running", "SAVED": "PRISM saved",
              "NEEDS_ACTION": "PRISM needs action", "NEEDS_CONFIRM_IMAGE": "Needs Confirm Image",
              "NOT_ELIGIBLE": "PRISM not run", "CANCELLED": "Cancelled"},
}
INTERRUPTED = "Analysis was interrupted. Check the image and run AI again if needed."
UNCONFIRMED = "The AI result could not be confirmed as saved."
GENERIC_FAILURE = "AI analysis did not complete. Nothing is resent automatically."
NEEDS_CONFIRM = "Confirm the image type before AI analysis."


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class BatchDeferred(Exception):
    """Nothing was sent; the stage stays waiting."""


class PrismPrepareRefused(Exception):
    """PRISM receipt preparation refused before any model work (plain ``detail``, HTTP ``status``)."""

    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


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


def _stage(state, detail=None, deferrals=0):
    return {"state": state, "detail": detail, "deferrals": deferrals, "updated_utc": _now()}


class BatchRunner:
    """Runs both stages for this app's batches on one background thread, one stage at a time."""

    def __init__(self, store: BatchStore, *, workspace_id: str, stage_for: Callable[[str], tuple[str, str] | None],
                 has_result: Callable[[str, str], bool], run_grader: Callable[[str, str, str, str], None],
                 run_prism: Callable[[str], None], queue_open: Callable[[], bool], deferred_details: set[str],
                 idle_seconds: float = 1.0, deferred_seconds: float = 30.0, clock=None):
        self.store, self.workspace_id = store, workspace_id
        self.stage_for, self.has_result = stage_for, has_result
        self.run_grader, self.run_prism, self.queue_open = run_grader, run_prism, queue_open
        # Clinician wording of refusals that happen before anything is sent: safe to try again later.
        self.deferred_details = frozenset(deferred_details)
        self.idle_seconds, self.deferred_seconds = idle_seconds, deferred_seconds
        self.stop_event, self.wake = threading.Event(), threading.Event()
        self.thread = None
        self.deferred_note = None
        self.clock = clock or time.monotonic
        self.waiting_until = {}
        self._recover()

    @staticmethod
    def _task(stage):
        return "global" if stage == "grader" else "lesion-roi"

    def _recover(self):
        # A stage interrupted while running may have been sent: never resent automatically.
        for batch in self.store.all():
            changed = False
            for image_id, item in batch["items"].items():
                for stage in STAGES:
                    if item[stage]["state"] == "RUNNING":
                        saved = self.has_result(image_id, self._task(stage))
                        item[stage] = _stage("SAVED") if saved else _stage("NEEDS_ACTION", INTERRUPTED)
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
            eligible = self.stage_for(image_id) is not None
            item = {}
            for stage in STAGES:
                if self.has_result(image_id, self._task(stage)):
                    item[stage] = _stage("SAVED")
                elif not eligible:
                    item[stage] = _stage("NEEDS_CONFIRM_IMAGE", NEEDS_CONFIRM)
                else:
                    item[stage] = _stage("PENDING")
            items[image_id] = item
        batch = {"schema": SCHEMA, "batch_id": "batch_" + uuid4().hex[:16], "workspace_id": self.workspace_id,
                 "created_utc": _now(), "cancelled": False, "order": unique, "items": items}
        self.store.save(batch)
        self.wake.set()
        return self.summary(batch)

    def cancel(self, batch_id):
        batch = self.store.load(batch_id)
        batch["cancelled"] = True
        for item in batch["items"].values():
            for stage in STAGES:
                if item[stage]["state"] == "PENDING":
                    item[stage] = _stage("CANCELLED")
        self.store.save(batch)
        return self.summary(batch)

    def summary(self, batch):
        counts = {stage: {} for stage in STAGES}
        rows, complete = [], 0
        for image_id in batch["order"]:
            item = batch["items"][image_id]
            row = {"image_id": image_id}
            for stage in STAGES:
                state = item[stage]["state"]
                counts[stage][state] = counts[stage].get(state, 0) + 1
                row[stage] = state
                row[stage + "_label"] = LABELS[stage][state]
                row[stage + "_detail"] = item[stage].get("detail")
            row["complete"] = item["grader"]["state"] == "SAVED" and item["prism"]["state"] == "SAVED"
            complete += row["complete"]
            rows.append(row)
        waiting = sum(counts[stage].get("PENDING", 0) + counts[stage].get("RUNNING", 0) for stage in STAGES)
        return {"batch_id": batch["batch_id"], "created_utc": batch["created_utc"], "cancelled": batch["cancelled"],
                "total": len(batch["order"]), "complete": complete, "counts": counts, "items": rows,
                "active": not batch["cancelled"] and waiting > 0, "note": self.deferred_note if waiting else None}

    def list(self):
        return [self.summary(batch) for batch in self.store.all() if batch["workspace_id"] == self.workspace_id]

    def _next(self):
        """The first runnable stage: an image's grader, then its PRISM once the grader is settled.

        A stage waiting after a refusal before sending is skipped until its wait ends, so it never holds
        up the other images. Returns (None, None, None, waiting) where waiting tells whether any is left."""
        now, waiting = self.clock(), False
        for batch in self.store.all():
            if batch["workspace_id"] != self.workspace_id or batch["cancelled"]:
                continue
            for image_id in batch["order"]:
                item = batch["items"][image_id]
                for stage in STAGES:
                    if item[stage]["state"] != "PENDING" or (stage == "prism" and item["grader"]["state"] not in TERMINAL):
                        continue
                    if self.waiting_until.get((batch["batch_id"], image_id, stage), 0) > now:
                        waiting = True
                        continue
                    return batch, image_id, stage, waiting
        return None, None, None, waiting

    def _set(self, batch_id, image_id, stage, state, detail=None, deferrals=0):
        batch = self.store.load(batch_id)
        batch["items"][image_id][stage] = _stage(state, detail, deferrals)
        self.store.save(batch)

    def _defer(self, batch, image_id, stage, detail):
        deferrals = batch["items"][image_id][stage].get("deferrals", 0) + 1
        if deferrals > MAX_DEFERRALS:
            self._set(batch["batch_id"], image_id, stage, "NEEDS_ACTION",
                      "The image kept changing or the AI server was not available. Run AI again when ready.")
            return True
        self._set(batch["batch_id"], image_id, stage, "PENDING", None, deferrals)
        self.deferred_note = detail
        self.waiting_until[(batch["batch_id"], image_id, stage)] = self.clock() + self.deferred_seconds
        return True   # Nothing was sent; move on to the next image's stage.

    def step(self) -> bool:
        """Run at most one stage. Returns True when a stage was settled."""
        batch, image_id, stage, waiting = self._next()
        if batch is None:
            if waiting:
                raise BatchDeferred()
            return False
        if not self.queue_open():
            self.deferred_note = "Waiting for AI hours or today's limit; the batch continues automatically."
            raise BatchDeferred()
        task = self._task(stage)
        if self.stage_for(image_id) is None:
            # Re-checked before every stage: the type or source rights may have changed since the batch began.
            self._set(batch["batch_id"], image_id, stage, "NEEDS_CONFIRM_IMAGE", NEEDS_CONFIRM)
            return True
        if self.has_result(image_id, task):
            self._set(batch["batch_id"], image_id, stage, "SAVED")
            return True
        deferrals = batch["items"][image_id][stage].get("deferrals", 0)
        self._set(batch["batch_id"], image_id, stage, "RUNNING", None, deferrals)
        try:
            if stage == "grader":
                model_id, modality = self.stage_for(image_id)
                self.run_grader(image_id, model_id, modality, f"regular-{batch['batch_id']}-{image_id}")
            else:
                self.run_prism(image_id)
        except PrismPrepareRefused as refusal:
            # Preparation never starts model work. Server loading or busy: wait. A precondition: PRISM not run.
            if refusal.detail in self.deferred_details:
                return self._defer(batch, image_id, stage, refusal.detail)
            self._set(batch["batch_id"], image_id, stage, "NOT_ELIGIBLE", refusal.detail)
            return True
        except Exception as error:
            detail = getattr(error, "detail", None)
            if isinstance(detail, str) and detail in self.deferred_details:
                return self._defer(batch, image_id, stage, detail)
            self._set(batch["batch_id"], image_id, stage, "NEEDS_ACTION",
                      detail if isinstance(detail, str) else GENERIC_FAILURE)
            return True
        # Trusted readback: the saved case must now hold this stage's result.
        saved = self.has_result(image_id, task)
        self._set(batch["batch_id"], image_id, stage, "SAVED" if saved else "NEEDS_ACTION",
                  None if saved else UNCONFIRMED)
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
