#!/usr/bin/env python3
"""La vedetta dei siti di addiplatform: guarda DA FUORI se un sito cade o un orologio si ferma, e lo dice a Marco.

Gira su GitHub ogni 10 minuti (.github/workflows/vedetta.yml), fuori da Ergonet: se cade il server dei siti, la vedetta no.
Per ogni sito di siti.json:
  1. la prima pagina: deve rispondere 200, oppure 403 con la pagina della password (il sito chiuso: risponde lo stesso);
  2. /api/stato.php: deve dire che il database risponde (il PHP e il database dietro la cache, che la prima pagina può
     nascondere);
  3. gli orologi che quel sito deve avere (in siti.json, coi minuti oltre i quali sono fermi): l'ultima volta che sono
     finiti bene, e se no perché (rifiutati per la chiave sbagliata, finiti con un errore, interrotti, mai chiamati).
Un sito che non risponde si riprova 3 volte, a 15 secondi l'una dall'altra: un singhiozzo non è un avviso.

Gli avvisi sono «issue» di questo repository, una per problema: GitHub manda l'email a Marco (e la notifica sull'app GitHub).
Una volta sola: finché il problema c'è l'avviso resta aperto (un promemoria al giorno); quando passa, la vedetta scrive
«tornato a posto» e lo chiude da sola. Se Marco ne chiude uno lui (una cosa voluta), la vedetta non lo riapre per 7 giorni.
Quello che non si è potuto guardare (gli orologi di un sito che non risponde) non si apre e non si chiude.

Se la vedetta stessa non può lavorare (la rete del giro, GitHub che rifiuta), il giro finisce in rosso e GitHub manda la sua
email «Run failed»: anche questo è un avviso.

  python3 vedetta.py            un giro
  python3 vedetta.py --prova    un avviso di prova, aperto e chiuso subito (arriva l'email?)
Le prove: python3 prova_vedetta.py (siti e GitHub finti, sul computer).
"""
import concurrent.futures, datetime, json, os, socket, ssl, sys, time, urllib.error, urllib.request
from zoneinfo import ZoneInfo

QUI = os.path.dirname(os.path.abspath(__file__))
ROMA = ZoneInfo('Europe/Rome')
# ⚠️ Il firewall davanti ai siti (FireShield di Ergonet) risponde 403 a un nome di programma inventato: ci si presenta come
# un browser, sennò ogni sito sembra giù (provato l'11/9 e il 15/10/26 su questi server).
NAVIGATORE = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36'
TEMPO = float(os.environ.get('VEDETTA_TEMPO', '20'))          # secondi di attesa per una risposta
TENTATIVI = int(os.environ.get('VEDETTA_TENTATIVI', '3'))
ATTESA = float(os.environ.get('VEDETTA_ATTESA', '15'))        # secondi fra un tentativo e l'altro
CONTROLLO = os.environ.get('VEDETTA_CONTROLLO', 'https://www.google.com/generate_204')   # la rete del giro c'è?
API = os.environ.get('GITHUB_API_URL', 'https://api.github.com').rstrip('/')
REPO = os.environ.get('GITHUB_REPOSITORY', 'autuoridesign/addi-vedetta')
GETTONE = os.environ.get('GITHUB_TOKEN', '')
AVVISA = os.environ.get('VEDETTA_AVVISA', 'autuoridesign')   # chi viene chiamato nell'avviso (così l'email arriva di sicuro)
ETICHETTA, RISOLTO = 'vedetta', 'risolto'
SILENZIO = 7 * 86400          # un avviso chiuso da Marco non si riapre per 7 giorni
PROMEMORIA = 24 * 3600        # un avviso aperto da un giorno: «ancora così»
PAGINA_CHIUSA = 'class="addi-privato"'   # la pagina della password dei siti chiusi (addi_sito_privato_pagina)

# il nome di ogni orologio e la lettera che lo accorda («fermo», «ferma»)
OROLOGI = {'avvisi': ("l'orologio degli avvisi", 'o'), 'posta': ('la lettura della posta', 'a'), 'pulizia': ('la pulizia della notte', 'a')}


def durata(s):
    s = max(0, int(s))
    if s < 90: return 'un minuto' if s >= 45 else 'meno di un minuto'
    if s < 5400: return f'{round(s / 60)} minuti'
    if s < 129600: return f'{round(s / 3600)} ore' if round(s / 3600) != 1 else "un'ora"
    g = round(s / 86400)
    return 'un giorno' if g == 1 else f'{g} giorni'


def fa(s):
    return 'adesso' if s < 45 else durata(s) + ' fa'


def adesso():
    finta = os.environ.get('VEDETTA_ORA')    # solo per le prove: «adesso» a un'ora scelta
    return datetime.datetime.fromisoformat(finta).astimezone(ROMA) if finta else datetime.datetime.now(ROMA)


# Di notte (dalle 22 alle 8) un orologio fermo aspetta il mattino: è un problema lento (una pulizia della notte rifiutata
# si vede alle 3). Un sito giù invece avvisa subito, a qualunque ora.
def notte():
    return not 8 <= adesso().hour < 22


def quando(t=None):
    t = t or adesso()
    return t.strftime('%H:%M del %d/%m')


def perche(e):
    """Il motivo di una risposta mancata, in parole: si legge dopo «Il sito» o «/api/stato.php»."""
    r = getattr(e, 'reason', e)
    if isinstance(r, (socket.timeout, TimeoutError)) or 'timed out' in str(r):
        return f'non risponde entro {TEMPO:.0f} secondi'
    if isinstance(r, ConnectionRefusedError): return 'rifiuta la connessione'
    if isinstance(r, ConnectionResetError): return 'chiude la connessione a metà'
    if isinstance(r, ssl.SSLCertVerificationError): return f'ha un certificato che non va ({r.verify_message})'
    if isinstance(r, ssl.SSLError): return f'non riesce a fare la connessione sicura ({r})'[:160]
    if isinstance(r, socket.gaierror): return "non si trova: il suo nome non c'è nel DNS"
    return f'non risponde ({r})'[:160]


def leggi(url):
    """(codice, testo), o (None, perché) se non risponde."""
    r = urllib.request.Request(url, headers={'User-Agent': NAVIGATORE, 'Accept': 'text/html,application/json,*/*', 'Cache-Control': 'no-cache'})
    try:
        with urllib.request.urlopen(r, timeout=TEMPO) as h:
            return h.status, h.read(400_000).decode('utf-8', 'replace')
    except urllib.error.HTTPError as e:
        return e.code, e.read(400_000).decode('utf-8', 'replace')
    except Exception as e:   # tempo scaduto, connessione rifiutata, certificato, nome che non si trova
        return None, perche(e)


def spiega(c):
    return {403: ' (vietato: un blocco davanti al sito?)', 404: ' (non trovata)', 500: ' (un errore del sito)',
            502: ' (il server dietro non risponde)', 503: ' (il server non ce la fa o è spento)', 504: ' (il server dietro non risponde in tempo)'}.get(c, '')


def una_volta(sito):
    """({'sito': (titolo, dettaglio)} o {}, lo stato letto o None)."""
    base = sito['indirizzo'].rstrip('/')
    c, t = leggi(base + '/')
    if c is None:
        return {'sito': ('il sito non risponde', f'Il sito {t}.')}, None
    if not (c == 200 or (c == 403 and PAGINA_CHIUSA in t)):
        return {'sito': (f'il sito risponde con un errore ({c})', f'La prima pagina risponde {c}{spiega(c)}.')}, None
    c, t = leggi(base + '/api/stato.php')
    if c is None:
        return {'sito': ('il sito non dice come sta', f'La prima pagina risponde, ma /api/stato.php {t}.')}, None
    try: j = json.loads(t)              # anche il 503 di stato.php dice cosa manca: {"database": false}
    except ValueError: j = None
    if c != 200 or not isinstance(j, dict) or j.get('database') is not True:
        db = ': il database non risponde' if isinstance(j, dict) and j.get('database') is False else ''
        return {'sito': ('il sito non dice come sta', f'La prima pagina risponde, ma /api/stato.php risponde {c}{spiega(c) if c != 200 else ""}{db}.')}, None
    return {}, j


def orologi(sito, stato):
    """(problemi, noti) degli orologi: noti = le chiavi di cui si sa com'è (a posto o no)."""
    attesi = sito.get('orologi') or {}
    o = stato.get('orologi')
    if not isinstance(o, dict):
        if not attesi: return {}, {'orologi'}
        return {'orologi': ('il sito non dice come vanno gli orologi', 'In /api/stato.php gli orologi non ci sono (la tabella addi_orologi manca?).')}, {'orologi'}
    problemi, noti = {}, {'orologi'} | {f'orologio:{n}' for n in OROLOGI}
    num = lambda v: isinstance(v, int) and not isinstance(v, bool)
    for nome, minuti in attesi.items():
        lim = int(minuti) * 60
        recente = lambda v: num(v) and v <= lim
        x = o.get(nome) if isinstance(o.get(nome), dict) else {}
        ok, chiamata, rifiuto, da, esito = (x.get(k) for k in ('ultimo_ok', 'ultima_chiamata', 'ultimo_rifiuto', 'ascolta_da', 'esito'))
        if recente(ok): continue
        cosa, g = OROLOGI.get(nome, (nome, 'o'))
        lo = 'lo' if g == 'o' else 'la'
        ogni = f'(deve finire bene almeno ogni {durata(lim)})'
        dal = f"l'ultima volta che è finit{g} bene è {fa(ok)}" if num(ok) else f'da quando il sito {lo} segna non è mai finit{g} bene'
        if recente(rifiuto):
            t = (f'{cosa} è rifiutat{g}', f'Il pannello di Ergonet {lo} chiama con la chiave sbagliata: rifiutat{g} l\'ultima volta {fa(rifiuto)}; {dal} {ogni}. '
                 'Va rimesso l\'indirizzo giusto nel pannello di Ergonet (CRON.md di addiplatform).')
        elif recente(chiamata) and esito == 'errore':
            t = (f'{cosa} finisce con un errore', f'Viene chiamat{g} (l\'ultima volta {fa(chiamata)}) ma finisce con un errore; {dal} {ogni}. Il perché sta nella tabella addi_orologi del sito.')
        elif recente(chiamata) and esito == 'interrotto':
            t = (f'{cosa} si interrompe a metà', f'Viene chiamat{g} (l\'ultima volta {fa(chiamata)}) ma si ferma a metà (memoria o tempo finiti); {dal} {ogni}.')
        elif recente(chiamata) and esito == 'in corso' and chiamata < 900:
            continue                                            # sta girando adesso
        elif recente(chiamata):
            t = (f'{cosa} non finisce', f'Viene chiamat{g} (l\'ultima volta {fa(chiamata)}, esito «{esito or "?"}») ma non finisce bene; {dal} {ogni}.')
        elif chiamata is None and rifiuto is None:
            if num(da) and da <= lim: continue                  # il sito lo segna da poco: «mai» non vuol dire fermo
            t = (f'{cosa} non è mai partit{g}', f'Da quando il sito {lo} segna ({durata(da) if num(da) else "?"}) nessuno l\'ha chiamat{g} {ogni}: nel pannello di Ergonet manca il cron?')
        else:
            ultime = [v for v in (chiamata, rifiuto) if num(v)]
            ultima = min(ultime) if ultime else None
            come = ' (ed era rifiutata: chiave sbagliata)' if num(rifiuto) and rifiuto == ultima else ''
            t = (f'{cosa} è ferm{g}', (f'L\'ultima chiamata è arrivata {fa(ultima)}{come}; ' if ultima is not None else '')
                 + f'{dal} {ogni}. Il cron del pannello di Ergonet non chiama più.')
        problemi[f'orologio:{nome}'] = t
    return problemi, noti


def guarda(sito):
    """(problemi, noti) di un sito: {chiave: (titolo, dettaglio)} e le chiavi di cui si sa com'è."""
    for i in range(TENTATIVI):
        problemi, stato = una_volta(sito)
        if not problemi: break
        if i < TENTATIVI - 1: time.sleep(ATTESA)
    else:
        titolo, dettaglio = problemi['sito']
        return {'sito': (titolo, dettaglio + f' ({TENTATIVI} tentativi, a {ATTESA:.0f} secondi l\'uno dall\'altro.)')}, {'sito'}
    p, noti = orologi(sito, stato)
    return p, {'sito'} | noti


# ---- gli avvisi: le issue di questo repository ----------------------------------------------------------------------

def api(metodo, percorso, dati=None):
    r = urllib.request.Request(API + percorso, method=metodo, data=None if dati is None else json.dumps(dati).encode(),
                               headers={'Authorization': f'Bearer {GETTONE}', 'Accept': 'application/vnd.github+json',
                                        'X-GitHub-Api-Version': '2022-11-28', 'User-Agent': 'addi-vedetta', 'Content-Type': 'application/json'})
    with urllib.request.urlopen(r, timeout=30) as h:
        b = h.read()
        return json.loads(b) if b else None


def segno(sito, chiave):
    return f'<!-- vedetta:{sito["chiave"]}:{chiave} -->'


def momento(s):
    return datetime.datetime.fromisoformat(s.replace('Z', '+00:00')) if s else None


def apri(sito, chiave, titolo, dettaglio):
    corpo = (f'**{sito["nome"]}** ({sito["indirizzo"]}): {dettaglio}\n\n'
             f'Visto dalla vedetta alle {quando()} (ora di Roma). Quando torna a posto, questo avviso si chiude da solo. '
             f'Se è una cosa voluta, chiudilo tu: la vedetta non lo riapre per 7 giorni.\n\n@{AVVISA}\n\n{segno(sito, chiave)}\n')
    n = api('POST', f'/repos/{REPO}/issues', {'title': f'{sito["nome"]}: {titolo}', 'body': corpo, 'labels': [ETICHETTA]})['number']
    print(f'  APERTO #{n} {sito["nome"]}: {titolo}')


def chiudi(sito, chiave, avviso):
    inizio = momento(avviso.get('created_at'))
    dopo = f', dopo {durata((adesso() - inizio).total_seconds())}' if inizio else ''
    api('POST', f'/repos/{REPO}/issues/{avviso["number"]}/comments', {'body': f'✅ Tornato a posto alle {quando()} (ora di Roma){dopo}.'})
    api('PATCH', f'/repos/{REPO}/issues/{avviso["number"]}', {'state': 'closed', 'state_reason': 'completed', 'labels': [ETICHETTA, RISOLTO]})
    print(f'  CHIUSO #{avviso["number"]} {sito["nome"]} ({chiave}): tornato a posto')


def promemoria(sito, chiave, avviso, titolo, dettaglio):
    agg, inizio = momento(avviso.get('updated_at')), momento(avviso.get('created_at'))
    if not agg or (adesso() - agg).total_seconds() < PROMEMORIA: return
    da = f' da {durata((adesso() - inizio).total_seconds())}' if inizio else ''
    api('POST', f'/repos/{REPO}/issues/{avviso["number"]}/comments', {'body': f'Ancora così alle {quando()} (ora di Roma){da}: {titolo}. {dettaglio}'})
    print(f'  PROMEMORIA #{avviso["number"]} {sito["nome"]}: {titolo}')


def avvisi_di_prima():
    """{segno: avviso aperto} e {segno: chiuso da Marco da meno di 7 giorni}."""
    elenco = api('GET', f'/repos/{REPO}/issues?state=all&labels={ETICHETTA}&per_page=100&sort=updated&direction=desc') or []
    aperti, zitti = {}, {}
    for a in elenco:
        if a.get('pull_request'): continue
        corpo = a.get('body') or ''
        i = corpo.find('<!-- vedetta:')
        if i < 0: continue
        s = corpo[i:corpo.find('-->', i) + 3]
        if a.get('state') == 'open':
            aperti.setdefault(s, a)
        elif RISOLTO not in {l.get('name') for l in a.get('labels') or []}:
            chiuso = momento(a.get('closed_at'))
            if chiuso and (adesso() - chiuso).total_seconds() < SILENZIO: zitti.setdefault(s, a)
    return aperti, zitti


def prova():
    sito = {'nome': 'Prova della vedetta', 'chiave': 'prova', 'indirizzo': 'https://github.com/' + REPO}
    corpo = (f'Se ti arriva questa email, gli avvisi della vedetta funzionano. Mandata alle {quando()} (ora di Roma); '
             f'si chiude subito da sola.\n\n@{AVVISA}\n\n{segno(sito, "prova")}\n')
    n = api('POST', f'/repos/{REPO}/issues', {'title': 'Prova della vedetta: se ti arriva questa email, gli avvisi funzionano', 'body': corpo, 'labels': [ETICHETTA]})['number']
    api('PATCH', f'/repos/{REPO}/issues/{n}', {'state': 'closed', 'state_reason': 'completed', 'labels': [ETICHETTA, RISOLTO]})
    print(f'avviso di prova #{n}: aperto e chiuso')
    return 0


def principale(argv):
    if '--prova' in argv: return prova()
    siti = json.load(open(os.path.join(QUI, os.environ.get('VEDETTA_SITI', 'siti.json')), encoding='utf-8'))['siti']
    c, t = leggi(CONTROLLO)
    if c is None or c >= 500:
        print(f'NO: la rete della vedetta non va ({t if c is None else c}): non guardo i siti, non apro né chiudo niente')
        return 2
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(siti)) as ex:
        visti = list(ex.map(guarda, siti))
    aperti, zitti = avvisi_di_prima()
    for sito, (problemi, noti) in zip(siti, visti):
        print(f'{sito["nome"]}: ' + ('a posto' if not problemi else '; '.join(t for t, _ in problemi.values())))
        for chiave in sorted(noti):
            s = segno(sito, chiave)
            if chiave in problemi:
                titolo, dettaglio = problemi[chiave]
                if s in aperti: promemoria(sito, chiave, aperti[s], titolo, dettaglio)
                elif s in zitti: print(f'  zitto: #{zitti[s]["number"]} chiuso da Marco da meno di 7 giorni')
                elif chiave != 'sito' and notte(): print('  di notte: l\'avviso di un orologio aspetta le 8')
                else: apri(sito, chiave, titolo, dettaglio)
            elif s in aperti:
                chiudi(sito, chiave, aperti[s])
    return 0


if __name__ == '__main__':
    sys.exit(principale(sys.argv[1:]))
