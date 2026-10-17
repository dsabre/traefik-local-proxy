
# Local Docker Proxy

Reverse proxy locale basato su [Traefik](https://traefik.io/), utilizzato per esporre i progetti di sviluppo tramite domini `.localhost` e HTTPS, senza dover installare PHP o altri runtime direttamente sul sistema host.

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
└── README.md
```

## Avvio del proxy

La rete Docker condivisa viene creata una sola volta:

```bash
docker network create web
```

Se esiste già, non è necessario ricrearla.

Avviare Traefik:

```bash
docker compose up -d
```

Verificare lo stato:

```bash
docker compose ps
docker compose logs -f traefik
```

Il container utilizza la policy `restart: unless-stopped`, quindi riparte automaticamente all'avvio di Docker, purché non sia stato arrestato esplicitamente.

## Gestione dei certificati HTTPS

Il file `domains.txt` contiene i domini da includere nel certificato locale, uno per riga.

Esempio:

```text
localhost
legacy.vodafone.localhost
ricettario.localhost
bigpillow-app.localhost
```

Sono supportati commenti preceduti da `#` e righe vuote.

### Generare o aggiornare il certificato

```bash
./generate-cert.sh
```

Lo script:

1. Legge i domini da `domains.txt`.
2. Ignora commenti e righe vuote.
3. Genera il certificato e la chiave con `mkcert`.
4. Riavvia Traefik per caricare il nuovo certificato.

I file vengono salvati in:

```text
certs/local-cert.pem
certs/local-key.pem
```

La CA locale di `mkcert` deve essere installata sul sistema per evitare avvisi di certificato non attendibile.

**Importante:** quando aggiungi o rimuovi domini, rigenera il certificato. Il certificato generato contiene soltanto i nomi specificati al momento della generazione.

La chiave privata non deve essere condivisa o pubblicata.

## Aggiungere un progetto

Ogni progetto deve:

1. Avere un proprio file Compose.
2. Collegarsi alla rete Docker esterna `web`.
3. Dichiarare le label Traefik necessarie.
4. Essere raggiungibile da Traefik sulla porta interna corretta.
5. Avere il proprio dominio aggiunto a `domains.txt`.

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

Non è necessario pubblicare la porta dell'applicazione sull'host: il traffico passa attraverso la rete Docker condivisa.

## Gestione quotidiana

| Operazione | Comando |
|---|---|
| Avviare Traefik | `docker compose up -d` |
| Arrestare Traefik | `docker compose down` |
| Riavviare Traefik | `docker compose restart traefik` |
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

Definisce il container Traefik, le porte pubblicate sull'host, i file montati e la rete Docker condivisa.

## Troubleshooting

### Il browser segnala un certificato non valido

Verificare che il dominio sia presente in `domains.txt`, rigenerare il certificato e controllare che la CA di `mkcert` sia attendibile sul sistema.

### Traefik restituisce `404 page not found`

Verificare che il container del progetto sia in esecuzione, che `traefik.enable=true` sia presente e che la regola `Host(...)` corrisponda esattamente al dominio richiesto.

### Traefik non raggiunge l'applicazione

Verificare che il progetto e Traefik condividano la rete `web` e che la label `traefik.http.services.<nome>.loadbalancer.server.port` indichi la porta effettivamente in ascolto nel container.

### Il certificato non contiene il nuovo dominio

Eseguire nuovamente `./generate-cert.sh` dalla directory del proxy e verificare il risultato prima di riprovare la connessione.

## Sicurezza

Questo proxy è destinato allo sviluppo locale.

- Non esporre pubblicamente la porta Docker API.
- Non condividere la chiave privata dei certificati.
- Non utilizzare i certificati locali in produzione.
- Mantenere `exposedByDefault: false` per evitare di esporre automaticamente container non configurati.

