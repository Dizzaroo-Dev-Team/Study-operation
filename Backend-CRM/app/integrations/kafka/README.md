# Neurodoc Backend Kafka Integration Guide

This backend uses Kafka through the Data Platform Event Hub integration for inbound event consumption only. The implementation is designed to be shareable with other applications that need a simple Kafka consumer for syncing the six core collections:

- local_users
- local_app_attribute_definitions
- local_app_user_attributes
- local_hub_user_attributes
- local_policies
- local_resources

## What is included

The current integration includes:

- A Kafka consumer that connects to the Data Platform Event Hub and subscribes to configured topics.
- Topic-specific event handlers for users, resources, policies, app-scoped attributes, and attribute definitions.
- Shared MongoDB models for persistent sync state of the six target collections.
- Startup wiring in the backend server so Kafka is initialized automatically when the app starts.

---

## Complete Kafka file inventory

The following files are the core building blocks for a complete Kafka integration in this repository.

### 1. Consumer runtime

- [src/kafka/dataPlatformConsumer.js](src/kafka/dataPlatformConsumer.js) – Single consumer runtime for the Data Platform Event Hub connection, topic subscription, and message loop.

### 2. Event routing and handlers

- [src/kafka/events/index.js](src/kafka/events/index.js) – Central topic registry and router that maps topics to handlers.
- [src/kafka/events/helpers.js](src/kafka/events/helpers.js) – Shared envelope parsing, routing guard helpers, and action dispatch helpers.
- [src/kafka/events/userEvent.js](src/kafka/events/userEvent.js) – Handles user create/update/delete events.
- [src/kafka/events/hubUserAttributeEvent.js](src/kafka/events/hubUserAttributeEvent.js) – Handles hub user attribute events.
- [src/kafka/events/appUserAttributeEvent.js](src/kafka/events/appUserAttributeEvent.js) – Handles app-scoped user attribute events.
- [src/kafka/events/appAttributeDefinitionEvent.js](src/kafka/events/appAttributeDefinitionEvent.js) – Handles attribute-definition events.
- [src/kafka/events/policyEvent.js](src/kafka/events/policyEvent.js) – Handles policy events.
- [src/kafka/events/resourceEvent.js](src/kafka/events/resourceEvent.js) – Handles resource events.

### 3. Shared models and contracts

- [src/models/syncModels.js](src/models/syncModels.js) – MongoDB schemas for mirrored Kafka state such as local users, policies, resources, and app attributes.

### 4. Utilities and shared runtime helpers

- [src/utils/iamConfig.js](src/utils/iamConfig.js) – Application ID and attribute allowlist resolution helpers.
- [src/utils/logger.js](src/utils/logger.js) – Shared logging module used across Kafka components.

### 5. Service integrations and startup wiring

- [src/server.js](src/server.js) – Starts the consumer during backend startup and shuts it down cleanly on exit.

```js
// Data-platform EventHub consumer — the only active EventHub connection, non-blocking.
// Consumes milestone events plus all IAM entity-sync topics over one connection.
const { initializeDataPlatformConsumer } = require('./kafka/dataPlatformConsumer');
setImmediate(() => {
  initializeDataPlatformConsumer().catch((err) => {
    serverLogger.error(
      { err: err?.message, stack: err?.stack },
      'Data-platform Kafka consumer startup error'
    );
  });
});
```

---

## Required environment variables

The current implementation expects the following environment variables.

### Connection and identity

| Variable | Required | Purpose |
|---|---:|---|
| KAFKA_BROKERS | Yes | Comma-separated list of self-hosted Kafka brokers (host:port). |
| DATAPLATFORM_KAFKA_GROUP_ID | Yes | Consumer group ID for the Data Platform consumer. |
| KAFKA_CONSUMER_CLIENT_ID | Yes | Client ID for the consumer. |
| KAFKA_PRODUCER_CLIENT_ID | Yes | Client ID for the producer. |
| KAFKA_START_FROM_BEGINNING | No | Replays existing messages on first subscription when set to true. |

### Routing and app targeting

| Variable | Required | Purpose |
|---|---:|---|
| DATA_PLATFORM_APP_ID | Yes | Identifies the target application for routing checks. |
| KAFKA_REQUIRED_SOURCE | Yes | Required source tag that must match the incoming envelope source. |

### Topic mapping

| Variable | Required | Purpose |
|---|---:|---|
| USERS_KAFKA_TOPIC | No | Topic for user events. |
| HUB_USER_ATTRIBUTES_KAFKA_TOPIC | No | Topic for hub user attribute events. |
| APP_USER_ATTRIBUTES_KAFKA_TOPIC | No | Topic for app-scoped user attribute events. |
| RESOURCES_KAFKA_TOPIC | No | Topic for resource events. |
| POLICIES_KAFKA_TOPIC | No | Topic for policy events. |
| APP_ATTRIBUTE_DEFINITIONS_KAFKA_TOPIC | No | Topic for app attribute definition events. |
| MILESTONE_KAFKA_TOPIC | No | Topic for milestone events. |
| DOCUMENTS_KAFKA_TOPIC | No | Topic for document notification events. |


### Attribute and policy filtering

| Variable | Required | Purpose |
|---|---:|---|
| SUBJECT_ROLE_KEY | No | Subject role attribute key used by policy evaluation. |
| SUBJECT_ACCESS_KEY | No | Subject access attribute key used by policy evaluation. |

---
