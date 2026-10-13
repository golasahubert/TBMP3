"""Manifest audycji: audycje/<folder>/manifest.json — kolejność, źródła i stan każdej pozycji."""
import json
import os
import re
from pathlib import Path

KATALOG = Path(os.environ.get("TBMP3_DIR", Path(__file__).resolve().parent.parent / "audycje"))
SYGNALY = Path(os.environ.get("TBMP3_SYGNALY", Path(__file__).resolve().parent.parent / "sygnaly"))



def _pulpit_windows():
    """Pulpit Windows widziany z WSL (jedyny prawdziwy profil w /mnt/c/Users)."""
    pomijane = {"Default", "Default User", "Public", "All Users"}
    kandydaci = [p for p in Path("/mnt/c/Users").glob("*/Desktop")
                 if p.parent.name not in pomijane and p.is_dir()]
    return kandydaci[0] if len(kandydaci) == 1 else None


EKSPORT = Path(os.environ["TBMP3_EKSPORT"]) if os.environ.get("TBMP3_EKSPORT") else _pulpit_windows()

SKROTY_CYKLI = {
    "Romantycy Muzyki Rockowej": "RMR",
    "Trójka Pod Księżycem": "TPK",
    "Wieczór Płytowy": "WP",
    "Czas Na Rock": "CNR",
}

# pola ustawiane przez użytkownika/agenta — zachowywane przy odświeżaniu ze strony
POLA_UZYTKOWNIKA = ("plik", "zrodlo", "zapytanie", "pomin", "uwagi")


def bezpieczna_nazwa(tekst, maks=90):
    tekst = re.sub(r'[\\/:*?"<>|]', "", tekst)
    return re.sub(r"\s+", " ", tekst).strip(" .")[:maks]


def skrot_cyklu(cykl):
    if not cykl:
        return "TB"
    return SKROTY_CYKLI.get(cykl) or "".join(w[0] for w in cykl.split() if w[0].isupper()) or "TB"


def nazwa_folderu(dane):
    return bezpieczna_nazwa(f'{dane["data"]} {skrot_cyklu(dane["cykl"])} - {dane["tytul"]}')


def etykieta(poz, szer=2):
    """Numer pozycji: '07' dla pozycji ze strony, '07a' dla dodatkowej wstawionej po 7."""
    if "po" in poz:
        return f'{poz["po"]:0{szer}d}{poz["nr"][-1]}'
    return f'{poz["nr"]:0{szer}d}'


def nazwa_pozycji(poz, szer=2):
    nr = etykieta(poz, szer)
    if poz["typ"] == "utwor" and poz.get("wykonawca") and poz.get("utwor"):
        opis = f'{poz["wykonawca"]} - {poz["utwor"]}'
    else:
        opis = poz["tekst"]
    return bezpieczna_nazwa(f"{nr} {opis}")


class Audycja:
    def __init__(self, folder: Path, dane: dict):
        self.folder = folder
        self.dane = dane

    # ------------------------------------------------------------ wczytywanie
    @classmethod
    def znajdz(cls, audycja_id):
        if KATALOG.exists():
            for m in KATALOG.glob("*/manifest.json"):
                dane = json.loads(m.read_text(encoding="utf-8"))
                if dane.get("id") == int(audycja_id):
                    return cls(m.parent, dane)
        return None

    @classmethod
    def wczytaj(cls, audycja_id):
        a = cls.znajdz(audycja_id)
        if not a:
            raise SystemExit(f"Brak manifestu audycji {audycja_id}. Najpierw: ./tb info {audycja_id}")
        return a

    @classmethod
    def utworz_lub_odswiez(cls, dane_ze_strony):
        istniejaca = cls.znajdz(dane_ze_strony["id"])
        if istniejaca:
            stare = {p["nr"]: p for p in istniejaca.dane["pozycje"]}
            for p in dane_ze_strony["pozycje"]:
                for pole in POLA_UZYTKOWNIKA:
                    if pole in stare.get(p["nr"], {}):
                        p[pole] = stare[p["nr"]][pole]
            dane_ze_strony["ustawienia"] = istniejaca.dane.get("ustawienia", {})
            dane_ze_strony["dodatkowe"] = istniejaca.dane.get("dodatkowe", [])
            a = cls(istniejaca.folder, dane_ze_strony)
        else:
            a = cls(KATALOG / nazwa_folderu(dane_ze_strony), dane_ze_strony)
            a.dane.setdefault("ustawienia", {})
        a.zapisz()
        return a

    def zapisz(self):
        self.folder.mkdir(parents=True, exist_ok=True)
        (self.folder / "manifest.json").write_text(
            json.dumps(self.dane, ensure_ascii=False, indent=2), encoding="utf-8")

    # ------------------------------------------------------------ pomocnicze
    @property
    def oryginaly(self):
        return self.folder / "oryginaly"

    @property
    def przetworzone(self):
        return self.folder / "przetworzone"

    @property
    def szerokosc_nr(self):
        return max(2, len(str(len(self.dane["pozycje"]))))

    def pozycja(self, nr):
        for p in self.kolejnosc():
            if str(p["nr"]) == str(nr):
                return p
        raise SystemExit(f"Audycja {self.dane['id']} nie ma pozycji {nr}")

    def sciezka(self, poz):
        """Ścieżka do pliku pozycji (albo None, jeśli jeszcze go nie ma)."""
        if poz.get("plik"):
            s = self.folder / poz["plik"]
            if s.exists():
                return s
        return None

    def kolejnosc(self):
        """Pozycje do złożenia: ze strony + dodatkowe (np. sygnał przed nr 1), posortowane."""
        wszystkie = list(self.dane["pozycje"]) + list(self.dane.get("dodatkowe", []))
        return sorted(wszystkie, key=lambda p: (p.get("po", p["nr"]), "po" in p, str(p["nr"])))

    def dodaj(self, po, typ, tekst):
        """Wstawia pozycję spoza strony (np. sygnał) po pozycji `po` (0 = na początek)."""
        dodatkowe = self.dane.setdefault("dodatkowe", [])
        zajete = {p["nr"] for p in dodatkowe if p["po"] == po}
        litera = next(c for c in "abcdefghijklmnopqrstuvwxyz" if f"{po}{c}" not in zajete)
        poz = {"nr": f"{po}{litera}", "po": po, "typ": typ, "tekst": tekst}
        dodatkowe.append(poz)
        return poz

    def brakujace(self):
        return [p for p in self.kolejnosc() if not p.get("pomin") and not self.sciezka(p)]
