#!/usr/bin/env python3
"""Le prove della vedetta: siti finti e un GitHub finto sul computer, nessuna rete vera (18/10/26).

Ogni caso prepara i siti finti (prima pagina, /api/stato.php, ritardi, singhiozzi) e gli avvisi che ci sono già, fa girare
vedetta.py VERO in un processo a parte, e guarda cosa ha chiesto al GitHub finto (avvisi aperti, commenti, chiusure):

  1 tutto a posto (un sito aperto, uno chiuso con la password): nessun avviso
  2 un sito che rifiuta la connessione: un avviso, col nome, il perché, i tentativi, la chiamata a Marco, il segno
  3 lo stesso giro di nuovo: niente di nuovo (né avviso né commento)
  4 il sito torna su: «tornato a posto» e l'avviso chiuso, con l'etichetta «risolto»
  5 la prima pagina in errore (500)            6 un 403 che NON è la pagina della password: giù
  7 stato.php dice che il database non risponde 8 il sito che non risponde in tempo
  9 un singhiozzo (il primo tentativo cade, il secondo no): nessun avviso, ma il secondo tentativo c'è stato
 10 l'orologio fermo                           11 rifiutato (chiave sbagliata) anche nelle prime ore dopo il caricamento
 12 finisce con un errore                      13 appena caricato e mai chiamato: si aspetta
 14 mai chiamato da troppo: avviso             15 un orologio che quel sito non deve avere: non si guarda
 16 sito giù: l'avviso di un suo orologio NON si chiude (non si è potuto guardare)
 17 stato.php senza orologi: avviso solo dove gli orologi servono, e quelli già aperti restano
 18 il promemoria dopo un giorno, non prima    19 chiuso da Marco: zitto per 7 giorni, poi di nuovo; chiuso da «risolto»: subito
 20 la rete del giro che non va: il giro finisce in rosso e non tocca gli avvisi
 21 l'avviso di prova: aperto e chiuso         22 GitHub che rifiuta: il giro finisce in rosso
 23 due siti giù: due avvisi                   24 «in corso» da poco: si aspetta; da un quarto d'ora: avviso
 25 un orologio tolto da siti.json: il suo avviso si chiude
 26 stato.php che risponde 500 anche con dentro «database: true»: giù
 27 stato.php che risponde 200 con «database: false»: giù (la regola del database da sola)
 28 di notte (dalle 22 alle 8) un sito giù avvisa subito, un orologio aspetta le 8

  python3 prova_vedetta.py            le prove (~15 s)
  python3 prova_vedetta.py --morsi    ogni rottura di vedetta.py deve far diventare rosso il caso che la deve vedere
"""
import datetime, hashlib, http.server, json, os, pathlib, re, socket, subprocess, sys, tempfile, threading, time, urllib.parse

QUI = pathlib.Path(__file__).resolve().parent
VEDETTA = pathlib.Path(os.environ.get('VEDETTA_FILE') or QUI / 'vedetta.py')
esiti = []


def prova(nome, ok, dettaglio=''):
    esiti.append(bool(ok))
    print(('  OK   ' if ok else '  NO   ') + nome + ('' if ok else f'  ← {str(dettaglio)[:300]}'))


# ---- il mondo finto ---------------------------------------------------------------------------------------------------
SITI = {}          # chiave → {'home': (codice, corpo), 'stato': (codice, corpo), 'ritardo': s, 'cade': n, 'visite': n}
AVVISI = []        # le issue del GitHub finto
CHIAMATE = []      # (metodo, percorso, dati)
GUASTI = {'rete': None, 'api': False}
CHIUSA = '<!DOCTYPE html><html><body class="addi-privato"><form>password</form></body></html>'
APERTA = '<!DOCTYPE html><html><body class="bt-theme">ciao</body></html>'


def oggi_alle(h):
    """Oggi all'ora h di Roma (le prove vedono gli avvisi «di adesso» come fatti poco prima di quell'ora)."""
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo('Europe/Rome')).replace(hour=h, minute=0, second=0, microsecond=0).isoformat()


def ora(s=0):
    """Un momento per il GitHub finto: s secondi prima dell'«adesso» della vedetta (le 12 di Roma di oggi)."""
    base = datetime.datetime.fromisoformat(oggi_alle(12)).astimezone(datetime.timezone.utc)
    return (base - datetime.timedelta(seconds=s)).strftime('%Y-%m-%dT%H:%M:%SZ')


class Finto(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def rispondi(self, codice, corpo, tipo='text/html'):
        b = corpo.encode() if isinstance(corpo, str) else json.dumps(corpo).encode()
        try:
            self.send_response(codice); self.send_header('Content-Type', tipo); self.send_header('Content-Length', str(len(b))); self.end_headers()
            self.wfile.write(b)
        except (BrokenPipeError, ConnectionResetError):
            pass   # il caso 8: la vedetta ha già smesso di aspettare

    def do_GET(self): self.giro('GET')
    def do_POST(self): self.giro('POST')
    def do_PATCH(self): self.giro('PATCH')

    def giro(self, metodo):
        u = urllib.parse.urlparse(self.path)
        dati = None
        if metodo in ('POST', 'PATCH'):
            n = int(self.headers.get('Content-Length') or 0)
            dati = json.loads(self.rfile.read(n) or b'null')
        if u.path == '/ok':
            if GUASTI['rete']: return self.rispondi(GUASTI['rete'], 'giù')
            return self.rispondi(204, '')
        if u.path.startswith('/gh/'):
            CHIAMATE.append((metodo, u.path + ('?' + u.query if u.query else ''), dati))
            return self.github(metodo, u, dati)
        m = re.match(r'^/([a-z]+)(/api/stato\.php|/)$', u.path)
        if not m or m.group(1) not in SITI: return self.rispondi(404, 'no')
        s = SITI[m.group(1)]
        s['visite'] = s.get('visite', 0) + (m.group(2) == '/')
        if s.get('ritardo'): time.sleep(s['ritardo'])
        if m.group(2) == '/' and s.get('cade', 0) > 0:
            s['cade'] -= 1
            return self.rispondi(503, 'singhiozzo')
        c, corpo = s['home'] if m.group(2) == '/' else s['stato']
        return self.rispondi(c, corpo, 'text/html' if m.group(2) == '/' else 'application/json')

    def github(self, metodo, u, dati):
        if GUASTI['api'] and metodo != 'GET': return self.rispondi(500, {'message': 'rotto'}, 'application/json')
        if metodo == 'GET' and u.path == '/gh/repos/o/r/issues':
            q = urllib.parse.parse_qs(u.query)
            el = [a for a in AVVISI if any(l['name'] == q.get('labels', [''])[0] for l in a['labels'])]
            return self.rispondi(200, sorted(el, key=lambda a: a['updated_at'], reverse=True), 'application/json')
        if metodo == 'POST' and u.path == '/gh/repos/o/r/issues':
            a = {'number': len(AVVISI) + 1, 'title': dati['title'], 'body': dati['body'], 'state': 'open', 'commenti': [],
                 'labels': [{'name': l} for l in dati.get('labels', [])], 'created_at': ora(), 'updated_at': ora(), 'closed_at': None}
            AVVISI.append(a)
            return self.rispondi(201, a, 'application/json')
        m = re.match(r'^/gh/repos/o/r/issues/(\d+)(/comments)?$', u.path)
        if m:
            a = AVVISI[int(m.group(1)) - 1]
            if metodo == 'POST' and m.group(2):
                a['commenti'].append(dati['body']); a['updated_at'] = ora()
                return self.rispondi(201, {'id': 1}, 'application/json')
            if metodo == 'PATCH':
                if 'state' in dati:
                    a['state'] = dati['state']; a['closed_at'] = ora() if dati['state'] == 'closed' else None
                if 'labels' in dati: a['labels'] = [{'name': l} for l in dati['labels']]
                a['updated_at'] = ora()
                return self.rispondi(200, a, 'application/json')
        return self.rispondi(404, {'message': 'Not Found'}, 'application/json')


SERVER = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Finto)
threading.Thread(target=SERVER.serve_forever, daemon=True).start()
P = SERVER.server_address[1]
_s = socket.socket(); _s.bind(('127.0.0.1', 0)); CHIUSO = _s.getsockname()[1]; _s.close()   # una porta dove nessuno ascolta


def stato(**orologi):
    base = {'ascolta_da': 86400, 'ultima_chiamata': 60, 'ultimo_ok': 60, 'ultimo_rifiuto': None, 'esito': 'ok'}
    return {'database': True, 'orologi': {n: {**base, **orologi.get(n, {})} for n in ('avvisi', 'posta', 'pulizia')}}


def sito(chiave, home=(200, APERTA), st=None, **kw):
    SITI[chiave] = {'home': home, 'stato': (200, st if st is not None else stato()), **kw}


def avviso(chiave, sito_, stato_='open', labels=('vedetta',), creato=3600, aggiornato=3600, chiuso=None):
    AVVISI.append({'number': len(AVVISI) + 1, 'title': f'{sito_}: vecchio', 'body': f'testo\n\n<!-- vedetta:{sito_}:{chiave} -->\n',
                   'state': stato_, 'commenti': [], 'labels': [{'name': l} for l in labels], 'created_at': ora(creato),
                   'updated_at': ora(aggiornato), 'closed_at': ora(chiuso) if chiuso is not None else None})
    return AVVISI[-1]


def giro(elenco, *argomenti, controllo=None, ora_=None):
    """Fa girare vedetta.py vero coi siti di elenco: [(chiave, nome, orologi, giù?)]. Torna (codice, uscita).
    Di giorno (le 12 di Roma) se il caso non dice un'altra ora: le regole della notte le prova il caso 28."""
    CHIAMATE.clear()
    with tempfile.NamedTemporaryFile('w', suffix='.json', delete=False) as f:
        json.dump({'siti': [{'nome': n, 'chiave': k, 'indirizzo': f'http://127.0.0.1:{CHIUSO if giu else P}/{k}', 'orologi': o}
                            for k, n, o, giu in elenco]}, f)
    env = {**os.environ, 'VEDETTA_SITI': f.name, 'GITHUB_API_URL': f'http://127.0.0.1:{P}/gh', 'GITHUB_REPOSITORY': 'o/r',
           'GITHUB_TOKEN': 'finto', 'VEDETTA_CONTROLLO': controllo or f'http://127.0.0.1:{P}/ok', 'VEDETTA_TEMPO': '1',
           'VEDETTA_ATTESA': '0.05', 'VEDETTA_TENTATIVI': '3', 'VEDETTA_AVVISA': 'autuoridesign',
           'VEDETTA_ORA': ora_ or oggi_alle(12)}
    r = subprocess.run([sys.executable, str(VEDETTA), *argomenti], env=env, capture_output=True, text=True, timeout=120)
    os.unlink(f.name)
    return r.returncode, r.stdout + r.stderr


def azzera():
    SITI.clear(); AVVISI.clear(); CHIAMATE.clear(); GUASTI.update(rete=None, api=False)


def scritte(): return [c for c in CHIAMATE if c[0] != 'GET']
def aperti(): return [a for a in AVVISI if a['state'] == 'open']


A = ('a', 'Alfa', {'avvisi': 20}, False)
B = ('b', 'Beta', {'pulizia': 1560}, False)
C = ('c', 'Gamma', {}, False)


def casi():
    # 1 tutto a posto
    azzera(); sito('a'); sito('b', home=(403, CHIUSA)); sito('c')
    c, u = giro([A, B, C])
    prova('1 tutto a posto (aperto, chiuso con la password, senza orologi): nessun avviso, esce 0', c == 0 and not scritte(), (c, scritte(), u))

    # 2 giù: rifiuta la connessione
    azzera(); sito('b', home=(403, CHIUSA))
    c, u = giro([('a', 'Alfa', {'avvisi': 20}, True), B])
    a = AVVISI[0] if AVVISI else {}
    prova('2 sito giù: un avviso solo, esce 0', c == 0 and len(AVVISI) == 1, (c, AVVISI, u))
    prova('2 il titolo dice chi e cosa', a.get('title') == 'Alfa: il sito non risponde', a.get('title'))
    prova('2 il perché e i tentativi', 'rifiuta la connessione' in a.get('body', '') and '3 tentativi' in a.get('body', ''), a.get('body'))
    prova('2 chiama Marco (così l\'email arriva) e porta il segno', '@autuoridesign' in a.get('body', '') and '<!-- vedetta:a:sito -->' in a.get('body', ''), a.get('body'))
    prova('2 con l\'etichetta vedetta', [l['name'] for l in a.get('labels', [])] == ['vedetta'], a.get('labels'))

    # 3 di nuovo
    c, u = giro([('a', 'Alfa', {'avvisi': 20}, True), B])
    prova('3 ancora giù: niente di nuovo (né avviso né commento)', c == 0 and not scritte() and len(AVVISI) == 1, (scritte(), u))

    # 4 torna su
    sito('a')
    c, u = giro([A, B])
    a = AVVISI[0]
    prova('4 tornato su: «tornato a posto» e avviso chiuso con «risolto»', a['state'] == 'closed' and any('Tornato a posto' in x for x in a['commenti'])
          and {l['name'] for l in a['labels']} == {'vedetta', 'risolto'}, (a, u))

    # 5 errore 500
    azzera(); sito('a', home=(500, 'boom')); sito('b', home=(403, CHIUSA))
    c, u = giro([A, B])
    prova('5 la prima pagina in errore: avviso «errore (500)»', len(AVVISI) == 1 and 'errore (500)' in AVVISI[0]['title'], (AVVISI, u))

    # 6 un 403 che non è la pagina della password
    azzera(); sito('a', home=(403, '<html><body>Forbidden by firewall</body></html>')); sito('b', home=(403, CHIUSA))
    c, u = giro([A, B])
    prova('6 un 403 qualunque è un sito giù; quello con la password no', len(AVVISI) == 1 and AVVISI[0]['title'].startswith('Alfa:') and '403' in AVVISI[0]['title'], (AVVISI, u))

    # 7 il database
    azzera(); sito('a'); SITI['a']['stato'] = (503, {'database': False}); sito('b', home=(403, CHIUSA))
    c, u = giro([A, B])
    prova('7 stato.php: il database non risponde → avviso che lo dice', len(AVVISI) == 1 and 'non dice come sta' in AVVISI[0]['title'] and 'database non risponde' in AVVISI[0]['body'], (AVVISI, u))

    # 8 non risponde in tempo
    azzera(); sito('a', ritardo=1.5); sito('b', home=(403, CHIUSA))
    c, u = giro([A, B])
    prova('8 risponde troppo tardi: avviso «non risponde entro»', len(AVVISI) == 1 and 'non risponde entro' in AVVISI[0]['body'], (AVVISI, u))

    # 9 singhiozzo
    azzera(); sito('a', cade=1); sito('b', home=(403, CHIUSA))
    c, u = giro([A, B])
    prova('9 un singhiozzo: nessun avviso, e il secondo tentativo c\'è stato', not AVVISI and SITI['a']['visite'] == 2, (AVVISI, SITI['a'].get('visite'), u))

    # 10 orologio fermo
    azzera(); sito('a', st=stato(avvisi={'ultimo_ok': 3000, 'ultima_chiamata': 3000})); sito('b', home=(403, CHIUSA))
    c, u = giro([A, B])
    t = AVVISI[0] if AVVISI else {}
    prova('10 orologio fermo: «l\'orologio degli avvisi è fermo», con da quanto', len(AVVISI) == 1 and t['title'] == "Alfa: l'orologio degli avvisi è fermo"
          and '50 minuti fa' in t['body'] and '<!-- vedetta:a:orologio:avvisi -->' in t['body'], (AVVISI, u))

    # 11 rifiutato anche nelle prime ore
    azzera(); sito('a'); sito('b', home=(403, CHIUSA), st=stato(pulizia={'ascolta_da': 7200, 'ultimo_ok': None, 'ultima_chiamata': None, 'ultimo_rifiuto': 3600, 'esito': ''}))
    c, u = giro([A, B])
    prova('11 rifiutata (chiave sbagliata) anche appena caricato', len(AVVISI) == 1 and AVVISI[0]['title'] == 'Beta: la pulizia della notte è rifiutata'
          and 'chiave sbagliata' in AVVISI[0]['body'] and 'la chiama' in AVVISI[0]['body'], (AVVISI, u))

    # 12 errore
    azzera(); sito('a', st=stato(avvisi={'ultimo_ok': 5000, 'ultima_chiamata': 60, 'esito': 'errore'})); sito('b', home=(403, CHIUSA))
    c, u = giro([A, B])
    prova('12 finisce con un errore', len(AVVISI) == 1 and 'finisce con un errore' in AVVISI[0]['title'], (AVVISI, u))

    # 13 appena caricato, mai chiamato
    azzera(); sito('a', st=stato(avvisi={'ascolta_da': 600, 'ultimo_ok': None, 'ultima_chiamata': None, 'esito': ''})); sito('b', home=(403, CHIUSA))
    c, u = giro([A, B])
    prova('13 mai chiamato ma il sito lo segna da 10 minuti: si aspetta', not AVVISI, (AVVISI, u))

    # 14 mai chiamato da troppo
    azzera(); sito('a', st=stato(avvisi={'ascolta_da': 5000, 'ultimo_ok': None, 'ultima_chiamata': None, 'esito': ''})); sito('b', home=(403, CHIUSA))
    c, u = giro([A, B])
    prova('14 mai chiamato da più del limite: «non è mai partito»', len(AVVISI) == 1 and 'non è mai partito' in AVVISI[0]['title'], (AVVISI, u))

    # 15 un orologio che quel sito non deve avere
    azzera(); sito('a'); sito('b', home=(403, CHIUSA), st=stato(avvisi={'ultimo_ok': 99999, 'ultima_chiamata': 99999}, posta={'ultimo_ok': None, 'ultima_chiamata': None, 'ascolta_da': 99999}))
    c, u = giro([A, B])
    prova('15 gli orologi che il sito non deve avere non si guardano', not AVVISI, (AVVISI, u))

    # 16 sito giù: l'avviso del suo orologio resta aperto
    azzera(); sito('b', home=(403, CHIUSA)); vecchio = avviso('orologio:avvisi', 'a')
    c, u = giro([('a', 'Alfa', {'avvisi': 20}, True), B])
    prova('16 sito giù: l\'avviso del suo orologio non si chiude (non si è potuto guardare)', vecchio['state'] == 'open' and not vecchio['commenti']
          and len(AVVISI) == 2 and AVVISI[1]['title'] == 'Alfa: il sito non risponde', (AVVISI, u))

    # 17 stato.php senza orologi
    azzera(); sito('a', st={'database': True, 'orologi': None}); sito('c', st={'database': True, 'orologi': None}); vecchio = avviso('orologio:avvisi', 'a')
    c, u = giro([A, C])
    nuovi = AVVISI[1:]
    prova('17 senza orologi: avviso solo per il sito che li deve avere, quello vecchio resta aperto',
          len(nuovi) == 1 and nuovi[0]['title'] == 'Alfa: il sito non dice come vanno gli orologi' and vecchio['state'] == 'open' and not vecchio['commenti'], (AVVISI, u))

    # 18 promemoria
    azzera(); sito('b', home=(403, CHIUSA)); vecchio = avviso('sito', 'a', creato=90000, aggiornato=90000); fresco = avviso('sito', 'd', creato=3600, aggiornato=3600)
    c, u = giro([('a', 'Alfa', {}, True), ('d', 'Delta', {}, True), B])
    prova('18 un giorno dopo: un promemoria «Ancora così»; aggiornato da un\'ora: niente', len(vecchio['commenti']) == 1 and 'Ancora così' in vecchio['commenti'][0]
          and not fresco['commenti'] and len(AVVISI) == 2, (AVVISI, u))

    # 19 chiuso da Marco
    azzera(); sito('b', home=(403, CHIUSA))
    avviso('sito', 'a', stato_='closed', chiuso=2 * 86400); avviso('sito', 'd', stato_='closed', chiuso=8 * 86400); avviso('sito', 'e', stato_='closed', labels=('vedetta', 'risolto'), chiuso=86400)
    c, u = giro([('a', 'Alfa', {}, True), ('d', 'Delta', {}, True), ('e', 'Epsilon', {}, True), B])
    titoli = sorted(a['title'] for a in AVVISI[3:])
    prova('19 chiuso da Marco 2 giorni fa: zitto; 8 giorni fa: di nuovo; chiuso da «risolto»: subito', titoli == ['Delta: il sito non risponde', 'Epsilon: il sito non risponde'], (titoli, u))

    # 20 la rete del giro
    for guasto in (500, 'rifiutata'):
        azzera(); sito('b', home=(403, CHIUSA)); GUASTI['rete'] = 500 if guasto == 500 else None
        c, u = giro([('a', 'Alfa', {}, True), B], controllo=f'http://127.0.0.1:{CHIUSO}/ok' if guasto == 'rifiutata' else None)
        prova(f'20 la rete del giro non va ({guasto}): rosso, e GitHub non si tocca', c != 0 and not CHIAMATE and not AVVISI, (c, CHIAMATE, u))

    # 21 l'avviso di prova
    azzera()
    c, u = giro([A], '--prova')
    a = AVVISI[0] if AVVISI else {}
    prova('21 la prova: un avviso aperto e chiuso subito, chiama Marco', c == 0 and len(AVVISI) == 1 and a['state'] == 'closed' and 'Prova della vedetta' in a['title']
          and '@autuoridesign' in a['body'] and {l['name'] for l in a['labels']} == {'vedetta', 'risolto'}, (AVVISI, u))

    # 22 GitHub che rifiuta
    azzera(); sito('b', home=(403, CHIUSA)); GUASTI['api'] = True
    c, u = giro([('a', 'Alfa', {}, True), B])
    prova('22 GitHub rifiuta l\'avviso: il giro finisce in rosso', c != 0, (c, u))

    # 23 due siti giù
    azzera()
    c, u = giro([('a', 'Alfa', {}, True), ('b', 'Beta', {}, True)])
    prova('23 due siti giù: due avvisi', sorted(a['title'] for a in AVVISI) == ['Alfa: il sito non risponde', 'Beta: il sito non risponde'], (AVVISI, u))

    # 24 in corso
    azzera(); sito('a', st=stato(avvisi={'ultimo_ok': 5000, 'ultima_chiamata': 30, 'esito': 'in corso'})); sito('b', home=(403, CHIUSA), st=stato(pulizia={'ultimo_ok': 99000, 'ultima_chiamata': 1000, 'esito': 'in corso'}))
    c, u = giro([A, B])
    prova('24 «in corso» da 30 secondi: si aspetta; da un quarto d\'ora passato: «non finisce»', [a['title'] for a in AVVISI] == ['Beta: la pulizia della notte non finisce'], (AVVISI, u))

    # 25 un orologio tolto da siti.json
    azzera(); sito('a'); vecchio = avviso('orologio:posta', 'a')
    c, u = giro([A])
    prova('25 un orologio tolto dall\'elenco: il suo avviso si chiude', vecchio['state'] == 'closed', (AVVISI, u))

    # 26 stato.php 500 con «database: true»
    azzera(); sito('a'); SITI['a']['stato'] = (500, {'database': True, 'orologi': None}); sito('b', home=(403, CHIUSA))
    c, u = giro([A, B])
    prova('26 stato.php 500 anche con «database: true»: giù', len(AVVISI) == 1 and 'non dice come sta' in AVVISI[0]['title'], (AVVISI, u))

    # 27 la regola del database da sola: 200, ma «database: false»
    azzera(); sito('a'); SITI['a']['stato'] = (200, {'database': False}); sito('b', home=(403, CHIUSA))
    c, u = giro([A, B])
    prova('27 stato.php 200 ma «database: false»: giù, e lo dice', len(AVVISI) == 1 and 'database non risponde' in AVVISI[0]['body'], (AVVISI, u))

    # 28 la notte
    rifiutata = stato(pulizia={'ascolta_da': 7200, 'ultimo_ok': None, 'ultima_chiamata': None, 'ultimo_rifiuto': 600, 'esito': ''})
    azzera(); sito('b', home=(403, CHIUSA), st=rifiutata)
    c, u = giro([('a', 'Alfa', {}, True), B], ora_=oggi_alle(3))
    prova('28 alle 3 di notte: il sito giù avvisa subito, l\'orologio rifiutato aspetta', [a['title'] for a in AVVISI] == ['Alfa: il sito non risponde'], (AVVISI, u))
    c, u = giro([('a', 'Alfa', {}, True), B], ora_=oggi_alle(8))
    prova('28 alle 8: l\'avviso dell\'orologio parte', [a['title'] for a in AVVISI] == ['Alfa: il sito non risponde', 'Beta: la pulizia della notte è rifiutata'], (AVVISI, u))


# ---------------------------------------------------------------------------------------------------------------------
# I morsi: ogni rottura si scrive in una copia di vedetta.py, le prove girano su quella e il caso indicato deve diventare
# rosso. Il file vero non si tocca.
MORSI = [
    ('un tentativo solo', 'for i in range(TENTATIVI):', 'for i in range(1):', '9 '),
    ('ogni 403 è un sito su', "(c == 403 and PAGINA_CHIUSA in t)", "(c == 403)", '6 '),
    ('il database non si guarda', "j.get('database') is not True", "j.get('database') is None", '27 '),
    ('la pazienza copre anche i rifiuti', '        if recente(ok): continue', '        if recente(ok) or (ok is None and num(da) and da <= lim): continue', '11 '),
    ('si chiude anche quello che non si è guardato', 'for chiave in sorted(noti):', "for chiave in sorted(noti | {'orologi', 'orologio:avvisi', 'orologio:posta', 'orologio:pulizia'}):", '16 '),
    ('un avviso a ogni giro', '                if s in aperti: promemoria(', '                if False: promemoria(', '3 '),
    ('chiuso da Marco non conta', '                elif s in zitti:', '                elif False:', '19 '),
    ('nessuno chiama Marco', "\\n\\n@{AVVISA}\\n\\n{segno(sito, chiave)}", "\\n\\n{segno(sito, chiave)}", '2 '),
    ('la rete del giro non si guarda', "        return 2\n", "        pass\n", '20 '),
    ('un promemoria a ogni giro', '< PROMEMORIA: return', '< 0: return', '18 '),
    ('si guardano tutti gli orologi', '    for nome, minuti in attesi.items():', "    for nome, minuti in {**{n: 20 for n in OROLOGI}, **attesi}.items():", '15 '),
    ('«in corso» da poco è un avviso', "esito == 'in corso' and chiamata < 900:", "esito == 'in corso' and chiamata < 0:", '24 '),
    ('di notte gli orologi avvisano lo stesso', "elif chiave != 'sito' and notte():", 'elif False:', '28 '),
    ('di notte tace anche il sito giù', "elif chiave != 'sito' and notte():", 'elif notte():', '28 '),
]


def morsi():
    vero = VEDETTA.read_text(encoding='utf-8')
    impronta = hashlib.sha256(vero.encode()).hexdigest()
    presi = 0
    with tempfile.TemporaryDirectory() as d:
        for nome, prima, dopo, caso in MORSI:
            if vero.count(prima) != 1:
                print(f'  ??   {nome}: il pezzo da rompere non c\'è una volta sola'); continue
            copia = pathlib.Path(d) / 'vedetta.py'
            copia.write_text(vero.replace(prima, dopo), encoding='utf-8')
            r = subprocess.run([sys.executable, __file__], env={**os.environ, 'VEDETTA_FILE': str(copia)}, capture_output=True, text=True, timeout=600)
            rossi = [l.strip() for l in r.stdout.splitlines() if l.startswith('  NO')]
            visto = any(l.startswith('NO   ' + caso) for l in rossi)
            presi += r.returncode != 0 and visto
            print(('  MORDE ' if r.returncode != 0 and visto else '  NON MORDE ') + f'{nome} (deve vederlo il {caso.strip()}): ' + (rossi[0][:140] if rossi else 'tutto verde'))
    ok = hashlib.sha256(VEDETTA.read_text(encoding='utf-8').encode()).hexdigest() == impronta
    print(f'\n{presi} morsi su {len(MORSI)}' + ('' if ok else '  ← vedetta.py È CAMBIATO'))
    return presi == len(MORSI) and ok


if __name__ == '__main__':
    if '--morsi' in sys.argv:
        sys.exit(0 if morsi() else 1)
    casi()
    print(f'\n{sum(esiti)} su {len(esiti)}' + ('' if all(esiti) else '  ← ROSSO'))
    sys.exit(0 if all(esiti) else 1)
