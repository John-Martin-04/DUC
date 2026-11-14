# Federation traffic: all28_fedavg

Everything that crossed the household boundary. Payload bytes, without MQTT overhead; retained re-deliveries excluded.

| kind | direction | messages | payload_bytes |
|---|---|---|---|
| global | server to homes (one publish; multiply by receivers) | 122 | 6470419 |
| metrics | home to server | 3416 | 564781 |
| status | home to server | 56 | 364 |
| update | home to server | 3360 | 177104094 |

Kinds seen: global, metrics, status, update. No sensor events, windows or labels.

Broker counters, including protocol overhead (since the broker started):

- `$SYS/broker/bytes/received`: 184439004
- `$SYS/broker/bytes/sent`: 543577357
- `$SYS/broker/messages/received`: 25104
- `$SYS/broker/messages/sent`: 26857
- `$SYS/broker/messages/stored`: 82
