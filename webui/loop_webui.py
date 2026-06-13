"""WebUI mixin para AgentLoop: emite eventos SSE al navegador vía cola interna.

Extraído de agent/loop.py. Mixin de AgentLoop; vive en webui/ porque webui está en el paquete instalado.
Las funciones TUI (Rich/Live) se mantienen en ui/loop_tui.py.
"""
from __future__ import annotations
import queue as _queue
import time
from typing import Any, Optional

import agent.logger as log


class WebUIMixin:
    """Métodos exclusivos del modo WebUI.

    Se mezclan en AgentLoop. Los atributos que usa (context, config,
    is_subagent, _webui_queue, _plan_tasks, _turn_inp, _turn_out,
    _compacting_ctx, run) los define AgentLoop.__init__.
    """

    # ── Contrato con AgentLoop (annotations-only, sin valor) ─────────────────
    is_subagent:    bool
    config:         Any
    context:        Any
    _webui_queue:   Optional[Any]   # queue.SimpleQueue[dict] | None
    _plan_tasks:    list[dict]
    _turn_inp:      int
    _turn_out:      int
    _compacting_ctx: bool

    def _webui_emit(self, event: dict) -> None:
        q = getattr(self, "_webui_queue", None)
        if q is None:
            return
        try:
            if self.is_subagent:
                event = {**event,
                         "subagent":       True,
                         "subagent_name":  getattr(self.config, "agent_name",  ""),
                         "subagent_emoji": getattr(self.config, "agent_emoji", "🤖")}
            q.put_nowait(event)
        except _queue.Full:
            # El consumidor SSE se desconectó o va demasiado lento.
            # Loggear el primer drop y luego cada 100 para no saturar el log.
            _cnt = getattr(self, "_webui_drop_count", 0) + 1
            self._webui_drop_count = _cnt
            if _cnt == 1 or _cnt % 100 == 0:
                log.warning("webui_queue_full", drops=_cnt,
                            event_type=event.get("type"),
                            hint="SSE consumer may be disconnected")
        except Exception as e:
            log.debug("webui_emit_error", error=str(e))

    def _webui_status(self) -> dict:
        tok     = self.context.token_estimate()
        tok_max = self.context.max_tokens
        compact_thr = self.context.compact_threshold
        cpct_raw = int(tok / max(tok_max, 1) * 100)
        thresh_pct = int(compact_thr * 100)
        if getattr(self, "_compacting_ctx", False) or cpct_raw >= thresh_pct:
            compact_hint = "↻ compactando"
        elif cpct_raw >= thresh_pct - 10:
            compact_hint = "↻ cerca compactación"
        else:
            compact_hint = ""
        tasks = getattr(self, "_plan_tasks", [])
        _rt = getattr(self, "rt", None)
        _think = getattr(_rt, "think_level", "off")
        if _think not in ("off", "minimal", "low", "medium", "high"):
            _think = "off"
        return {
            "type":         "status",
            "agent_emoji":  getattr(self.config, "agent_emoji", "🤖"),
            "agent_name":   getattr(self.config, "agent_name",  "OOCode"),
            "agent_id":     getattr(self.config, "agent_id",    "main"),
            "model":        getattr(self.config, "model",        "—"),
            "context_tokens": tok,
            "context_max":    tok_max,
            "context_pct":    min(cpct_raw, 100),
            "compact_threshold_pct": thresh_pct,
            "compact_hint":   compact_hint,
            "tokens_in":    self._turn_inp,
            "tokens_out":   self._turn_out,
            # mem/rag — mismos datos que la línea 2 del status del TUI (paridad).
            "mem_hits":     getattr(getattr(self, "memory", None), "last_hits", 0) or 0,
            "rag_hits":     getattr(getattr(self, "_workspace_rag", None), "last_hits", 0) or 0,
            "rag_available": getattr(getattr(self, "_workspace_rag", None), "last_available", 0) or 0,
            # think/reasoning — paridad con "think:med.+r" del toolbar TUI (WebUI badge + Vim header)
            "think_level":  _think,
            "reasoning":    bool(getattr(_rt, "reasoning", False) is True),
            "task_total":   len(tasks),
            "task_done":    sum(1 for t in tasks if t.get("status") == "done"),
            "task_active":  next((t.get("text","")[:60] for t in tasks if t.get("status") == "active"), ""),
        }

    def run_for_webui(self, user_message: str, images=None) -> None:
        """Wrapper for WebUI: runs a turn and emits done/error events to _webui_queue."""
        # Emitir status al inicio del turno para actualizar la barra de contexto
        # antes de que el agente empiece a responder (streaming).
        self._webui_emit(self._webui_status())
        try:
            self.run(user_message, images)
            response = getattr(self, '_last_response', '') or ''
            # Emitir evento 'done' y 'inference_done' para indicar finalización de inferencia
            self._webui_emit({**self._webui_status(), "type": "done", "response": response})
            self._webui_emit({**self._webui_status(), "type": "inference_done"})
        except Exception as exc:
            self._webui_emit({"type": "error", "error": str(exc)})

    def _set_plan_task_active(self, idx: int) -> None:
        """Marca tareas < idx como done, idx como active, resto pending."""
        now = time.time()
        for i, task in enumerate(self._plan_tasks):
            if i < idx:
                if task["status"] != "done":
                    task["status"] = "done"
                    if not task["end_ts"]:
                        task["end_ts"] = now
            elif i == idx:
                if task["status"] != "active":
                    task["status"] = "active"
                    if not task["start_ts"]:
                        task["start_ts"] = now
            else:
                if task["status"] == "active":
                    task["status"] = "pending"
        # Emitir progreso al WebUI para actualizar el bloque de plan en tiempo real
        _done_n = sum(1 for t in self._plan_tasks if t["status"] == "done")
        _total  = len(self._plan_tasks)
        _active_text = self._plan_tasks[idx]["text"] if idx < _total else ""
        self._webui_emit({
            "type":        "plan_progress",
            "done":        _done_n,
            "total":       _total,
            "active":      idx,
            "active_text": _active_text,
            "tasks":       [{"text": t["text"], "status": t["status"]}
                            for t in self._plan_tasks],
        })

    def _mark_all_plan_tasks_done(self) -> None:
        """Marca todas las tareas del plan como done (si no lo estaban ya)."""
        now = time.time()
        for t in self._plan_tasks:
            if t["status"] != "done":
                t["status"] = "done"
                if not t["end_ts"]:
                    t["end_ts"] = now
        _total = len(self._plan_tasks)
        self._webui_emit({
            "type":   "plan_progress",
            "done":   _total,
            "total":  _total,
            "active": _total,
            "active_text": "",
            "tasks":  [{"text": t["text"], "status": t["status"]}
                       for t in self._plan_tasks],
        })

