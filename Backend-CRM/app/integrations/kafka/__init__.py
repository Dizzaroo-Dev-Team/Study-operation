"""
Data Platform Kafka CONSUMER — faithful Python port of ``D:/kafka`` (Node.js).

Mirrors the reference bundle 1:1 (adapted to Python/FastAPI + motor):
  - ``data_platform_consumer``  <- dataPlatformConsumer.js  (connection/lifecycle)
  - ``events/``                 <- events/*.js               (router + entity handlers)
  - ``models/sync_models``      <- models/syncModels.js      (collection contracts)
  - ``utils/``                  <- utils/*.js                (config + logger + cache)

Single inbound Kafka connection (KAFKA_BROKERS — self-hosted broker, PLAINTEXT)
— the same Data Platform connection the milestone PRODUCER
(``app.integrations.milestones_kafka``) uses. It subscribes to the six IAM
entity-sync topics and mirrors them into MongoDB ``local_*`` collections (plus,
for users, a Postgres ``users`` row so synced identities can authenticate).

NOTE: the reference also wired inbound ``milestone`` + ``document notification``
handlers. This app is the PRODUCER for those topics, so they are intentionally
not consumed here — only the six IAM sync topics are.

Keep this ``__init__`` import-light (no aiokafka) so importing an event handler
(e.g. from the auth path) never drags the consumer runtime into request code.

Public entry points live in ``data_platform_consumer`` and are wired into the
FastAPI lifespan in ``app.main``.
"""
