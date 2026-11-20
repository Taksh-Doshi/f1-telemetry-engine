# Tyre degradation v4: race fixed-effects headline

## Headline method and eligibility

V4 uses the corrected race fixed-effects estimator as its headline. Each race
fit controls for driver, race lap, and compound intercepts, then estimates a
separate tyre-age slope by compound. Only full-column-rank designs contribute
to the reported race estimates. Independent race-level slopes are pooled with
DerSimonian-Laird random effects and normal 95% intervals.

The minimum data rule is 500 clean race laps in the existing
`clean_laps` view and at least 3 full-rank races for a
circuit/compound pool. Below-threshold races remain in the status and
per-race tables but are excluded from circuit pools and headline validation.
Circuit/compound groups without three qualifying races use the cross-circuit
pool and are marked as such in the prediction API. Clean-lap totals can be
reduced by the view's pit, safety/red flag, wet compound, inaccurate/deleted,
and lap-one filters.

## Data accounting

- Source rows: 60,706; complete model rows: 60,227.
- Excluded rows with missing/invalid required values: 479.
- Race sessions with clean data: 66; eligible full-rank races: 59; rank-deficient: 6; failed fits: 0.

### Low-data races

| race_id | circuit | clean_laps | low_data_reason |
| --- | --- | --- | --- |
| 2022-17 | Singapore Grand Prix | 277 | 277 clean laps; minimum is 500. Raw lap filters removed/omitted 588 wet-compound, 219 safety/red-flag, 45 pit-affected and 20 opening laps (categories may overlap). |
| 2024-9 | Canadian Grand Prix | 318 | 318 clean laps; minimum is 500. Raw lap filters removed/omitted 846 wet-compound, 186 safety/red-flag, 89 pit-affected and 20 opening laps (categories may overlap). |
| 2022-18 | Japanese Grand Prix | 0 | 0 clean laps; minimum is 500. Raw lap filters removed/omitted 507 wet-compound, 38 safety/red-flag, 83 pit-affected and 20 opening laps (categories may overlap). |
| 2024-21 | São Paulo Grand Prix | 0 | 0 clean laps; minimum is 500. Raw lap filters removed/omitted 1134 wet-compound, 149 safety/red-flag, 68 pit-affected and 18 opening laps (categories may overlap). |

### Rank-deficient race designs

| race_id | circuit | clean_laps | design_rank | design_columns |
| --- | --- | --- | --- | --- |
| 2024-9 | Canadian Grand Prix | 318 | 46.0000 | 47.0000 |
| 2022-19 | United States Grand Prix | 778 | 69.0000 | 70.0000 |
| 2022-7 | Monaco Grand Prix | 540 | 75.0000 | 76.0000 |
| 2024-16 | Italian Grand Prix | 927 | 75.0000 | 76.0000 |
| 2023-9 | Austrian Grand Prix | 1186 | 89.0000 | 90.0000 |
| 2023-4 | Azerbaijan Grand Prix | 846 | 70.0000 | 71.0000 |

## Headline race fixed-effects degradation

Slopes are seconds per tyre-age lap; negative estimates are retained, not
clamped. Circuit pools include only eligible full-rank races and require at
least 3 distinct race estimates.

### Cross-circuit pools

| compound | pooled_slope_seconds_per_lap | lower_95 | upper_95 | race_estimates | negative_race_slope_share | tau_squared | laps |
| --- | --- | --- | --- | --- | --- | --- | --- |
| HARD | 0.0507 | 0.0438 | 0.0576 | 58 | 0.0690 | 0.0006 | 26995 |
| MEDIUM | 0.0627 | 0.0539 | 0.0714 | 58 | 0.0345 | 0.0010 | 20784 |
| SOFT | 0.0902 | 0.0744 | 0.1060 | 51 | 0.1176 | 0.0021 | 7576 |

### Circuit/compound pools

| circuit | compound | pooled_slope_seconds_per_lap | lower_95 | upper_95 | race_estimates | negative_race_slope_share | tau_squared | laps |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Abu Dhabi Grand Prix | HARD | 0.0571 | 0.0524 | 0.0619 | 3 | 0.0000 | 0.0000 | 2026 |
| Abu Dhabi Grand Prix | MEDIUM | 0.0808 | 0.0481 | 0.1135 | 3 | 0.0000 | 0.0008 | 923 |
| Australian Grand Prix | HARD | 0.0091 | -0.0339 | 0.0520 | 3 | 0.3333 | 0.0013 | 1957 |
| Australian Grand Prix | MEDIUM | 0.0801 | 0.0628 | 0.0975 | 3 | 0.0000 | 0.0000 | 461 |
| Bahrain Grand Prix | HARD | 0.1148 | 0.0970 | 0.1326 | 3 | 0.0000 | 0.0002 | 1335 |
| Bahrain Grand Prix | SOFT | 0.1408 | 0.1149 | 0.1668 | 3 | 0.0000 | 0.0005 | 1194 |
| Belgian Grand Prix | HARD | 0.1119 | 0.0460 | 0.1779 | 3 | 0.0000 | 0.0025 | 619 |
| Belgian Grand Prix | MEDIUM | 0.1195 | 0.0524 | 0.1866 | 3 | 0.0000 | 0.0034 | 1025 |
| Belgian Grand Prix | SOFT | 0.1093 | 0.0297 | 0.1889 | 3 | 0.0000 | 0.0048 | 473 |
| British Grand Prix | HARD | -0.0402 | -0.1468 | 0.0665 | 3 | 0.3333 | 0.0082 | 306 |
| British Grand Prix | MEDIUM | -0.0467 | -0.1755 | 0.0822 | 3 | 0.6667 | 0.0127 | 1258 |
| British Grand Prix | SOFT | 0.0462 | -0.0508 | 0.1433 | 3 | 0.3333 | 0.0064 | 576 |
| Dutch Grand Prix | HARD | 0.0236 | 0.0039 | 0.0434 | 3 | 0.3333 | 0.0003 | 1079 |
| Dutch Grand Prix | MEDIUM | 0.0549 | 0.0398 | 0.0699 | 3 | 0.0000 | 0.0001 | 1075 |
| Dutch Grand Prix | SOFT | 0.0565 | 0.0325 | 0.0805 | 3 | 0.0000 | 0.0004 | 1144 |
| Hungarian Grand Prix | HARD | 0.0544 | 0.0311 | 0.0778 | 3 | 0.0000 | 0.0004 | 1795 |
| Hungarian Grand Prix | MEDIUM | 0.0604 | 0.0512 | 0.0697 | 3 | 0.0000 | 0.0000 | 1472 |
| Hungarian Grand Prix | SOFT | 0.1073 | 0.0874 | 0.1273 | 3 | 0.0000 | 0.0000 | 348 |
| Mexico City Grand Prix | HARD | 0.0301 | 0.0195 | 0.0407 | 3 | 0.0000 | 0.0001 | 1352 |
| Mexico City Grand Prix | MEDIUM | 0.0406 | 0.0161 | 0.0651 | 3 | 0.0000 | 0.0004 | 1713 |
| Mexico City Grand Prix | SOFT | 0.3481 | -0.2794 | 0.9756 | 3 | 0.0000 | 0.2765 | 414 |
| Miami Grand Prix | HARD | 0.0153 | 0.0015 | 0.0290 | 3 | 0.0000 | 0.0001 | 1719 |
| Miami Grand Prix | MEDIUM | 0.0235 | 0.0118 | 0.0352 | 3 | 0.0000 | 0.0001 | 1096 |
| Miami Grand Prix | SOFT | 0.0064 | -0.0590 | 0.0717 | 3 | 0.6667 | 0.0017 | 75 |
| Saudi Arabian Grand Prix | HARD | 0.0284 | 0.0128 | 0.0441 | 3 | 0.0000 | 0.0001 | 1477 |
| Saudi Arabian Grand Prix | MEDIUM | 0.0362 | 0.0211 | 0.0513 | 3 | 0.0000 | 0.0001 | 737 |
| Spanish Grand Prix | HARD | 0.0965 | 0.0426 | 0.1504 | 3 | 0.0000 | 0.0022 | 889 |
| Spanish Grand Prix | MEDIUM | 0.0768 | 0.0417 | 0.1119 | 3 | 0.0000 | 0.0009 | 1238 |
| Spanish Grand Prix | SOFT | 0.0865 | 0.0376 | 0.1354 | 3 | 0.0000 | 0.0018 | 1390 |

## Fuel mismatch and fuel-assumption sensitivity

Race-lap fixed effects absorb the shared lap-by-lap fuel trend. Synthetic
experiments compare a known true fuel effect with a mismatched correction.
Within-stint slopes move with the difference in fuel assumptions; the race
fixed-effects slopes should remain invariant across assumed fuel settings.

| true_fuel_effect_s_per_kg | assumed_fuel_effect_s_per_kg | method | compound | true_slope | estimated_slope | bias | correct_assumption_slope | fuel_mismatch_bias | max_slope_change_across_assumptions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0400 | 0.0200 | Stint slopes | SOFT | 0.1000 | 0.0632 | -0.0368 | 0.0999 | -0.0367 | — |
| 0.0400 | 0.0200 | Stint slopes | MEDIUM | 0.0600 | 0.0245 | -0.0355 | 0.0612 | -0.0367 | — |
| 0.0400 | 0.0200 | Stint slopes | HARD | 0.0300 | -0.0066 | -0.0366 | 0.0301 | -0.0367 | — |
| 0.0400 | 0.0200 | Race fixed effects | SOFT | 0.1000 | 0.0987 | -0.0013 | — | — | 0.0000 |
| 0.0400 | 0.0300 | Race fixed effects | SOFT | 0.1000 | 0.0987 | -0.0013 | — | — | 0.0000 |
| 0.0400 | 0.0400 | Race fixed effects | SOFT | 0.1000 | 0.0987 | -0.0013 | — | — | 0.0000 |
| 0.0400 | 0.0200 | Race fixed effects | MEDIUM | 0.0600 | 0.0603 | 0.0003 | — | — | 0.0000 |
| 0.0400 | 0.0300 | Race fixed effects | MEDIUM | 0.0600 | 0.0603 | 0.0003 | — | — | 0.0000 |
| 0.0400 | 0.0400 | Race fixed effects | MEDIUM | 0.0600 | 0.0603 | 0.0003 | — | — | 0.0000 |
| 0.0400 | 0.0200 | Race fixed effects | HARD | 0.0300 | 0.0297 | -0.0003 | — | — | 0.0000 |
| 0.0400 | 0.0300 | Race fixed effects | HARD | 0.0300 | 0.0297 | -0.0003 | — | — | 0.0000 |
| 0.0400 | 0.0400 | Race fixed effects | HARD | 0.0300 | 0.0297 | -0.0003 | — | — | 0.0000 |
| 0.0400 | 0.0300 | Stint slopes | SOFT | 0.1000 | 0.0807 | -0.0193 | 0.0990 | -0.0183 | — |
| 0.0400 | 0.0300 | Stint slopes | MEDIUM | 0.0600 | 0.0410 | -0.0190 | 0.0594 | -0.0183 | — |
| 0.0400 | 0.0300 | Stint slopes | HARD | 0.0300 | 0.0113 | -0.0187 | 0.0296 | -0.0183 | — |
| 0.0400 | 0.0200 | Race fixed effects | SOFT | 0.1000 | 0.0996 | -0.0004 | — | — | 0.0000 |
| 0.0400 | 0.0300 | Race fixed effects | SOFT | 0.1000 | 0.0996 | -0.0004 | — | — | 0.0000 |
| 0.0400 | 0.0400 | Race fixed effects | SOFT | 0.1000 | 0.0996 | -0.0004 | — | — | 0.0000 |
| 0.0400 | 0.0200 | Race fixed effects | MEDIUM | 0.0600 | 0.0598 | -0.0002 | — | — | 0.0000 |
| 0.0400 | 0.0300 | Race fixed effects | MEDIUM | 0.0600 | 0.0598 | -0.0002 | — | — | 0.0000 |
| 0.0400 | 0.0400 | Race fixed effects | MEDIUM | 0.0600 | 0.0598 | -0.0002 | — | — | 0.0000 |
| 0.0400 | 0.0200 | Race fixed effects | HARD | 0.0300 | 0.0304 | 0.0004 | — | — | 0.0000 |
| 0.0400 | 0.0300 | Race fixed effects | HARD | 0.0300 | 0.0304 | 0.0004 | — | — | 0.0000 |
| 0.0400 | 0.0400 | Race fixed effects | HARD | 0.0300 | 0.0304 | 0.0004 | — | — | 0.0000 |
| 0.0200 | 0.0400 | Stint slopes | SOFT | 0.1000 | 0.1373 | 0.0373 | 0.1006 | 0.0367 | — |
| 0.0200 | 0.0400 | Stint slopes | MEDIUM | 0.0600 | 0.0967 | 0.0367 | 0.0600 | 0.0367 | — |
| 0.0200 | 0.0400 | Stint slopes | HARD | 0.0300 | 0.0664 | 0.0364 | 0.0298 | 0.0367 | — |
| 0.0200 | 0.0200 | Race fixed effects | SOFT | 0.1000 | 0.1003 | 0.0003 | — | — | 0.0000 |
| 0.0200 | 0.0300 | Race fixed effects | SOFT | 0.1000 | 0.1003 | 0.0003 | — | — | 0.0000 |
| 0.0200 | 0.0400 | Race fixed effects | SOFT | 0.1000 | 0.1003 | 0.0003 | — | — | 0.0000 |
| 0.0200 | 0.0200 | Race fixed effects | MEDIUM | 0.0600 | 0.0599 | -0.0001 | — | — | 0.0000 |
| 0.0200 | 0.0300 | Race fixed effects | MEDIUM | 0.0600 | 0.0599 | -0.0001 | — | — | 0.0000 |
| 0.0200 | 0.0400 | Race fixed effects | MEDIUM | 0.0600 | 0.0599 | -0.0001 | — | — | 0.0000 |
| 0.0200 | 0.0200 | Race fixed effects | HARD | 0.0300 | 0.0292 | -0.0008 | — | — | 0.0000 |
| 0.0200 | 0.0300 | Race fixed effects | HARD | 0.0300 | 0.0292 | -0.0008 | — | — | 0.0000 |
| 0.0200 | 0.0400 | Race fixed effects | HARD | 0.0300 | 0.0292 | -0.0008 | — | — | 0.0000 |

Maximum spread in cross-circuit fixed-effects estimates across the 0.02, 0.03,
and 0.04 s/kg assumptions:

| compound | max_abs_slope_change |
| --- | --- |
| HARD | 0.0000 |
| MEDIUM | 0.0000 |
| SOFT | 0.0000 |

The within-stint estimates are shown only as a labelled sensitivity check:

| assumed_fuel_effect_s_per_kg | compound | pooled_slope_seconds_per_lap | lower_95 | upper_95 | median_slope_seconds_per_lap | negative_stint_slope_share | stints | races | bootstrap_replicates | weighting |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0200 | HARD | 0.0217 | 0.0078 | 0.0334 | 0.0356 | 0.2596 | 1175 | 64 | 1000 | stint lap count |
| 0.0200 | MEDIUM | 0.0221 | -0.0033 | 0.0445 | 0.0434 | 0.2956 | 1167 | 65 | 1000 | stint lap count |
| 0.0200 | SOFT | 0.0229 | -0.0548 | 0.0905 | 0.0690 | 0.1898 | 469 | 39 | 1000 | stint lap count |
| 0.0300 | HARD | 0.0405 | 0.0274 | 0.0524 | 0.0530 | 0.1779 | 1175 | 64 | 1000 | stint lap count |
| 0.0300 | MEDIUM | 0.0404 | 0.0137 | 0.0655 | 0.0608 | 0.2339 | 1167 | 65 | 1000 | stint lap count |
| 0.0300 | SOFT | 0.0409 | -0.0361 | 0.1097 | 0.0860 | 0.1301 | 469 | 39 | 1000 | stint lap count |
| 0.0400 | HARD | 0.0592 | 0.0463 | 0.0708 | 0.0715 | 0.1013 | 1175 | 64 | 1000 | stint lap count |
| 0.0400 | MEDIUM | 0.0588 | 0.0322 | 0.0810 | 0.0791 | 0.1740 | 1167 | 65 | 1000 | stint lap count |
| 0.0400 | SOFT | 0.0590 | -0.0164 | 0.1244 | 0.1035 | 0.0959 | 469 | 39 | 1000 | stint lap count |

## Synthetic parameter recovery

| method | compound | true_slope | recovered_slope | error | full_rank_races | rank | columns |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Primary stint slopes | SOFT | 0.1000 | 0.0997 | -0.0003 | 12 | — | — |
| Corrected race fixed effects | SOFT | 0.1000 | 0.0997 | -0.0003 | 12 | — | — |
| Primary stint slopes | MEDIUM | 0.0600 | 0.0593 | -0.0007 | 12 | — | — |
| Corrected race fixed effects | MEDIUM | 0.0600 | 0.0595 | -0.0005 | 12 | — | — |
| Primary stint slopes | HARD | 0.0300 | 0.0303 | 0.0003 | 12 | — | — |
| Corrected race fixed effects | HARD | 0.0300 | 0.0304 | 0.0004 | 12 | — | — |
| Flawed v2 design | all | — | — | — | 0 | 121.0000 | 124.0000 |

Fuel mismatch is reported separately above; recovery is not evidence that
real-world confounding has been eliminated.

## Held-out evaluation

Relative lap-time MAE compares the headline fixed-effects pools with a
zero-degradation baseline. Eligible and low-data races are summarized
separately. Leave-one-race-out excludes the held-out race from the training
pools. The chronological evaluation trains on 2022-2023 and tests on 2024.

### Summary; only eligible rows are the headline

| validation | data_group | races | laps | stints | baseline_relative_mae_seconds | model_relative_mae_seconds | cross_circuit_fallback_stints |
| --- | --- | --- | --- | --- | --- | --- | --- |
| leave-one-race-out | eligible | 64 | 57906 | 2779 | 1.0434 | 1.0199 | 2779 |
| leave-one-race-out | low_data | 2 | 553 | 32 | 3.4149 | 3.9785 | 32 |
| train 2022-2023, test 2024 | eligible | 22 | 20841 | 934 | 0.9292 | 0.8426 | 934 |
| train 2022-2023, test 2024 | low_data | 1 | 290 | 18 | 3.2058 | 3.7747 | 18 |

### 2024 chronological races

| race_id | year | round | circuit | clean_laps | quality_status | laps | stints | baseline_relative_mae_seconds | model_relative_mae_seconds | cross_circuit_fallback_stints |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2024-1 | 2024 | 1 | Bahrain Grand Prix | 1024 | eligible | 1010 | 60 | 0.8499 | 0.5031 | 60 |
| 2024-10 | 2024 | 10 | Spanish Grand Prix | 1206 | eligible | 1192 | 60 | 0.9781 | 0.5747 | 60 |
| 2024-11 | 2024 | 11 | Austrian Grand Prix | 1269 | eligible | 1263 | 61 | 0.9490 | 0.4621 | 61 |
| 2024-12 | 2024 | 12 | British Grand Prix | 662 | eligible | 651 | 37 | 1.4419 | 1.1993 | 37 |
| 2024-13 | 2024 | 13 | Hungarian Grand Prix | 1254 | eligible | 1209 | 49 | 1.0449 | 0.7070 | 49 |
| 2024-14 | 2024 | 14 | Belgian Grand Prix | 751 | eligible | 712 | 46 | 0.5834 | 0.4438 | 46 |
| 2024-15 | 2024 | 15 | Dutch Grand Prix | 1354 | eligible | 1354 | 46 | 0.9704 | 0.4999 | 46 |
| 2024-16 | 2024 | 16 | Italian Grand Prix | 927 | eligible | 918 | 47 | 0.6127 | 0.5172 | 47 |
| 2024-17 | 2024 | 17 | Azerbaijan Grand Prix | 881 | eligible | 881 | 36 | 0.6398 | 0.8053 | 36 |
| 2024-18 | 2024 | 18 | Singapore Grand Prix | 1109 | eligible | 1099 | 40 | 0.8847 | 0.7113 | 40 |
| 2024-19 | 2024 | 19 | United States Grand Prix | 937 | eligible | 933 | 40 | 0.6336 | 0.7591 | 40 |
| 2024-2 | 2024 | 2 | Saudi Arabian Grand Prix | 816 | eligible | 735 | 22 | 0.5514 | 1.0743 | 22 |
| 2024-20 | 2024 | 20 | Mexico City Grand Prix | 1061 | eligible | 1048 | 35 | 0.7621 | 0.5751 | 35 |
| 2024-22 | 2024 | 22 | Las Vegas Grand Prix | 826 | eligible | 790 | 50 | 0.6985 | 0.6955 | 50 |
| 2024-23 | 2024 | 23 | Qatar Grand Prix | 717 | eligible | 702 | 34 | 0.9886 | 1.5966 | 34 |
| 2024-24 | 2024 | 24 | Abu Dhabi Grand Prix | 921 | eligible | 908 | 39 | 0.8042 | 0.3805 | 39 |
| 2024-3 | 2024 | 3 | Australian Grand Prix | 857 | eligible | 776 | 40 | 0.5773 | 0.4499 | 40 |
| 2024-4 | 2024 | 4 | Japanese Grand Prix | 790 | eligible | 764 | 46 | 1.4538 | 1.1703 | 46 |
| 2024-5 | 2024 | 5 | Chinese Grand Prix | 762 | eligible | 669 | 42 | 0.9607 | 0.5682 | 42 |
| 2024-6 | 2024 | 6 | Miami Grand Prix | 934 | eligible | 913 | 43 | 0.5110 | 0.5840 | 43 |
| 2024-7 | 2024 | 7 | Emilia Romagna Grand Prix | 1164 | eligible | 1136 | 40 | 1.2419 | 0.5415 | 40 |
| 2024-8 | 2024 | 8 | Monaco Grand Prix | 1187 | eligible | 1178 | 21 | 2.3051 | 3.7451 | 21 |
| 2024-9 | 2024 | 9 | Canadian Grand Prix | 318 | low_data | 290 | 18 | 3.2058 | 3.8025 | 18 |

### Per-race leave-one-out results, including low-data rows

| race_id | year | round | circuit | clean_laps | quality_status | laps | stints | baseline_relative_mae_seconds | model_relative_mae_seconds | cross_circuit_fallback_stints |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2022-1 | 2022 | 1 | Bahrain Grand Prix | 893 | eligible | 748 | 55 | 1.0747 | 0.6965 | 55 |
| 2022-10 | 2022 | 10 | British Grand Prix | 676 | eligible | 656 | 41 | 1.5670 | 1.7928 | 41 |
| 2022-11 | 2022 | 11 | Austrian Grand Prix | 843 | eligible | 839 | 42 | 0.9663 | 0.5507 | 42 |
| 2022-12 | 2022 | 12 | French Grand Prix | 833 | eligible | 800 | 39 | 0.6790 | 0.5451 | 39 |
| 2022-13 | 2022 | 13 | Hungarian Grand Prix | 1203 | eligible | 1200 | 59 | 0.9649 | 0.6838 | 59 |
| 2022-14 | 2022 | 14 | Belgian Grand Prix | 645 | eligible | 602 | 46 | 1.1018 | 0.8186 | 46 |
| 2022-15 | 2022 | 15 | Dutch Grand Prix | 1139 | eligible | 1072 | 68 | 0.6234 | 0.4189 | 68 |
| 2022-16 | 2022 | 16 | Italian Grand Prix | 778 | eligible | 770 | 38 | 0.6729 | 0.5705 | 38 |
| 2022-17 | 2022 | 17 | Singapore Grand Prix | 277 | low_data | 263 | 14 | 3.6240 | 4.1824 | 14 |
| 2022-19 | 2022 | 19 | United States Grand Prix | 778 | eligible | 733 | 45 | 0.6559 | 0.6288 | 45 |
| 2022-2 | 2022 | 2 | Saudi Arabian Grand Prix | 651 | eligible | 639 | 34 | 0.8360 | 1.1851 | 34 |
| 2022-20 | 2022 | 20 | Mexico City Grand Prix | 1284 | eligible | 1283 | 42 | 0.8350 | 0.7361 | 42 |
| 2022-21 | 2022 | 21 | São Paulo Grand Prix | 941 | eligible | 930 | 57 | 0.7557 | 0.5511 | 57 |
| 2022-22 | 2022 | 22 | Abu Dhabi Grand Prix | 1032 | eligible | 1026 | 50 | 0.9222 | 0.5457 | 50 |
| 2022-3 | 2022 | 3 | Australian Grand Prix | 813 | eligible | 802 | 36 | 1.0552 | 1.4875 | 36 |
| 2022-4 | 2022 | 4 | Emilia Romagna Grand Prix | 773 | eligible | 771 | 23 | 2.3760 | 3.4339 | 23 |
| 2022-5 | 2022 | 5 | Miami Grand Prix | 878 | eligible | 865 | 41 | 0.5527 | 0.8243 | 41 |
| 2022-6 | 2022 | 6 | Spanish Grand Prix | 1104 | eligible | 1093 | 69 | 1.1789 | 0.7317 | 69 |
| 2022-7 | 2022 | 7 | Monaco Grand Prix | 540 | eligible | 520 | 18 | 5.4956 | 6.2859 | 18 |
| 2022-8 | 2022 | 8 | Azerbaijan Grand Prix | 764 | eligible | 686 | 35 | 0.7012 | 0.7434 | 35 |
| 2022-9 | 2022 | 9 | Canadian Grand Prix | 1029 | eligible | 985 | 43 | 0.7777 | 0.7026 | 43 |
| 2023-1 | 2023 | 1 | Bahrain Grand Prix | 914 | eligible | 877 | 61 | 0.8202 | 0.4501 | 61 |
| 2023-10 | 2023 | 10 | British Grand Prix | 802 | eligible | 774 | 38 | 0.5310 | 0.5016 | 38 |
| 2023-11 | 2023 | 11 | Hungarian Grand Prix | 1158 | eligible | 1131 | 50 | 0.8579 | 0.5908 | 50 |
| 2023-12 | 2023 | 12 | Belgian Grand Prix | 721 | eligible | 675 | 45 | 1.4922 | 1.0969 | 45 |
| 2023-13 | 2023 | 13 | Dutch Grand Prix | 805 | eligible | 786 | 39 | 3.1527 | 3.7353 | 39 |
| 2023-14 | 2023 | 14 | Italian Grand Prix | 878 | eligible | 878 | 44 | 0.8503 | 0.4680 | 44 |
| 2023-15 | 2023 | 15 | Singapore Grand Prix | 958 | eligible | 958 | 42 | 0.9805 | 1.2850 | 42 |
| 2023-16 | 2023 | 16 | Japanese Grand Prix | 702 | eligible | 660 | 42 | 0.9506 | 0.5995 | 42 |
| 2023-17 | 2023 | 17 | Qatar Grand Prix | 834 | eligible | 784 | 58 | 0.6318 | 0.7296 | 58 |
| 2023-18 | 2023 | 18 | United States Grand Prix | 919 | eligible | 895 | 51 | 0.7106 | 0.5406 | 51 |
| 2023-19 | 2023 | 19 | Mexico City Grand Prix | 1134 | eligible | 1088 | 41 | 1.5043 | 1.4561 | 41 |
| 2023-2 | 2023 | 2 | Saudi Arabian Grand Prix | 829 | eligible | 798 | 36 | 0.8358 | 1.2057 | 36 |
| 2023-20 | 2023 | 20 | São Paulo Grand Prix | 986 | eligible | 981 | 49 | 1.0309 | 0.9486 | 49 |
| 2023-21 | 2023 | 21 | Las Vegas Grand Prix | 738 | eligible | 710 | 40 | 0.9355 | 1.2268 | 40 |
| 2023-22 | 2023 | 22 | Abu Dhabi Grand Prix | 1063 | eligible | 1055 | 54 | 0.6619 | 0.3755 | 54 |
| 2023-3 | 2023 | 3 | Australian Grand Prix | 769 | eligible | 706 | 19 | 1.3824 | 2.3775 | 19 |
| 2023-4 | 2023 | 4 | Azerbaijan Grand Prix | 846 | eligible | 799 | 31 | 0.5323 | 0.9470 | 31 |
| 2023-5 | 2023 | 5 | Miami Grand Prix | 1078 | eligible | 1073 | 37 | 0.7346 | 0.6337 | 37 |
| 2023-6 | 2023 | 6 | Monaco Grand Prix | 1007 | eligible | 999 | 27 | 1.7370 | 1.9594 | 27 |
| 2023-7 | 2023 | 7 | Spanish Grand Prix | 1207 | eligible | 1184 | 58 | 0.7803 | 0.5796 | 58 |
| 2023-8 | 2023 | 8 | Canadian Grand Prix | 1092 | eligible | 1066 | 46 | 0.6029 | 0.6526 | 46 |
| 2023-9 | 2023 | 9 | Austrian Grand Prix | 1186 | eligible | 1168 | 56 | 0.8283 | 0.4425 | 56 |
| 2024-1 | 2024 | 1 | Bahrain Grand Prix | 1024 | eligible | 1010 | 60 | 0.8499 | 0.5058 | 60 |
| 2024-10 | 2024 | 10 | Spanish Grand Prix | 1206 | eligible | 1192 | 60 | 0.9781 | 0.5799 | 60 |
| 2024-11 | 2024 | 11 | Austrian Grand Prix | 1269 | eligible | 1263 | 61 | 0.9490 | 0.4722 | 61 |
| 2024-12 | 2024 | 12 | British Grand Prix | 662 | eligible | 651 | 37 | 1.4419 | 1.2008 | 37 |
| 2024-13 | 2024 | 13 | Hungarian Grand Prix | 1254 | eligible | 1209 | 49 | 1.0449 | 0.7038 | 49 |
| 2024-14 | 2024 | 14 | Belgian Grand Prix | 751 | eligible | 712 | 46 | 0.5834 | 0.4412 | 46 |
| 2024-15 | 2024 | 15 | Dutch Grand Prix | 1354 | eligible | 1354 | 46 | 0.9704 | 0.4934 | 46 |
| 2024-16 | 2024 | 16 | Italian Grand Prix | 927 | eligible | 918 | 47 | 0.6127 | 0.5154 | 47 |
| 2024-17 | 2024 | 17 | Azerbaijan Grand Prix | 881 | eligible | 881 | 36 | 0.6398 | 0.8105 | 36 |
| 2024-18 | 2024 | 18 | Singapore Grand Prix | 1109 | eligible | 1099 | 40 | 0.8847 | 0.6996 | 40 |
| 2024-19 | 2024 | 19 | United States Grand Prix | 937 | eligible | 933 | 40 | 0.6336 | 0.7538 | 40 |
| 2024-2 | 2024 | 2 | Saudi Arabian Grand Prix | 816 | eligible | 735 | 22 | 0.5514 | 1.0730 | 22 |
| 2024-20 | 2024 | 20 | Mexico City Grand Prix | 1061 | eligible | 1048 | 35 | 0.7621 | 0.5845 | 35 |
| 2024-22 | 2024 | 22 | Las Vegas Grand Prix | 826 | eligible | 790 | 50 | 0.6985 | 0.6967 | 50 |
| 2024-23 | 2024 | 23 | Qatar Grand Prix | 717 | eligible | 702 | 34 | 0.9886 | 1.5713 | 34 |
| 2024-24 | 2024 | 24 | Abu Dhabi Grand Prix | 921 | eligible | 908 | 39 | 0.8042 | 0.3828 | 39 |
| 2024-3 | 2024 | 3 | Australian Grand Prix | 857 | eligible | 776 | 40 | 0.5773 | 0.4518 | 40 |
| 2024-4 | 2024 | 4 | Japanese Grand Prix | 790 | eligible | 764 | 46 | 1.4538 | 1.1741 | 46 |
| 2024-5 | 2024 | 5 | Chinese Grand Prix | 762 | eligible | 669 | 42 | 0.9607 | 0.5746 | 42 |
| 2024-6 | 2024 | 6 | Miami Grand Prix | 934 | eligible | 913 | 43 | 0.5110 | 0.5771 | 43 |
| 2024-7 | 2024 | 7 | Emilia Romagna Grand Prix | 1164 | eligible | 1136 | 40 | 1.2419 | 0.5443 | 40 |
| 2024-8 | 2024 | 8 | Monaco Grand Prix | 1187 | eligible | 1178 | 21 | 2.3051 | 3.7295 | 21 |
| 2024-9 | 2024 | 9 | Canadian Grand Prix | 318 | low_data | 290 | 18 | 3.2058 | 3.7747 | 18 |

## Limitations

The model modestly beats the zero-degradation baseline in the eligible
held-out summaries above, but this is not causal validation. Race fixed
effects remove shared lap evolution, while race exclusions and rank deficiency
limit coverage. Fuel correction is approximate; the fixed-effects estimator
is invariant to this particular linear fuel term because race-lap effects
absorb it. Weekend-relative SOFT/MEDIUM/HARD labels do not identify the
underlying Pirelli C1-C5 rubber, and pooled estimates may not distinguish
compounds. Circuit intervals can be wide, especially with few qualifying
races. Drivers often pit before tyre fall-off, creating survivorship bias.
Do not treat estimates or `cliff_lap` outputs as detected physical cliffs or
pit-strategy advice.

The v4 artifact is `models\tyre_degradation_v4.joblib`. The earlier
stint-slope analysis remains documented in [results_v3.md](results_v3.md).
