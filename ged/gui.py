"""Interface gráfica do GED Offline.

O formulário de busca e as colunas da tabela não existem até que um
diretório seja lido: eles são construídos a partir dos campos de índice
que os XML daquela pasta trouxerem. É isso que permite usar a mesma
ferramenta num acervo de despesas, de licitações ou de qualquer outra
natureza sem alterar o programa.

O layout se ajusta à tela disponível. Como o número de campos de índice
varia — uma pasta pode trazer oito, a raiz de um acervo misto pode trazer
vinte — a área de filtros rola dentro de uma altura fixa, para nunca
empurrar a tabela de resultados para fora da janela num notebook.
"""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from . import catalogo as cat
from . import conteudo as cont
from . import exportador
from .busca import Criterios, a_ler_para_conteudo, buscar
from .texto import formatar_inteiro

LARGURA_PREVIA = 230
FILTROS_POR_LINHA = 4
ALTURA_MAX_FILTROS = 116
LIMITE_AVISO_CONTEUDO = 150

CAMPOS_ESTREITOS = ("numero", "num", "ano", "data", "valor", "tipo", "fonte", "paginas")


def abrir_arquivo(caminho: str) -> None:
    try:
        if sys.platform.startswith("win"):
            os.startfile(caminho)  # type: ignore[attr-defined]
        elif sys.platform == "darwin":
            subprocess.run(["open", caminho], check=False)
        else:
            subprocess.run(["xdg-open", caminho], check=False)
    except OSError as exc:
        messagebox.showerror("Erro ao abrir o arquivo", str(exc))


def abrir_pasta_do_arquivo(caminho: str) -> None:
    """Abre o gerenciador de arquivos já com o documento selecionado."""
    alvo = Path(caminho)
    try:
        if sys.platform.startswith("win"):
            # O explorer devolve código 1 mesmo quando funciona, então o
            # resultado não é conferido de propósito.
            subprocess.run(["explorer", f"/select,{alvo}"], check=False)
        elif sys.platform == "darwin":
            subprocess.run(["open", "-R", str(alvo)], check=False)
        else:
            subprocess.run(["xdg-open", str(alvo.parent)], check=False)
    except OSError as exc:
        messagebox.showerror("Erro ao abrir a pasta", str(exc))


class AreaRolavel(ttk.Frame):
    """Contêiner que cresce até uma altura máxima e depois rola.

    Existe para o bloco de filtros: o número de campos depende do acervo,
    e sem um teto ele empurraria a tabela para fora da tela.
    """

    def __init__(self, master, altura_max: int = ALTURA_MAX_FILTROS) -> None:
        super().__init__(master)
        self.altura_max = altura_max
        self.tela = tk.Canvas(self, highlightthickness=0, height=1)
        self.barra = ttk.Scrollbar(self, orient="vertical", command=self.tela.yview)
        self.interno = ttk.Frame(self.tela)
        self._janela = self.tela.create_window((0, 0), window=self.interno, anchor="nw")
        self.tela.configure(yscrollcommand=self.barra.set)
        self.tela.pack(side="left", fill="both", expand=True)
        self.interno.bind("<Configure>", self._ajustar_altura)
        self.tela.bind("<Configure>", self._ajustar_largura)
        self.tela.bind("<Enter>", lambda _e: self._ligar_roda(True))
        self.tela.bind("<Leave>", lambda _e: self._ligar_roda(False))

    def _ajustar_altura(self, _evento=None) -> None:
        self.tela.configure(scrollregion=self.tela.bbox("all"))
        desejada = self.interno.winfo_reqheight()
        self.tela.configure(height=min(desejada, self.altura_max))
        if desejada > self.altura_max:
            self.barra.pack(side="right", fill="y")
        else:
            self.barra.pack_forget()

    def _ajustar_largura(self, evento) -> None:
        self.tela.itemconfigure(self._janela, width=evento.width)

    def _ligar_roda(self, ligar: bool) -> None:
        if ligar:
            self.tela.bind_all("<MouseWheel>", self._rolar)
        else:
            self.tela.unbind_all("<MouseWheel>")

    def _rolar(self, evento) -> None:
        if self.interno.winfo_reqheight() > self.altura_max:
            self.tela.yview_scroll(-1 * (evento.delta // 120), "units")


class DialogoTipo(tk.Toplevel):
    """Escolha do tipo de documento a consultar.

    Uma pasta costuma ter um tipo só, mas apontar para a raiz de um acervo
    mistura despesas com licitações e soma os vocabulários, enchendo a
    busca de campos que não valem para o que se procura. Aqui se escolhe o
    tipo e, com ele, o conjunto de índices.
    """

    def __init__(self, master, grupos: list[cat.GrupoTipo], ativo: str = "") -> None:
        super().__init__(master)
        self.title("Tipo de documento")
        self.resizable(False, False)
        self.escolha: cat.GrupoTipo | None = None
        self._grupos = grupos

        corpo = ttk.Frame(self, padding=14)
        corpo.pack(fill="both", expand=True)

        ttk.Label(
            corpo,
            text="Este diretório tem mais de um tipo de documento.\n"
            "Escolha qual consultar — os campos de busca serão os índices desse tipo.",
            justify="left",
        ).pack(anchor="w", pady=(0, 10))

        self.var_escolha = tk.StringVar(value=ativo or grupos[0].rotulo)

        for grupo in grupos:
            texto = (
                f"{grupo.rotulo}  —  {formatar_inteiro(grupo.total_documentos)} documento(s), "
                f"{formatar_inteiro(grupo.total_paginas)} página(s), "
                f"{len(grupo.vocabulario)} índice(s)"
            )
            ttk.Radiobutton(corpo, text=texto, value=grupo.rotulo, variable=self.var_escolha).pack(
                anchor="w", pady=1
            )
            ttk.Label(
                corpo,
                text="      " + (", ".join(grupo.vocabulario[:8]) or "(sem índices)")
                + ("..." if len(grupo.vocabulario) > 8 else ""),
                foreground="#777",
                font=("", 8),
            ).pack(anchor="w", pady=(0, 6))

        ttk.Separator(corpo).pack(fill="x", pady=6)
        ttk.Radiobutton(
            corpo,
            text="Todos os tipos  —  mostra tudo, com os índices somados",
            value="",
            variable=self.var_escolha,
        ).pack(anchor="w")

        botoes = ttk.Frame(corpo)
        botoes.pack(fill="x", pady=(14, 0))
        ttk.Button(botoes, text="Confirmar", command=self._confirmar).pack(side="right")
        ttk.Button(botoes, text="Cancelar", command=self.destroy).pack(side="right", padx=6)

        self.transient(master)
        self.grab_set()
        self.bind("<Return>", lambda _e: self._confirmar())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.update_idletasks()
        x = master.winfo_rootx() + (master.winfo_width() - self.winfo_width()) // 2
        y = master.winfo_rooty() + 90
        self.geometry(f"+{max(x, 0)}+{max(y, 0)}")

    def _confirmar(self) -> None:
        rotulo = self.var_escolha.get()
        self.escolha = next((g for g in self._grupos if g.rotulo == rotulo), None)
        self.destroy()


class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("GED Offline — consulta ao acervo digitalizado")
        self._dimensionar_para_a_tela()

        self.catalogo_completo: cat.Catalogo | None = None
        self.catalogo: cat.Catalogo | None = None
        self.grupos: list[cat.GrupoTipo] = []
        self.cache = cont.CacheConteudo()
        self.resultado = None
        self.criterios_do_resultado = Criterios()

        self._fila: queue.Queue = queue.Queue()
        self._trabalho: threading.Thread | None = None
        self._cancelar = threading.Event()
        self._filtros: dict[str, tk.StringVar] = {}
        self._linha_para_doc: dict[str, cat.Documento] = {}
        self._imagem_previa = None

        self._montar()

    def _dimensionar_para_a_tela(self) -> None:
        """Abre numa janela que cabe na tela, inclusive em notebook."""
        largura = min(1250, self.winfo_screenwidth() - 60)
        altura = min(720, self.winfo_screenheight() - 110)
        x = max((self.winfo_screenwidth() - largura) // 2, 0)
        y = max((self.winfo_screenheight() - altura) // 3, 0)
        self.geometry(f"{largura}x{altura}+{x}+{y}")
        self.minsize(860, 480)

    # ------------------------------------------------------------ montagem
    def _montar(self) -> None:
        topo = ttk.Frame(self, padding=(8, 6, 8, 2))
        topo.pack(fill="x")

        ttk.Label(topo, text="Diretório:").grid(row=0, column=0, sticky="w")
        self.var_diretorio = tk.StringVar()
        ttk.Entry(topo, textvariable=self.var_diretorio).grid(row=0, column=1, sticky="we", padx=5)
        topo.columnconfigure(1, weight=1)

        ttk.Button(topo, text="Escolher...", command=self._escolher_diretorio).grid(row=0, column=2)

        self.var_subpastas = tk.BooleanVar(value=True)
        ttk.Checkbutton(topo, text="Subpastas", variable=self.var_subpastas).grid(row=0, column=3, padx=(8, 4))

        self.botao_ler = ttk.Button(topo, text="Ler diretório", command=self._iniciar_varredura)
        self.botao_ler.grid(row=0, column=4, padx=2)

        self.botao_tipo = ttk.Button(topo, text="Tipo: —", command=self._escolher_tipo, state="disabled")
        self.botao_tipo.grid(row=0, column=5, padx=2)

        self.botao_cancelar = ttk.Button(topo, text="Cancelar", command=self._pedir_cancelamento, state="disabled")
        self.botao_cancelar.grid(row=0, column=6, padx=2)

        linha_status = ttk.Frame(self, padding=(8, 0))
        linha_status.pack(fill="x")
        self.progresso = ttk.Progressbar(linha_status, mode="determinate", length=170)
        self.progresso.pack(side="left")
        self.var_status = tk.StringVar(value="Escolha um diretório e clique em Ler diretório.")
        ttk.Label(linha_status, textvariable=self.var_status, foreground="#555").pack(
            side="left", padx=8
        )

        # ---------------- busca
        quadro = ttk.LabelFrame(self, text="Busca", padding=(8, 4, 8, 6))
        quadro.pack(fill="x", padx=8, pady=(4, 4))

        linha1 = ttk.Frame(quadro)
        linha1.pack(fill="x")
        ttk.Label(linha1, text="Texto:").pack(side="left")
        self.var_termo = tk.StringVar()
        entrada = ttk.Entry(linha1, textvariable=self.var_termo, width=28)
        entrada.pack(side="left", padx=(4, 10))
        entrada.bind("<Return>", lambda _e: self._buscar())

        self.var_escopo_nome = tk.BooleanVar(value=True)
        self.var_escopo_indice = tk.BooleanVar(value=True)
        self.var_escopo_conteudo = tk.BooleanVar(value=False)
        ttk.Checkbutton(linha1, text="nome", variable=self.var_escopo_nome).pack(side="left")
        ttk.Checkbutton(linha1, text="índice", variable=self.var_escopo_indice).pack(side="left", padx=6)
        ttk.Checkbutton(linha1, text="conteúdo do PDF", variable=self.var_escopo_conteudo).pack(side="left")

        ttk.Button(linha1, text="Buscar", command=self._buscar).pack(side="right")
        ttk.Button(linha1, text="Limpar", command=self._limpar).pack(side="right", padx=5)
        self.botao_precarregar = ttk.Button(
            linha1, text="Ler conteúdo de todos", command=self._precarregar_conteudo, state="disabled"
        )
        self.botao_precarregar.pack(side="right", padx=5)

        linha2 = ttk.Frame(quadro)
        linha2.pack(fill="x", pady=(5, 0))
        self.var_indice_de = tk.StringVar()
        self.var_indice_ate = tk.StringVar()
        self.var_criacao_de = tk.StringVar()
        self.var_criacao_ate = tk.StringVar()
        self._periodo(linha2, "Período do índice:", self.var_indice_de, self.var_indice_ate)
        self.rotulo_campo_data = ttk.Label(linha2, text="", foreground="#777", font=("", 8))
        self.rotulo_campo_data.pack(side="left", padx=(4, 14))
        self._periodo(linha2, "Criação do arquivo:", self.var_criacao_de, self.var_criacao_ate)
        ttk.Label(linha2, text="aceita 2019, 11/2019 ou 29/11/2019", foreground="#777", font=("", 8)).pack(
            side="left", padx=6
        )

        self.area_filtros = AreaRolavel(quadro)
        self.area_filtros.pack(fill="x", pady=(5, 0))
        self.quadro_filtros = self.area_filtros.interno
        ttk.Label(
            self.quadro_filtros,
            text="Os campos de busca aparecem aqui depois que um diretório for lido — "
            "eles vêm dos próprios índices XML da pasta.",
            foreground="#777",
        ).pack(anchor="w")

        # ---------------- resultados
        painel = ttk.PanedWindow(self, orient="horizontal")
        painel.pack(fill="both", expand=True, padx=8)

        quadro_tabela = ttk.Frame(painel)
        painel.add(quadro_tabela, weight=5)

        self.tabela = ttk.Treeview(quadro_tabela, columns=(), show="headings", selectmode="browse")
        vsb = ttk.Scrollbar(quadro_tabela, orient="vertical", command=self.tabela.yview)
        hsb = ttk.Scrollbar(quadro_tabela, orient="horizontal", command=self.tabela.xview)
        self.tabela.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.tabela.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="we")
        quadro_tabela.rowconfigure(0, weight=1)
        quadro_tabela.columnconfigure(0, weight=1)
        self.tabela.bind("<Double-1>", lambda _e: self._abrir_selecionado())
        self.tabela.bind("<<TreeviewSelect>>", lambda _e: self._mostrar_previa())
        self.tabela.bind("<Button-3>", self._menu_de_contexto)
        self.tabela.tag_configure("ausente", foreground="#9B3A34")

        self.menu = tk.Menu(self, tearoff=0)
        self.menu.add_command(label="Abrir PDF", command=self._abrir_selecionado)
        self.menu.add_command(label="Abrir pasta do arquivo", command=self._abrir_pasta_selecionada)

        quadro_previa = ttk.LabelFrame(painel, text="Documento", padding=6)
        painel.add(quadro_previa, weight=1)
        self._imagem_previa = None
        self.rotulo_previa = ttk.Label(
            quadro_previa,
            text="Selecione um documento." if cont.DISPONIVEL else
                 "Pré-visualização indisponível:\nPyMuPDF não instalado.",
            anchor="n",
            justify="center",
            wraplength=LARGURA_PREVIA,
        )
        self.rotulo_previa.pack(fill="both", expand=True)
        ttk.Button(quadro_previa, text="Abrir PDF", command=self._abrir_selecionado).pack(fill="x", pady=(6, 2))
        ttk.Button(quadro_previa, text="Abrir pasta do arquivo", command=self._abrir_pasta_selecionada).pack(fill="x")

        # ---------------- rodapé
        rodape = ttk.Frame(self, padding=(8, 5))
        rodape.pack(fill="x")

        self.var_total_diretorio = tk.StringVar(value="Diretório: —")
        self.var_total_resultado = tk.StringVar(value="Resultado: —")
        self.var_avisos = tk.StringVar(value="")

        ttk.Label(rodape, textvariable=self.var_total_diretorio).grid(row=0, column=0, sticky="w")
        ttk.Label(rodape, textvariable=self.var_total_resultado, font=("", 9, "bold")).grid(
            row=1, column=0, sticky="w"
        )
        ttk.Label(rodape, textvariable=self.var_avisos, foreground="#8F6223", font=("", 8)).grid(
            row=2, column=0, sticky="w"
        )
        rodape.columnconfigure(1, weight=1)

        self.botao_txt = ttk.Button(rodape, text="Exportar TXT", command=self._exportar_txt, state="disabled")
        self.botao_txt.grid(row=0, column=2, rowspan=3, padx=4)
        self.botao_csv = ttk.Button(rodape, text="Exportar CSV", command=self._exportar_csv, state="disabled")
        self.botao_csv.grid(row=0, column=3, rowspan=3)

    @staticmethod
    def _periodo(master, rotulo: str, var_de: tk.StringVar, var_ate: tk.StringVar) -> None:
        ttk.Label(master, text=rotulo).pack(side="left")
        ttk.Entry(master, textvariable=var_de, width=11).pack(side="left", padx=(4, 2))
        ttk.Label(master, text="até").pack(side="left")
        ttk.Entry(master, textvariable=var_ate, width=11).pack(side="left", padx=2)

    # --------------------------------------------------------- diretório
    def _escolher_diretorio(self) -> None:
        escolhido = filedialog.askdirectory(title="Escolha o diretório do acervo")
        if escolhido:
            self.var_diretorio.set(escolhido)
            self._iniciar_varredura()

    def _iniciar_varredura(self) -> None:
        raiz = self.var_diretorio.get().strip()
        if not raiz:
            messagebox.showwarning("GED Offline", "Escolha um diretório primeiro.")
            return
        if not Path(raiz).exists():
            messagebox.showerror("GED Offline", f"Diretório não encontrado:\n{raiz}")
            return
        if self._ocupado():
            return

        self.cache = cont.CacheConteudo()
        self._comecar_trabalho("Lendo o diretório...")
        incluir = self.var_subpastas.get()

        def tarefa() -> None:
            try:
                resultado = cat.varrer(
                    raiz,
                    incluir_subpastas=incluir,
                    progresso=self._fila.put,
                    cancelado=self._cancelar.is_set,
                )
            except Exception as exc:
                self._fila.put(exc)
                return
            self._fila.put(("catalogo", resultado))

        self._rodar(tarefa)

    # ------------------------------------------------------------ tipos
    def _escolher_tipo(self, automatico: bool = False) -> None:
        if not self.grupos:
            return
        ativo = self.catalogo.tipo_ativo if self.catalogo else ""
        dialogo = DialogoTipo(self, self.grupos, ativo)
        self.wait_window(dialogo)
        if dialogo.escolha is None and not automatico:
            return  # cancelou: mantém a visão atual
        self._aplicar_tipo(dialogo.escolha)

    def _aplicar_tipo(self, grupo: cat.GrupoTipo | None) -> None:
        if self.catalogo_completo is None:
            return
        if grupo is None:
            self.catalogo = self.catalogo_completo
            self.botao_tipo.configure(text="Tipo: todos")
        else:
            self.catalogo = cat.subcatalogo(self.catalogo_completo, grupo)
            self.botao_tipo.configure(text=f"Tipo: {grupo.rotulo}")
        self._montar_filtros()
        self._montar_colunas()
        self._buscar()

    # ------------------------------------------------------------ threads
    def _ocupado(self) -> bool:
        if self._trabalho and self._trabalho.is_alive():
            messagebox.showinfo("GED Offline", "Aguarde a operação em andamento terminar.")
            return True
        return False

    def _comecar_trabalho(self, status: str) -> None:
        self._cancelar.clear()
        self.botao_ler.configure(state="disabled")
        self.botao_cancelar.configure(state="normal")
        self.progresso.configure(mode="indeterminate")
        self.progresso.start(12)
        self.var_status.set(status)

    def _terminar_trabalho(self) -> None:
        self.progresso.stop()
        self.progresso.configure(mode="determinate", value=0)
        self.botao_ler.configure(state="normal")
        self.botao_cancelar.configure(state="disabled")

    def _rodar(self, tarefa) -> None:
        self._trabalho = threading.Thread(target=tarefa, daemon=True)
        self._trabalho.start()
        self.after(120, self._drenar_fila)

    def _pedir_cancelamento(self) -> None:
        self._cancelar.set()
        self.var_status.set("Cancelando...")

    def _drenar_fila(self) -> None:
        try:
            while True:
                item = self._fila.get_nowait()
                if isinstance(item, Exception):
                    self._terminar_trabalho()
                    messagebox.showerror("Erro", str(item))
                    self.var_status.set("Falhou.")
                    return
                if isinstance(item, cat.Progresso):
                    if item.total:
                        self.progresso.configure(mode="determinate", maximum=item.total, value=item.atual)
                    self.var_status.set(f"[{item.fase}] {item.mensagem}")
                elif isinstance(item, tuple):
                    self._concluir(item)
                    return
        except queue.Empty:
            pass
        if self._trabalho and self._trabalho.is_alive():
            self.after(120, self._drenar_fila)
        else:
            self._terminar_trabalho()

    def _concluir(self, item: tuple) -> None:
        rotulo, carga = item
        self._terminar_trabalho()
        if rotulo == "catalogo":
            self.catalogo_completo = carga
            self.grupos = cat.agrupar_por_tipo(carga)
            self.botao_tipo.configure(state="normal" if self.grupos else "disabled")
            self.botao_precarregar.configure(state="normal" if cont.DISPONIVEL else "disabled")
            if len(self.grupos) > 1:
                # Mais de um tipo na mesma pasta: perguntar é melhor do que
                # somar vocabulários e encher a busca de campos inúteis.
                self._escolher_tipo(automatico=True)
            else:
                self._aplicar_tipo(self.grupos[0] if self.grupos else None)
            self._contar_paginas_em_segundo_plano()
        elif rotulo == "busca":
            self.resultado = carga
            self._preencher_tabela()
        elif rotulo == "paginas":
            self._atualizar_totais()
            self.var_status.set(f"Contagem de páginas concluída ({carga} documento(s) sem índice).")
        elif rotulo == "precarga":
            self.var_status.set(
                f"Conteúdo lido de {carga} documento(s). As buscas por conteúdo agora são instantâneas."
            )

    # ----------------------------------------------------- campos dinâmicos
    def _montar_filtros(self) -> None:
        for widget in self.quadro_filtros.winfo_children():
            widget.destroy()
        self._filtros.clear()

        campos_data = self.catalogo.campos_data if self.catalogo else []
        self.rotulo_campo_data.configure(
            text=f"({', '.join(campos_data)})" if campos_data else "(nenhum campo de data)"
        )

        if not self.catalogo or not self.catalogo.vocabulario:
            ttk.Label(
                self.quadro_filtros,
                text="Nenhum campo de índice encontrado neste diretório — "
                "a busca por texto e por nome do arquivo continua funcionando.",
                foreground="#777",
            ).pack(anchor="w")
            self.area_filtros._ajustar_altura()
            return

        for i, campo in enumerate(self.catalogo.vocabulario):
            linha, coluna = divmod(i, FILTROS_POR_LINHA)
            celula = ttk.Frame(self.quadro_filtros)
            celula.grid(row=linha, column=coluna, sticky="we", padx=(0, 10), pady=2)
            self.quadro_filtros.columnconfigure(coluna, weight=1)
            marca = " (data)" if campo in campos_data else ""
            ttk.Label(celula, text=campo + marca, font=("", 8)).pack(anchor="w")
            var = tk.StringVar()
            self._filtros[campo] = var
            entrada = ttk.Entry(celula, textvariable=var)
            entrada.pack(fill="x")
            entrada.bind("<Return>", lambda _e: self._buscar())

        self.area_filtros._ajustar_altura()

    def _montar_colunas(self) -> None:
        if not self.catalogo:
            return
        colunas = list(self.catalogo.vocabulario) + ["Páginas", "Arquivo", "Situação"]
        self.tabela.configure(columns=colunas)
        for coluna in colunas:
            self.tabela.heading(coluna, text=coluna)
            self.tabela.column(coluna, width=self._largura(coluna), anchor="w", stretch=False)

    @staticmethod
    def _largura(coluna: str) -> int:
        chave = coluna.lower()
        if chave == "arquivo":
            return 240
        if any(marca in chave for marca in CAMPOS_ESTREITOS):
            return 88
        return 140

    # -------------------------------------------------------------- busca
    def _criterios(self) -> Criterios:
        return Criterios(
            termo=self.var_termo.get(),
            escopo_nome=self.var_escopo_nome.get(),
            escopo_indice=self.var_escopo_indice.get(),
            escopo_conteudo=self.var_escopo_conteudo.get(),
            filtros={campo: var.get() for campo, var in self._filtros.items()},
            indice_de=self.var_indice_de.get(),
            indice_ate=self.var_indice_ate.get(),
            criacao_de=self.var_criacao_de.get(),
            criacao_ate=self.var_criacao_ate.get(),
        )

    def _buscar(self) -> None:
        if not self.catalogo:
            return
        criterios = self._criterios()
        self.criterios_do_resultado = criterios

        if not (criterios.escopo_conteudo and criterios.termo_limpo):
            self.resultado = buscar(self.catalogo, criterios)
            self._preencher_tabela()
            return

        if not cont.DISPONIVEL:
            messagebox.showwarning(
                "Busca por conteúdo indisponível",
                "A leitura do texto dos PDFs exige o pacote PyMuPDF, que não está instalado.\n"
                "A busca foi feita apenas no nome do arquivo e no índice.",
            )
            self.var_escopo_conteudo.set(False)
            self.resultado = buscar(self.catalogo, self._criterios())
            self._preencher_tabela()
            return

        pendentes = a_ler_para_conteudo(self.catalogo, criterios, self.cache)
        if not pendentes:
            # Nada novo a abrir: já está tudo em memória, ou o termo já
            # casou pelo nome e pelo índice. Responde na hora.
            self.resultado = buscar(self.catalogo, criterios, cache=self.cache)
            self._preencher_tabela()
            return

        if len(pendentes) > LIMITE_AVISO_CONTEUDO:
            prosseguir = messagebox.askyesno(
                "Buscar dentro dos PDFs",
                f"Esta busca precisa abrir {formatar_inteiro(len(pendentes))} arquivo(s) ainda não lidos.\n\n"
                "Preencher antes um campo de índice ou um período reduz bastante essa leitura.\n\n"
                "Continuar assim mesmo?",
            )
            if not prosseguir:
                return

        if self._ocupado():
            return
        self._comecar_trabalho("Procurando dentro dos PDFs...")

        def tarefa() -> None:
            def progresso(atual: int, total: int, nome: str) -> None:
                self._fila.put(cat.Progresso("conteúdo", atual, total, nome))

            try:
                resultado = buscar(
                    self.catalogo,
                    criterios,
                    cache=self.cache,
                    progresso=progresso,
                    cancelado=self._cancelar.is_set,
                )
            except Exception as exc:
                self._fila.put(exc)
                return
            self._fila.put(("busca", resultado))

        self._rodar(tarefa)

    def _precarregar_conteudo(self) -> None:
        if not self.catalogo or self._ocupado():
            return
        if not cont.DISPONIVEL:
            messagebox.showwarning("Indisponível", "O pacote PyMuPDF não está instalado.")
            return
        documentos = [d for d in self.catalogo.documentos if d.localizado]
        self._comecar_trabalho(f"Lendo o conteúdo de {formatar_inteiro(len(documentos))} PDF(s)...")

        def tarefa() -> None:
            lidos = 0
            for i, documento in enumerate(documentos):
                if self._cancelar.is_set():
                    break
                self._fila.put(cat.Progresso("conteúdo", i, len(documentos), documento.nome_arquivo))
                self.cache.texto(documento.caminho)
                if documento.paginas is None:
                    documento.paginas = self.cache.paginas(documento.caminho)
                lidos += 1
            self._fila.put(("precarga", lidos))

        self._rodar(tarefa)

    def _contar_paginas_em_segundo_plano(self) -> None:
        if not self.catalogo_completo or not cont.DISPONIVEL:
            return
        faltantes = [d for d in self.catalogo_completo.documentos if d.paginas is None and d.localizado]
        if not faltantes:
            return
        self.var_status.set(f"Contando páginas de {formatar_inteiro(len(faltantes))} PDF(s) sem índice...")

        def tarefa() -> None:
            contados = cat.contar_paginas_faltantes(
                self.catalogo_completo, self.cache, cancelado=self._cancelar.is_set
            )
            self._fila.put(("paginas", contados))

        self._rodar(tarefa)

    def _limpar(self) -> None:
        self.var_termo.set("")
        for var in self._filtros.values():
            var.set("")
        for var in (self.var_indice_de, self.var_indice_ate, self.var_criacao_de, self.var_criacao_ate):
            var.set("")
        self._buscar()

    # ----------------------------------------------------------- tabela
    def _preencher_tabela(self) -> None:
        self.tabela.delete(*self.tabela.get_children())
        self._linha_para_doc.clear()
        if not self.catalogo or self.resultado is None:
            return

        for documento in self.resultado.documentos:
            valores = [documento.valor(c) for c in self.catalogo.vocabulario]
            valores.append(documento.paginas if documento.paginas is not None else "?")
            valores.append(documento.nome_arquivo)
            valores.append("ok" if documento.localizado else "sem PDF")
            linha = self.tabela.insert(
                "", "end", values=valores, tags=() if documento.localizado else ("ausente",)
            )
            self._linha_para_doc[linha] = documento

        self._atualizar_totais()
        estado = "normal" if self.resultado.documentos else "disabled"
        self.botao_txt.configure(state=estado)
        self.botao_csv.configure(state=estado)
        self.var_status.set("Busca concluída.")

    def _atualizar_totais(self) -> None:
        if not self.catalogo:
            return
        c = self.catalogo
        escopo = f"Tipo {c.tipo_ativo}" if c.tipo_ativo else "Diretório"
        self.var_total_diretorio.set(
            f"{escopo}: {formatar_inteiro(c.total_documentos)} documentos · "
            f"{formatar_inteiro(c.total_paginas)} páginas"
            + (f" (+{c.paginas_desconhecidas} não contados)" if c.paginas_desconhecidas else "")
        )
        if self.resultado is None:
            return
        r = self.resultado
        self.var_total_resultado.set(
            f"Resultado: {formatar_inteiro(r.total_documentos)} documentos · "
            f"{formatar_inteiro(r.total_paginas)} páginas"
            + (f" (+{r.paginas_desconhecidas} não contados)" if r.paginas_desconhecidas else "")
        )

        avisos = []
        if r.sem_pdf:
            avisos.append(f"{r.sem_pdf} do índice sem PDF localizado")
        if c.xmls_tolerantes:
            avisos.append(f"{c.xmls_tolerantes} XML lido em modo tolerante")
        if r.conteudo_usado and r.sem_texto:
            avisos.append(f"{r.sem_texto} PDF sem camada de texto")
        if r.conteudo_usado and r.nao_verificados:
            avisos.append(f"{r.nao_verificados} não verificados (sem PDF no diretório)")
        if r.cancelado:
            avisos.append("busca interrompida — resultado parcial")
        self.var_avisos.set(" · ".join(avisos))

    # ---------------------------------------------------------- documento
    def _selecionado(self) -> cat.Documento | None:
        selecao = self.tabela.selection()
        return self._linha_para_doc.get(selecao[0]) if selecao else None

    def _menu_de_contexto(self, evento) -> None:
        linha = self.tabela.identify_row(evento.y)
        if not linha:
            return
        self.tabela.selection_set(linha)
        self.menu.tk_popup(evento.x_root, evento.y_root)

    def _sem_pdf(self) -> None:
        messagebox.showwarning(
            "PDF não localizado",
            "Este registro veio de um índice XML, mas o PDF correspondente "
            "não está no diretório lido.",
        )

    def _abrir_selecionado(self) -> None:
        documento = self._selecionado()
        if not documento:
            return
        if not documento.localizado:
            self._sem_pdf()
            return
        abrir_arquivo(str(documento.caminho))

    def _abrir_pasta_selecionada(self) -> None:
        documento = self._selecionado()
        if not documento:
            return
        if not documento.localizado:
            self._sem_pdf()
            return
        abrir_pasta_do_arquivo(str(documento.caminho))

    def _mostrar_previa(self) -> None:
        documento = self._selecionado()
        if not documento or not cont.DISPONIVEL:
            return
        if not documento.localizado:
            self._imagem_previa = None
            self.rotulo_previa.configure(image="", text="(sem PDF para pré-visualizar)")
            return
        dados = cont.primeira_pagina_png(documento.caminho, LARGURA_PREVIA)
        if not dados:
            self._imagem_previa = None
            self.rotulo_previa.configure(image="", text="(não foi possível abrir este PDF)")
            return
        imagem = tk.PhotoImage(data=dados)
        self._imagem_previa = imagem
        self.rotulo_previa.configure(image=imagem, text="")

    # -------------------------------------------------------- exportação
    def _exportar_txt(self) -> None:
        self._exportar(exportador.exportar_txt, ".txt", [("Texto", "*.txt")])

    def _exportar_csv(self) -> None:
        self._exportar(exportador.exportar_csv, ".csv", [("CSV", "*.csv")])

    def _exportar(self, funcao, extensao: str, tipos) -> None:
        if not self.catalogo or self.resultado is None or not self.resultado.documentos:
            return
        destino = filedialog.asksaveasfilename(
            title="Salvar relatório",
            defaultextension=extensao,
            filetypes=tipos,
            initialfile=f"busca_ged{extensao}",
        )
        if not destino:
            return
        try:
            funcao(destino, self.catalogo, self.resultado, self.criterios_do_resultado)
        except OSError as exc:
            messagebox.showerror("Erro ao salvar", str(exc))
            return
        self.var_status.set(f"Relatório salvo em {destino}")
        if messagebox.askyesno("Relatório salvo", f"Salvo em:\n{destino}\n\nAbrir agora?"):
            abrir_arquivo(destino)


def executar() -> None:
    App().mainloop()
