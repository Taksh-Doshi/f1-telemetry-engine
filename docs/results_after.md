# Tyre degradation model: relative-pace results

## What changed

Instead of predicting absolute lap time, this analysis subtracts the median of
each driver's first three clean laps in each stint from every lap in that
stint. Short stints use all available clean laps and are counted. The model
uses the measured lap time without a fuel-correction constant: race-lap-number
fixed effects absorb shared fuel burn and track evolution across the race.
Driver-stint fixed effects control for pace differences within each stint.

The fit for each race is
`relative_time ~ driver_stint_FE + race_lap_FE + tyre_life:compound`.
The resulting race/compound estimates are pooled with a DerSimonian-Laird
random-effects meta-analysis and 95% confidence intervals. A circuit-specific
pool is used only when at least 3 separate races contribute;
otherwise prediction falls back to the across-circuit compound estimate with
a warning.

## Data accounting and diagnostics

Input clean-view rows: **60,706**. Rows excluded from this
model for missing or invalid required fields: **479**.
Missing required values by field: year=0, round=0, circuit=0, driver_code=0, compound=330, tyre_life=418, stint_number=0, lap_number=0, lap_time_seconds=0.
Stints with fewer than three clean baseline laps: **62**;
those stints use the available first laps rather than being dropped.
Fresh-tyre flag: 47,247 true, 12,980 false,
0 unknown.

Fuel-sensitivity diagnostic uses the prior per-race, driver-fixed-effect slope
fit (not the new fixed-effects model), at 0, 0.015, 0.03, and 0.06 seconds per
race lap:

| fuel_burn_seconds_per_lap | compound | race_fits | mean_slope_seconds_per_lap | negative_slope_share |
| --- | --- | --- | --- | --- |
| 0.0000 | HARD | 59 | -0.0232 | 0.6102 |
| 0.0000 | MEDIUM | 64 | -0.0232 | 0.5156 |
| 0.0000 | SOFT | 33 | -0.0270 | 0.5455 |
| 0.0150 | HARD | 59 | -0.0078 | 0.4576 |
| 0.0150 | MEDIUM | 64 | -0.0076 | 0.4531 |
| 0.0150 | SOFT | 33 | -0.0084 | 0.4242 |
| 0.0300 | HARD | 59 | 0.0077 | 0.3390 |
| 0.0300 | MEDIUM | 64 | 0.0080 | 0.3750 |
| 0.0300 | SOFT | 33 | 0.0102 | 0.3636 |
| 0.0600 | HARD | 59 | 0.0387 | 0.2034 |
| 0.0600 | MEDIUM | 64 | 0.0392 | 0.2188 |
| 0.0600 | SOFT | 33 | 0.0473 | 0.2424 |

Tyre-age correlations with race lap and stint lap:

| tyre_set | laps | tyre_life_vs_race_lap_r | tyre_life_vs_stint_lap_r | fresh_flag_unknown_laps |
| --- | --- | --- | --- | --- |
| all | 60227 | 0.5249 | 0.9773 | 0 |
| fresh | 47247 | 0.5385 | 0.9859 | 0 |
| used | 12980 | 0.4718 | 0.9674 | 0 |

The clearest structural problem is the near-collinearity between tyre age and
stint lap (r=0.977 overall,
0.986 for fresh sets, and
0.967 for used sets).
That leaves little independent information to identify wear. The assumed fuel
correction most strongly changes the old slope diagnostic: changing the rate
from 0 to 0.060 seconds per race lap moves its mean slope
from -0.0240 to 0.0407 seconds
per tyre-age lap and changes the negative-slope share from
55.8% to 21.8%.
These are sensitivities, not evidence that the larger fuel rate is correct.

## Per-race and pooled slope estimates

The range check is an explicit flag, not a filter: estimates outside the
roughly -0.05 to +0.5 seconds/lap range remain in the table. There are
148 pool-eligible race/compound estimates, 38
additional finite estimates flagged for too little data or unusable standard
error, 96/148 (64.9%)
eligible estimates below zero, 66 rank-deficient fixed-effects
race designs, and 0 failed races.

| year | round | circuit | compound | slope_seconds_per_lap | standard_error | laps | drivers | stints | status | plausibility_flag |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2022 | 1 | Bahrain Grand Prix | HARD | 0.1033 | 0.0242 | 91 | 7 | 7 | collinear_design_130_of_131 | within_approx_range |
| 2022 | 1 | Bahrain Grand Prix | MEDIUM | 0.0798 | 0.0110 | 294 | 20 | 23 | collinear_design_130_of_131 | within_approx_range |
| 2022 | 1 | Bahrain Grand Prix | SOFT | 0.1303 | 0.0130 | 508 | 20 | 48 | collinear_design_130_of_131 | within_approx_range |
| 2022 | 10 | British Grand Prix | HARD | -0.7614 | 0.0568 | 151 | 12 | 12 | collinear_design_94_of_95 | outside_approx_-0.05_to_0.5 |
| 2022 | 10 | British Grand Prix | MEDIUM | -0.7656 | 0.0550 | 355 | 14 | 19 | collinear_design_94_of_95 | outside_approx_-0.05_to_0.5 |
| 2022 | 10 | British Grand Prix | SOFT | -0.5727 | 0.0570 | 170 | 13 | 16 | collinear_design_94_of_95 | outside_approx_-0.05_to_0.5 |
| 2022 | 11 | Austrian Grand Prix | HARD | -0.0013 | 0.0096 | 544 | 20 | 23 | collinear_design_112_of_113 | within_approx_range |
| 2022 | 11 | Austrian Grand Prix | MEDIUM | 0.0145 | 0.0190 | 299 | 18 | 20 | collinear_design_112_of_113 | within_approx_range |
| 2022 | 12 | French Grand Prix | HARD | -0.0043 | 0.0096 | 523 | 19 | 23 | collinear_design_93_of_94 | within_approx_range |
| 2022 | 12 | French Grand Prix | MEDIUM | -0.0153 | 0.0120 | 310 | 20 | 22 | collinear_design_93_of_94 | within_approx_range |
| 2022 | 13 | Hungarian Grand Prix | HARD | 0.0224 | 0.0129 | 251 | 9 | 9 | collinear_design_129_of_130 | within_approx_range |
| 2022 | 13 | Hungarian Grand Prix | MEDIUM | 0.0443 | 0.0048 | 665 | 20 | 31 | collinear_design_129_of_130 | within_approx_range |
| 2022 | 13 | Hungarian Grand Prix | SOFT | 0.0803 | 0.0202 | 287 | 16 | 21 | collinear_design_129_of_130 | within_approx_range |
| 2022 | 14 | Belgian Grand Prix | HARD | 0.0465 | 0.0223 | 232 | 15 | 15 | collinear_design_95_of_96 | within_approx_range |
| 2022 | 14 | Belgian Grand Prix | MEDIUM | 0.0763 | 0.0285 | 339 | 18 | 32 | collinear_design_95_of_96 | within_approx_range |
| 2022 | 14 | Belgian Grand Prix | SOFT | 0.0798 | 0.0369 | 74 | 7 | 7 | collinear_design_95_of_96 | within_approx_range |
| 2022 | 15 | Dutch Grand Prix | HARD | -0.0180 | 0.0090 | 261 | 17 | 17 | collinear_design_146_of_148 | within_approx_range |
| 2022 | 15 | Dutch Grand Prix | MEDIUM | -0.0109 | 0.0079 | 448 | 18 | 25 | collinear_design_146_of_148 | within_approx_range |
| 2022 | 15 | Dutch Grand Prix | SOFT | 0.0097 | 0.0090 | 430 | 19 | 38 | collinear_design_146_of_148 | within_approx_range |
| 2022 | 16 | Italian Grand Prix | HARD | -0.0266 | 0.0117 | 253 | 10 | 10 | collinear_design_86_of_87 | within_approx_range |
| 2022 | 16 | Italian Grand Prix | MEDIUM | -0.0409 | 0.0076 | 368 | 18 | 18 | collinear_design_86_of_87 | within_approx_range |
| 2022 | 16 | Italian Grand Prix | SOFT | -0.0270 | 0.0123 | 157 | 11 | 12 | collinear_design_86_of_87 | within_approx_range |
| 2022 | 17 | Singapore Grand Prix | MEDIUM | -0.5160 | 0.0430 | 190 | 11 | 12 | collinear_design_45_of_47 | outside_approx_-0.05_to_0.5 |
| 2022 | 17 | Singapore Grand Prix | SOFT | -0.4735 | 0.0402 | 87 | 5 | 6 | collinear_design_45_of_47 | outside_approx_-0.05_to_0.5 |
| 2022 | 19 | United States Grand Prix | HARD | -0.0383 | 0.0087 | 474 | 18 | 27 | collinear_design_101_of_103 | within_approx_range |
| 2022 | 19 | United States Grand Prix | MEDIUM | -0.0105 | 0.0085 | 303 | 18 | 26 | collinear_design_101_of_103 | within_approx_range |
| 2022 | 19 | United States Grand Prix | SOFT | -0.1875 | 0.0517 | 1 | 1 | 1 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2022 | 2 | Saudi Arabian Grand Prix | HARD | -0.0888 | 0.0159 | 429 | 17 | 18 | collinear_design_77_of_78 | outside_approx_-0.05_to_0.5 |
| 2022 | 2 | Saudi Arabian Grand Prix | MEDIUM | -0.0092 | 0.0391 | 222 | 18 | 18 | collinear_design_77_of_78 | within_approx_range |
| 2022 | 20 | Mexico City Grand Prix | HARD | -0.0238 | 0.0072 | 217 | 7 | 7 | collinear_design_114_of_115 | within_approx_range |
| 2022 | 20 | Mexico City Grand Prix | MEDIUM | -0.0262 | 0.0023 | 666 | 19 | 19 | collinear_design_114_of_115 | within_approx_range |
| 2022 | 20 | Mexico City Grand Prix | SOFT | -0.0052 | 0.0079 | 401 | 15 | 17 | collinear_design_114_of_115 | within_approx_range |
| 2022 | 21 | São Paulo Grand Prix | HARD | 0.0628 | 0.0201 | 10 | 1 | 1 | too_little_data_or_unusable_se | within_approx_range |
| 2022 | 21 | São Paulo Grand Prix | MEDIUM | -0.0102 | 0.0084 | 473 | 18 | 29 | collinear_design_119_of_120 | within_approx_range |
| 2022 | 21 | São Paulo Grand Prix | SOFT | -0.0188 | 0.0112 | 458 | 17 | 29 | collinear_design_119_of_120 | within_approx_range |
| 2022 | 22 | Abu Dhabi Grand Prix | HARD | -0.0153 | 0.0104 | 580 | 20 | 23 | collinear_design_109_of_110 | within_approx_range |
| 2022 | 22 | Abu Dhabi Grand Prix | MEDIUM | 0.0454 | 0.0190 | 409 | 19 | 25 | collinear_design_109_of_110 | within_approx_range |
| 2022 | 22 | Abu Dhabi Grand Prix | SOFT | 0.0497 | 0.0352 | 43 | 3 | 3 | too_little_data_or_unusable_se | within_approx_range |
| 2022 | 3 | Australian Grand Prix | HARD | -0.1073 | 0.0093 | 593 | 19 | 22 | collinear_design_86_of_87 | outside_approx_-0.05_to_0.5 |
| 2022 | 3 | Australian Grand Prix | MEDIUM | 0.0173 | 0.0175 | 220 | 16 | 17 | collinear_design_86_of_87 | within_approx_range |
| 2022 | 4 | Emilia Romagna Grand Prix | HARD | -0.2409 | 0.0048 | 31 | 1 | 1 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2022 | 4 | Emilia Romagna Grand Prix | MEDIUM | -0.2269 | 0.0037 | 699 | 18 | 18 | collinear_design_71_of_72 | outside_approx_-0.05_to_0.5 |
| 2022 | 4 | Emilia Romagna Grand Prix | SOFT | -0.1446 | 0.0557 | 43 | 4 | 5 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2022 | 5 | Miami Grand Prix | HARD | -0.0662 | 0.0065 | 519 | 19 | 19 | collinear_design_95_of_96 | outside_approx_-0.05_to_0.5 |
| 2022 | 5 | Miami Grand Prix | MEDIUM | -0.0400 | 0.0154 | 326 | 19 | 22 | collinear_design_95_of_96 | within_approx_range |
| 2022 | 5 | Miami Grand Prix | SOFT | -0.0148 | 0.0627 | 33 | 3 | 3 | too_little_data_or_unusable_se | within_approx_range |
| 2022 | 6 | Spanish Grand Prix | HARD | 0.1074 | 0.0112 | 34 | 1 | 1 | too_little_data_or_unusable_se | within_approx_range |
| 2022 | 6 | Spanish Grand Prix | MEDIUM | 0.0558 | 0.0129 | 463 | 20 | 26 | collinear_design_137_of_138 | within_approx_range |
| 2022 | 6 | Spanish Grand Prix | SOFT | 0.0606 | 0.0130 | 607 | 19 | 44 | collinear_design_137_of_138 | within_approx_range |
| 2022 | 7 | Monaco Grand Prix | HARD | -0.4005 | 0.0113 | 247 | 11 | 14 | collinear_design_80_of_83 | outside_approx_-0.05_to_0.5 |
| 2022 | 7 | Monaco Grand Prix | MEDIUM | -0.3391 | 0.0328 | 287 | 10 | 11 | collinear_design_80_of_83 | outside_approx_-0.05_to_0.5 |
| 2022 | 7 | Monaco Grand Prix | SOFT | -1.3782 | 0.0593 | 6 | 1 | 1 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2022 | 8 | Azerbaijan Grand Prix | HARD | -0.0651 | 0.0112 | 543 | 19 | 25 | collinear_design_94_of_95 | outside_approx_-0.05_to_0.5 |
| 2022 | 8 | Azerbaijan Grand Prix | MEDIUM | -0.0024 | 0.0227 | 210 | 20 | 21 | collinear_design_94_of_95 | within_approx_range |
| 2022 | 8 | Azerbaijan Grand Prix | SOFT | -0.0520 | 0.0223 | 11 | 1 | 1 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2022 | 9 | Canadian Grand Prix | HARD | -0.0325 | 0.0096 | 758 | 19 | 30 | collinear_design_111_of_112 | within_approx_range |
| 2022 | 9 | Canadian Grand Prix | MEDIUM | -0.0235 | 0.0243 | 271 | 19 | 21 | collinear_design_111_of_112 | within_approx_range |
| 2023 | 1 | Bahrain Grand Prix | HARD | 0.0306 | 0.0093 | 513 | 19 | 34 | collinear_design_126_of_127 | within_approx_range |
| 2023 | 1 | Bahrain Grand Prix | MEDIUM | 0.2409 | 0.0257 | 8 | 1 | 1 | too_little_data_or_unusable_se | within_approx_range |
| 2023 | 1 | Bahrain Grand Prix | SOFT | 0.0722 | 0.0138 | 393 | 20 | 34 | collinear_design_126_of_127 | within_approx_range |
| 2023 | 10 | British Grand Prix | HARD | -0.0532 | 0.0112 | 116 | 8 | 8 | collinear_design_89_of_90 | outside_approx_-0.05_to_0.5 |
| 2023 | 10 | British Grand Prix | MEDIUM | -0.0384 | 0.0051 | 438 | 17 | 18 | collinear_design_89_of_90 | within_approx_range |
| 2023 | 10 | British Grand Prix | SOFT | -0.0432 | 0.0088 | 248 | 15 | 17 | collinear_design_89_of_90 | within_approx_range |
| 2023 | 11 | Hungarian Grand Prix | HARD | -0.0117 | 0.0074 | 723 | 18 | 28 | collinear_design_124_of_125 | within_approx_range |
| 2023 | 11 | Hungarian Grand Prix | MEDIUM | -0.0187 | 0.0069 | 408 | 16 | 23 | collinear_design_124_of_125 | within_approx_range |
| 2023 | 11 | Hungarian Grand Prix | SOFT | 0.0287 | 0.0140 | 27 | 3 | 3 | too_little_data_or_unusable_se | within_approx_range |
| 2023 | 12 | Belgian Grand Prix | HARD | 0.1541 | 0.0295 | 10 | 1 | 1 | too_little_data_or_unusable_se | within_approx_range |
| 2023 | 12 | Belgian Grand Prix | MEDIUM | 0.0328 | 0.0172 | 369 | 19 | 27 | collinear_design_100_of_101 | within_approx_range |
| 2023 | 12 | Belgian Grand Prix | SOFT | 0.0248 | 0.0240 | 342 | 19 | 28 | collinear_design_100_of_101 | within_approx_range |
| 2023 | 13 | Dutch Grand Prix | HARD | -0.9154 | 0.0137 | 38 | 1 | 1 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2023 | 13 | Dutch Grand Prix | MEDIUM | -0.8624 | 0.0153 | 157 | 9 | 9 | collinear_design_100_of_101 | outside_approx_-0.05_to_0.5 |
| 2023 | 13 | Dutch Grand Prix | SOFT | -0.8561 | 0.0133 | 610 | 20 | 36 | collinear_design_100_of_101 | outside_approx_-0.05_to_0.5 |
| 2023 | 14 | Italian Grand Prix | HARD | 0.0278 | 0.0079 | 474 | 19 | 19 | collinear_design_94_of_95 | within_approx_range |
| 2023 | 14 | Italian Grand Prix | MEDIUM | 0.0112 | 0.0081 | 404 | 19 | 25 | collinear_design_94_of_95 | within_approx_range |
| 2023 | 15 | Singapore Grand Prix | HARD | -0.0373 | 0.0077 | 522 | 18 | 18 | collinear_design_100_of_101 | within_approx_range |
| 2023 | 15 | Singapore Grand Prix | MEDIUM | -0.0160 | 0.0128 | 383 | 17 | 21 | collinear_design_100_of_101 | within_approx_range |
| 2023 | 15 | Singapore Grand Prix | SOFT | -0.1368 | 0.0696 | 53 | 3 | 3 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2023 | 16 | Japanese Grand Prix | HARD | 0.0386 | 0.0166 | 419 | 16 | 23 | collinear_design_100_of_101 | within_approx_range |
| 2023 | 16 | Japanese Grand Prix | MEDIUM | 0.0454 | 0.0142 | 225 | 15 | 19 | collinear_design_100_of_101 | within_approx_range |
| 2023 | 16 | Japanese Grand Prix | SOFT | 0.0381 | 0.0139 | 58 | 8 | 9 | collinear_design_100_of_101 | within_approx_range |
| 2023 | 17 | Qatar Grand Prix | HARD | -0.1066 | 0.0156 | 369 | 18 | 25 | collinear_design_121_of_122 | outside_approx_-0.05_to_0.5 |
| 2023 | 17 | Qatar Grand Prix | MEDIUM | -0.1319 | 0.0118 | 455 | 18 | 40 | collinear_design_121_of_122 | outside_approx_-0.05_to_0.5 |
| 2023 | 17 | Qatar Grand Prix | SOFT | -0.1991 | 0.1182 | 10 | 2 | 2 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2023 | 18 | United States Grand Prix | HARD | -0.0253 | 0.0090 | 393 | 18 | 21 | collinear_design_112_of_113 | within_approx_range |
| 2023 | 18 | United States Grand Prix | MEDIUM | -0.0015 | 0.0076 | 518 | 20 | 33 | collinear_design_112_of_113 | within_approx_range |
| 2023 | 18 | United States Grand Prix | SOFT | 0.2661 | 0.0536 | 8 | 2 | 2 | too_little_data_or_unusable_se | within_approx_range |
| 2023 | 19 | Mexico City Grand Prix | HARD | -0.0236 | 0.0183 | 497 | 19 | 26 | collinear_design_117_of_119 | within_approx_range |
| 2023 | 19 | Mexico City Grand Prix | MEDIUM | -0.0409 | 0.0111 | 630 | 19 | 24 | collinear_design_117_of_119 | within_approx_range |
| 2023 | 19 | Mexico City Grand Prix | SOFT | -0.0755 | 0.0189 | 7 | 1 | 1 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2023 | 2 | Saudi Arabian Grand Prix | HARD | -0.0565 | 0.0108 | 478 | 20 | 20 | collinear_design_89_of_90 | outside_approx_-0.05_to_0.5 |
| 2023 | 2 | Saudi Arabian Grand Prix | MEDIUM | -0.0535 | 0.0120 | 324 | 18 | 20 | collinear_design_89_of_90 | outside_approx_-0.05_to_0.5 |
| 2023 | 2 | Saudi Arabian Grand Prix | SOFT | -0.0316 | 0.0544 | 27 | 2 | 2 | too_little_data_or_unusable_se | within_approx_range |
| 2023 | 20 | São Paulo Grand Prix | MEDIUM | -0.3099 | 0.0950 | 333 | 15 | 15 | collinear_design_118_of_119 | outside_approx_-0.05_to_0.5 |
| 2023 | 20 | São Paulo Grand Prix | SOFT | -0.3626 | 0.0932 | 653 | 17 | 35 | collinear_design_118_of_119 | outside_approx_-0.05_to_0.5 |
| 2023 | 21 | Las Vegas Grand Prix | HARD | -0.1191 | 0.0176 | 576 | 19 | 29 | collinear_design_87_of_88 | outside_approx_-0.05_to_0.5 |
| 2023 | 21 | Las Vegas Grand Prix | MEDIUM | -0.0674 | 0.0386 | 159 | 15 | 15 | collinear_design_87_of_88 | outside_approx_-0.05_to_0.5 |
| 2023 | 21 | Las Vegas Grand Prix | SOFT | 0.1942 | 0.1019 | 3 | 1 | 1 | too_little_data_or_unusable_se | within_approx_range |
| 2023 | 22 | Abu Dhabi Grand Prix | HARD | -0.0123 | 0.0065 | 794 | 20 | 36 | collinear_design_113_of_114 | within_approx_range |
| 2023 | 22 | Abu Dhabi Grand Prix | MEDIUM | 0.0202 | 0.0113 | 269 | 19 | 20 | collinear_design_113_of_114 | within_approx_range |
| 2023 | 3 | Australian Grand Prix | HARD | -0.1062 | 0.0047 | 667 | 18 | 23 | collinear_design_84_of_86 | outside_approx_-0.05_to_0.5 |
| 2023 | 3 | Australian Grand Prix | MEDIUM | -0.0450 | 0.0116 | 93 | 14 | 14 | collinear_design_84_of_86 | within_approx_range |
| 2023 | 3 | Australian Grand Prix | SOFT | -0.1676 | 0.0650 | 9 | 2 | 2 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2023 | 4 | Azerbaijan Grand Prix | HARD | -0.0769 | 0.0057 | 708 | 20 | 22 | collinear_design_88_of_90 | outside_approx_-0.05_to_0.5 |
| 2023 | 4 | Azerbaijan Grand Prix | MEDIUM | -0.0195 | 0.0184 | 137 | 17 | 18 | collinear_design_88_of_90 | within_approx_range |
| 2023 | 4 | Azerbaijan Grand Prix | SOFT | -0.3232 | 0.0841 | 1 | 1 | 1 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2023 | 5 | Miami Grand Prix | HARD | -0.0573 | 0.0043 | 787 | 20 | 20 | collinear_design_96_of_97 | outside_approx_-0.05_to_0.5 |
| 2023 | 5 | Miami Grand Prix | MEDIUM | -0.0435 | 0.0096 | 286 | 17 | 17 | collinear_design_96_of_97 | within_approx_range |
| 2023 | 5 | Miami Grand Prix | SOFT | -0.4830 | 0.1688 | 5 | 2 | 2 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2023 | 6 | Monaco Grand Prix | HARD | 0.0465 | 0.0127 | 633 | 17 | 17 | collinear_design_85_of_86 | within_approx_range |
| 2023 | 6 | Monaco Grand Prix | MEDIUM | 0.0285 | 0.0081 | 347 | 12 | 12 | collinear_design_85_of_86 | within_approx_range |
| 2023 | 6 | Monaco Grand Prix | SOFT | 0.2577 | 0.0139 | 27 | 1 | 1 | too_little_data_or_unusable_se | within_approx_range |
| 2023 | 7 | Spanish Grand Prix | HARD | 0.0013 | 0.0086 | 509 | 18 | 22 | collinear_design_128_of_129 | within_approx_range |
| 2023 | 7 | Spanish Grand Prix | MEDIUM | -0.0073 | 0.0095 | 374 | 15 | 17 | collinear_design_128_of_129 | within_approx_range |
| 2023 | 7 | Spanish Grand Prix | SOFT | -0.0207 | 0.0096 | 324 | 19 | 23 | collinear_design_128_of_129 | within_approx_range |
| 2023 | 8 | Canadian Grand Prix | HARD | -0.0379 | 0.0087 | 770 | 19 | 28 | collinear_design_115_of_116 | within_approx_range |
| 2023 | 8 | Canadian Grand Prix | MEDIUM | -0.0505 | 0.0103 | 315 | 18 | 21 | collinear_design_115_of_116 | outside_approx_-0.05_to_0.5 |
| 2023 | 8 | Canadian Grand Prix | SOFT | -0.0105 | 0.0157 | 7 | 2 | 2 | too_little_data_or_unusable_se | within_approx_range |
| 2023 | 9 | Austrian Grand Prix | HARD | 0.0030 | 0.0067 | 667 | 19 | 29 | collinear_design_126_of_128 | within_approx_range |
| 2023 | 9 | Austrian Grand Prix | MEDIUM | 0.0042 | 0.0082 | 518 | 19 | 30 | collinear_design_126_of_128 | within_approx_range |
| 2023 | 9 | Austrian Grand Prix | SOFT | -0.1437 | 0.0450 | 1 | 1 | 1 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2024 | 1 | Bahrain Grand Prix | HARD | 0.0325 | 0.0089 | 731 | 20 | 37 | collinear_design_118_of_119 | within_approx_range |
| 2024 | 1 | Bahrain Grand Prix | SOFT | 0.0512 | 0.0164 | 293 | 20 | 25 | collinear_design_118_of_119 | within_approx_range |
| 2024 | 10 | Spanish Grand Prix | HARD | 0.0658 | 0.0152 | 346 | 13 | 13 | collinear_design_128_of_129 | within_approx_range |
| 2024 | 10 | Spanish Grand Prix | MEDIUM | -0.0010 | 0.0093 | 401 | 19 | 19 | collinear_design_128_of_129 | within_approx_range |
| 2024 | 10 | Spanish Grand Prix | SOFT | 0.0599 | 0.0124 | 459 | 20 | 30 | collinear_design_128_of_129 | within_approx_range |
| 2024 | 11 | Austrian Grand Prix | HARD | 0.0347 | 0.0055 | 671 | 20 | 27 | collinear_design_134_of_135 | within_approx_range |
| 2024 | 11 | Austrian Grand Prix | MEDIUM | 0.0490 | 0.0046 | 592 | 20 | 34 | collinear_design_134_of_135 | within_approx_range |
| 2024 | 11 | Austrian Grand Prix | SOFT | -0.6128 | 0.0452 | 6 | 2 | 2 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2024 | 12 | British Grand Prix | HARD | 0.1527 | 0.0147 | 39 | 3 | 3 | too_little_data_or_unusable_se | within_approx_range |
| 2024 | 12 | British Grand Prix | MEDIUM | 0.1397 | 0.0085 | 465 | 19 | 24 | collinear_design_81_of_83 | within_approx_range |
| 2024 | 12 | British Grand Prix | SOFT | 0.2655 | 0.0314 | 158 | 13 | 14 | collinear_design_81_of_83 | within_approx_range |
| 2024 | 13 | Hungarian Grand Prix | HARD | 0.0095 | 0.0102 | 821 | 20 | 30 | collinear_design_129_of_130 | within_approx_range |
| 2024 | 13 | Hungarian Grand Prix | MEDIUM | -0.0117 | 0.0110 | 399 | 17 | 23 | collinear_design_129_of_130 | within_approx_range |
| 2024 | 13 | Hungarian Grand Prix | SOFT | -0.0449 | 0.0402 | 34 | 6 | 6 | collinear_design_129_of_130 | within_approx_range |
| 2024 | 14 | Belgian Grand Prix | HARD | -0.0267 | 0.0144 | 377 | 16 | 23 | collinear_design_98_of_99 | within_approx_range |
| 2024 | 14 | Belgian Grand Prix | MEDIUM | -0.0266 | 0.0125 | 317 | 19 | 27 | collinear_design_98_of_99 | within_approx_range |
| 2024 | 14 | Belgian Grand Prix | SOFT | -0.0420 | 0.0144 | 57 | 3 | 4 | too_little_data_or_unusable_se | within_approx_range |
| 2024 | 15 | Dutch Grand Prix | HARD | -0.0168 | 0.0054 | 780 | 20 | 20 | collinear_design_118_of_119 | within_approx_range |
| 2024 | 15 | Dutch Grand Prix | MEDIUM | 0.0044 | 0.0090 | 470 | 19 | 20 | collinear_design_118_of_119 | within_approx_range |
| 2024 | 15 | Dutch Grand Prix | SOFT | 0.0209 | 0.0078 | 104 | 5 | 6 | collinear_design_118_of_119 | within_approx_range |
| 2024 | 16 | Italian Grand Prix | HARD | -0.0256 | 0.0072 | 686 | 20 | 30 | collinear_design_102_of_104 | within_approx_range |
| 2024 | 16 | Italian Grand Prix | MEDIUM | -0.0121 | 0.0159 | 240 | 19 | 19 | collinear_design_102_of_104 | within_approx_range |
| 2024 | 16 | Italian Grand Prix | SOFT | -0.2133 | 0.1069 | 1 | 1 | 1 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2024 | 17 | Azerbaijan Grand Prix | HARD | -0.0755 | 0.0094 | 695 | 19 | 20 | collinear_design_85_of_86 | outside_approx_-0.05_to_0.5 |
| 2024 | 17 | Azerbaijan Grand Prix | MEDIUM | -0.0153 | 0.0314 | 186 | 16 | 16 | collinear_design_85_of_86 | within_approx_range |
| 2024 | 18 | Singapore Grand Prix | HARD | -0.0064 | 0.0054 | 512 | 17 | 17 | collinear_design_105_of_106 | within_approx_range |
| 2024 | 18 | Singapore Grand Prix | MEDIUM | -0.0014 | 0.0080 | 506 | 19 | 19 | collinear_design_105_of_106 | within_approx_range |
| 2024 | 18 | Singapore Grand Prix | SOFT | -0.0218 | 0.0319 | 91 | 5 | 7 | collinear_design_105_of_106 | within_approx_range |
| 2024 | 19 | United States Grand Prix | HARD | -0.0591 | 0.0126 | 536 | 19 | 19 | collinear_design_95_of_96 | outside_approx_-0.05_to_0.5 |
| 2024 | 19 | United States Grand Prix | MEDIUM | -0.0295 | 0.0083 | 398 | 19 | 22 | collinear_design_95_of_96 | within_approx_range |
| 2024 | 19 | United States Grand Prix | SOFT | 1.3161 | 0.1314 | 3 | 1 | 1 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2024 | 2 | Saudi Arabian Grand Prix | HARD | -0.1004 | 0.0071 | 570 | 15 | 15 | collinear_design_85_of_86 | outside_approx_-0.05_to_0.5 |
| 2024 | 2 | Saudi Arabian Grand Prix | MEDIUM | -0.0921 | 0.0102 | 191 | 17 | 17 | collinear_design_85_of_86 | outside_approx_-0.05_to_0.5 |
| 2024 | 2 | Saudi Arabian Grand Prix | SOFT | -0.0888 | 0.0311 | 55 | 5 | 6 | collinear_design_85_of_86 | outside_approx_-0.05_to_0.5 |
| 2024 | 20 | Mexico City Grand Prix | HARD | -0.0020 | 0.0039 | 638 | 17 | 17 | collinear_design_105_of_106 | within_approx_range |
| 2024 | 20 | Mexico City Grand Prix | MEDIUM | 0.0258 | 0.0122 | 417 | 18 | 19 | collinear_design_105_of_106 | within_approx_range |
| 2024 | 20 | Mexico City Grand Prix | SOFT | 1.5560 | 0.1083 | 6 | 3 | 3 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2024 | 22 | Las Vegas Grand Prix | HARD | 0.0037 | 0.0172 | 640 | 20 | 36 | collinear_design_107_of_108 | within_approx_range |
| 2024 | 22 | Las Vegas Grand Prix | MEDIUM | 0.0526 | 0.0274 | 181 | 19 | 19 | collinear_design_107_of_108 | within_approx_range |
| 2024 | 22 | Las Vegas Grand Prix | SOFT | 0.4134 | 0.1096 | 5 | 2 | 2 | too_little_data_or_unusable_se | within_approx_range |
| 2024 | 23 | Qatar Grand Prix | HARD | -0.1976 | 0.0196 | 198 | 13 | 17 | collinear_design_84_of_86 | outside_approx_-0.05_to_0.5 |
| 2024 | 23 | Qatar Grand Prix | MEDIUM | -0.1865 | 0.0208 | 477 | 17 | 19 | collinear_design_84_of_86 | outside_approx_-0.05_to_0.5 |
| 2024 | 23 | Qatar Grand Prix | SOFT | -0.0198 | 0.0580 | 42 | 3 | 3 | too_little_data_or_unusable_se | within_approx_range |
| 2024 | 24 | Abu Dhabi Grand Prix | HARD | 0.0221 | 0.0105 | 652 | 19 | 24 | collinear_design_99_of_100 | within_approx_range |
| 2024 | 24 | Abu Dhabi Grand Prix | MEDIUM | 0.0108 | 0.0083 | 245 | 17 | 17 | collinear_design_99_of_100 | within_approx_range |
| 2024 | 24 | Abu Dhabi Grand Prix | SOFT | 0.1277 | 0.0108 | 24 | 1 | 2 | too_little_data_or_unusable_se | within_approx_range |
| 2024 | 3 | Australian Grand Prix | HARD | -0.0224 | 0.0078 | 697 | 18 | 36 | collinear_design_111_of_112 | within_approx_range |
| 2024 | 3 | Australian Grand Prix | MEDIUM | 0.0034 | 0.0114 | 148 | 16 | 16 | collinear_design_111_of_112 | within_approx_range |
| 2024 | 3 | Australian Grand Prix | SOFT | -0.0108 | 0.0326 | 12 | 3 | 3 | too_little_data_or_unusable_se | within_approx_range |
| 2024 | 4 | Japanese Grand Prix | HARD | -0.8583 | 0.0712 | 500 | 18 | 28 | collinear_design_105_of_106 | outside_approx_-0.05_to_0.5 |
| 2024 | 4 | Japanese Grand Prix | MEDIUM | -0.9044 | 0.0850 | 234 | 14 | 17 | collinear_design_105_of_106 | outside_approx_-0.05_to_0.5 |
| 2024 | 4 | Japanese Grand Prix | SOFT | -0.7552 | 0.0857 | 56 | 7 | 8 | collinear_design_105_of_106 | outside_approx_-0.05_to_0.5 |
| 2024 | 5 | Chinese Grand Prix | HARD | 0.0403 | 0.0198 | 423 | 18 | 25 | collinear_design_104_of_105 | within_approx_range |
| 2024 | 5 | Chinese Grand Prix | MEDIUM | 0.0594 | 0.0215 | 283 | 20 | 27 | collinear_design_104_of_105 | within_approx_range |
| 2024 | 5 | Chinese Grand Prix | SOFT | 0.1011 | 0.0407 | 56 | 6 | 6 | collinear_design_104_of_105 | within_approx_range |
| 2024 | 6 | Miami Grand Prix | HARD | -0.0390 | 0.0063 | 413 | 19 | 19 | collinear_design_98_of_99 | within_approx_range |
| 2024 | 6 | Miami Grand Prix | MEDIUM | -0.0463 | 0.0068 | 484 | 20 | 25 | collinear_design_98_of_99 | within_approx_range |
| 2024 | 6 | Miami Grand Prix | SOFT | -0.0514 | 0.0073 | 37 | 3 | 3 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2024 | 7 | Emilia Romagna Grand Prix | HARD | 0.0098 | 0.0070 | 684 | 19 | 19 | collinear_design_109_of_110 | within_approx_range |
| 2024 | 7 | Emilia Romagna Grand Prix | MEDIUM | 0.0236 | 0.0078 | 467 | 20 | 24 | collinear_design_109_of_110 | within_approx_range |
| 2024 | 7 | Emilia Romagna Grand Prix | SOFT | -0.2326 | 0.1312 | 13 | 2 | 3 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2024 | 8 | Monaco Grand Prix | HARD | -0.1579 | 0.0052 | 764 | 13 | 13 | collinear_design_100_of_101 | outside_approx_-0.05_to_0.5 |
| 2024 | 8 | Monaco Grand Prix | MEDIUM | -0.1715 | 0.0078 | 391 | 8 | 8 | collinear_design_100_of_101 | outside_approx_-0.05_to_0.5 |
| 2024 | 8 | Monaco Grand Prix | SOFT | -0.0620 | 0.0138 | 32 | 2 | 2 | too_little_data_or_unusable_se | outside_approx_-0.05_to_0.5 |
| 2024 | 9 | Canadian Grand Prix | HARD | -0.3164 | 0.0400 | 81 | 6 | 6 | collinear_design_48_of_50 | outside_approx_-0.05_to_0.5 |
| 2024 | 9 | Canadian Grand Prix | MEDIUM | -0.2952 | 0.0147 | 237 | 15 | 17 | collinear_design_48_of_50 | outside_approx_-0.05_to_0.5 |

Nominal compound random-effects pools:

| compound | pooled_slope_seconds_per_lap | lower_95 | upper_95 | race_estimates | tau_squared | negative_slope_share |
| --- | --- | --- | --- | --- | --- | --- |
| HARD | -0.0509 | -0.0682 | -0.0336 | 58 | 0.0041 | 0.7069 |
| MEDIUM | -0.0631 | -0.0894 | -0.0367 | 64 | 0.0107 | 0.6562 |
| SOFT | -0.0813 | -0.1618 | -0.0007 | 26 | 0.0387 | 0.5000 |

Circuit-specific pools (at least 3 races):

| circuit | compound | pooled_slope_seconds_per_lap | lower_95 | upper_95 | race_estimates | tau_squared |
| --- | --- | --- | --- | --- | --- | --- |
| Abu Dhabi Grand Prix | HARD | -0.0026 | -0.0500 | 0.0449 | 3 | 0.0003 |
| Abu Dhabi Grand Prix | MEDIUM | 0.0194 | -0.0154 | 0.0541 | 3 | 0.0001 |
| Australian Grand Prix | HARD | -0.0787 | -0.1970 | 0.0396 | 3 | 0.0022 |
| Australian Grand Prix | MEDIUM | -0.0093 | -0.0920 | 0.0733 | 3 | 0.0009 |
| Austrian Grand Prix | HARD | 0.0128 | -0.0403 | 0.0660 | 3 | 0.0004 |
| Austrian Grand Prix | MEDIUM | 0.0238 | -0.0528 | 0.1004 | 3 | 0.0008 |
| Azerbaijan Grand Prix | HARD | -0.0747 | -0.0940 | -0.0554 | 3 | 0.0000 |
| Azerbaijan Grand Prix | MEDIUM | -0.0132 | -0.0691 | 0.0428 | 3 | 0.0000 |
| Bahrain Grand Prix | HARD | 0.0461 | -0.0155 | 0.1077 | 3 | 0.0004 |
| Bahrain Grand Prix | SOFT | 0.0853 | -0.0180 | 0.1885 | 3 | 0.0015 |
| Belgian Grand Prix | HARD | 0.0079 | -0.4562 | 0.4720 | 2 | 0.0023 |
| Belgian Grand Prix | MEDIUM | 0.0234 | -0.1022 | 0.1491 | 3 | 0.0022 |
| Belgian Grand Prix | SOFT | 0.0452 | -0.2926 | 0.3830 | 2 | 0.0005 |
| British Grand Prix | HARD | -0.4051 | -4.9043 | 4.0941 | 2 | 0.2491 |
| British Grand Prix | MEDIUM | -0.2014 | -0.6002 | 0.1974 | 3 | 0.0248 |
| British Grand Prix | SOFT | -0.1120 | -0.7915 | 0.5675 | 3 | 0.0734 |
| Canadian Grand Prix | HARD | -0.1088 | -0.2677 | 0.0501 | 3 | 0.0036 |
| Canadian Grand Prix | MEDIUM | -0.1235 | -0.5067 | 0.2598 | 3 | 0.0235 |
| Dutch Grand Prix | HARD | -0.0171 | -0.0760 | 0.0418 | 2 | 0.0000 |
| Dutch Grand Prix | MEDIUM | -0.2894 | -1.2206 | 0.6418 | 3 | 0.1404 |
| Dutch Grand Prix | SOFT | -0.2751 | -1.2957 | 0.7456 | 3 | 0.1687 |
| Hungarian Grand Prix | HARD | 0.0048 | -0.0397 | 0.0492 | 3 | 0.0002 |
| Hungarian Grand Prix | MEDIUM | 0.0051 | -0.0961 | 0.1062 | 3 | 0.0016 |
| Hungarian Grand Prix | SOFT | 0.0225 | -0.7701 | 0.8152 | 2 | 0.0068 |
| Italian Grand Prix | HARD | -0.0078 | -0.0899 | 0.0743 | 3 | 0.0010 |
| Italian Grand Prix | MEDIUM | -0.0141 | -0.0947 | 0.0665 | 3 | 0.0009 |
| Mexico City Grand Prix | HARD | -0.0139 | -0.0534 | 0.0257 | 3 | 0.0002 |
| Mexico City Grand Prix | MEDIUM | -0.0149 | -0.0814 | 0.0516 | 3 | 0.0006 |
| Mexico City Grand Prix | SOFT | -0.0052 | -0.0208 | 0.0104 | 1 | 0.0000 |
| Miami Grand Prix | HARD | -0.0542 | -0.0852 | -0.0233 | 3 | 0.0001 |
| Miami Grand Prix | MEDIUM | -0.0448 | -0.0672 | -0.0224 | 3 | 0.0000 |
| Monaco Grand Prix | HARD | -0.1707 | -0.6151 | 0.2737 | 3 | 0.0319 |
| Monaco Grand Prix | MEDIUM | -0.1581 | -0.5298 | 0.2136 | 3 | 0.0220 |
| Saudi Arabian Grand Prix | HARD | -0.0822 | -0.1468 | -0.0176 | 3 | 0.0005 |
| Saudi Arabian Grand Prix | MEDIUM | -0.0629 | -0.1454 | 0.0196 | 3 | 0.0008 |
| Singapore Grand Prix | MEDIUM | -0.1651 | -0.4669 | 0.1368 | 3 | 0.0141 |
| Singapore Grand Prix | SOFT | -0.2470 | -3.1165 | 2.6225 | 2 | 0.1007 |
| Spanish Grand Prix | HARD | 0.0324 | -0.3771 | 0.4419 | 2 | 0.0019 |
| Spanish Grand Prix | MEDIUM | 0.0148 | -0.0612 | 0.0908 | 3 | 0.0008 |
| Spanish Grand Prix | SOFT | 0.0328 | -0.0927 | 0.1583 | 3 | 0.0024 |
| United States Grand Prix | HARD | -0.0392 | -0.0774 | -0.0009 | 3 | 0.0001 |
| United States Grand Prix | MEDIUM | -0.0136 | -0.0494 | 0.0222 | 3 | 0.0001 |

Relative weekend-rank pools (softest/middle/hardest):

| relative_rank | pooled_slope_seconds_per_lap | lower_95 | upper_95 | race_estimates | tau_squared |
| --- | --- | --- | --- | --- | --- |
| hardest | -0.0509 | -0.0682 | -0.0336 | 58 | 0.0041 |
| middle | -0.0631 | -0.0894 | -0.0367 | 64 | 0.0107 |
| softest | -0.0813 | -0.1618 | -0.0007 | 26 | 0.0387 |

With only the labels SOFT/MEDIUM/HARD, relative-rank coding is ordered exactly
like those labels. It cannot recover which underlying Pirelli C1-C5 rubber was
used at each event. Therefore the nominal and relative-rank checks provide the
same ordering information, not an independent cure for cross-weekend compound
differences.

Compound ordering checks:

- Old approach: 3/9 complete season/circuit groups were SOFT > MEDIUM > HARD
  (33.3%).
- New nominal race fits: 6/17
  complete races (35.3%) had SOFT > MEDIUM > HARD.
- New relative-rank fits: 6/17
  complete races (35.3%) had softest > middle > hardest.
- Prior absolute-time slopes: 25/60 were negative (41.7%); new eligible
  race-level slopes: 96/148 (64.9%) were negative.

Before-versus-after comparison:

| approach | leave-one-race-out relative MAE (s) | negative slope share | complete-group compound ordering |
| --- | ---: | ---: | ---: |
| Original absolute-time model (before) | not measured on relative target | 25/60 (41.7%) | 3/9 (33.3%) |
| Legacy driver-adjusted formula, refit on relative target | 1.0996 | 40/60 (66.7%) | 4/10 (40.0%) |
| New race fixed-effects pool, nominal compounds | 1.1356 | 96/148 (64.9%) | 6/17 (35.3%) |
| New race fixed-effects pool, relative rank | 1.1356 | 96/148 (64.9%) | 6/17 (35.3%) |

The original absolute-time MAE cannot be compared directly to these relative-target scores.
The old/new ordering denominators differ because the old result grouped by
season and circuit, the relative-target legacy diagnostic groups by circuit,
and the new fixed-effects diagnostic groups by race.

## Honest validation on relative lap time

Leave-one-race-out holds out all laps from one year/round. Chronological
validation trains on 2022–2023 and tests only on 2024. The "legacy pooled
linear" comparator is refit on the same relative target using the older pooled
tyre-age/compound and driver-effect formula; this avoids comparing absolute
seconds to relative seconds.

Race-held-out MAE is the mean of per-race MAEs:

| model | mean_race_mae_seconds | standard_deviation_race_mae_seconds | races |
| --- | --- | --- | --- |
| No degradation (zero) | 1.0986 | 1.0358 | 66 |
| Legacy pooled linear, refit on relative target | 1.0996 | 0.8986 | 66 |
| New race-FE pool by nominal compound | 1.1356 | 0.8068 | 66 |
| New race-FE pool by relative rank | 1.1356 | 0.8068 | 66 |

Chronological 2022–2023 train / 2024 test:

| train_years | test_year | model | mae_seconds | laps |
| --- | --- | --- | --- | --- |
| 2022-2023 | 2024 | No degradation (zero) | 0.8867 | 21727 |
| 2022-2023 | 2024 | Legacy pooled linear, refit on relative target | 0.9219 | 21727 |
| 2022-2023 | 2024 | New race-FE pool by nominal compound | 0.9980 | 21727 |
| 2022-2023 | 2024 | New race-FE pool by relative rank | 0.9980 | 21727 |

Per-race errors for the race-held-out winner (No degradation (zero)):

| year | round | circuit | mae_seconds | laps |
| --- | --- | --- | --- | --- |
| 2022 | 1 | Bahrain Grand Prix | 0.7303 | 893 |
| 2022 | 10 | British Grand Prix | 1.8500 | 676 |
| 2022 | 11 | Austrian Grand Prix | 0.5886 | 843 |
| 2022 | 12 | French Grand Prix | 0.5821 | 833 |
| 2022 | 13 | Hungarian Grand Prix | 0.7166 | 1203 |
| 2022 | 14 | Belgian Grand Prix | 0.7603 | 645 |
| 2022 | 15 | Dutch Grand Prix | 0.4030 | 1139 |
| 2022 | 16 | Italian Grand Prix | 0.5750 | 778 |
| 2022 | 17 | Singapore Grand Prix | 4.0556 | 277 |
| 2022 | 19 | United States Grand Prix | 0.6265 | 778 |
| 2022 | 2 | Saudi Arabian Grand Prix | 1.2792 | 651 |
| 2022 | 20 | Mexico City Grand Prix | 0.6248 | 1284 |
| 2022 | 21 | São Paulo Grand Prix | 0.5320 | 941 |
| 2022 | 22 | Abu Dhabi Grand Prix | 0.5532 | 1032 |
| 2022 | 3 | Australian Grand Prix | 1.5458 | 813 |
| 2022 | 4 | Emilia Romagna Grand Prix | 3.2702 | 773 |
| 2022 | 5 | Miami Grand Prix | 0.8511 | 878 |
| 2022 | 6 | Spanish Grand Prix | 0.8379 | 1104 |
| 2022 | 7 | Monaco Grand Prix | 6.0343 | 540 |
| 2022 | 8 | Azerbaijan Grand Prix | 0.7543 | 764 |
| 2022 | 9 | Canadian Grand Prix | 0.6739 | 1029 |
| 2023 | 1 | Bahrain Grand Prix | 0.4722 | 914 |
| 2023 | 10 | British Grand Prix | 0.4750 | 802 |
| 2023 | 11 | Hungarian Grand Prix | 0.5871 | 1158 |
| 2023 | 12 | Belgian Grand Prix | 1.0598 | 721 |
| 2023 | 13 | Dutch Grand Prix | 3.3630 | 805 |
| 2023 | 14 | Italian Grand Prix | 0.4348 | 878 |
| 2023 | 15 | Singapore Grand Prix | 1.2723 | 958 |
| 2023 | 16 | Japanese Grand Prix | 0.5448 | 702 |
| 2023 | 17 | Qatar Grand Prix | 0.7112 | 834 |
| 2023 | 18 | United States Grand Prix | 0.5651 | 919 |
| 2023 | 19 | Mexico City Grand Prix | 1.3506 | 1134 |
| 2023 | 2 | Saudi Arabian Grand Prix | 1.2710 | 829 |
| 2023 | 20 | São Paulo Grand Prix | 0.8446 | 986 |
| 2023 | 21 | Las Vegas Grand Prix | 1.3091 | 738 |
| 2023 | 22 | Abu Dhabi Grand Prix | 0.3765 | 1063 |
| 2023 | 3 | Australian Grand Prix | 2.3969 | 769 |
| 2023 | 4 | Azerbaijan Grand Prix | 1.0932 | 846 |
| 2023 | 5 | Miami Grand Prix | 0.6671 | 1078 |
| 2023 | 6 | Monaco Grand Prix | 1.9978 | 1007 |
| 2023 | 7 | Spanish Grand Prix | 0.5300 | 1207 |
| 2023 | 8 | Canadian Grand Prix | 0.5849 | 1092 |
| 2023 | 9 | Austrian Grand Prix | 0.4738 | 1186 |
| 2024 | 1 | Bahrain Grand Prix | 0.4880 | 1024 |
| 2024 | 10 | Spanish Grand Prix | 0.6363 | 1206 |
| 2024 | 11 | Austrian Grand Prix | 0.5370 | 1269 |
| 2024 | 12 | British Grand Prix | 1.2291 | 662 |
| 2024 | 13 | Hungarian Grand Prix | 0.6960 | 1254 |
| 2024 | 14 | Belgian Grand Prix | 0.4507 | 751 |
| 2024 | 15 | Dutch Grand Prix | 0.4974 | 1354 |
| 2024 | 16 | Italian Grand Prix | 0.5551 | 927 |
| 2024 | 17 | Azerbaijan Grand Prix | 0.9589 | 881 |
| 2024 | 18 | Singapore Grand Prix | 0.6640 | 1109 |
| 2024 | 19 | United States Grand Prix | 0.8262 | 937 |
| 2024 | 2 | Saudi Arabian Grand Prix | 1.1734 | 816 |
| 2024 | 20 | Mexico City Grand Prix | 0.5741 | 1061 |
| 2024 | 22 | Las Vegas Grand Prix | 0.7265 | 826 |
| 2024 | 23 | Qatar Grand Prix | 1.5146 | 717 |
| 2024 | 24 | Abu Dhabi Grand Prix | 0.4023 | 921 |
| 2024 | 3 | Australian Grand Prix | 0.4533 | 857 |
| 2024 | 4 | Japanese Grand Prix | 1.2879 | 790 |
| 2024 | 5 | Chinese Grand Prix | 0.5321 | 762 |
| 2024 | 6 | Miami Grand Prix | 0.5698 | 934 |
| 2024 | 7 | Emilia Romagna Grand Prix | 0.5584 | 1164 |
| 2024 | 8 | Monaco Grand Prix | 3.3619 | 1187 |
| 2024 | 9 | Canadian Grand Prix | 3.5884 | 318 |

## Results and limitations

The no-degradation baseline scores 1.0986 seconds mean race MAE and
0.8867 seconds on the 2024 season holdout. The nominal new model
scores 1.1356 seconds mean race MAE. **The new model does not beat the zero baseline on the race-held-out average**, but it is not called validated unless both cross-validation
and chronological holdout show a benefit with useful uncertainty intervals.
Inspect the season-held-out table and pooled intervals before interpreting it.

This design separates common race-lap effects from within-stint tyre-age
patterns, but tyre life is still highly related to stint lap number. Driver
stint fixed effects and race-lap fixed effects can leave little independent
variation to identify wear; the rank-deficiency flags quantify this issue.
Long stints are selected by strategy and survivorship, because teams often pit
before tyres fully degrade. Compound names are relative to each weekend and
do not identify the underlying rubber. The first-three-lap baseline may
include tyres that are already used, and shorter stints have noisier
references. These are exploratory observational estimates, not causal tyre
degradation or validated strategy guidance. The prediction API clips its point
estimate to non-negative loss for planning, but its uncertainty interval keeps
negative values when supported by the fitted data.

No database schema was changed. The previous artifact is preserved in
`models/legacy/`; the new joblib artifact is
`models/tyre_degradation_relative.joblib`.
