#!/usr/bin/env python3
"""Il campanello della vedetta: cron-job.org la fa partire davvero ogni 10 minuti (21/10/26).

L'orario di GitHub (vedetta.yml) non basta: GitHub fa partire gli orari quando ha posto, e dal 19/10/26 la vedetta partiva
ogni 2,5-6,5 ore invece che ogni 10 minuti. cron-job.org (gratis, nessun abbonamento) suona al minuto giusto: ogni 10 minuti
chiede a GitHub di far partire la vedetta adesso, come il pulsante «Run workflow». L'orario di GitHub resta di riserva, se un
giorno il campanello tace.

Si lancia una volta sul Mac (e di nuovo solo per cambiare una chiave):
  1. chiede le due chiavi senza mostrarle: quella di cron-job.org e quella di GitHub, che può solo far partire la vedetta;
  2. prova la chiave di GitHub facendo partire un giro adesso: se non va, si ferma senza toccare cron-job.org;
  3. su cron-job.org crea il campanello, o lo aggiorna se c'è già (lo riconosce dall'indirizzo che chiama): ai minuti 3, 13,
     23, 33, 43 e 53 di ogni ora, con un'email a Marco se GitHub lo rifiuta 3 volte di fila (la chiave cancellata), quando
     torna a posto e se cron-job.org lo spegne.
Le chiavi non si scrivono da nessuna parte sul Mac e non si stampano: quella di GitHub resta solo su cron-job.org.

  python3 campanello.py
Le prove: python3 prova_campanello.py (GitHub e cron-job.org finti, sul computer).
"""
import datetime, getpass, json, os, sys, urllib.error, urllib.request
from zoneinfo import ZoneInfo

REPO = 'autuoridesign/addi-vedetta'
GIRO = 'vedetta.yml'
GITHUB = os.environ.get('CAMPANELLO_GITHUB', 'https://api.github.com').rstrip('/')
CRONJOB = os.environ.get('CAMPANELLO_CRONJOB', 'https://api.cron-job.org').rstrip('/')
# quello che il campanello chiama a ogni suono (il «Run workflow» di GitHub): è anche il segno per ritrovarlo su cron-job.org
SUONO = f'https://api.github.com/repos/{REPO}/actions/workflows/{GIRO}/dispatches'
MINUTI = [3, 13, 23, 33, 43, 53]        # gli stessi dell'orario di riserva in vedetta.yml: lontano dall'inizio dell'ora
ROMA = ZoneInfo('Europe/Rome')
SEGRETI = []                            # le due chiavi: tolte da tutto quello che si stampa, anche dai messaggi dei servizi


def di(testo=''):
    for s in SEGRETI: testo = testo.replace(s, '***')
    print(testo, flush=True)


def chiama(base, metodo, percorso, chiave, dati=None):
    """(codice, risposta letta), o (None, il perché) se il servizio non risponde."""
    testa = {'Authorization': f'Bearer {chiave}', 'Content-Type': 'application/json', 'User-Agent': 'addi-vedetta-campanello'}
    if base == GITHUB: testa |= {'Accept': 'application/vnd.github+json', 'X-GitHub-Api-Version': '2022-11-28'}
    r = urllib.request.Request(base + percorso, method=metodo, headers=testa, data=None if dati is None else json.dumps(dati).encode())
    try:
        with urllib.request.urlopen(r, timeout=30) as h:
            c, b = h.status, h.read()
    except urllib.error.HTTPError as e:
        c, b = e.code, e.read()
    except Exception as e:      # la rete del Mac, il nome che non si trova, il tempo scaduto
        return None, str(getattr(e, 'reason', e))
    try: return c, (json.loads(b) if b else {})
    except ValueError: return c, {}


def detto(r):
    """Le parole del servizio, se ci sono, per capire un rifiuto."""
    m = isinstance(r, dict) and (r.get('message') or r.get('error'))
    return f' (dice: «{str(m)[:200]}»)' if m else ''


def prova_github(chiave):
    """Fa partire un giro della vedetta con la chiave: True se GitHub l'accetta."""
    c, r = chiama(GITHUB, 'POST', f'/repos/{REPO}/actions/workflows/{GIRO}/dispatches', chiave, {'ref': 'main'})
    if c is not None and 200 <= c < 300:
        di('✅ La chiave di GitHub va: è partito un giro della vedetta (lo vedi in Actions).')
        return True
    perche = {None: f'GitHub non risponde ({r}): la rete del Mac?',
              401: 'GitHub non la riconosce: copiata male o cancellata. Rifalla col link e rilancia.',
              403: 'GitHub dice che non può far partire la vedetta: nel link, alla voce «Actions», ci vuole «Read and write».',
              404: 'GitHub dice che non vede addi-vedetta: alla voce «Repository access» scegli «Only select repositories» e poi addi-vedetta.',
              422: 'GitHub non la fa partire: la vedetta è spenta su GitHub? (Actions, Vedetta, «Enable workflow»)'}
    di('❌ La chiave di GitHub non va. ' + perche.get(c, f'GitHub risponde {c}.') + ('' if c is None else detto(r)))
    di('   Non ho toccato cron-job.org.')
    return False


def campanello(chiave_github):
    """Il lavoro di cron-job.org: ogni 10 minuti il «Run workflow» della vedetta, con la chiave di GitHub."""
    return {'url': SUONO, 'title': 'La vedetta di addiplatform, ogni 10 minuti', 'enabled': True, 'saveResponses': False,
            'requestMethod': 1,                                    # POST
            'schedule': {'timezone': 'Europe/Rome', 'expiresAt': 0, 'hours': [-1], 'mdays': [-1], 'minutes': MINUTI, 'months': [-1], 'wdays': [-1]},
            # un rifiuto solo può essere un singhiozzo di GitHub: l'email dopo 3 di fila (mezz'ora)
            'notification': {'onFailure': True, 'onFailureCount': 3, 'onSuccess': True, 'onDisable': True},
            'extendedData': {'headers': {'Authorization': f'Bearer {chiave_github}', 'Accept': 'application/vnd.github+json',
                                         'X-GitHub-Api-Version': '2022-11-28', 'Content-Type': 'application/json'},
                             'body': json.dumps({'ref': 'main'})}}


def rifiuto_cronjob(c, r):
    return '❌ cron-job.org ' + {None: f'non risponde ({r}): la rete del Mac?',
                                401: 'non riconosce la sua chiave: copiala di nuovo (Settings, API) e rilancia.',
                                403: 'rifiuta la chiave da qui: se alla chiave hai messo un limite di indirizzi IP, toglilo.',
                                429: 'dice che per oggi le richieste sono finite (ne dà 100 al giorno): riprova domani.'}.get(c, f'risponde {c}.') + ('' if c is None else detto(r))


def prepara_cronjob(chiave, chiave_github):
    c, r = chiama(CRONJOB, 'GET', '/jobs', chiave)
    if c != 200:
        di(rifiuto_cronjob(c, r)); return False
    uguali = [j for j in r.get('jobs') or [] if j.get('url') == SUONO]
    if uguali:
        n, fatto = uguali[0].get('jobId'), 'aggiornato'
        c, r = chiama(CRONJOB, 'PATCH', f'/jobs/{n}', chiave, {'job': campanello(chiave_github)})
    else:
        c, r = chiama(CRONJOB, 'PUT', '/jobs', chiave, {'job': campanello(chiave_github)})
        n, fatto = (r.get('jobId') if isinstance(r, dict) else None), 'creato'
    if c is None or not 200 <= c < 300 or not n:
        di(rifiuto_cronjob(c, r)); return False
    # si rilegge com'è davvero su cron-job.org (le intestazioni, dove c'è la chiave di GitHub, non si guardano)
    c, r = chiama(CRONJOB, 'GET', f'/jobs/{n}', chiave)
    j = r.get('jobDetails') if c == 200 and isinstance(r, dict) else None
    if not isinstance(j, dict):
        di(f'⚠️ Il campanello è {fatto} su cron-job.org (n. {n}), ma non riesco a rileggerlo: guardalo sul sito, in Cronjobs.')
        return True
    s = j.get('schedule') or {}
    giusto = (j.get('enabled') is True and j.get('url') == SUONO and j.get('requestMethod') == 1
              and sorted(s.get('minutes') or []) == MINUTI and s.get('hours') == [-1])
    if not giusto:
        di(f'❌ Il campanello è {fatto} su cron-job.org (n. {n}), ma rileggendolo non è come deve essere: guardalo sul sito, in Cronjobs.')
        return False
    t = j.get('nextExecution')
    prossimo = f'; il primo suono alle {datetime.datetime.fromtimestamp(t, ROMA):%H:%M}' if isinstance(t, int) and t > 0 else ''
    di(f'✅ Il campanello è {fatto} su cron-job.org (n. {n}): suona ai minuti 3, 13, 23, 33, 43 e 53 di ogni ora{prossimo}.')
    if len(uguali) > 1:
        di(f'⚠️ Su cron-job.org i campanelli uguali sono {len(uguali)}: ho {fatto} il primo, gli altri cancellali dal sito (Cronjobs), sennò la vedetta parte due volte.')
    return True


def principale(chiave_cronjob, chiave_github):
    SEGRETI[:] = [k for k in (chiave_cronjob, chiave_github) if k]
    # prima di mandare una chiave a qualcuno: sono quelle giuste, al posto giusto?
    if chiave_cronjob.startswith(('github_pat_', 'ghp_')):
        di('❌ Le chiavi sono invertite: prima quella di cron-job.org, poi quella di GitHub. Non ho fatto niente.'); return 1
    if chiave_github.startswith('ghp_'):
        di('❌ Questa è una chiave «classic» di GitHub, che apre tutti i tuoi repository: fai quella del link (comincia con github_pat_). Non ho fatto niente.'); return 1
    if not prova_github(chiave_github): return 1
    return 0 if prepara_cronjob(chiave_cronjob, chiave_github) else 1


def chiedi(domanda):
    for _ in range(3):
        v = getpass.getpass(domanda).strip()
        if v: return v
        print('   Vuota: incollala di nuovo.')
    sys.exit('Niente chiave: non ho fatto niente.')


if __name__ == '__main__':
    print('Il campanello della vedetta. Le chiavi non si vedono mentre le incolli: è normale, poi premi Invio.\n')
    a = chiedi('La chiave di cron-job.org: ')
    b = chiedi('La chiave di GitHub (comincia con github_pat_): ')
    sys.exit(principale(a, b))
