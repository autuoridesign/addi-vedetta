#!/usr/bin/env python3
"""Le prove del campanello: un GitHub finto e un cron-job.org finto sul computer, nessuna rete vera (21/10/26).

Ogni caso prepara i due servizi finti, fa lavorare campanello.py VERO con due chiavi inventate e guarda cosa ha chiesto:

  1 il primo giro: un giro della vedetta fatto partire con la chiave, poi su cron-job.org UN campanello nuovo, com'è giusto
    (l'indirizzo di GitHub, POST, la chiave di GitHub, {"ref": "main"}, i minuti 3…53 di ogni ora, le email)
  2 di nuovo con una chiave nuova di GitHub: lo stesso campanello aggiornato, nessuno nuovo
  3 GitHub non riconosce la chiave: si ferma, cron-job.org non si tocca   4 la chiave non vede addi-vedetta
  5 la chiave senza il permesso di far partire la vedetta                  6 cron-job.org non riconosce la sua chiave
  7 le chiavi invertite: nessuna chiave parte                              8 una chiave «classic» di GitHub: si ferma
  9 un altro lavoro di Marco su cron-job.org non si tocca                 10 i servizi ripetono le chiavi: non si stampano
 11 due campanelli uguali: si aggiorna il primo e lo dice                 12 rileggendolo non è come deve essere: rosso
 13 GitHub non risponde (la rete del Mac): si ferma

  python3 prova_campanello.py            le prove (~1 s)
  python3 prova_campanello.py --morsi    ogni rottura di campanello.py deve far diventare rosso il caso che la deve vedere
"""
import contextlib, hashlib, http.server, io, json, os, pathlib, re, socket, subprocess, sys, tempfile, threading, types

QUI = pathlib.Path(__file__).resolve().parent
CAMPANELLO = pathlib.Path(os.environ.get('CAMPANELLO_FILE') or QUI / 'campanello.py')
CRON, GH, GH2 = 'chiave-cron-INVENTATA-1234', 'github_pat_INVENTATA_5678', 'github_pat_NUOVA_INVENTATA_9012'
SUONO = 'https://api.github.com/repos/autuoridesign/addi-vedetta/actions/workflows/vedetta.yml/dispatches'
esiti, uscite = [], []


def prova(nome, ok, dettaglio=''):
    esiti.append(bool(ok))
    print(('  OK   ' if ok else '  NO   ') + nome + ('' if ok else f'  ← {str(dettaglio)[:300]}'))


# ---- i due servizi finti -------------------------------------------------------------------------------------------
LAVORI = {}        # i lavori di cron-job.org: numero → lavoro
CHIAMATE = []      # (servizio, metodo, percorso, Authorization, dati)
GUASTI = {}        # 'github': codice del «Run workflow»; 'cron': codice di GET /jobs; 'rilettura': campi cambiati


class Finto(http.server.BaseHTTPRequestHandler):
    servizio = ''
    def log_message(self, *a): pass

    def rispondi(self, codice, corpo=None):
        b = b'' if corpo is None else json.dumps(corpo).encode()
        self.send_response(codice); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b))); self.end_headers()
        self.wfile.write(b)

    def do_GET(self): self.giro('GET')
    def do_POST(self): self.giro('POST')
    def do_PUT(self): self.giro('PUT')
    def do_PATCH(self): self.giro('PATCH')

    def giro(self, metodo):
        n = int(self.headers.get('Content-Length') or 0)
        dati = json.loads(self.rfile.read(n)) if n else None
        chiave = self.headers.get('Authorization', '')
        CHIAMATE.append((self.servizio, metodo, self.path, chiave, dati))
        (self.github if self.servizio == 'github' else self.cron)(metodo, chiave, dati)

    def github(self, metodo, chiave, dati):
        if metodo != 'POST' or self.path != '/repos/autuoridesign/addi-vedetta/actions/workflows/vedetta.yml/dispatches':
            return self.rispondi(404, {'message': 'Not Found'})
        c = GUASTI.get('github', 204)
        if c == 204 and chiave not in (f'Bearer {GH}', f'Bearer {GH2}'): c = 401
        # il finto ripete la chiave nel suo messaggio: non deve arrivare sullo schermo (caso 10)
        self.rispondi(c, None if c == 204 else {'message': f'rifiutata: {chiave}'})

    def cron(self, metodo, chiave, dati):
        if chiave != f'Bearer {CRON}': return self.rispondi(401, {'error': f'chiave sconosciuta: {chiave}'})
        if metodo == 'GET' and self.path == '/jobs':
            if GUASTI.get('cron'): return self.rispondi(GUASTI['cron'], {'error': f'no ({chiave})'})
            return self.rispondi(200, {'jobs': [{'jobId': k, 'url': v['url'], 'title': v.get('title', ''), 'enabled': v.get('enabled')} for k, v in LAVORI.items()], 'someFailed': False})
        if metodo == 'PUT' and self.path == '/jobs':
            k = max(LAVORI, default=100) + 1
            LAVORI[k] = dati['job']
            return self.rispondi(200, {'jobId': k})
        m = re.fullmatch(r'/jobs/(\d+)', self.path)
        if m and int(m[1]) in LAVORI:
            k = int(m[1])
            if metodo == 'PATCH':
                LAVORI[k] = {**LAVORI[k], **dati['job']}
                return self.rispondi(200, {})
            if metodo == 'GET':
                return self.rispondi(200, {'jobDetails': {**LAVORI[k], 'jobId': k, 'nextExecution': 1_800_000_000, **GUASTI.get('rilettura', {})}})
        self.rispondi(404, {'error': 'non c\'è'})


def servizio(nome):
    gestore = type(f'Finto_{nome}', (Finto,), {'servizio': nome})
    s = http.server.ThreadingHTTPServer(('127.0.0.1', 0), gestore)
    threading.Thread(target=s.serve_forever, daemon=True).start()
    return f'http://127.0.0.1:{s.server_address[1]}'


os.environ['CAMPANELLO_GITHUB'] = servizio('github')
os.environ['CAMPANELLO_CRONJOB'] = servizio('cron')
# ⚠️ campanello.py si legge e si compila ogni volta, senza import: Python tiene da parte il file compilato e lo riconosce
# dall'ora (al secondo) e dalla lunghezza, e due rotture lunghe uguali scritte nello stesso secondo facevano girare la
# rottura di prima (visto il 21/10/26: due «non morde» falsi).
cp = types.ModuleType('campanello'); cp.__file__ = str(CAMPANELLO)
exec(compile(CAMPANELLO.read_text(encoding='utf-8'), str(CAMPANELLO), 'exec'), cp.__dict__)


def giro(chiave_cron=CRON, chiave_github=GH):
    CHIAMATE.clear()
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        codice = cp.principale(chiave_cron, chiave_github)
    uscite.append(out.getvalue())
    return codice, out.getvalue()


def azzera(**guasti):
    LAVORI.clear(); GUASTI.clear(); GUASTI.update(guasti)


def di(servizio): return [c for c in CHIAMATE if c[0] == servizio]
def nostri(): return [v for v in LAVORI.values() if v['url'] == SUONO]


def com_e_giusto(j, chiave):
    s, x, n = j.get('schedule', {}), j.get('extendedData', {}), j.get('notification', {})
    return (j.get('url') == SUONO and j.get('enabled') is True and j.get('requestMethod') == 1
            and s.get('minutes') == [3, 13, 23, 33, 43, 53] and s.get('hours') == [-1] and s.get('mdays') == [-1]
            and s.get('months') == [-1] and s.get('wdays') == [-1] and s.get('timezone') == 'Europe/Rome'
            and x.get('headers', {}).get('Authorization') == f'Bearer {chiave}' and json.loads(x.get('body') or 'null') == {'ref': 'main'}
            and n.get('onFailure') is True and n.get('onDisable') is True)


def casi():
    # 1 il primo giro
    azzera()
    c, u = giro()
    g = di('github')
    prova('1 il giro di prova: un «Run workflow» della vedetta, con la chiave di GitHub e {"ref": "main"}',
          len(g) == 1 and g[0][3] == f'Bearer {GH}' and g[0][4] == {'ref': 'main'}, (CHIAMATE, u))
    prova('1 su cron-job.org UN campanello nuovo, com\'è giusto', c == 0 and len(LAVORI) == 1 and com_e_giusto(nostri()[0], GH)
          and [m for _, m, *_ in di('cron')].count('PUT') == 1, (c, LAVORI, u))
    prova('1 lo dice: creato, ogni 10 minuti, il primo suono', 'creato' in u and '3, 13, 23, 33, 43 e 53' in u and 'il primo suono alle' in u, u)

    # 2 di nuovo, con la chiave nuova
    c, u = giro(chiave_github=GH2)
    prova('2 di nuovo con una chiave nuova: lo stesso campanello aggiornato, nessuno nuovo',
          c == 0 and len(LAVORI) == 1 and com_e_giusto(nostri()[0], GH2) and 'PUT' not in [m for _, m, *_ in di('cron')] and 'aggiornato' in u, (c, LAVORI, u))

    # 3, 4, 5 GitHub rifiuta la chiave
    for caso, codice, parole in (('3', 401, 'non la riconosce'), ('4', 404, 'Only select repositories'), ('5', 403, 'Read and write')):
        azzera(github=codice)
        c, u = giro()
        prova(f'{caso} GitHub risponde {codice}: si ferma, lo spiega, e cron-job.org non si tocca',
              c == 1 and parole in u and not di('cron') and not LAVORI and 'Non ho toccato cron-job.org' in u, (c, CHIAMATE, u))

    # 6 cron-job.org non riconosce la sua chiave
    azzera()
    c, u = giro(chiave_cron='un-altra-chiave-INVENTATA')
    prova('6 cron-job.org rifiuta la sua chiave: rosso, lo spiega, nessun campanello', c == 1 and 'non riconosce la sua chiave' in u
          and not LAVORI and [m for _, m, *_ in di('cron')] == ['GET'], (c, CHIAMATE, u))

    # 7, 8 le chiavi sbagliate non partono nemmeno
    azzera()
    c, u = giro(chiave_cron=GH, chiave_github=CRON)
    prova('7 le chiavi invertite: si ferma prima di mandarle a qualcuno', c == 1 and 'invertite' in u and not CHIAMATE, (c, CHIAMATE, u))
    c, u = giro(chiave_github='ghp_CLASSIC_INVENTATA')
    prova('8 una chiave «classic»: si ferma prima di mandarla a qualcuno', c == 1 and 'classic' in u and not CHIAMATE, (c, CHIAMATE, u))

    # 9 un altro lavoro di Marco
    azzera()
    LAVORI[7] = {'url': 'https://esempio.it/un-altro-lavoro', 'title': 'suo', 'enabled': True}
    c, u = giro()
    prova('9 un altro lavoro su cron-job.org non si tocca, il campanello nasce accanto', c == 0 and LAVORI[7] == {'url': 'https://esempio.it/un-altro-lavoro', 'title': 'suo', 'enabled': True}
          and len(nostri()) == 1 and not any(m == 'PATCH' and p == '/jobs/7' for _, m, p, *_ in di('cron')), (LAVORI, u))

    # 11 due campanelli uguali
    azzera()
    LAVORI[201] = {'url': SUONO, 'title': 'uno'}; LAVORI[202] = {'url': SUONO, 'title': 'due'}
    c, u = giro()
    prova('11 due campanelli uguali: si aggiorna il primo e lo dice', c == 0 and com_e_giusto(LAVORI[201], GH) and LAVORI[202] == {'url': SUONO, 'title': 'due'}
          and 'uguali sono 2' in u, (LAVORI, u))

    # 12 rileggendolo non è come deve essere
    azzera(rilettura={'requestMethod': 0})
    c, u = giro()
    prova('12 cron-job.org lo salva diverso (GET invece di POST): rosso, e lo dice', c == 1 and 'non è come deve essere' in u, (c, u))

    # 13 GitHub non risponde
    azzera()
    s = socket.socket(); s.bind(('127.0.0.1', 0)); chiusa = f'http://127.0.0.1:{s.getsockname()[1]}'; s.close()
    vero, cp.GITHUB = cp.GITHUB, chiusa
    try: c, u = giro()
    finally: cp.GITHUB = vero
    prova('13 GitHub non risponde: si ferma e lo dice, cron-job.org non si tocca', c == 1 and 'non risponde' in u and not di('cron') and not LAVORI, (c, CHIAMATE, u))

    # 10 in nessun giro una chiave è arrivata sullo schermo (i finti le ripetono nei loro messaggi: 3, 4, 5, 6)
    chiavi = (CRON, GH, GH2, 'un-altra-chiave-INVENTATA', 'ghp_CLASSIC_INVENTATA')
    trovate = [k for k in chiavi for t in uscite if k in t]
    prova(f'10 le chiavi non si stampano mai ({len(uscite)} giri, anche quando i servizi le ripetono)', not trovate and any('***' in t for t in uscite), trovate)


# ---------------------------------------------------------------------------------------------------------------------
# I morsi: ogni rottura si scrive in una copia di campanello.py, le prove girano su quella e il caso indicato deve diventare
# rosso. Il file vero non si tocca.
MORSI = [
    ('il campanello senza la chiave di GitHub', "'Authorization': f'Bearer {chiave_github}', 'Accept'", "'Authorization': 'Bearer ', 'Accept'", '1 '),
    ('ogni ora invece che ogni 10 minuti', 'MINUTI = [3, 13, 23, 33, 43, 53]', 'MINUTI = [3]', '1 '),
    ('il campanello che chiama con GET', "'requestMethod': 1,", "'requestMethod': 0,", '1 '),
    ('ogni volta un campanello nuovo', '    if uguali:', '    if False:', '2 '),
    ('GitHub rifiuta ma si va avanti', '    if not prova_github(chiave_github): return 1', '    prova_github(chiave_github)', '3 '),
    ('si aggiorna anche un lavoro che non è il nostro', "if j.get('url') == SUONO]", 'if True]', '9 '),
    ('le chiavi si stampano', "    for s in SEGRETI: testo = testo.replace(s, '***')", '    pass', '10 '),
    ('le chiavi invertite partono lo stesso', "    if chiave_cronjob.startswith(('github_pat_', 'ghp_')):", '    if False:', '7 '),
    ('non si rilegge', "    giusto = (j.get('enabled') is True", "    giusto = True or (j.get('enabled') is True", '12 '),
]


def morsi():
    vero = CAMPANELLO.read_text(encoding='utf-8')
    impronta = hashlib.sha256(vero.encode()).hexdigest()
    presi = 0
    with tempfile.TemporaryDirectory() as d:
        for nome, prima, dopo, caso in MORSI:
            if vero.count(prima) != 1:
                print(f'  ??   {nome}: il pezzo da rompere non c\'è una volta sola'); continue
            copia = pathlib.Path(d) / 'campanello.py'
            copia.write_text(vero.replace(prima, dopo), encoding='utf-8')
            r = subprocess.run([sys.executable, __file__], env={**os.environ, 'CAMPANELLO_FILE': str(copia)}, capture_output=True, text=True, timeout=120)
            rossi = [l.strip() for l in r.stdout.splitlines() if l.startswith('  NO')]
            visto = any(l.startswith('NO   ' + caso) for l in rossi)
            presi += r.returncode != 0 and visto
            print(('  MORDE ' if r.returncode != 0 and visto else '  NON MORDE ') + f'{nome} (deve vederlo il {caso.strip()}): ' + (rossi[0][:140] if rossi else 'tutto verde'))
    ok = hashlib.sha256(CAMPANELLO.read_text(encoding='utf-8').encode()).hexdigest() == impronta
    print(f'\n{presi} morsi su {len(MORSI)}' + ('' if ok else '  ← campanello.py È CAMBIATO'))
    return presi == len(MORSI) and ok


if __name__ == '__main__':
    if '--morsi' in sys.argv:
        sys.exit(0 if morsi() else 1)
    casi()
    print(f'\n{sum(esiti)} su {len(esiti)}' + ('' if all(esiti) else '  ← ROSSO'))
    sys.exit(0 if all(esiti) else 1)
