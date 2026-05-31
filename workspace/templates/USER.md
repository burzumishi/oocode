# USER.md — Sobre Tu Usuario

_Actualiza este fichero a medida que conoces mejor a la persona que ayudas._

## Datos Básicos

- **Nombre:** __NOMBRE DEL USUARIO__
- **Llamado:** __ALIAS__
- **Zona horaria:** Europe/Madrid (UTC+1/UTC+2)
- **Idioma:** Español
- **Estilo:** Directo, técnico, sin rodeos

## Proyectos Activos

## Preferencias

- **Tech:** Python 3.13, C17, SQL (PostgreSQL/SQLite), Bash
- **Enfoque:** Práctico, orientado a soluciones reales

## Contexto del Agente Office

- **Rol:** Documentación corporativa, RFCs, informes técnicos, actas
- **Especialidad:** Documentos formales, plantillas Office, gestión de activos
- **Flujo:** Leer contexto → Buscar plantillas → Generar documento → Verificar formato → Guardar
- **Herramientas clave:** `doc_create_rfc`, `doc_project_save`, `xlsx_create_report`, `doc_fill_template`

## Notas

### Lecciones del Usuario

- Prefiere soluciones prácticas y orientadas a resultados
- Valoriza la documentación estructurada (RFCs por fase)
- Usa subagentes para delegar tareas independientes
- Aplica linting y tests antes de commit

### Decisiones Técnicas Importantes

- Modernización de código legacy a C17
- División de `mud.h` en 8 subarchivos para balance del preprocesador
- Uso intensivo de LSP para análisis semántico
- Evitar `compose_down -v` sin confirmación explícita

### Herramientas Favoritas

- `python_exec` para análisis rápido sin crear ficheros temporales
- `code_outline` antes de editar ficheros >1000 líneas
- `affected_files` antes de renombrar símbolos
- `lsp_call_hierarchy` para entender flujo de llamadas

### Documentación y RFCs

- Prefiere RFCs estructurados para cambios de infraestructura
- Usa plantillas .docx para documentos formales
- Genera informes Excel para tablas y registros
- Valida documentos antes de guardar

### Gestión de Activos

- Usa CMDB para seguimiento de activos IT
- Registra cambios en `cmdb.csv`
- Mantiene `risk_register.csv` para riesgos conocidos
