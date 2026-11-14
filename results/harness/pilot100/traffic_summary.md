# Federation traffic: pilot100

Everything that crossed the household boundary. Payload bytes, without MQTT overhead; retained re-deliveries excluded.

| kind | direction | messages | payload_bytes |
|---|---|---|---|
| global | server to homes (one publish; multiply by receivers) | 101 | 4921072 |
| metrics | home to server | 505 | 81213 |
| status | home to server | 10 | 65 |
| update | home to server | 500 | 24304549 |

Kinds seen: global, metrics, status, update. No sensor events, windows or labels.

Broker counters, including protocol overhead (since the broker started):

- `$SYS/broker/bytes/received`: 29353204
- `$SYS/broker/bytes/sent`: 78389988
- `$SYS/broker/messages/received`: 3802
- `$SYS/broker/messages/sent`: 4124
- `$SYS/broker/messages/stored`: 59
