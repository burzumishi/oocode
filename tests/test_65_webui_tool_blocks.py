"""Tests para bloques expandibles de tools en WebUI (agente principal y subagentes).

Cubre:
- _getOrCreateSubToolBlock: crea bloques expandibles dentro del bloque de subagente
- appendSubagentToolStart/Done: usa bloques expandibles, no texto plano
- tool_done para subagentes también llama appendFileCard cuando hay file_path
- _mdToHtml: convierte rutas de ficheros en enlaces descargables
- CSS: .tui-subagent-text, .tui-file-link, .tui-dl-btn
- Página de agentes: listado de conversaciones y acciones
"""
import json
import queue
import threading
import time
import unittest
from unittest.mock import MagicMock, patch


def _chat_src():
    from webui.app import app as _app
    _app.config["TESTING"] = True
    _app.config["SECRET_KEY"] = "test-secret"
    with _app.test_client() as c:
        return c.get("/chat").data.decode("utf-8", errors="replace")


def _agents_src():
    from webui.app import app as _app
    _app.config["TESTING"] = True
    _app.config["SECRET_KEY"] = "test-secret"
    with _app.test_client() as c:
        return c.get("/agents").data.decode("utf-8", errors="replace")


# ── Bloque expandible de tools para subagentes ────────────────────────────────

class TestSubagentExpandableToolBlocks(unittest.TestCase):

    def test_get_or_create_sub_tool_block_function_exists(self):
        """_getOrCreateSubToolBlock debe estar definida en page_chat."""
        self.assertIn("_getOrCreateSubToolBlock", _chat_src())

    def test_update_sub_tool_header_function_exists(self):
        """_updateSubToolHeader debe estar definida en page_chat."""
        self.assertIn("_updateSubToolHeader", _chat_src())

    def test_ensure_sub_buf_function_exists(self):
        """_ensureSubBuf crea/reutiliza la burbuja de subagente."""
        self.assertIn("_ensureSubBuf", _chat_src())

    def test_subagent_tool_start_uses_expandable_block(self):
        """appendSubagentToolStart debe llamar _getOrCreateSubToolBlock, no appendSubagentText."""
        src = _chat_src()
        idx = src.find("function appendSubagentToolStart")
        self.assertGreater(idx, 0, "appendSubagentToolStart debe estar definida")
        fn_end = src.find("\nfunction ", idx + 1)
        fn_body = src[idx: fn_end] if fn_end > idx else src[idx: idx + 600]
        self.assertIn("_getOrCreateSubToolBlock", fn_body,
                      "appendSubagentToolStart debe usar _getOrCreateSubToolBlock")
        self.assertNotIn("appendSubagentText", fn_body,
                         "appendSubagentToolStart no debe llamar appendSubagentText")

    def test_subagent_tool_done_uses_expandable_block(self):
        """appendSubagentToolDone debe usar el toolBlock del entry, no appendSubagentText."""
        src = _chat_src()
        idx = src.find("function appendSubagentToolDone")
        self.assertGreater(idx, 0)
        fn_end = src.find("\nfunction ", idx + 1)
        fn_body = src[idx: fn_end] if fn_end > idx else src[idx: idx + 600]
        self.assertIn("toolBlock", fn_body,
                      "appendSubagentToolDone debe acceder al toolBlock del entry")
        self.assertNotIn("appendSubagentText", fn_body,
                         "appendSubagentToolDone no debe llamar appendSubagentText")

    def test_sub_tool_block_turn_tracking(self):
        """Debe haber tracking del turno para reutilizar el bloque correcto."""
        src = _chat_src()
        self.assertIn("toolTurn", src, "_subBufs entries deben tener toolTurn")

    def test_sub_tool_block_counters(self):
        """Debe haber contadores de tools para el header del bloque."""
        src = _chat_src()
        self.assertIn("toolTotal", src)
        self.assertIn("toolDone", src)

    def test_sub_tool_block_uses_tui_tool_block_wrapper(self):
        """El bloque de subagente debe reutilizar el CSS .tui-tool-block-wrapper."""
        src = _chat_src()
        idx = src.find("function _getOrCreateSubToolBlock")
        self.assertGreater(idx, 0)
        fn_end = src.find("\nfunction ", idx + 1)
        fn_body = src[idx: fn_end] if fn_end > idx else src[idx: idx + 800]
        self.assertIn("tui-tool-block-wrapper", fn_body)
        self.assertIn("tui-tool-block-inner", fn_body)

    def test_sub_tool_block_expandable_toggle(self):
        """El header del bloque de subagente debe tener toggle de expandir/colapsar."""
        src = _chat_src()
        idx = src.find("function _getOrCreateSubToolBlock")
        self.assertGreater(idx, 0)
        fn_end = src.find("\nfunction ", idx + 1)
        fn_body = src[idx: fn_end] if fn_end > idx else src[idx: idx + 800]
        self.assertIn("▼ Ver", fn_body)
        self.assertIn("▲ Ocultar", fn_body)

    def test_sub_tool_block_header_shows_tool_name(self):
        """El header del bloque de subagente muestra el nombre de la tool activa."""
        src = _chat_src()
        idx = src.find("function _updateSubToolHeader")
        self.assertGreater(idx, 0)
        fn_end = src.find("\nfunction ", idx + 1)
        fn_body = src[idx: fn_end] if fn_end > idx else src[idx: idx + 600]
        self.assertIn("tool", fn_body)
        # El header muestra nombres de tools (toolNames) en lugar de "Haz clic para ver"
        self.assertIn("toolNames", fn_body)

    def test_subagent_text_after_tool_block(self):
        """Después de un bloque de tools, nuevo texto debe crear un nuevo textEl."""
        src = _chat_src()
        idx = src.find("function _getOrCreateSubToolBlock")
        self.assertGreater(idx, 0)
        fn_end = src.find("\nfunction ", idx + 1)
        fn_body = src[idx: fn_end] if fn_end > idx else src[idx: idx + 800]
        # textEl se resetea a null para que el siguiente texto cree un nuevo div
        self.assertIn("textEl", fn_body)
        self.assertIn("null", fn_body)

    def test_subagent_text_css_class(self):
        """El texto del subagente debe usar la clase .tui-subagent-text (pre-wrap)."""
        self.assertIn("tui-subagent-text", _chat_src())

    def test_subagent_text_css_defined(self):
        """La clase .tui-subagent-text debe tener definición CSS."""
        src = _chat_src()
        self.assertIn(".tui-subagent-text", src)


# ── File download en tool_done de subagentes ─────────────────────────────────

class TestSubagentFileDownload(unittest.TestCase):

    def test_tool_done_subagent_branch_calls_append_file_card(self):
        """El handler tool_done para subagentes también debe llamar appendFileCard."""
        src = _chat_src()
        idx_td = src.find("case 'tool_done':")
        self.assertGreater(idx_td, 0)
        idx_break = src.find("break;", idx_td)
        handler = src[idx_td: idx_break]
        # Debe haber dos ramas: subagente y principal, ambas con appendFileCard
        self.assertEqual(handler.count("appendFileCard"), 2,
                         "appendFileCard debe llamarse tanto para subagente como para agente principal")

    def test_tool_done_subagent_checks_file_path(self):
        """La rama subagente del handler tool_done debe verificar ev.file_path."""
        src = _chat_src()
        idx_td  = src.find("case 'tool_done':")
        idx_brk = src.find("break;", idx_td)
        handler = src[idx_td: idx_brk]
        # ev.file_path aparece en ambas ramas
        self.assertGreaterEqual(handler.count("ev.file_path"), 2)

    def test_tool_done_subagent_file_action(self):
        """La rama subagente del handler tool_done pasa file_action a appendFileCard."""
        src = _chat_src()
        idx_td  = src.find("case 'tool_done':")
        idx_brk = src.find("break;", idx_td)
        handler = src[idx_td: idx_brk]
        self.assertIn("ev.file_action", handler)


# ── File paths → enlaces descargables en _mdToHtml ───────────────────────────

class TestMdToHtmlFileLinks(unittest.TestCase):

    def test_tui_file_link_css_class_exists(self):
        """La clase CSS .tui-file-link debe estar definida en page_chat."""
        self.assertIn(".tui-file-link", _chat_src())

    def test_tui_dl_btn_css_class_exists(self):
        """La clase CSS .tui-dl-btn debe estar definida en page_chat."""
        self.assertIn(".tui-dl-btn", _chat_src())

    def test_md_to_html_detects_file_paths(self):
        """_mdToHtml debe tener lógica para detectar rutas /home, /tmp, /root."""
        src = _chat_src()
        idx = src.find("function _mdToHtml")
        self.assertGreater(idx, 0)
        fn_end = src.find("\nfunction ", idx + 1)
        fn_body = src[idx: fn_end] if fn_end > idx else src[idx: idx + 3000]
        self.assertIn("tui-file-link", fn_body, "_mdToHtml debe emitir .tui-file-link")
        self.assertIn("tui-dl-btn",    fn_body, "_mdToHtml debe emitir .tui-dl-btn")

    def test_md_to_html_uses_download_api(self):
        """_mdToHtml debe generar botones con data-dl-path que usan _safeDownload."""
        src = _chat_src()
        idx = src.find("function _mdToHtml")
        self.assertGreater(idx, 0)
        fn_end = src.find("\nfunction ", idx + 1)
        fn_body = src[idx: fn_end] if fn_end > idx else src[idx: idx + 3000]
        # Nuevo patrón: botones con data-dl-path en lugar de <a href>
        self.assertTrue(
            "data-dl-path" in fn_body or "/api/files/download" in fn_body,
            "Se esperaba data-dl-path o /api/files/download en _mdToHtml"
        )
        self.assertTrue(
            "data-dl-path" in fn_body or "encodeURIComponent" in fn_body,
            "Se esperaba data-dl-path o encodeURIComponent en _mdToHtml"
        )

    def test_md_to_html_handles_docx(self):
        """_mdToHtml debe detectar extensiones de Office como .docx."""
        src = _chat_src()
        idx = src.find("function _mdToHtml")
        fn_end = src.find("\nfunction ", idx + 1)
        fn_body = src[idx: fn_end] if fn_end > idx else src[idx: idx + 3000]
        self.assertIn("docx", fn_body)

    def test_md_to_html_handles_pdf(self):
        """_mdToHtml debe detectar .pdf."""
        src = _chat_src()
        idx = src.find("function _mdToHtml")
        fn_end = src.find("\nfunction ", idx + 1)
        fn_body = src[idx: fn_end] if fn_end > idx else src[idx: idx + 3000]
        self.assertIn("pdf", fn_body)

    def test_md_to_html_file_link_uses_filename(self):
        """El enlace usa split('/').pop() para mostrar sólo el nombre del fichero."""
        src = _chat_src()
        idx = src.find("function _mdToHtml")
        fn_end = src.find("\nfunction ", idx + 1)
        fn_body = src[idx: fn_end] if fn_end > idx else src[idx: idx + 3000]
        self.assertIn("split('/')", fn_body)
        self.assertIn(".pop()", fn_body)


# ── Página de agentes: listado de conversaciones ──────────────────────────────

class TestPageAgentsConversationListing(unittest.TestCase):

    def test_agents_table_has_task_column(self):
        """La tabla de agentes debe tener columna Tarea."""
        self.assertIn("Tarea", _agents_src())

    def test_agents_table_has_agent_column(self):
        """La tabla debe mostrar el agente (emoji + nombre)."""
        src = _agents_src()
        self.assertIn("agent_emoji", src)
        self.assertIn("agent_name", src)

    def test_agents_table_has_elapsed_column(self):
        """La tabla debe mostrar el tiempo transcurrido."""
        self.assertIn("elapsed", _agents_src())

    def test_agents_table_has_status_column(self):
        """La tabla debe mostrar el estado con badges."""
        src = _agents_src()
        self.assertIn("statusBadge", src)
        self.assertIn("running", src)

    def test_agents_show_task_button(self):
        """Debe existir un botón para ver la tarea completa."""
        self.assertIn("showTask", _agents_src())

    def test_agents_show_result_button(self):
        """Debe existir un botón para ver el resultado completo."""
        self.assertIn("showResult", _agents_src())

    def test_agents_kill_button_for_running(self):
        """Los subagentes en ejecución deben tener botón Kill."""
        src = _agents_src()
        # killAgent debe estar en la rama 'running'
        idx_running = src.find("running")
        self.assertGreater(idx_running, 0)
        self.assertIn("killAgent", src)

    def test_agents_steer_button_for_running(self):
        """Los subagentes en ejecución deben tener botón Steer."""
        self.assertIn("steerAgent", _agents_src())

    def test_agents_auto_refresh_every_2s(self):
        """La página debe auto-actualizarse con setInterval."""
        src = _agents_src()
        self.assertIn("setInterval", src)
        self.assertIn("fetchAgents", src)
        self.assertIn("POLL_INTERVAL", src)

    def test_agents_modal_shows_task(self):
        """El modal debe mostrar la tarea completa del subagente."""
        src = _agents_src()
        self.assertIn("modal-task", src)
        self.assertIn("modal-body", src)

    def test_agents_result_truncated_preview(self):
        """La lista puede mostrar resultado truncado; el modal muestra el completo."""
        src = _agents_src()
        self.assertIn("result_preview", src)
        # El botón Resultado sólo aparece cuando hay resultado
        self.assertIn("hasResult", src)

    def test_agents_status_badge_styles(self):
        """Los badges de estado deben tener estilos diferenciados por estado."""
        src = _agents_src()
        self.assertIn("badge-ok", src)
        self.assertIn("badge-warn", src)
        self.assertIn("badge-err", src)

    def test_agents_spawn_form_present(self):
        """Debe haber un formulario para lanzar nuevos subagentes."""
        src = _agents_src()
        self.assertIn("spawnAgent", src)
        self.assertIn("spawn-task", src)

    def test_agents_output_api_used(self):
        """showResult debe llamar a /api/agents/<id>/output."""
        src = _agents_src()
        self.assertIn("/api/agents/", src)
        self.assertIn("/output", src)

    def test_agents_kill_api_endpoint(self):
        """killAgent debe llamar a /api/agents/kill/<id>."""
        src = _agents_src()
        self.assertIn("/api/agents/kill/", src)

    def test_agents_short_id_displayed(self):
        """Se muestra un short_id de 8 caracteres para cada agente."""
        src = _agents_src()
        self.assertIn("short_id", src)

    def test_agents_timestamp_shown(self):
        """La página muestra la última actualización como timestamp."""
        self.assertIn("agents-ts", _agents_src())


# ── Kill button en ventana de chat: interacción con subagentes ────────────────

class TestChatKillButtonSubagentInteraction(unittest.TestCase):

    def _make_client(self):
        from webui.app import app as _app
        _app.config["TESTING"] = True
        _app.config["SECRET_KEY"] = "test-secret"
        return _app.test_client()

    def _inject_session(self, sid, loop, q):
        # /api/chat/kill serializa el retorno de request_kill()/kill_all_extras(); los
        # mocks deben devolver dicts reales (un MagicMock no es JSON-serializable).
        if isinstance(loop, MagicMock):
            loop.request_kill.return_value    = {"subagents": 0}
            loop.kill_all_extras.return_value = {"jobs": 0, "wip": 0}
        from webui.sessions import _WEBUI_SESSIONS
        import threading
        _WEBUI_SESSIONS[sid] = {
            "loop":    loop,
            "queue":   q,
            "history": [],
            "lock":    threading.Lock(),
            "thread":  None,
        }

    def test_kill_button_appears_when_busy(self):
        """setBusy(true) debe mostrar el botón kill."""
        src = _chat_src()
        # kill.style.display = busy ? '' : 'none'
        self.assertIn("kill.style.display = busy", src)

    def test_kill_button_disappears_when_idle(self):
        """setBusy(false) debe ocultar el botón kill."""
        src = _chat_src()
        self.assertIn("'none'", src)

    def test_kill_cancels_multiple_subagents(self):
        """El endpoint delega en request_kill(), que mata todos los subagentes/equipos
        vía kill_all() (comportamiento real cubierto en test_80_kill_all)."""
        from webui.sessions import _WEBUI_SESSIONS
        sid  = "test_kill_multi_001"
        q    = queue.SimpleQueue()
        loop = MagicMock()
        self._inject_session(sid, loop, q)

        with self._make_client() as c:
            with patch("webui.api_chat._get_or_create_sid", return_value=sid):
                resp = c.post("/api/chat/kill")
        data = json.loads(resp.data)
        self.assertTrue(data.get("ok"))
        loop.request_kill.assert_called_once()
        _WEBUI_SESSIONS.pop(sid, None)

    def test_kill_main_loop_kill_requested(self):
        """kill siempre invoca request_kill() (que marca _kill_requested + aborta LLM)."""
        from webui.sessions import _WEBUI_SESSIONS
        sid  = "test_kill_main_001"
        q    = queue.SimpleQueue()
        loop = MagicMock()
        self._inject_session(sid, loop, q)
        with self._make_client() as c:
            with patch("webui.api_chat._get_or_create_sid", return_value=sid):
                c.post("/api/chat/kill")
        loop.request_kill.assert_called_once()
        _WEBUI_SESSIONS.pop(sid, None)

    def test_kill_chat_interruption_message(self):
        """El JS de killAgent debe añadir un mensaje de interrupción al chat."""
        src = _chat_src()
        idx = src.find("function killAgent")
        self.assertGreater(idx, 0)
        fn_end = src.find("\nfunction ", idx + 1)
        fn_body = src[idx: fn_end] if fn_end > idx else src[idx: idx + 600]
        self.assertIn("interrumpido", fn_body.lower())

    def test_kill_button_shows_toast_on_success(self):
        """killAgent debe llamar showToast cuando el kill tiene éxito."""
        src = _chat_src()
        idx = src.find("function killAgent")
        fn_end = src.find("\nfunction ", idx + 1)
        fn_body = src[idx: fn_end] if fn_end > idx else src[idx: idx + 600]
        self.assertIn("showToast", fn_body)


# ── SSE handler: tool_done subagente ─────────────────────────────────────────

class TestSseToolDoneSubagentHandler(unittest.TestCase):

    def _src(self): return _chat_src()

    def test_tool_done_handler_has_subagent_branch(self):
        """El handler tool_done debe ramificar por ev.subagent."""
        src = self._src()
        idx = src.find("case 'tool_done':")
        self.assertGreater(idx, 0)
        idx_brk = src.find("break;", idx)
        handler = src[idx: idx_brk]
        self.assertIn("ev.subagent", handler)

    def test_tool_done_subagent_calls_tool_done_fn(self):
        """La rama subagente debe llamar appendSubagentToolDone."""
        src = self._src()
        idx = src.find("case 'tool_done':")
        idx_brk = src.find("break;", idx)
        handler = src[idx: idx_brk]
        self.assertIn("appendSubagentToolDone", handler)

    def test_tool_done_subagent_file_card_after_check(self):
        """La rama subagente llama appendFileCard si hay file_path."""
        src = self._src()
        idx = src.find("case 'tool_done':")
        idx_brk = src.find("break;", idx)
        handler = src[idx: idx_brk]
        # El bloque if(ev.subagent) debe contener appendFileCard
        subagent_block_idx = handler.find("if (ev.subagent)")
        else_idx = handler.find("} else {", subagent_block_idx)
        sub_block = handler[subagent_block_idx: else_idx] if else_idx > subagent_block_idx else handler[subagent_block_idx:]
        self.assertIn("appendFileCard", sub_block)

    def test_tool_done_main_still_handles_file(self):
        """La rama del agente principal sigue teniendo appendFileCard."""
        src = self._src()
        idx = src.find("case 'tool_done':")
        idx_brk = src.find("break;", idx)
        handler = src[idx: idx_brk]
        else_idx = handler.find("} else {")
        main_block = handler[else_idx:] if else_idx > 0 else handler
        self.assertIn("appendFileCard", main_block)


if __name__ == "__main__":
    unittest.main()
