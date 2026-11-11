"""CV Booster window: a program SEPARATE from the server.

Why two programs: pywebview (the window, running on .NET) and the server used to share the same
Python process and its single lock (the GIL). Under load (page loading), they would sometimes wait
on each other: everything froze (« Ne répond pas », 2 to 3 launches out of 10, measured on 05/11).
Separated, they can no longer block each other. This program only: shows the page, paints the title
bar, and tells the server when the window closes. Everything else is in serveur.py.
"""

import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent
# Development copy (no version.json, written by the installer build): said in the window title
TITRE = "CV Booster" if (APP / "version.json").is_file() else "CV Booster · développement"
TRAVAIL = Path(os.environ.get("CVB_DONNEES") or APP.parent) / ".cv-booster"  # data: see lancer.pyw

COULEURS_BARRE = {  # (bar background, text, border): same shades as the interface sidebar
    True: ("#151615", "#E8E8E5", "#2E302E"),   # dark theme
    False: ("#F2F1ED", "#1F2421", "#E2E0D9"),  # light theme
}


def journal(evenement: str) -> None:
    """Timestamped step log, tests only (CVB_JOURNAL=1)."""
    if os.environ.get("CVB_JOURNAL"):
        with open(TRAVAIL / "journal-fenetre.txt", "a", encoding="utf-8") as f:
            f.write(f"{time.time():.2f} fenetre {evenement}\n")


def sortie_immediate() -> None:
    """Exit without waiting for .NET/WebView2 to unload (os._exit can hang for 2 s or more)."""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE            # declared types: otherwise the call fails
        k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k32.TerminateProcess(k32.GetCurrentProcess(), 0)
    finally:
        os._exit(0)


def peindre_barre(hwnd: int, sombre: bool) -> None:
    """Native title bar colors (Windows 11; no effect, and no error, on Windows 10)."""
    try:
        import ctypes
        from ctypes import wintypes
        dwm = ctypes.windll.dwmapi

        def regler(attribut: int, valeur: int) -> None:
            v = wintypes.DWORD(valeur)
            dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), attribut, ctypes.byref(v), ctypes.sizeof(v))

        def colorref(hexa: str) -> int:  # "#RRGGBB" → 0x00BBGGRR
            r, g, b = int(hexa[1:3], 16), int(hexa[3:5], 16), int(hexa[5:7], 16)
            return b << 16 | g << 8 | r

        fond, texte, bord = COULEURS_BARRE[sombre]
        regler(20, int(sombre))       # DWMWA_USE_IMMERSIVE_DARK_MODE
        regler(35, colorref(fond))    # DWMWA_CAPTION_COLOR
        regler(36, colorref(texte))   # DWMWA_TEXT_COLOR
        regler(34, colorref(bord))    # DWMWA_BORDER_COLOR
    except Exception:  # noqa: BLE001 - purely cosmetic
        pass


def trouver_hwnd(titre: str = TITRE, essais: int = 50) -> int:
    """The window of THIS process with this title, found via Windows."""
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.windll.user32
    pid = os.getpid()
    for _ in range(essais):
        trouvee = []

        @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
        def visiter(hwnd, _):
            p = wintypes.DWORD()
            u32.GetWindowThreadProcessId(hwnd, ctypes.byref(p))
            if p.value == pid and u32.IsWindowVisible(hwnd):
                tampon = ctypes.create_unicode_buffer(256)
                u32.GetWindowTextW(hwnd, tampon, 256)
                if tampon.value == titre:
                    trouvee.append(hwnd)
            return True

        u32.EnumWindows(visiter, 0)
        if trouvee:
            return trouvee[0]
        time.sleep(0.1)
    return 0


class Api:
    """Methods called by the page (window.pywebview.api.*)."""

    def __init__(self, adresse: str):
        self.adresse = adresse
        self.hwnd = 0

    def theme(self, sombre):
        """The page switches theme → the title bar follows, and the choice is saved for the next launch."""
        if self.hwnd:
            peindre_barre(self.hwnd, bool(sombre))
        try:
            (TRAVAIL / "theme.txt").write_text("sombre" if sombre else "clair", encoding="utf-8")
        except OSError:
            pass

    def _dialogue(self, sorte: str, **options):
        """Windows file dialog (Save As / Open). Returns a path, or "" if cancelled."""
        import webview
        genre = getattr(getattr(webview, "FileDialog", None), sorte, None) or \
            getattr(webview, f"{sorte}_DIALOG")  # newer / older pywebview
        res = webview.windows[0].create_file_dialog(genre, file_types=("Sauvegarde CV Booster (*.zip)",), **options)
        if isinstance(res, (list, tuple)):
            res = res[0] if res else ""
        return str(res or "")

    def choisir_enregistrement(self, nom):
        """« Sauvegarder mes données »: where to save the file (USB drive, OneDrive…)."""
        return self._dialogue("SAVE", save_filename=nom, directory=str(Path.home() / "Documents"))

    def premier_plan(self):
        """Just before the server opens Explorer, Word or a PDF: this window is in the foreground (she just clicked),
        so it lets Windows hand the foreground over. Otherwise the new window only flashes in the taskbar."""
        try:
            import ctypes
            ctypes.windll.user32.AllowSetForegroundWindow(-1)  # ASFW_ANY
        except Exception:  # noqa: BLE001 - cosmetic: at worst, the window appears behind
            pass
        return True

    def choisir_sauvegarde(self):
        """« Restaurer une sauvegarde »: the .zip file to restore."""
        return self._dialogue("OPEN", directory=str(Path.home() / "Documents"))

    def fermer(self):
        """The page's « Fermer » button, or the window's close box: tell the server, then exit."""
        journal("fermer")
        try:
            urllib.request.urlopen(urllib.request.Request(self.adresse + "/api/quitter", data=b"", method="POST"),
                                   timeout=1.5)
        except Exception:  # noqa: BLE001 - server already stopped: nothing to do
            pass
        sortie_immediate()


def preparer(api: Api, sombre: bool) -> None:
    """As soon as the window exists: CV Booster icon (window + taskbar) and repainted title bar.
    Only Windows calls that don't wait on anything."""
    try:
        import ctypes
        u32 = ctypes.windll.user32
        api.hwnd = trouver_hwnd()
        journal(f"préparée hwnd={api.hwnd}")
        if not api.hwnd:
            return
        peindre_barre(api.hwnd, sombre)
        ico = str(APP / "icone.ico")
        for type_icone, taille in ((1, 32), (0, 16)):  # ICON_BIG, ICON_SMALL
            h = u32.LoadImageW(None, ico, 1, taille, taille, 0x0010)  # IMAGE_ICON, LR_LOADFROMFILE
            if h:
                u32.PostMessageW(api.hwnd, 0x0080, type_icone, h)  # WM_SETICON, without waiting
    except Exception:  # noqa: BLE001 - purely cosmetic
        pass


def fenetre_edge(adresse: str) -> None:
    """Fallback without pywebview: the interface in an Edge window in app mode."""
    import subprocess
    import webbrowser
    for base in (os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"), os.environ.get("ProgramFiles", "")):
        edge = Path(base) / "Microsoft/Edge/Application/msedge.exe"
        if edge.is_file():
            subprocess.Popen([str(edge), f"--app={adresse}", "--window-size=1040,900"],
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            return
    webbrowser.open(adresse)


def ouvrir(adresse: str) -> None:
    sys.path.insert(0, str(APP / "lib"))
    try:
        import webview
    except Exception:  # noqa: BLE001 - pywebview missing or broken
        fenetre_edge(adresse)
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CVBooster.App")  # own icon (taskbar)
    except Exception:  # noqa: BLE001
        pass
    # Light theme by default; otherwise the last one picked in the app (saved by Api.theme), so the title
    # bar has the right color from the start, before the page has even loaded.
    try:
        sombre = (TRAVAIL / "theme.txt").read_text(encoding="utf-8").strip() == "sombre"
    except OSError:
        sombre = False
    api = Api(adresse)
    url = f"{adresse}/?fenetre=native"
    if os.environ.get("CVB_TEST_FERMER"):  # tests: the page clicks « Fermer » itself after N seconds
        url += f"&test-fermer={os.environ['CVB_TEST_FERMER']}"
    if os.environ.get("CVB_PAGE"):  # tests: open a screen directly (e.g. "vue=cv")
        url += f"&{os.environ['CVB_PAGE']}"
    try:
        fenetre = webview.create_window(TITRE, url, js_api=api, width=1120, height=880, min_size=(760, 560),
                                        text_select=True, background_color=COULEURS_BARRE[sombre][0])
        fenetre.events.shown += lambda: (journal("shown"), preparer(api, sombre))
        fenetre.events.loaded += lambda: journal("page chargée")
        fenetre.events.closing += lambda: threading.Thread(target=api.fermer, daemon=True).start()  # the close box
        TRAVAIL.mkdir(parents=True, exist_ok=True)
        webview.start(private_mode=False, storage_path=str(TRAVAIL / "fenetre"))  # keeps the chosen theme
    except Exception:  # noqa: BLE001 - WebView2 missing, etc.
        fenetre_edge(adresse)
        return
    api.fermer()  # window closed some other way: tell the server and exit
