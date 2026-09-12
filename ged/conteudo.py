"""Leitura dos PDFs: texto e contagem de páginas.

O texto lido fica guardado em memória enquanto a janela estiver aberta.
Numa pasta típica são cerca de 25 MB — o suficiente para que a primeira busca por conteúdo pague o tempo de abrir os arquivos e todas as seguintes respondam na hora, sem gravar nada em disco.
"""
from __future__ import annotations

from pathlib import Path

try:
    import pymupdf
except ImportError:  # pragma: no cover - nome antigo do módulo
    try:
        import fitz as pymupdf
    except ImportError:
        pymupdf = None

DISPONIVEL = pymupdf is not None


class CacheConteudo:
    """Texto e contagem de páginas já lidos nesta sessão."""

    def __init__(self) -> None:
        self._texto: dict[str, str] = {}
        self._paginas: dict[str, int] = {}
        self._falhas: dict[str, str] = {}

    # -------------------------------------------------------------- texto
    def texto(self, caminho: Path | str) -> str:
        """Texto do PDF, lido na primeira chamada e reaproveitado depois."""
        chave = str(caminho)
        if chave in self._texto:
            return self._texto[chave]
        if not DISPONIVEL:
            return ""
        try:
            with pymupdf.open(chave) as doc:
                partes = [pagina.get_text() for pagina in doc]
                self._paginas[chave] = doc.page_count
            texto = "\n".join(partes)
        except Exception as exc:
            self._falhas[chave] = str(exc)
            texto = ""
        self._texto[chave] = texto
        return texto

    def ja_lido(self, caminho: Path | str) -> bool:
        return str(caminho) in self._texto

    def tem_texto(self, caminho: Path | str) -> bool:
        """Falso para PDF que é só imagem — ou que falhou ao abrir."""
        return bool(self._texto.get(str(caminho), "").strip())

    # ------------------------------------------------------------ páginas
    def paginas(self, caminho: Path | str) -> int | None:
        """Número de páginas, lido só da estrutura do arquivo (não renderiza)."""
        chave = str(caminho)
        if chave in self._paginas:
            return self._paginas[chave]
        if not DISPONIVEL:
            return None
        try:
            with pymupdf.open(chave) as doc:
                self._paginas[chave] = doc.page_count
        except Exception as exc:
            self._falhas[chave] = str(exc)
            return None
        return self._paginas[chave]

    # ---------------------------------------------------------- problemas
    @property
    def falhas(self) -> dict[str, str]:
        return dict(self._falhas)

    def sem_texto(self, caminhos: list[str]) -> int:
        """Quantos, entre os já lidos, não tinham texto para procurar."""
        return sum(
            1 for c in caminhos if c in self._texto and not self._texto[c].strip()
        )


def primeira_pagina_png(caminho: Path | str, largura: int = 320) -> bytes | None:
    """Miniatura da primeira página, para a pré-visualização da interface."""
    if not DISPONIVEL:
        return None
    try:
        with pymupdf.open(str(caminho)) as doc:
            if doc.page_count == 0:
                return None
            pagina = doc.load_page(0)
            zoom = largura / pagina.rect.width
            pix = pagina.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom))
            return pix.tobytes("ppm")
    except Exception:
        return None
