"""Fenêtre de CV Booster : un programme À PART du serveur.

Pourquoi deux programmes : pywebview (la fenêtre, qui tourne sur .NET) et le serveur partageaient le même
processus Python et son verrou unique (le GIL). Sous charge (chargement de la page), ils s'attendaient
parfois mutuellement : tout se figeait (« Ne répond pas », 2 à 3 démarrages sur 10, mesuré le 05/11).
Séparés, ils ne peuvent plus se bloquer. Ce programme ne fait que : afficher la page, peindre la barre de
titre, et prévenir le serveur quand on ferme. Tout le reste est dans serveur.py.
"""

import os
import sys
import threading
import time
import urllib.request
from pathlib import Path

APP = Path(__file__).resolve().parent
TRAVAIL = Path(os.environ.get("CVB_DONNEES") or APP.parent) / ".cv-booster"  # données : voir lancer.pyw

COULEURS_BARRE = {  # (fond de la barre, texte, bordure) — mêmes teintes que la barre latérale de l'interface
    True: ("#151615", "#E8E8E5", "#2E302E"),   # thème sombre
    False: ("#F2F1ED", "#1F2421", "#E2E0D9"),  # thème clair
}


def journal(evenement: str) -> None:
    """Journal horodaté des étapes, seulement en test (CVB_JOURNAL=1)."""
    if os.environ.get("CVB_JOURNAL"):
        with open(TRAVAIL / "journal-fenetre.txt", "a", encoding="utf-8") as f:
            f.write(f"{time.time():.2f} fenetre {evenement}\n")


def sortie_immediate() -> None:
    """Fin du programme sans attendre le déchargement de .NET/WebView2 (os._exit peut bloquer 2 s ou plus)."""
    try:
        import ctypes
        from ctypes import wintypes
        k32 = ctypes.windll.kernel32
        k32.GetCurrentProcess.restype = wintypes.HANDLE            # types déclarés : sinon l'appel échoue
        k32.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        k32.TerminateProcess(k32.GetCurrentProcess(), 0)
    finally:
        os._exit(0)


def peindre_barre(hwnd: int, sombre: bool) -> None:
    """Couleurs de la barre de titre native (Windows 11 ; sans effet, sans erreur, sur Windows 10)."""
    try:
        import ctypes
        from ctypes import wintypes
        dwm = ctypes.windll.dwmapi

        def regler(attribut: int, valeur: int) -> None:
            v = wintypes.DWORD(valeur)
            dwm.DwmSetWindowAttribute(wintypes.HWND(hwnd), attribut, ctypes.byref(v), ctypes.sizeof(v))

        def colorref(hexa: str) -> int:  # « #RRGGBB » → 0x00BBGGRR
            r, g, b = int(hexa[1:3], 16), int(hexa[3:5], 16), int(hexa[5:7], 16)
            return b << 16 | g << 8 | r

        fond, texte, bord = COULEURS_BARRE[sombre]
        regler(20, int(sombre))       # DWMWA_USE_IMMERSIVE_DARK_MODE
        regler(35, colorref(fond))    # DWMWA_CAPTION_COLOR
        regler(36, colorref(texte))   # DWMWA_TEXT_COLOR
        regler(34, colorref(bord))    # DWMWA_BORDER_COLOR
    except Exception:  # noqa: BLE001 - purement cosmétique
        pass


def trouver_hwnd(titre: str = "CV Booster", essais: int = 50) -> int:
    """La fenêtre de CE processus portant ce titre, trouvée via Windows."""
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
    """Méthodes appelées par la page (window.pywebview.api.*)."""

    def __init__(self, adresse: str):
        self.adresse = adresse
        self.hwnd = 0

    def theme(self, sombre):
        """La page change de thème → la barre de titre suit, et le choix est retenu pour le prochain lancement."""
        if self.hwnd:
            peindre_barre(self.hwnd, bool(sombre))
        try:
            (TRAVAIL / "theme.txt").write_text("sombre" if sombre else "clair", encoding="utf-8")
        except OSError:
            pass

    def fermer(self):
        """Bouton « Fermer » de la page, ou croix de la fenêtre : on prévient le serveur, puis on sort."""
        journal("fermer")
        try:
            urllib.request.urlopen(urllib.request.Request(self.adresse + "/api/quitter", data=b"", method="POST"),
                                   timeout=1.5)
        except Exception:  # noqa: BLE001 - serveur déjà arrêté : rien à faire
            pass
        sortie_immediate()


def preparer(api: Api, sombre: bool) -> None:
    """Dès que la fenêtre existe : icône CV Booster (fenêtre + barre des tâches) et barre de titre repeinte.
    Uniquement des appels Windows qui n'attendent personne."""
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
                u32.PostMessageW(api.hwnd, 0x0080, type_icone, h)  # WM_SETICON, sans attendre
    except Exception:  # noqa: BLE001 - purement cosmétique
        pass


def fenetre_edge(adresse: str) -> None:
    """Repli sans pywebview : l'interface dans une fenêtre Edge en mode application."""
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
    except Exception:  # noqa: BLE001 - pywebview absent ou cassé
        fenetre_edge(adresse)
        return
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("CVBooster.App")  # icône propre (barre des tâches)
    except Exception:  # noqa: BLE001
        pass
    # Thème clair par défaut ; sinon le dernier choisi dans l'appli (noté par Api.theme), pour que la barre
    # de titre ait d'emblée la bonne couleur, avant même que la page soit chargée.
    try:
        sombre = (TRAVAIL / "theme.txt").read_text(encoding="utf-8").strip() == "sombre"
    except OSError:
        sombre = False
    api = Api(adresse)
    url = f"{adresse}/?fenetre=native"
    if os.environ.get("CVB_TEST_FERMER"):  # tests : la page clique elle-même sur « Fermer » après N secondes
        url += f"&test-fermer={os.environ['CVB_TEST_FERMER']}"
    if os.environ.get("CVB_PAGE"):  # tests : ouvrir directement un écran (ex. « vue=cv »)
        url += f"&{os.environ['CVB_PAGE']}"
    try:
        fenetre = webview.create_window("CV Booster", url, js_api=api, width=1120, height=880, min_size=(760, 560),
                                        text_select=True, background_color=COULEURS_BARRE[sombre][0])
        fenetre.events.shown += lambda: (journal("shown"), preparer(api, sombre))
        fenetre.events.loaded += lambda: journal("page chargée")
        fenetre.events.closing += lambda: threading.Thread(target=api.fermer, daemon=True).start()  # la croix
        TRAVAIL.mkdir(parents=True, exist_ok=True)
        webview.start(private_mode=False, storage_path=str(TRAVAIL / "fenetre"))  # garde le thème choisi
    except Exception:  # noqa: BLE001 - WebView2 absent, etc.
        fenetre_edge(adresse)
        return
    api.fermer()  # fenêtre fermée autrement : on prévient le serveur et on sort
