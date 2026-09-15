#!/usr/bin/env python3
"""GED Offline — consulta ao acervo digitalizado.

    python main.py                          abre a interface gráfica
    python main.py --buscar <dir> [opções]  busca pela linha de comando
    python main.py --selftest               testes rápidos do parser
"""
from __future__ import annotations

import argparse
import importlib.util
import subprocess
import sys

for _saida in (sys.stdout, sys.stderr):
    if hasattr(_saida, "reconfigure"):
        try:
            _saida.reconfigure(encoding="utf-8")
        except (ValueError, OSError):
            pass

# O PyMuPDF é necessário para ler o texto dos PDFs, contar páginas de arquivos sem índice e gerar a miniatura. Sem ele o programa ainda busca por nome e por índice, então a falha na instalação não é fatal.
DEPENDENCIAS = {("pymupdf", "fitz"): "PyMuPDF"}


def garantir_dependencias() -> None:
    for modulos, pacote in DEPENDENCIAS.items():
        if any(importlib.util.find_spec(nome) is not None for nome in modulos):
            continue
        print(f"[GED Offline] Instalando '{pacote}'...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", pacote])
            print(f"[GED Offline] '{pacote}' instalado.")
        except (subprocess.CalledProcessError, OSError) as exc:
            print(
                f"[GED Offline] Não foi possível instalar '{pacote}' ({exc}).\n"
                "             A busca por nome e por índice continua funcionando; "
                "a busca por conteúdo e a pré-visualização ficam indisponíveis."
            )


def _cli(args: argparse.Namespace) -> None:
    from ged import catalogo as cat
    from ged import conteudo as cont
    from ged import exportador
    from ged.busca import Criterios, buscar
    from ged.texto import formatar_inteiro

    print(f"Lendo {args.buscar} ...")
    catalogo = cat.varrer(args.buscar, incluir_subpastas=not args.sem_subpastas)
    print(
        f"  {formatar_inteiro(catalogo.total_documentos)} documento(s), "
        f"{catalogo.pdfs_encontrados} PDF(s), {catalogo.xmls_lidos} índice(s)"
        + (f", {catalogo.xmls_tolerantes} em modo tolerante" if catalogo.xmls_tolerantes else "")
    )
    print(f"  Campos de índice descobertos: {', '.join(catalogo.vocabulario) or '(nenhum)'}")

    if catalogo.campos_data:
        print(f"  Campos de data reconhecidos: {', '.join(catalogo.campos_data)}")

    grupos = cat.agrupar_por_tipo(catalogo)
    if args.tipo:
        escolhido = next(
            (g for g in grupos if g.rotulo.lower() == args.tipo.lower()), None
        )
        if escolhido is None:
            print(f"\nTipo '{args.tipo}' não encontrado. Disponíveis: "
                  + ", ".join(g.rotulo for g in grupos))
            return
        catalogo = cat.subcatalogo(catalogo, escolhido)
        print(f"  Tipo selecionado: {escolhido.rotulo} ({len(catalogo.vocabulario)} índices)")
    elif len(grupos) > 1:
        print("  Tipos presentes: " + ", ".join(
            f"{g.rotulo} ({g.total_documentos})" for g in grupos
        ) + "  — use --tipo para restringir")

    criterios = Criterios(
        termo=args.termo or "",
        escopo_conteudo=args.conteudo,
        filtros=dict(par.split("=", 1) for par in args.filtro or []),
        indice_de=args.indice_de or "",
        indice_ate=args.indice_ate or "",
        criacao_de=args.criacao_de or "",
        criacao_ate=args.criacao_ate or "",
    )
    cache = cont.CacheConteudo() if args.conteudo else None
    resultado = buscar(catalogo, criterios, cache=cache)

    print(
        f"\nResultado: {formatar_inteiro(resultado.total_documentos)} documento(s), "
        f"{formatar_inteiro(resultado.total_paginas)} página(s)"
    )
    for documento in resultado.documentos[: args.limite]:
        print(f"  - {documento.nome_arquivo}  ({documento.paginas or '?'} pág.)")
    if resultado.total_documentos > args.limite:
        print(f"  ... e mais {resultado.total_documentos - args.limite}")

    if args.csv:
        exportador.exportar_csv(args.csv, catalogo, resultado, criterios)
        print(f"\nCSV salvo em {args.csv}")
    if args.txt:
        exportador.exportar_txt(args.txt, catalogo, resultado, criterios)
        print(f"TXT salvo em {args.txt}")


def main() -> None:
    parser = argparse.ArgumentParser(description="GED Offline")
    parser.add_argument("--buscar", metavar="DIR", help="Busca num diretório e sai, sem abrir a janela.")
    parser.add_argument("--termo", help="Texto livre a procurar.")
    parser.add_argument("--filtro", action="append", metavar="CAMPO=VALOR", help="Filtro por campo de índice (repetível).")
    parser.add_argument("--conteudo", action="store_true", help="Procurar também dentro do texto dos PDFs.")
    parser.add_argument("--tipo", help="Restringir a um tipo de documento (ex.: Despesa).")
    parser.add_argument("--indice-de", help="Início do período sobre a data do índice (2019, 11/2019, 29/11/2019).")
    parser.add_argument("--indice-ate", help="Fim do período sobre a data do índice.")
    parser.add_argument("--criacao-de", help="Início do período sobre a data de criação do arquivo.")
    parser.add_argument("--criacao-ate", help="Fim do período sobre a data de criação do arquivo.")
    parser.add_argument("--sem-subpastas", action="store_true", help="Não descer nas subpastas.")
    parser.add_argument("--csv", metavar="ARQUIVO", help="Exportar o resultado em CSV.")
    parser.add_argument("--txt", metavar="ARQUIVO", help="Exportar o resultado em TXT.")
    parser.add_argument("--limite", type=int, default=10, help="Quantos resultados listar no terminal.")
    parser.add_argument("--selftest", action="store_true", help="Roda os testes rápidos.")
    args = parser.parse_args()

    if args.selftest:
        from tests.selftest import rodar

        rodar()
        return

    garantir_dependencias()

    if args.buscar:
        _cli(args)
        return

    if importlib.util.find_spec("tkinter") is None:
        print(
            "ERRO: o módulo 'tkinter' não está disponível nesta instalação do Python.\n"
            "No Windows, reinstale o Python marcando a opção 'tcl/tk and IDLE'."
        )
        sys.exit(1)

    from ged.gui import executar

    executar()


if __name__ == "__main__":
    main()

