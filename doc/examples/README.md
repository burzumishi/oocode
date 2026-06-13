# Configuraciones de ejemplo

Tres perfiles de `oocode.json` listos para copiar a `~/.oocode/oocode.json`, según la
VRAM de tu GPU y el modelo Ollama que ejecutes. Son **configuraciones mínimas**: OOCode
las fusiona con los valores por defecto, así que solo contienen lo que cambia respecto al
default (backend, modelo, ventana de contexto y un par de límites). El resto de bloques
(`permissions`, `webui`, `mcp`, `subagents`…) se rellenan solos con sus defaults.

| Fichero | Modelo | Cuant. | VRAM objetivo | Contexto |
|---------|--------|--------|---------------|----------|
| `oocode.4b-q4_0.json` | `qwen3.5:4b` | `q4_0` | ~8 GB  | 131K |
| `oocode.4b-q8_0.json` | `qwen3.5:4b` | `q8_0` | ~12 GB | 131K |
| `oocode.9b-q8_0.json` | `qwen3.5:9b` | `q8_0` | ~16 GB | 131K |

## Cómo usarlas

```bash
# 1. Descarga el modelo con la cuantización del perfil (la cuant. se elige aquí, NO en oocode.json)
ollama pull qwen3.5:4b          # o la variante q8_0 / 9b que toque

# 2. Copia el perfil que encaje con tu hardware
cp doc/examples/oocode.4b-q4_0.json ~/.oocode/oocode.json

# 3. Ajusta el host si tu Ollama no está en localhost
#    (edita "api".host) y arranca
python oocode.py --doctor
```

## Sobre la cuantización (q4_0 vs q8_0)

La cuantización **no se configura en `oocode.json`** — se decide al hacer `ollama pull`
(el tag del modelo). Por eso los perfiles `4b-q4_0` y `4b-q8_0` comparten la misma
ventana de contexto: la diferencia real es la **VRAM** que ocupan los pesos y la
**calidad** de salida.

- **`q4_0`** — pesos a 4 bits: ocupa ~la mitad de VRAM, deja más sitio para el contexto
  (KV cache). Mejor para tarjetas pequeñas (8 GB) o contextos enormes. Algo menos preciso.
- **`q8_0`** — pesos a 8 bits: ~el doble de VRAM que `q4_0`, calidad notablemente mejor.
  Elígelo si te sobra VRAM.
- Subir de **4b a 9b** mejora el razonamiento pero exige bastante más VRAM; con 16 GB,
  `9b q8_0` a 131K de contexto es el punto dulce.

> **Nota sobre el contexto.** No pongas `contextWindow`/`num_ctx` al máximo del modelo
> "porque sí": una ventana gigante consume VRAM en KV cache y deja menos margen para la
> generación, además de degradar la compactación automática. 131K es un buen equilibrio
> para estos perfiles. Si vas justo de VRAM, baja a `65536`.

Más detalle en [`doc/02_configuration.md`](../02_configuration.md) → *Configuración por hardware*.
