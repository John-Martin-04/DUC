# Federation traffic: pilot

Everything that crossed the household boundary. Payload bytes, without MQTT overhead; retained re-deliveries excluded.

| kind | direction | messages | payload_bytes |
|---|---|---|---|
| global | server to homes (one publish; multiply by receivers) | 21 | 1023087 |
| metrics | home to server | 105 | 16508 |
| status | home to server | 10 | 65 |
| update | home to server | 102 | 4860577 |

Kinds seen: global, metrics, status, update. No sensor events, windows or labels.

Broker counters, including protocol overhead (since the broker started):

- `$SYS/broker/bytes/received`: 5910637
- `$SYS/broker/bytes/sent`: 15917508
- `$SYS/broker/messages/received`: 835
- `$SYS/broker/messages/sent`: 1075
- `$SYS/broker/messages/stored`: 59
