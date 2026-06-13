"""Higiene de schemas de tools MCP: cada parámetro debe estar bien definido para que el
LLM use la tool correctamente.

Reglas (un schema mal definido lleva al modelo a invocar mal la tool):
- cada propiedad declara un tipo (`type`, o `enum`/`anyOf`/`oneOf`/`$ref`),
- cada propiedad tiene `description` no vacía,
- cada nombre en `required` existe en `properties`,
- la tool tiene `name` y `description` no vacías.

Guarda contra regresiones (p.ej. añadir una tool con un param sin type, como tenían
xlsx_write.value, pptx.slide_index, http_request.body, etc. antes de 2026-06).
"""
import importlib
import pytest

_MCP_MODULES = [
    "oocode_assistant", "devops_assistant", "database_assistant", "system_assistant",
    "word_assistant", "excel_assistant", "pptx_assistant", "mail_assistant",
    "cmdb_assistant", "security_assistant", "iot_assistant", "http_client_assistant",
]

_TYPE_KEYS = ("type", "enum", "anyOf", "oneOf", "$ref")


def _load_tools(mod):
    m = importlib.import_module(f"mcp_servers.{mod}")
    return list(getattr(m, "_TOOLS", []))


@pytest.mark.parametrize("mod", _MCP_MODULES)
def test_mcp_tool_schemas_well_defined(mod):
    tools = _load_tools(mod)
    assert tools, f"{mod} no expone _TOOLS"
    for t in tools:
        name = t.get("name", "")
        assert name, f"{mod}: tool sin nombre"
        assert (t.get("description") or "").strip(), f"{mod}:{name} sin descripción"
        sch = t.get("inputSchema") or {}
        props = sch.get("properties", {}) if isinstance(sch, dict) else {}
        for pn, pd in props.items():
            assert isinstance(pd, dict), f"{mod}:{name} param {pn} no es objeto"
            assert any(k in pd for k in _TYPE_KEYS), \
                f"{mod}:{name} param '{pn}' SIN type/enum"
            assert (pd.get("description") or "").strip(), \
                f"{mod}:{name} param '{pn}' sin description"
        for r in sch.get("required", []) if isinstance(sch, dict) else []:
            assert r in props, f"{mod}:{name} required '{r}' no está en properties"


def test_no_param_without_type_globally():
    """Agregado: cero parámetros sin type en TODOS los MCP (regresión de 2026-06)."""
    offenders = []
    for mod in _MCP_MODULES:
        for t in _load_tools(mod):
            sch = t.get("inputSchema") or {}
            for pn, pd in (sch.get("properties", {}) if isinstance(sch, dict) else {}).items():
                if isinstance(pd, dict) and not any(k in pd for k in _TYPE_KEYS):
                    offenders.append(f"{mod}:{t.get('name')}.{pn}")
    assert not offenders, f"params sin type: {offenders}"
