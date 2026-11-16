# pw-channel

The PlaceholderWorks channel service. It receives a client's data through their adapter, decides which channel to use and when, and talks to customers on voice, WhatsApp and email. Closed source; installed by a client adapter repo (for example `adam-vacations-adapter`) and started with its CLI.

```
client webhook ──► intake API ──► adapter (client code) ──► CustomerRecord ──► journey (Postgres)
                                                                                  │
                                worker: claim due step ──► policy gate ──► channel.execute()
                                                                                  │
                         voice (telephony + STT + TTS) · WhatsApp · email  ──► outcome ──► next step
                         replies, clicks, opt-outs, booking/payment events ──► journey_events inbox ──► rules
```

## Layout

| Path | What it holds |
|---|---|
| `pw_channel/app.py` | `create_app()`: the FastAPI service (intake, webhooks, voice websockets, dashboard API) |
| `pw_channel/runner.py` | the CLI every adapter repo wraps: `llm`, `channel`, `worker`, `migrate`, `check` |
| `pw_channel/core/` | `Channel` base class, channel registry, `CallTarget`, record store (Postgres) |
| `pw_channel/intake/` | intake API, adapter registry, built-in adapters (`builtin.canonical`, `builtin.fields`), ingestion events, replay |
| `pw_channel/orchestrator/` | the dependency scheduler: journey templates, Postgres store, rules engine, dispatcher, worker |
| `pw_channel/policy/` | contact hours, consent, opt-out blocks, DND (`DndChecker` providers), daily contact caps |
| `pw_channel/channels/voice/` | `VoiceChannel`; `telephony/` (`TelephonyProvider`: acefone, website), `stt/`, `tts/`, `vad/` providers; pipeline and processors |
| `pw_channel/channels/whatsapp/` | `WhatsAppChannel`; `providers/` (`WhatsAppProvider`: meta, karix, nowonextel) and the provider pool; one inbound webhook pipeline; send API; campaigns |
| `pw_channel/channels/email/` | `EmailChannel`; `providers/` (`EmailProvider`: smtp); templates; tracked links and unsubscribe |
| `pw_channel/admin/`, `auth/` | dashboard API, journeys API, RBAC |
| `pw_channel/db/migrations/` | ordered SQL migrations (`0001_base.sql`, `0002_platform.sql`) |
| `ui/` | dashboard source (React); builds into `pw_channel/static/dashboard` |

## Adding a provider

Every provider family has one base class and one registry. A new provider is one file plus one registry line (or an entry point in the client's adapter repo):

| Family | Base class | Registry | Entry-point group |
|---|---|---|---|
| Telephony | `channels/voice/telephony/base.py:TelephonyProvider` | `channels/voice/telephony/registry.py` | `pw.telephony` |
| STT | `channels/voice/stt/base.py:STTProvider` | `channels/voice/stt/factory.py` | `pw.stt` |
| TTS | `channels/voice/tts/base.py:TTSProvider` | `channels/voice/tts/factory.py` | `pw.tts` |
| VAD | `channels/voice/vad/base.py:VADProvider` | `channels/voice/vad/factory.py` | `pw.vad` |
| WhatsApp | `channels/whatsapp/providers/base.py:WhatsAppProvider` | `channels/whatsapp/providers/pool.py` | `pw.whatsapp` |
| Email | `channels/email/providers/base.py:EmailProvider` | `channels/email/providers/registry.py` | `pw.email` |
| DND | `policy/dnd.py:DndChecker` | `policy/dnd.py` | `pw.dnd` |
| Channel | `core/channel.py:Channel` | `core/registry.py` | `pw.channels` |

## Journeys

A journey is a list of steps in the client's `pw.toml`. A step runs when the steps it `depends_on` finish with an outcome listed in `when`. Events (`booking.confirmed`, `whatsapp.replied`, `link.clicked`, `opt_out`, `call.callback`, ...) arrive in the `journey_events` inbox and are applied by `on` rules: `complete`, `stop`, `cancel:<step>`, `pause:<duration>`, `reschedule:<step>`, `start:<journey>`, `block`. State lives in Postgres (`journeys`, `journey_tasks`, `task_deps`, `journey_events`), so several workers can run (`FOR UPDATE SKIP LOCKED`) and a crashed worker's steps are picked up when their lease expires.

## Endpoints

| Path | Purpose |
|---|---|
| `POST /api/intake/{intake}/records` | client's raw records → adapter → journeys |
| `POST /api/intake/{intake}/events` | client's payment/booking events → journey rules |
| `POST /api/channel/whatsapp/webhook[/{provider}]` | WhatsApp inbound |
| `POST /api/channel/whatsapp/send`, `/text` | send a resume link or text (used by agent tools) |
| `GET /api/channel/email/click/{token}`, `/unsubscribe/{token}` | email tracking and opt-out |
| `GET /api/admin/journeys[/{id}]`, `/api/admin/journeys/templates` | inspect journeys, templates and loaded adapters |
| `/ws/acefone`, `/ws/website`, `/webhooks/acefone` | voice streams and provider callbacks |

Old paths (`/api/qms/{intake}/calls`, `/api/ingestion/calls`, `/webhook`, `/webhook/karix`, `/api/whatsapp/voicebot/*`) still work.

## Develop

```bash
uv sync --all-extras
uv run pytest                                  # unit + Postgres-backed scheduler tests (embedded Postgres)
uv run python tests/checks/check_call_lifecycle.py   # older script checks
```
