# Local Docker Proxy

Reverse proxy locale basato su [Traefik](https://traefik.io/), utilizzato per esporre i progetti di sviluppo tramite domini `.localhost` e HTTPS, senza dover installare PHP o altri runtime direttamente sul sistema host.

Insieme al proxy viene avviata una **dashboard** (`https://dashboard.localhost`) che mostra una card per ogni progetto configurato in `domains.txt`, con il suo stato, i collegamenti rapidi e la directory del progetto.

## Requisiti

- Docker Engine e Docker Compose
- `mkcert` per generare certificati HTTPS attendibili
- Una rete Docker condivisa chiamata `web`

## Architettura

Traefik è il punto di ingresso comune per i progetti locali.

- HTTP (`80`): reindirizza automaticamente a HTTPS.
- HTTPS (`443`): gestisce le connessioni TLS.
- Docker provider: individua i container configurati con le label Traefik.
- File provider: carica la configurazione TLS.
- Certificati: conservati localmente nella directory `certs/`.

Ogni progetto mantiene il proprio `docker-compose.yaml` e può essere avviato o arrestato indipendentemente dal proxy.

La dashboard è un servizio separato (`dashboard`) definito nello stesso `docker-compose.yaml` di Traefik. È un piccolo server Python (solo libreria standard) eseguito in un container: sul sistema host non serve alcun runtime. Non pubblica porte sull'host, non usa il socket Docker ed è raggiungibile solo tramite Traefik.

## Struttura

```text
proxy/
├── docker-compose.yaml
├── traefik.yaml
├── dynamic.yaml
├── domains.txt
├── generate-cert.sh
├── certs/
│   ├── local-cert.pem
│   └── local-key.pem
├── dashboard/
│   ├── Dockerfile
│   ├── app.py
│   ├── index.html
│   ├── app.js
│   └── style.css
└── README.md
```

## Avvio

La rete Docker condivisa viene creata una sola volta:

```bash
docker network create web
```

Se esiste già, non è necessario ricrearla.

Avviare Traefik e la dashboard:

```bash
docker compose up -d --build
```

Verificare lo stato:

```bash
docker compose ps
docker compose logs -f traefik
docker compose logs -f dashboard
```

I container utilizzano la policy `restart: unless-stopped`, quindi ripartono automaticamente all'avvio di Docker, purché non siano stati arrestati esplicitamente.

## Configurazione dei domini (`domains.txt`)

`domains.txt` è l'unico file di configurazione dei progetti. Viene letto sia da `generate-cert.sh` (per il certificato) sia dalla dashboard (per le card).

Ogni riga ha questo formato, con tutti i campi dopo il dominio facoltativi:

```text
dominio | Nome | etichetta | rotte | directory
```

| Campo | Descrizione |
|---|---|
| `dominio` | Dominio completo, ad esempio `app.example.localhost`. |
| `Nome` | Nome mostrato nella card. |
| `etichetta` | Categoria della card, usata per filtri e ordinamento. |
| `rotte` | Link rapidi relativi al sito, separati da virgola: `/percorso Etichetta, /altro Altra etichetta`. Il primo spazio separa il percorso dall'etichetta, che se manca diventa il percorso stesso. |
| `directory` | Directory del progetto. Deve iniziare con `/` o `~`; viene mostrata nella card e copiata negli appunti al click, esattamente come scritta. |

Per saltare un campo intermedio lasciarlo vuoto:

```text
ricettario.localhost | | | | ~/Projects/ricettario
```

Esempio completo:

```text
# dominio | Nome | etichetta | rotte (/percorso Etichetta, ...) | directory
# localhost e dashboard.localhost sono aggiunti da generate-cert.sh
app.example.localhost | Example APP | example | /example Pagina di esempio | ~/Projects/app
ricettario.localhost
```

Regole generali:

- Le righe vuote e i commenti preceduti da `#` vengono ignorati (anche a fine riga). Per questo il carattere `#` non può comparire in rotte, nomi o directory.
- I domini con caratteri jolly (`*`) e quelli non validi vengono ignorati dalla dashboard.
- I percorsi delle rotte non possono contenere spazi né virgole. Sono sempre accodati a `https://<dominio>`, quindi non possono puntare a un host diverso.
- `localhost` e `dashboard.localhost` non vanno scritti: li aggiunge sempre `generate-cert.sh`.

### Nome ed etichetta automatici

Se nome ed etichetta non sono indicati, vengono ricavati dal dominio, senza il suffisso `.localhost`: il primo segmento diventa il nome e i segmenti successivi l'etichetta.

| Dominio | Nome | Etichetta |
|---|---|---|
| `app.example.localhost` | App | example |
| `ricettario.localhost` | Ricettario | nessuna |
| `other-app.localhost` | Other App | nessuna |
| `api.shop.localhost` | Api | shop |

I valori scritti a mano hanno sempre la precedenza e si applicano in modo indipendente: si può indicare solo il nome e lasciare l'etichetta automatica, o viceversa.

## Gestione dei certificati HTTPS

Il certificato locale include i domini presenti in `domains.txt` più quelli di base (`localhost` e `dashboard.localhost`), che lo script aggiunge sempre. Eventuali duplicati vengono eliminati.

### Generare o aggiornare il certificato

```bash
./generate-cert.sh
```

Lo script:

1. Legge i domini da `domains.txt`, considerando solo il primo campo di ogni riga.
2. Ignora commenti e righe vuote.
3. Aggiunge i domini di base ed elimina i duplicati.
4. Genera il certificato e la chiave con `mkcert`.
5. Riavvia Traefik per caricare il nuovo certificato.

I file vengono salvati in:

```text
certs/local-cert.pem
certs/local-key.pem
```

La CA locale di `mkcert` deve essere installata sul sistema per evitare avvisi di certificato non attendibile.

**Importante:** quando aggiungi o rimuovi domini, rigenera il certificato. Il certificato generato contiene soltanto i nomi specificati al momento della generazione. Se modifichi solo nome, etichetta, rotte o directory di un dominio già presente, la rigenerazione non è necessaria.

La chiave privata non deve essere condivisa o pubblicata.

## Aggiungere un progetto

Ogni progetto deve:

1. Avere un proprio file Compose.
2. Collegarsi alla rete Docker esterna `web`.
3. Dichiarare le label Traefik necessarie.
4. Essere raggiungibile da Traefik sulla porta interna corretta.
5. Avere il proprio dominio aggiunto a `domains.txt`, con eventuali nome, etichetta, rotte e directory.

Esempio di configurazione Compose:

```yaml
services:
  app:
    image: nginx:alpine
    networks:
      - web
    labels:
      - "traefik.enable=true"
      - "traefik.docker.network=web"
      - "traefik.http.routers.example.rule=Host(`example.localhost`)"
      - "traefik.http.routers.example.entrypoints=websecure"
      - "traefik.http.routers.example.tls=true"
      - "traefik.http.services.example.loadbalancer.server.port=80"

networks:
  web:
    external: true
```

Adatta il nome del servizio, il dominio, il nome del router e la porta interna al progetto reale.

Dopo aver aggiunto il dominio a `domains.txt`, aggiorna il certificato:

```bash
./generate-cert.sh
```

Avvia quindi il progetto dalla sua directory:

```bash
docker compose up -d
```

Il progetto sarà raggiungibile tramite:

```text
https://example.localhost
```

La card compare nella dashboard entro pochi secondi, senza modificare il codice. Non è necessario pubblicare la porta dell'applicazione sull'host: il traffico passa attraverso la rete Docker condivisa.

## Dashboard

La dashboard è raggiungibile su:

```text
https://dashboard.localhost
```

### Cosa mostra

- Una griglia responsive di card, una per dominio di `domains.txt`.
- Ogni card riporta nome, dominio, stato, etichetta (se presente), i link alle rotte configurate, il pulsante **Apri** per la radice del sito e la directory del progetto (se definita). La card non è cliccabile nel suo insieme: si usano i link e i pulsanti al suo interno.
- Nell'intestazione, l'indicatore dello stato del proxy e il conteggio dei progetti online.
- Se almeno un progetto ha un'etichetta, filtri cliccabili in testata: "Tutti", "Senza etichetta" e una voce per etichetta. Il filtro scelto viene ricordato dal browser.
- Le card sono ordinate per etichetta (prima quelle senza) e, a parità di etichetta, per nome.
- Un clic sulla directory copia il percorso negli appunti (funziona perché la pagina è servita in HTTPS su un dominio `.localhost`).
- La pagina si aggiorna da sola ogni 8 secondi.

### Come viene determinato lo stato

La dashboard non usa il socket Docker. Il suo backend si collega a Traefik con SNI e `Host` del dominio e interpreta la risposta:

| Risposta | Stato |
|---|---|
| `404` con corpo esatto `404 page not found` (risposta interna di Traefik per un router inesistente) | **Offline**: container spento o senza label Traefik |
| `502`, `503` o `504` | **Errore**: il router esiste ma il backend non risponde |
| Qualsiasi altra risposta (anche `401`, `404` dell'applicazione, redirect) | **Online** |
| Connessione a Traefik non riuscita | **Sconosciuto**, proxy segnalato come non raggiungibile |

Un progetto spento intenzionalmente risulta quindi semplicemente offline, e un errore HTTP dell'applicazione non viene scambiato per un container fermo. L'unico caso limite è un'applicazione che risponda esattamente con il `404` testuale di Traefik: verrebbe letta come offline.

### Variabili d'ambiente

Si impostano nella sezione `environment` del servizio `dashboard` in `docker-compose.yaml`.

| Variabile | Descrizione | Predefinito |
|---|---|---|
| `TRAEFIK_HOST` | Host di Traefik nella rete `web` | `traefik` |
| `TRAEFIK_PORT` | Porta HTTPS di Traefik | `443` |
| `DOMAINS_FILE` | Percorso di `domains.txt` nel container | `/config/domains.txt` |
| `APP_TITLE` | Titolo della pagina | `Local Projects` |
| `HIDE_DOMAINS` | Domini, separati da virgola, da non mostrare come card | `localhost` |
| `PROBE_TIMEOUT` | Timeout in secondi dei controlli di stato | `2` |

Se aggiungi un altro dominio di servizio da includere nel certificato ma non nella dashboard, aggiornalo sia in `BASE_DOMAINS` di `generate-cert.sh` sia in `HIDE_DOMAINS`.

### Avviare, arrestare e aggiornare

| Operazione | Comando |
|---|---|
| Avviare la dashboard | `docker compose up -d dashboard` |
| Arrestare la dashboard | `docker compose stop dashboard` |
| Visualizzare i log | `docker compose logs -f dashboard` |
| Applicare modifiche al codice (`dashboard/`) | `docker compose up -d --build dashboard` |

Dopo aver aggiornato `app.js` o `style.css`, fai un ricaricamento forzato della pagina (`Ctrl+Shift+R`) per evitare la cache del browser.

Le modifiche a `domains.txt` non richiedono rebuild: vengono lette a ogni richiesta.

## Gestione quotidiana

| Operazione | Comando |
|---|---|
| Avviare Traefik e dashboard | `docker compose up -d --build` |
| Arrestare tutto | `docker compose down` |
| Riavviare Traefik | `docker compose restart traefik` |
| Riavviare la dashboard | `docker compose restart dashboard` |
| Visualizzare i log | `docker compose logs -f traefik` |
| Verificare i container | `docker compose ps` |
| Rigenerare il certificato | `./generate-cert.sh` |

Per avviare o arrestare un progetto, eseguire i comandi Compose dalla directory del progetto stesso. Non è necessario riavviare Traefik a ogni avvio o arresto di un'applicazione.

## Configurazione

### `traefik.yaml`

Contiene la configurazione statica di Traefik:

- Entry point HTTP e HTTPS.
- Reindirizzamento da HTTP a HTTPS.
- Provider Docker.
- Provider file per la configurazione TLS.

### `dynamic.yaml`

Contiene la configurazione TLS dinamica e il certificato predefinito utilizzato da Traefik.

### `docker-compose.yaml`

Definisce i servizi `traefik` e `dashboard`, le porte pubblicate sull'host (solo quelle di Traefik), i file montati e la rete Docker condivisa. Il servizio `dashboard` monta `domains.txt` in sola lettura ed è esposto da Traefik tramite label (`dashboard.localhost`, HTTPS, porta interna `8000`).

### `dashboard/`

Contiene il codice della dashboard, copiato nell'immagine in fase di build:

- `Dockerfile`: immagine `python:alpine`, esecuzione come utente non privilegiato.
- `app.py`: lettura di `domains.txt`, controlli di stato e API `/api/projects`.
- `index.html`, `app.js`, `style.css`: interfaccia.

## Troubleshooting

### Il browser segnala un certificato non valido

Verificare che il dominio sia presente in `domains.txt`, rigenerare il certificato e controllare che la CA di `mkcert` sia attendibile sul sistema.

### Traefik restituisce `404 page not found`

Verificare che il container del progetto sia in esecuzione, che `traefik.enable=true` sia presente e che la regola `Host(...)` corrisponda esattamente al dominio richiesto.

### Traefik non raggiunge l'applicazione

Verificare che il progetto e Traefik condividano la rete `web` e che la label `traefik.http.services.<nome>.loadbalancer.server.port` indichi la porta effettivamente in ascolto nel container.

### Il certificato non contiene il nuovo dominio

Eseguire nuovamente `./generate-cert.sh` dalla directory del proxy e verificare il risultato prima di riprovare la connessione.

### Un progetto in esecuzione risulta offline nella dashboard

Lo stato offline indica che Traefik non ha un router per quel dominio. Verificare le label Traefik del progetto e che la regola `Host(...)` corrisponda esattamente al dominio scritto in `domains.txt`.

### Una modifica a `domains.txt` non compare nella dashboard

`domains.txt` è montato come file singolo: se l'editor lo salva sostituendo il file (ad esempio `sed -i`), il container può continuare a vedere la versione precedente. Eseguire `docker compose restart dashboard`. Il file non viene montato tramite l'intera directory per non esporre `certs/` e la chiave privata.

### La dashboard mostra "Impossibile leggere la configurazione dei domini"

Verificare che `domains.txt` esista accanto a `docker-compose.yaml` e sia leggibile, poi controllare i log con `docker compose logs dashboard`.

### Il clic sulla directory non copia il percorso

La copia negli appunti richiede un contesto sicuro: aprire la dashboard tramite `https://dashboard.localhost` e non tramite un indirizzo diverso.

## Sicurezza

Questo proxy è destinato allo sviluppo locale.

- Non esporre pubblicamente la porta Docker API.
- Non condividere la chiave privata dei certificati.
- Non utilizzare i certificati locali in produzione.
- Mantenere `exposedByDefault: false` per evitare di esporre automaticamente container non configurati.
- Il socket Docker è montato in sola lettura solo nel container Traefik; la dashboard non vi accede.
- La dashboard non pubblica porte sull'host, gira con filesystem in sola lettura, senza capability aggiuntive e con `no-new-privileges`. Verso Traefik usa una connessione TLS senza verifica del certificato, limitata alla rete Docker interna.
- La dashboard mostra solo i dati presenti in `domains.txt` e, in caso di errore di lettura, un messaggio generico senza dettagli sul sistema.
