# La vedetta

Guarda da fuori i siti di addiplatform e avvisa Marco se **un sito cade** o **un orologio si ferma** (i lavori che il
pannello di Ergonet fa partire a orario: gli avvisi, la lettura della posta, la pulizia della notte).

Gira su GitHub ogni 10 minuti, fuori da Ergonet: se cade il server dei siti, la vedetta no. Gratis (il repository è
pubblico), nessun abbonamento.

## Cosa guarda

Per ogni sito di `siti.json`:

1. la prima pagina risponde (anche chiusa con la password);
2. `/api/stato.php` dice che il database risponde;
3. gli orologi che quel sito deve avere sono finiti bene di recente. Se no, dice perché: fermo, rifiutato (la chiave
   sbagliata nel pannello di Ergonet), finito con un errore, interrotto a metà, mai partito.

Un sito che non risponde si riprova 3 volte, a 15 secondi l'una dall'altra: un singhiozzo non è un avviso.

## Come arrivano gli avvisi

Ogni problema è un avviso (una «issue» di questo repository): GitHub manda l'**email** a Marco, e la notifica sull'app
GitHub del telefono se c'è. Uno solo per problema: finché c'è, resta aperto (un promemoria al giorno); quando passa, la
vedetta scrive «tornato a posto» e lo chiude da sola.

- **Di notte** (dalle 22 alle 8) un sito giù avvisa subito; un orologio fermo aspetta le 8 (è un problema lento).
- **Una cosa voluta?** Chiudi tu l'avviso: la vedetta non lo riapre per 7 giorni.
- **La vedetta stessa non può lavorare** (la sua rete, GitHub): il giro finisce in rosso e GitHub manda la sua email
  «Run failed». Anche questo è un avviso.
- **Provare che le email arrivano**: Actions → Vedetta → Run workflow → spunta «prova». Arriva un avviso di prova, già
  chiuso.

## Aggiungere un sito o un orologio

In `siti.json`: il nome, l'indirizzo, e gli orologi che il pannello di Ergonet deve chiamare con i minuti oltre i quali
sono fermi (avvisi e posta ogni 5 minuti: 20; pulizia una volta al giorno: 1560, cioè 26 ore). Un orologio che non è
nell'elenco non si guarda. Il sito deve avere `/api/stato.php` (addiplatform dal 18/10/26).

## Le prove

    python3 prova_vedetta.py            34 prove con siti e GitHub finti, nessuna rete vera (~8 secondi)
    python3 prova_vedetta.py --morsi    14 rotture di vedetta.py: ognuna deve far diventare rosso il suo caso

Girano anche su GitHub a ogni modifica (Actions → Prove).
