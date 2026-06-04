"""Blueprint /api/files/* — descarga, info y subida de ficheros."""
import mimetypes
import os
from pathlib import Path
from typing import Optional

from flask import Blueprint, jsonify, request, send_file

from webui.helpers import _human_size

bp = Blueprint("api_files", __name__)

_HOME = Path.home()


def _safe_path(raw: str) -> Optional[Path]:
    """Valida y normaliza una ruta para descarga. Solo permite ficheros bajo HOME o /tmp."""
    if not raw:
        return None
    try:
        p = Path(raw).expanduser().resolve()
        if not (str(p).startswith(str(_HOME)) or str(p).startswith("/tmp")):
            return None
        if p.is_file():
            return p
    except Exception:
        pass
    return None


@bp.route('/api/files/download')
def api_files_download():
    """Descarga un fichero generado por el agente."""
    raw = request.args.get("path", "").strip()
    p = _safe_path(raw)
    if p is None:
        return jsonify({"error": "Ruta inválida o fichero no encontrado"}), 404
    mime, _ = mimetypes.guess_type(str(p))
    mime = mime or "application/octet-stream"
    return send_file(
        str(p),
        mimetype=mime,
        as_attachment=True,
        download_name=p.name,
    )


@bp.route('/api/files/info')
def api_files_info():
    """Devuelve metadatos de un fichero generado."""
    raw = request.args.get("path", "").strip()
    p = _safe_path(raw)
    if p is None:
        return jsonify({"error": "Ruta inválida o fichero no encontrado"}), 404
    size = p.stat().st_size
    mime, _ = mimetypes.guess_type(str(p))
    return jsonify({
        "name":   p.name,
        "path":   str(p),
        "size":   size,
        "size_h": _human_size(size),
        "mime":   mime or "application/octet-stream",
        "ext":    p.suffix.lower(),
    })


@bp.route('/api/files/upload', methods=['POST'])
def api_files_upload():
    """Sube un fichero (imagen o texto) para enviarlo al agente con visión."""
    if 'file' not in request.files:
        return jsonify({"error": "Sin fichero (campo 'file' requerido)"}), 400

    f = request.files['file']
    if not f.filename:
        return jsonify({"error": "Nombre de fichero vacío"}), 400

    _IMG_EXTS  = {'.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.tiff'}
    _TEXT_EXTS = {'.txt', '.py', '.js', '.ts', '.jsx', '.tsx', '.md', '.json',
                  '.yaml', '.yml', '.csv', '.toml', '.ini', '.sh', '.html', '.css'}
    allowed = _IMG_EXTS | _TEXT_EXTS
    ext = Path(f.filename).suffix.lower()
    if ext not in allowed:
        return jsonify({"error": f"Tipo no permitido: {ext}"}), 400

    upload_dir = Path.home() / ".oocode" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    safe_name = f"{os.urandom(6).hex()}_{Path(f.filename).name}"
    dest = upload_dir / safe_name
    f.save(str(dest))

    is_image  = ext in _IMG_EXTS
    file_size = dest.stat().st_size

    return jsonify({
        "ok":     True,
        "path":   str(dest),
        "name":   f.filename,
        "size":   file_size,
        "size_h": _human_size(file_size),
        "type":   "image" if is_image else "text",
        "ext":    ext,
    })
