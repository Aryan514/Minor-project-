# Checker self-test on `runs/sample_S3`

Each case corrupts a temporary COPY of the run and re-runs the checker. The baseline must pass and every corruption must be flagged by the invariant it violates. This shows the checker can actually fail.

| Case | Corruption applied | Expected | Flagged by checker | OK |
|---|---|---|---|---|
| baseline (unmodified) | - | all PASS/N/A | nothing | yes |
| drop_event | removed GEM event seq 231 | I1 GEM FAIL, I6 GEM FAIL | I1/GEM, I5/both, I6/GEM | yes |
| swap_events | swapped UA events seq 231 and 234 | I2 UA FAIL | I2/UA | yes |
| change_value | changed EventTemp of GEM seq 234 by +1.0 | I3 GEM FAIL | I3/GEM | yes |
| delay_state | delayed UA notification of ControlState=ONLINE_REMOTE (seq 14) by 2 s | I4 UA FAIL | I4/UA | yes |
| double_winner | turned the rejection in conflict round 1 into an acceptance | I5 both FAIL | I5/both | yes |
