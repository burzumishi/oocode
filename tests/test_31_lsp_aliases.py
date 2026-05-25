"""Tests para _SERVER_ALIASES y compartición de clientes LSP en LspPool.

Reproducibugs el error "[Autoformat] No hay servidor LSP disponible para '.h'."
que ocurría porque LspPool creaba un proceso clangd separado por extensión —
el segundo proceso fallaba. Con aliases, .h/.hpp/.cc/.jsx/.tsx/.scss/.yml/.pm
comparten el cliente de su extensión canónica.

Cubre:
- _SERVER_ALIASES contiene los aliases esperados
- _SERVER_ALIASES no contiene alias circular o alias de canónico a canónico
- LspPool.get() resuelve .h → .c (mismo client object)
- LspPool.get() resuelve .hpp → .cpp
- LspPool.get() resuelve .jsx → .js
- LspPool.get() resuelve .tsx → .ts
- LspPool.get() resuelve .scss → .css
- LspPool.get() resuelve .yml → .yaml
- LspPool.get() resuelve .pm → .pl
- LspPool.get() con ext canónico (.c) no usa alias
- LspPool crea el cliente bajo la clave canónica, no bajo la alias
- Segunda llamada con ext alias devuelve el mismo objeto (no crea otro)
- LspPool.restart() usa la clave canónica
- _no_server_msg() en plugins/lsp.py usa alias para cmd lookup
- _EXT_TO_LANG contiene .hh y .cxx como cpp
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import MagicMock, patch


class TestServerAliasesDict:
    def test_h_aliases_to_c(self):
        from agent.lsp_client import _SERVER_ALIASES
        assert _SERVER_ALIASES[".h"] == ".c"

    def test_hpp_aliases_to_cpp(self):
        from agent.lsp_client import _SERVER_ALIASES
        assert _SERVER_ALIASES[".hpp"] == ".cpp"

    def test_hh_aliases_to_cpp(self):
        from agent.lsp_client import _SERVER_ALIASES
        assert _SERVER_ALIASES[".hh"] == ".cpp"

    def test_cc_aliases_to_cpp(self):
        from agent.lsp_client import _SERVER_ALIASES
        assert _SERVER_ALIASES[".cc"] == ".cpp"

    def test_cxx_aliases_to_cpp(self):
        from agent.lsp_client import _SERVER_ALIASES
        assert _SERVER_ALIASES[".cxx"] == ".cpp"

    def test_jsx_aliases_to_js(self):
        from agent.lsp_client import _SERVER_ALIASES
        assert _SERVER_ALIASES[".jsx"] == ".js"

    def test_tsx_aliases_to_ts(self):
        from agent.lsp_client import _SERVER_ALIASES
        assert _SERVER_ALIASES[".tsx"] == ".ts"

    def test_scss_aliases_to_css(self):
        from agent.lsp_client import _SERVER_ALIASES
        assert _SERVER_ALIASES[".scss"] == ".css"

    def test_less_aliases_to_css(self):
        from agent.lsp_client import _SERVER_ALIASES
        assert _SERVER_ALIASES[".less"] == ".css"

    def test_yml_aliases_to_yaml(self):
        from agent.lsp_client import _SERVER_ALIASES
        assert _SERVER_ALIASES[".yml"] == ".yaml"

    def test_pm_aliases_to_pl(self):
        from agent.lsp_client import _SERVER_ALIASES
        assert _SERVER_ALIASES[".pm"] == ".pl"

    def test_canonical_extensions_not_in_aliases(self):
        """Las extensiones canónicas (.c, .cpp, .js, .ts...) no deben ser alias."""
        from agent.lsp_client import _SERVER_ALIASES
        canonicals = {".c", ".cpp", ".js", ".ts", ".css", ".yaml", ".pl"}
        for canon in canonicals:
            assert canon not in _SERVER_ALIASES, (
                f"{canon} no debe ser alias — es la extensión canónica"
            )

    def test_no_circular_aliases(self):
        """No debe haber alias circular (ext → Y → ext)."""
        from agent.lsp_client import _SERVER_ALIASES
        for ext, canon in _SERVER_ALIASES.items():
            assert _SERVER_ALIASES.get(canon, canon) == canon, (
                f"Alias circular detectado: {ext} → {canon} → {_SERVER_ALIASES.get(canon)}"
            )

    def test_canonical_targets_have_server_cmd(self):
        """Todos los canonicales en _SERVER_ALIASES deben tener entrada en _SERVER_CMDS."""
        from agent.lsp_client import _SERVER_ALIASES, _SERVER_CMDS
        for ext, canon in _SERVER_ALIASES.items():
            assert canon in _SERVER_CMDS, (
                f"El canónico '{canon}' (alias de '{ext}') no tiene entrada en _SERVER_CMDS"
            )


class TestLspPoolAliasResolution:
    def _make_pool_with_mock_client(self):
        """Crea un LspPool donde LspClient.start() siempre funciona."""
        from agent.lsp_client import LspPool
        pool = LspPool.__new__(LspPool)
        pool._workspace = "/tmp/test"
        pool._timeout = 5.0
        import threading
        pool._lock = threading.Lock()
        pool._clients = {}
        from agent.lsp_client import _SERVER_CMDS
        pool._cmds = dict(_SERVER_CMDS)
        return pool

    def _inject_alive_client(self, pool, canonical: str) -> MagicMock:
        """Inyecta un cliente mock vivo en el pool bajo la clave canónica."""
        mock_client = MagicMock()
        mock_client.is_alive = True
        pool._clients[canonical] = mock_client
        return mock_client

    def test_h_returns_c_client(self):
        """pool.get('.h') devuelve el mismo cliente que pool.get('.c')."""
        pool = self._make_pool_with_mock_client()
        mock = self._inject_alive_client(pool, ".c")
        result = pool.get(".h")
        assert result is mock

    def test_hpp_returns_cpp_client(self):
        pool = self._make_pool_with_mock_client()
        mock = self._inject_alive_client(pool, ".cpp")
        result = pool.get(".hpp")
        assert result is mock

    def test_cc_returns_cpp_client(self):
        pool = self._make_pool_with_mock_client()
        mock = self._inject_alive_client(pool, ".cpp")
        result = pool.get(".cc")
        assert result is mock

    def test_hh_returns_cpp_client(self):
        pool = self._make_pool_with_mock_client()
        mock = self._inject_alive_client(pool, ".cpp")
        result = pool.get(".hh")
        assert result is mock

    def test_jsx_returns_js_client(self):
        pool = self._make_pool_with_mock_client()
        mock = self._inject_alive_client(pool, ".js")
        result = pool.get(".jsx")
        assert result is mock

    def test_tsx_returns_ts_client(self):
        pool = self._make_pool_with_mock_client()
        mock = self._inject_alive_client(pool, ".ts")
        result = pool.get(".tsx")
        assert result is mock

    def test_scss_returns_css_client(self):
        pool = self._make_pool_with_mock_client()
        mock = self._inject_alive_client(pool, ".css")
        result = pool.get(".scss")
        assert result is mock

    def test_yml_returns_yaml_client(self):
        pool = self._make_pool_with_mock_client()
        mock = self._inject_alive_client(pool, ".yaml")
        result = pool.get(".yml")
        assert result is mock

    def test_canonical_extension_not_affected(self):
        """pool.get('.c') con cliente .c activo devuelve ese cliente directamente."""
        pool = self._make_pool_with_mock_client()
        mock = self._inject_alive_client(pool, ".c")
        result = pool.get(".c")
        assert result is mock

    def test_client_stored_under_canonical_key(self):
        """Al crear cliente para .h, se almacena en self._clients['.c'], no ['.h']."""
        pool = self._make_pool_with_mock_client()
        mock_client = MagicMock()
        mock_client.is_alive = True

        with patch("agent.lsp_client.LspClient") as MockLspClient, \
             patch("agent.lsp_client._which", return_value=True):
            MockLspClient.return_value = mock_client
            pool.get(".h")

        assert ".c" in pool._clients
        assert ".h" not in pool._clients

    def test_alias_reuses_existing_canonical_client(self):
        """Dos llamadas a .h y .c devuelven el mismo client object."""
        pool = self._make_pool_with_mock_client()
        mock_client = MagicMock()
        mock_client.is_alive = True

        with patch("agent.lsp_client.LspClient") as MockLspClient, \
             patch("agent.lsp_client._which", return_value=True):
            MockLspClient.return_value = mock_client
            c1 = pool.get(".c")   # crea cliente → .c
            c2 = pool.get(".h")   # alias → usa .c existente
            # Solo se crea UNA instancia de LspClient
            assert MockLspClient.call_count == 1
        assert c1 is c2

    def test_dead_canonical_client_triggers_restart(self):
        """Si el cliente canónico está muerto, se intenta reiniciar."""
        pool = self._make_pool_with_mock_client()
        dead_client = MagicMock()
        dead_client.is_alive = False
        pool._clients[".c"] = dead_client

        new_client = MagicMock()
        new_client.is_alive = True

        with patch("agent.lsp_client.LspClient") as MockLspClient, \
             patch("agent.lsp_client._which", return_value=True):
            MockLspClient.return_value = new_client
            result = pool.get(".h")

        assert result is new_client
        assert pool._clients[".c"] is new_client

    def test_restart_uses_canonical_key(self):
        """pool.restart('.h') elimina el cliente bajo clave '.c', no '.h'."""
        pool = self._make_pool_with_mock_client()
        mock = self._inject_alive_client(pool, ".c")

        with patch("agent.lsp_client.LspClient") as MockLspClient, \
             patch("agent.lsp_client._which", return_value=True):
            new_mock = MagicMock()
            new_mock.is_alive = True
            MockLspClient.return_value = new_mock
            pool.restart(".h")

        assert pool._clients.get(".c") is new_mock
        assert ".h" not in pool._clients


class TestExtToLangAliases:
    def test_hh_mapped_to_cpp(self):
        from agent.lsp_client import _EXT_TO_LANG
        assert _EXT_TO_LANG[".hh"] == "cpp"

    def test_cxx_mapped_to_cpp(self):
        from agent.lsp_client import _EXT_TO_LANG
        assert _EXT_TO_LANG[".cxx"] == "cpp"

    def test_h_still_mapped_to_c(self):
        from agent.lsp_client import _EXT_TO_LANG
        assert _EXT_TO_LANG[".h"] == "c"

    def test_hpp_still_mapped_to_cpp(self):
        from agent.lsp_client import _EXT_TO_LANG
        assert _EXT_TO_LANG[".hpp"] == "cpp"


class TestNoServerMsgAlias:
    def test_h_with_clangd_installed_no_error(self):
        """Con clangd instalado, _no_server_msg para .h usa el canal .c → clangd."""
        from plugins.lsp import _no_server_msg
        # plugins/lsp.py importa _which directamente — parchear en ese módulo
        with patch("plugins.lsp._which", return_value=True):
            msg = _no_server_msg("/project/file.h")
        # Con clangd instalado devuelve "No hay servidor disponible"
        # (el pool no pudo arrancar) — no dice "no encontrado"
        assert "no encontrado" not in msg.lower()

    def test_h_without_clangd_gives_install_hint(self):
        """Sin clangd instalado, _no_server_msg para .h sugiere instalar clangd."""
        from plugins.lsp import _no_server_msg
        with patch("plugins.lsp._which", return_value=False):
            msg = _no_server_msg("/project/file.h")
        assert "clangd" in msg.lower()
        assert "no encontrado" in msg.lower() or "apt" in msg or "brew" in msg

    def test_hpp_without_clangd_gives_install_hint(self):
        from plugins.lsp import _no_server_msg
        with patch("plugins.lsp._which", return_value=False):
            msg = _no_server_msg("/project/file.hpp")
        assert "clangd" in msg.lower()
