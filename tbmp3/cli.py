"""Wiersz poleceń: ./tb <komenda> ...  (pomoc: ./tb -h, ./tb <komenda> -h)"""
import argparse
import shutil
import sys

from . import audio, pobieranie, scraper
from .manifest import EKSPORT, Audycja, etykieta

IKONY = {"utwor": "♪", "komentarz": "🎙", "sygnal": "📻"}


def _czas(s):
    return f"{int(s) // 60}:{int(s) % 60:02d}" if s else "?"


# ------------------------------------------------------------------ komendy

def k_lista(arg):
    wynik = scraper.lista_audycji(arg.cykl, arg.rok)
    if not arg.cykl:
        print("Cykle:", ", ".join(f"{n}={nazwa}" for n, nazwa in sorted(wynik["cykle"].items())))
    print(f'Cykl: {wynik["cykle"].get(wynik["cykl"], wynik["cykl"])}   rok: {wynik["rok"]}   '
          f'lata: {" ".join(map(str, wynik["lata"]))}')
    print("dostępność: M = cała audycja na Mixcloud, K = komentarze mp3, - = tylko opis\n")
    znak = {"mixcloud": "M", "komentarze": "K", "brak": "-"}
    for au in wynik["audycje"]:
        if arg.szukaj and arg.szukaj.lower() not in au["tytul"].lower():
            continue
        if arg.dostepne and au["dostepnosc"] == "brak":
            continue
        lokalnie = " [jest lokalnie]" if Audycja.znajdz(au["id"]) else ""
        print(f'{au["id"]:>5}  {au["data"]}  {znak[au["dostepnosc"]]}  {au["tytul"]}{lokalnie}')


def _tabela(a):
    szer = a.szerokosc_nr
    for p in a.kolejnosc():
        if p.get("pomin"):
            stan = "pominięta"
        elif a.sciezka(p):
            zr = p.get("zrodlo")
            stan = "✓ " + (f'{zr.get("tytul")} [{_czas(zr.get("czas"))}]' if isinstance(zr, dict) else "plik")
        elif p["typ"] == "komentarz" and p.get("mp3"):
            stan = "do pobrania z tbmp3"
        elif p["typ"] == "komentarz":
            stan = "BRAK PLIKU na stronie"
        elif p["typ"] == "sygnal":
            stan = "czeka na sygnał"
        else:
            stan = f'szukaj: {p.get("zapytanie")}'
        tekst = audio.tytul_rozdzialu(p)
        if p.get("uwagi"):
            tekst += f'  ({p["uwagi"]})'
        print(f'{etykieta(p, szer):>4} {IKONY.get(p["typ"], "?")} {tekst[:70]:<70} {stan}')


def _podsumowanie(a):
    poz = [p for p in a.kolejnosc() if not p.get("pomin")]
    gotowe = [p for p in poz if a.sciezka(p)]
    print(f"\nGotowe {len(gotowe)}/{len(poz)} pozycji.")
    for typ, nazwa in (("komentarz", "komentarze"), ("utwor", "utwory"), ("sygnal", "sygnały")):
        brak = [etykieta(p) for p in poz if p["typ"] == typ and not a.sciezka(p)]
        if brak:
            print(f"  brakuje ({nazwa}): {', '.join(brak)}")
    if a.dane.get("mixcloud"):
        print(f'  Mixcloud: {a.dane["mixcloud"]}'
              + (f' (pobrane: {a.dane["mixcloud_plik"]})' if a.dane.get("mixcloud_plik") else ""))


def k_info(arg):
    dane = scraper.audycja(arg.id)
    a = Audycja.utworz_lub_odswiez(dane)
    d = a.dane
    print(f'{d["tytul"]}\n{d["cykl"]} — {d["data"]}   (id {d["id"]})\n{d["url"]}')
    if d.get("komentarz"):
        print(f'Opis: {d["komentarz"][:300]}')
    if d.get("plyty"):
        print("Płyty: " + "; ".join(d["plyty"]))
    print(f"Folder: {a.folder}\n")
    _tabela(a)
    _podsumowanie(a)


def k_status(arg):
    a = Audycja.wczytaj(arg.id)
    print(f'{a.dane["tytul"]} — {a.dane["data"]}\nFolder: {a.folder}\n')
    _tabela(a)
    _podsumowanie(a)


def k_komentarze(arg):
    a = Audycja.wczytaj(arg.id)
    pobrane, bylo, bledy = pobieranie.komentarze(a, arg.nr)
    print(f"Pobrano {len(pobrane)}, już były {len(bylo)}, błędy {len(bledy)}.")
    for nr, e in bledy:
        print(f"  ✗ {nr}: {e}")
    bez_pliku = [str(p["nr"]) for p in a.dane["pozycje"] if p["typ"] == "komentarz" and not p.get("mp3")]
    if bez_pliku:
        print(f"Komentarze bez pliku na stronie: {', '.join(bez_pliku)}")


def k_szukaj(arg):
    a = Audycja.wczytaj(arg.id)
    p = a.pozycja(arg.nr)
    zapytanie = arg.zapytanie or p.get("zapytanie") or p["tekst"]
    print(f'Pozycja {etykieta(p)}: {p["tekst"]}\nZapytanie: {zapytanie}\n')
    for i, w in enumerate(pobieranie.szukaj(zapytanie, arg.ile), 1):
        print(f'{i}. [{_czas(w["czas"])}] {w["tytul"]}  — {w["kanal"]}\n   {w["url"]}')


def k_utwor(arg):
    a = Audycja.wczytaj(arg.id)
    p = a.pozycja(arg.nr)
    sciezka = pobieranie.utwor(a, p, arg.url)
    zr = p["zrodlo"]
    print(f'✓ {etykieta(p)} → {sciezka.name}  ({zr["tytul"]}, {_czas(zr["czas"])})')


def _wybierz_automatycznie(p, kandydaci):
    """Prosta heurystyka: rozsądna długość, wykonawca w tytule, bez live/cover/reaction."""
    wyk = (p.get("wykonawca") or "").lower()
    zle = ("live", "cover", "reaction", "karaoke", "lyrics video", "full album", "remix")

    def ocena(w):
        t = (w["tytul"] or "").lower()
        o = 0
        o += 3 if wyk and wyk in t else 0
        o += 2 if p.get("utwor") and p["utwor"].lower() in t else 0
        o -= 3 if any(z in t for z in zle) and not any(z in p["tekst"].lower() for z in zle) else 0
        o -= 5 if w["czas"] and (w["czas"] < 40 or w["czas"] > 20 * 60) else 0
        o += 1 if w["kanal"] and (w["kanal"].endswith("- Topic") or wyk in w["kanal"].lower()) else 0
        return o

    return max(kandydaci, key=ocena) if kandydaci else None


def k_utwory(arg):
    """Pobiera wszystkie brakujące utwory automatycznie (pierwszy sensowny wynik)."""
    a = Audycja.wczytaj(arg.id)
    brak = [p for p in a.kolejnosc() if p["typ"] == "utwor" and not p.get("pomin") and not a.sciezka(p)]
    print(f"Do pobrania: {len(brak)} utworów")
    for p in brak:
        try:
            w = _wybierz_automatycznie(p, pobieranie.szukaj(p.get("zapytanie") or p["tekst"], 5))
            if not w:
                print(f'  ✗ {etykieta(p)} brak wyników: {p.get("zapytanie")}')
                continue
            pobieranie.utwor(a, p, w["url"])
            print(f'  ✓ {etykieta(p)} {audio.tytul_rozdzialu(p)[:45]:<45} ← {w["tytul"]} [{_czas(w["czas"])}]')
        except Exception as e:  # noqa: BLE001
            print(f'  ✗ {etykieta(p)} {e}')


def k_ustaw(arg):
    a = Audycja.wczytaj(arg.id)
    p = a.pozycja(arg.nr)
    if arg.zapytanie is not None:
        p["zapytanie"] = arg.zapytanie
    if arg.pomin is not None:
        p["pomin"] = arg.pomin
    if arg.uwagi is not None:
        p["uwagi"] = arg.uwagi
    if arg.typ is not None:
        p["typ"] = arg.typ
    a.zapisz()
    print(f'{etykieta(p)}: typ={p["typ"]} pomin={p.get("pomin", False)} '
          f'zapytanie={p.get("zapytanie")!r} uwagi={p.get("uwagi")!r}')


def k_dodaj(arg):
    a = Audycja.wczytaj(arg.id)
    p = a.dodaj(arg.po, arg.typ, arg.tekst)
    a.zapisz()
    print(f'Dodano pozycję {p["nr"]} ({arg.typ}: {arg.tekst}) po pozycji {arg.po}.')
    if arg.plik:
        print(f"  plik: {pobieranie.przypisz_plik(a, p, arg.plik).name}")


def k_plik(arg):
    a = Audycja.wczytaj(arg.id)
    p = a.pozycja(arg.nr)
    print(f"✓ {etykieta(p)} ← {pobieranie.przypisz_plik(a, p, arg.plik).name}")


def k_sygnaly(arg):
    pliki = pobieranie.biblioteka_sygnalow()
    if not pliki:
        print(f"Biblioteka sygnałów jest pusta. Wrzuć pliki do: {pobieranie.SYGNALY}")
    for f in pliki:
        print(f"  {f.name}  [{_czas(audio.czas_trwania(f))}]")


def k_mixcloud(arg):
    a = Audycja.wczytaj(arg.id)
    sciezka, czas = pobieranie.mixcloud(a)
    print(f"✓ {sciezka}  [{_czas(czas)}]")


def _opcje(a, arg):
    opcje = dict(audio.DOMYSLNE)
    opcje.update(a.dane.get("ustawienia", {}))
    for k in audio.DOMYSLNE:
        v = getattr(arg, k, None)
        if v is not None:
            opcje[k] = v
    return opcje


def k_opcje(arg):
    a = Audycja.wczytaj(arg.id)
    opcje = _opcje(a, arg)
    a.dane["ustawienia"] = {k: v for k, v in opcje.items() if v != audio.DOMYSLNE[k]}
    a.zapisz()
    for k, v in opcje.items():
        print(f"  {k} = {v}")


def k_zloz(arg):
    a = Audycja.wczytaj(arg.id)
    opcje = _opcje(a, arg)
    brak = a.brakujace()
    if brak and not arg.pomin_brakujace:
        print("Brakuje plików dla pozycji: " + ", ".join(etykieta(p) for p in brak))
        print("Uzupełnij je, oznacz `./tb ustaw ID NR --pomin`, albo złóż z --pomin-brakujace.")
        sys.exit(1)
    okladka = pobieranie.okladka(a)
    wyjscie, czas, rozdzialy = audio.zloz(a, opcje, okladka)
    print(f"\n✓ {wyjscie}\n  czas {audio._hms(czas)}, rozdziałów {len(rozdzialy)}, "
          f"opcje: {', '.join(f'{k}={v}' for k, v in opcje.items())}")
    if brak:
        print("  bez pozycji: " + ", ".join(etykieta(p) for p in brak))
    if not arg.bez_eksportu:
        _eksportuj(wyjscie)


def _eksportuj(plik):
    if not EKSPORT:
        print("  (eksport pominięty: nie znaleziono pulpitu Windows — ustaw TBMP3_EKSPORT)")
        return
    cel = EKSPORT / plik.name
    shutil.copyfile(plik, cel)
    print(f"  → skopiowano na pulpit: {cel}")


def k_eksport(arg):
    a = Audycja.wczytaj(arg.id)
    pliki = sorted(a.folder.glob(f"{a.folder.name}.m4b")) + sorted(a.folder.glob(f"{a.folder.name}.mp3"))
    if not pliki:
        raise SystemExit("Audycja nie jest jeszcze złożona: ./tb zloz ID")
    for f in pliki:
        _eksportuj(f)


# ------------------------------------------------------------------ parser

def _dodaj_opcje_audio(sp):
    g = sp.add_argument_group("obróbka dźwięku")
    g.add_argument("--normalizuj", action=argparse.BooleanOptionalAction, default=None)
    g.add_argument("--glosnosc", type=float, help="docelowa głośność LUFS (domyślnie -16)")
    g.add_argument("--przytnij", action=argparse.BooleanOptionalAction, default=None, help="przycinanie ciszy")
    g.add_argument("--prog-ciszy", dest="prog_ciszy", type=int, help="próg ciszy dB (domyślnie -50)")
    g.add_argument("--odszumiaj", action=argparse.BooleanOptionalAction, default=None,
                   help="odszumianie komentarzy i sygnałów")
    g.add_argument("--crossfade", type=float, help="sekundy przenikania (0 = brak)")
    g.add_argument("--format", choices=["m4b", "mp3"])
    g.add_argument("--bitrate")


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tb", description="Audycje Tomasza Beksińskiego z tbmp3.pl")
    sub = ap.add_subparsers(dest="komenda", required=True)

    sp = sub.add_parser("lista", help="lista audycji (cykl/rok)")
    sp.add_argument("--cykl", type=int)
    sp.add_argument("--rok", type=int)
    sp.add_argument("--szukaj", help="filtr po tytule")
    sp.add_argument("--dostepne", action="store_true", help="tylko z komentarzami mp3 lub Mixcloud")
    sp.set_defaults(f=k_lista)

    for nazwa, f, pomoc in (("info", k_info, "pobierz opis audycji i utwórz/odśwież manifest"),
                            ("status", k_status, "stan pozycji audycji"),
                            ("mixcloud", k_mixcloud, "pobierz całą audycję z Mixcloud"),
                            ("utwory", k_utwory, "pobierz automatycznie wszystkie brakujące utwory")):
        sp = sub.add_parser(nazwa, help=pomoc)
        sp.add_argument("id", type=int)
        sp.set_defaults(f=f)

    sp = sub.add_parser("komentarze", help="pobierz komentarze mp3 z tbmp3.pl")
    sp.add_argument("id", type=int)
    sp.add_argument("nr", type=int, nargs="*", help="tylko te pozycje")
    sp.set_defaults(f=k_komentarze)

    sp = sub.add_parser("szukaj", help="kandydaci z YouTube dla pozycji")
    sp.add_argument("id", type=int)
    sp.add_argument("nr")
    sp.add_argument("--zapytanie")
    sp.add_argument("--ile", type=int, default=5)
    sp.set_defaults(f=k_szukaj)

    sp = sub.add_parser("utwor", help="pobierz utwór dla pozycji z podanego URL")
    sp.add_argument("id", type=int)
    sp.add_argument("nr")
    sp.add_argument("url")
    sp.set_defaults(f=k_utwor)

    sp = sub.add_parser("ustaw", help="zmień pozycję (zapytanie, pominięcie, uwagi, typ)")
    sp.add_argument("id", type=int)
    sp.add_argument("nr")
    sp.add_argument("--zapytanie")
    sp.add_argument("--pomin", action=argparse.BooleanOptionalAction, default=None)
    sp.add_argument("--uwagi")
    sp.add_argument("--typ", choices=["utwor", "komentarz", "sygnal"])
    sp.set_defaults(f=k_ustaw)

    sp = sub.add_parser("dodaj", help="wstaw pozycję spoza strony (np. sygnał) po pozycji N")
    sp.add_argument("id", type=int)
    sp.add_argument("--po", type=int, required=True, help="0 = na początek")
    sp.add_argument("--typ", default="sygnal", choices=["utwor", "komentarz", "sygnal"])
    sp.add_argument("--tekst", required=True)
    sp.add_argument("--plik", help="od razu przypisz plik (ścieżka albo nazwa z biblioteki sygnałów)")
    sp.set_defaults(f=k_dodaj)

    sp = sub.add_parser("plik", help="przypisz lokalny plik do pozycji (sygnał, własna płyta...)")
    sp.add_argument("id", type=int)
    sp.add_argument("nr")
    sp.add_argument("plik", help="ścieżka albo nazwa pliku z biblioteki sygnałów")
    sp.set_defaults(f=k_plik)

    sp = sub.add_parser("sygnaly", help="pokaż bibliotekę sygnałów")
    sp.set_defaults(f=k_sygnaly)

    sp = sub.add_parser("opcje", help="pokaż/zapisz ustawienia obróbki dla audycji")
    sp.add_argument("id", type=int)
    _dodaj_opcje_audio(sp)
    sp.set_defaults(f=k_opcje)

    sp = sub.add_parser("zloz", help="obróbka + scalenie w jeden opisany plik")
    sp.add_argument("id", type=int)
    sp.add_argument("--pomin-brakujace", action="store_true")
    sp.add_argument("--bez-eksportu", action="store_true", help="nie kopiuj wyniku na pulpit Windows")
    _dodaj_opcje_audio(sp)
    sp.set_defaults(f=k_zloz)

    sp = sub.add_parser("eksport", help="skopiuj złożoną audycję na pulpit Windows (TBMP3_EKSPORT)")
    sp.add_argument("id", type=int)
    sp.set_defaults(f=k_eksport)

    arg = ap.parse_args(argv)
    try:
        arg.f(arg)
    except KeyboardInterrupt:
        sys.exit(130)
