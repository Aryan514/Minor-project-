# Scenario results overview

| Scenario | I1 GEM | I1 UA | I2 GEM | I2 UA | I3 GEM | I3 UA | I4 GEM | I4 UA | I5 both | I6 GEM | I6 UA | Scenario checks | Run |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| [S3](S3_summary.md) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 4/4 | `S3_20261124-004854` |
| [S2](S2_summary.md) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | N/A | PASS | PASS | 5/5 | `S2_20261124-004915` |
| [S5](S5_summary.md) | PASS | PASS | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | 2/2 | `S5_20261124-004956` |
| [S1](S1_summary.md) | PASS | PASS | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | 0/0 | `S1_20261124-005043` |
| [S4](S4_summary.md) | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | PASS | 10/10 | `S4_20261124-005157` |
| [S6](S6_summary.md) | PASS | PASS | PASS | PASS | PASS | PASS | N/A | N/A | N/A | PASS | PASS | 5/5 | `S6_20261124-005257` |

> Latency = client receive time - core audit time, both `time.time_ns()` on the same laptop (loopback). The UA figure includes the client's 50 ms subscription publishing interval, and GEM sees the temperature only through the 1 Hz CEID 1007. These numbers describe this setup. They must not be read as one protocol being faster than the other.
