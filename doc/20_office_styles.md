# 🎨 Guía Completa de Estilos O365 para OOCode

## 📋 Índice

1. [Introducción](#introducción)
2. [Estilos en .docx con python-docx](#estilos-en-docx-con-python-docx)
3. [Estilos en .xlsx con openpyxl](#estilos-en-xlsx-con-openpyxl)
4. [Compatibilidad con O365 y LibreOffice](#compatibilidad-con-o365-y-libreoffice)
5. [Ejemplos Prácticos](#ejemplos-prácticos)
6. [Consideraciones Importantes](#consideraciones-importantes)

---

## Introducción

Esta guía documenta la implementación de estilos y formatos para documentos O365 (.docx, .xlsx) usando las herramientas disponibles en OOCode: **python-docx** y **openpyxl**.

### Herramientas Disponibles

| Herramienta | Descripción | Métodos Principales |
|-------------|-------------|---------------------|
| **python-docx** | Manipulación de documentos .docx | `add_paragraph`, `add_table`, `run_formatting` |
| **openpyxl** | Manipulación de hojas Excel | `CellStyle`, `Font`, `PatternFill`, `Border`, `Alignment` |
| **python-pptx** | Presentaciones .pptx | slides, layouts, gráficas nativas |
| **Gráficas OOXML (DrawingML)** | Gráficas nativas editables en Office | `insert_chart`, `xlsx_insert_chart`, `pptx_insert_chart` |
| **Pillow** | Manipulación de imágenes | Carga y procesamiento de imágenes |

---

## Estilos en .docx con python-docx

### 📌 Métodos Principales

#### 1. **Estilos de Párrafo**

```python
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_UNDERLINE

doc = Document()

# Añadir párrafo con estilo
p = doc.add_paragraph("Texto con estilo")
p.alignment = WD_ALIGN_PARAGRAPH.CENTER
p.paragraph_format.space_after = Pt(12)
p.paragraph_format.line_spacing = 1.5
```

#### 2. **Formato de Run (Texto)**

```python
from docx.shared import RGBColor
from docx.enum.text import WD_UNDERLINE

run = p.runs[0]
run.bold = True
run.italic = True
run.underline = WD_UNDERLINE.SINGLE
run.font.name = "Calibri"
run.font.size = Pt(12)
run.font.color.rgb = RGBColor(0, 0, 0)
run.font.name_set = "Calibri"
```

#### 3. **Estilos de Tabla**

```python
# Crear tabla
table = doc.add_table(rows=3, cols=2)

# Aplicar estilo a tabla
table.style = 'Table Grid'

# Configurar bordes y sombreado
for row in table.rows:
    for cell in row.cells:
        for paragraph in cell.paragraphs:
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
```

#### 4. **Estilos de Lista**

```python
# Añadir lista numerada
p = doc.add_paragraph()
run = p.add_run("Elemento de lista")
run.font.size = Pt(11)
run.font.name = "Calibri"
```

### 📊 Tabla de Métodos Disponibles

| Clase | Métodos Principales | Descripción |
|-------|---------------------|-------------|
| **Paragraph** | `alignment`, `style`, `runs`, `paragraph_format` | Formato de párrafo |
| **Run** | `bold`, `italic`, `underline`, `font`, `text` | Formato de texto |
| **Table** | `style`, `rows`, `columns`, `autofit` | Formato de tabla |
| **Cell** | `paragraphs`, `tables`, `merge`, `width` | Formato de celda |
| **ParagraphFormat** | `space_before`, `space_after`, `line_spacing` | Espaciado y alineación |

### 🎯 Propiedades de Font

```python
from docx.shared import RGBColor

font = run.font
font.name = "Calibri"          # Nombre de fuente
font.size = Pt(12)             # Tamaño en puntos
font.bold = True               # Negrita
font.italic = True             # Cursiva
font.underline = WD_UNDERLINE.SINGLE  # Subrayado
font.color.rgb = RGBColor(0, 0, 0)  # Color negro
font.name_set = "Calibri"      # Fuente alternativa
```

### 🎨 Propiedades de Párrafo

```python
from docx.shared import Pt

pf = p.paragraph_format
pf.space_before = Pt(0)        # Espacio antes
pf.space_after = Pt(12)        # Espacio después
pf.line_spacing = 1.5          # Interlineado
pf.alignment = WD_ALIGN_PARAGRAPH.CENTER  # Alineación
```

---

## Estilos en .xlsx con openpyxl

### 📌 Métodos Principales

#### 1. **Estilos de Celda**

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

wb = Workbook()
ws = wb.active

# Configurar estilo de fuente
font = Font(name='Calibri', size=11, bold=False, italic=False, 
            underline=False, color='FF000000')

# Configurar relleno
fill = PatternFill(start_color='FFD9E1F2', end_color='FFD9E1F2', 
                   pattern_type='solid')

# Configurar borde
thin_border = Border(
    left=Side(style='thin', color='FF000000'),
    right=Side(style='thin', color='FF000000'),
    top=Side(style='thin', color='FF000000'),
    bottom=Side(style='thin', color='FF000000')
)

# Configurar alineación
align = Alignment(horizontal='center', vertical='center', wrap_text=True)

# Aplicar estilos
cell = ws['A1']
cell.font = font
cell.fill = fill
cell.border = thin_border
cell.alignment = align
```

#### 2. **Formato Numérico**

```python
# Formato de número
cell.number_format = '#,##0.00'  # Moneda
cell.number_format = '0.0%'      # Porcentaje
cell.number_format = 'mmm-dd-yy' # Fecha
```

#### 3. **Protección de Celda**

```python
# Protección
cell.protection.locked = True
cell.protection.hidden = False
```

#### 4. **Hipervínculos**

```python
from openpyxl.utils import get_column_letter

cell.hyperlink = cell.hyperlink
cell.hyperlink.r_id = r_id
cell.hyperlink.label = 'Texto del enlace'
```

### 📊 Tabla de Métodos de Estilos

| Clase | Métodos Principales | Descripción |
|-------|---------------------|-------------|
| **Font** | `bold`, `italic`, `underline`, `size`, `color` | Formato de texto |
| **PatternFill** | `start_color`, `end_color`, `pattern_type` | Relleno de celda |
| **Border** | `left`, `right`, `top`, `bottom`, `diagonal` | Bordes de celda |
| **Side** | `style`, `color`, `border_style` | Borde individual |
| **Alignment** | `horizontal`, `vertical`, `wrap_text`, `text_rotation` | Alineación |

### 🎨 Tipos de Bordes

```python
# Estilos de borde disponibles
border_styles = ['thin', 'medium', 'thick', 'dotted', 'dashed', 
                  'double', 'hair', 'mediumDashed', 'mediumDotted']

# Crear borde personalizado
custom_border = Border(
    left=Side(style='thin', color='FF000000'),
    right=Side(style='thin', color='FF000000'),
    top=Side(style='thick', color='FFFF0000'),
    bottom=Side(style='dashed', color='FF0000FF')
)
```

### 🎨 Tipos de Relleno

```python
# Patrón de relleno
pattern_types = ['solid', 'gray125', 'gray25', 'gray50', 
                  'gray75', 'horizontal', 'vertical', 
                  'down', 'up', 'lightUp', 'lightDown',
                  'lightLeft', 'lightRight', 'checkerBoard']

# Relleno con gradiente
from openpyxl.styles import GradientFill

gradient = GradientFill(
    rgbColor1='FFFFFFFF',
    rgbColor2='FF000000',
    type='cycle'
)
```

---

## Compatibilidad con O365 y LibreOffice

### ✅ Compatibilidad Confirmada

| Característica | O365 | LibreOffice | Notas |
|----------------|------|-------------|-------|
| **Estilos de fuente** | ✅ | ✅ | Calibri, Arial, Times New Roman |
| **Negrita/Cursiva** | ✅ | ✅ | Soporte completo |
| **Subrayado** | ✅ | ✅ | Sencillo, doble, contable |
| **Colores de texto** | ✅ | ✅ | RGB completo |
| **Bordes de tabla** | ✅ | ✅ | Todos los estilos |
| **Sombreado** | ✅ | ✅ | Sólido y gradientes |
| **Alineación** | ✅ | ✅ | Horizontal y vertical |
| **Interlineado** | ✅ | ✅ | Múltiples valores |
| **Hipervínculos** | ✅ | ✅ | URL y texto |
| **Formato numérico** | ✅ | ✅ | Moneda, %, fecha |
| **Gráficos** | ✅ | ✅ | PNG, SVG, PDF |

### ⚠️ Consideraciones de Compatibilidad

1. **Fuente Calibri**: Es la fuente predeterminada de O365. Usarla garantiza máxima compatibilidad.
2. **Colores RGB**: Ambos soportan colores en formato RGB (000000 = negro, FFFFFFF = blanco).
3. **Bordes diagonales**: Soportados en ambos, pero pueden variar ligeramente en renderizado.
4. **Gráficos**: Las gráficas son objetos OOXML nativos (DrawingML), editables en Office — no imágenes PNG.
5. **Formatos condicionales**: Mejor soporte en O365, limitado en LibreOffice.

---

## Ejemplos Prácticos

### Ejemplo 1: Documento .docx Completo

```python
from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_UNDERLINE
from docx.oxml.ns import qn

def crear_documento_estilizado():
    doc = Document()
    
    # Título
    titulo = doc.add_paragraph("Reporte Mensual")
    titulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = titulo.runs[0]
    run.bold = True
    run.font.size = Pt(16)
    run.font.name = "Calibri"
    
    # Subtítulo
    subtitulo = doc.add_paragraph("Resumen de Actividad")
    subtitulo.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = subtitulo.runs[0]
    run.italic = True
    run.font.size = Pt(14)
    
    # Contenido
    contenido = doc.add_paragraph()
    run = contenido.runs[0]
    run.text = "Este es el contenido del documento."
    run.font.size = Pt(12)
    run.font.name = "Calibri"
    
    # Tabla
    tabla = doc.add_table(rows=3, cols=2)
    tabla.style = 'Table Grid'
    
    # Encabezado de tabla
    encabezado = tabla.rows[0].cells[0]
    for para in encabezado.paragraphs:
        para.alignment = WD_ALIGN_PARAGRAPH.CENTER
        run = para.runs[0]
        run.bold = True
        run.font.size = Pt(10)
    
    # Celdas de datos
    for i, row in enumerate(tabla.rows[1:], 1):
        for j, cell in enumerate(row.cells):
            para = cell.paragraphs[0]
            para.alignment = WD_ALIGN_PARAGRAPH.CENTER
            run = para.runs[0]
            run.text = f"Fila {i}, Columna {j}"
            run.font.size = Pt(10)
    
    return doc
```

### Ejemplo 2: Hoja Excel Formateada

```python
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Border, Side, Alignment

def crear_hoja_formateada():
    wb = Workbook()
    ws = wb.active
    
    # Título
    ws['A1'] = 'Reporte Financiero'
    ws['A1'].font = Font(name='Calibri', size=16, bold=True)
    ws['A1'].alignment = Alignment(horizontal='center', vertical='center')
    
    # Encabezados
    encabezados = ['Concepto', 'Ingresos', 'Gastos', 'Saldo']
    for col, texto in enumerate(encabezados, 1):
        cell = ws.cell(row=1, column=col, value=texto)
        cell.font = Font(name='Calibri', size=11, bold=True)
        cell.fill = PatternFill(start_color='FF4472C4', end_color='FF4472C4', 
                                pattern_type='solid')
        cell.font = Font(name='Calibri', size=11, bold=True, color='FFFFFFFF')
        cell.alignment = Alignment(horizontal='center', vertical='center')
    
    # Datos
    datos = [
        ['Ventas', 15000, 12000, 3000],
        ['Servicios', 8000, 6000, 2000],
        ['Otros', 5000, 4000, 1000]
    ]
    
    for row_idx, datos_row in enumerate(datos, 2):
        for col_idx, valor in enumerate(datos_row, 2):
            cell = ws.cell(row=row_idx, column=col_idx, value=valor)
            cell.font = Font(name='Calibri', size=11)
            cell.border = Border(
                left=Side(style='thin', color='FF000000'),
                right=Side(style='thin', color='FF000000'),
                top=Side(style='thin', color='FF000000'),
                bottom=Side(style='thin', color='FF000000')
            )
            cell.alignment = Alignment(horizontal='right', vertical='center')
    
    # Formato numérico
    for col in range(2, 5):
        for row in range(2, 5):
            ws.cell(row=row, column=col).number_format = '#,##0'
    
    return wb
```

### Ejemplo 3: Gráfica OOXML nativa en Word

La gráfica se inserta como objeto editable de Word (DrawingML), no como imagen. Con la tool `insert_chart`:

```json
{
  "path": "/tmp/informe.docx",
  "chart_type": "bar",
  "title": "Evolución Mensual",
  "data": {
    "categories": ["Enero", "Febrero", "Marzo", "Abril", "Mayo"],
    "series": [{"label": "Valor", "values": [12000, 15000, 18000, 22000, 25000]}]
  }
}
```

O dentro de `doc_create`, como un bloque más de `content_blocks`:

```json
{"type": "chart", "chart_type": "bar", "title": "Evolución Mensual",
 "data": {"categories": ["Ene","Feb","Mar"],
          "series": [{"label": "Valor", "values": [12000, 15000, 18000]}]}}
```

### Ejemplo 4: Informe completo nativo

Una sola llamada a `doc_create` con `content_blocks` (título, tabla, gráfica nativa) genera el
documento Word completo con estilos O365 — sin pasos intermedios ni imágenes PNG.

---

## Consideraciones Importantes

### 📦 Instalación de Dependencias

```bash
# Instalar todas las dependencias necesarias
pip install python-docx python-pptx openpyxl pillow docxtpl

# Verificar instalación
python -c "import docx, openpyxl, pptx, docxtpl; print('✅ Todas las librerías instaladas')"
```

### 🎨 Paleta de Colores O365

```python
from docx.shared import RGBColor
from openpyxl.styles import PatternFill

# Colores O365 oficiales
colores_o365 = {
    'blue': RGBColor(0, 112, 192),      # #0070C0
    'dark_blue': RGBColor(0, 51, 102),   # #003366
    'red': RGBColor(204, 0, 0),          # #CC0000
    'green': RGBColor(0, 128, 0),        # #008000
    'yellow': RGBColor(255, 204, 0),     # #FFCC00
    'white': RGBColor(255, 255, 255),
    'black': RGBColor(0, 0, 0)
}

# Colores para Excel
fill_o365 = {
    'blue': PatternFill(start_color='FF0070C0', end_color='FF0070C0', pattern_type='solid'),
    'red': PatternFill(start_color='FFCC0000', end_color='FFCC0000', pattern_type='solid'),
    'green': PatternFill(start_color='FF008000', end_color='FF008000', pattern_type='solid'),
}
```

### 📝 Best Practices

1. **Usar fuente Calibri**: Garantiza máxima compatibilidad con O365.
2. **Tamaños de fuente**: Mantener entre 10-14 pt para texto normal.
3. **Colores**: Usar paletas predefinidas para consistencia.
4. **Bordes**: Usar bordes finos (`thin`) para tablas profesionales.
5. **Interlineado**: 1.15-1.5 para documentos formales.
6. **Espaciado**: 6-12 pt entre párrafos.
7. **Gráficos**: Exportar a PNG con DPI 300 para alta calidad.

### ⚠️ Limitaciones

- **Gráficas**: se generan como OOXML nativo (DrawingML); tipos soportados en Word: bar, column, line, line_markers, area, pie, doughnut, scatter, stacked_bar, stacked_column, radar.
- **openpyxl**: Formatos condicionales limitados en versiones antiguas.
- **LibreOffice**: Algunos estilos avanzados pueden no renderizarse correctamente.

### 🔧 Solución de Problemas

```python
# Si los estilos no se aplican correctamente:
# 1. Verificar versión de python-docx
import docx
print(docx.__version__)  # >= 0.8.11

# 2. Verificar versión de openpyxl
import openpyxl
print(openpyxl.__version__)  # >= 3.0.0

# 3. Reiniciar servidor LSP para C/C++/Python
# lsp_restart(path)
```

---

## Referencias

- [python-docx documentación](https://python-docx.readthedocs.io/)
- [openpyxl documentación](https://openpyxl.readthedocs.io/)
- [python-pptx documentación](https://python-pptx.readthedocs.io/)
- [Pillow documentación](https://pillow.readthedocs.io/)

---

## Actualizaciones

| Versión | Fecha | Cambios |
|---------|-------|---------|
| 1.0 | 2026-05-25 | Creación inicial de la guía |

---

*Documento generado automáticamente por OOCode - WebCrawler*
