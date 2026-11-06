# Tyre degradation v3: fuel-corrected stint slopes

## What changed

The v2 design is invalid. It used driver-stint fixed effects and race-lap fixed
effects together. Within a stint, tyre age changes by exactly the same amount
as race lap, so those fixed effects absorb all independent age variation. V2's
66/66 rank-deficient slope estimates are numerical artifacts, not findings.
The full v2 report is preserved in [results_v2_flawed.md](results_v2_flawed.md).

V3's primary method fits an ordinary least-squares line to fuel-corrected lap
time versus tyre age within each stint of at least 8 clean laps.
It pools stint slopes by stint lap count and uses a cluster bootstrap that
resamples entire races for 95% intervals. This avoids treating stints in a
shared race as independent bootstrap samples. No 3%-slow-lap filtering was
applied; all eligible clean laps were retained.

## Fuel assumption and correction sign

For each race, fuel per lap is estimated as 110 kg divided by the maximum lap
number. The assumed lap-time effect is 0.03
seconds per kg, with 0.02, 0.03, 0.04
seconds per kg as the sensitivity band. These are approximate assumptions,
not measured fuel burn or car-specific coefficients.

The correction is
`corrected_time = observed_time + fuel_per_lap_kg * fuel_effect_s_per_kg * (lap - 1)`.
The sign is positive: a later lap is faster because it carries less fuel, so
we add that estimated time penalty to express it at the starting fuel load.
For example, with 60 race laps and 0.03 s/kg, the per-lap fuel change is
1.833 kg and each lap after lap 1 receives +0.055 s. Subtracting that positive
amount would move the lap in the wrong direction.

## Data accounting and diagnostics

- Source rows: 60,706; used rows: 60,227;
  excluded for missing/invalid required fields: 479.
- Missing values by field: {'year': 0, 'round': 0, 'circuit': 0, 'driver_code': 0, 'compound': 330, 'tyre_life': 418, 'stint_number': 0, 'lap_number': 0, 'lap_time_seconds': 0}.
- Invalid numeric values by field: {'year': 0, 'round': 0, 'tyre_life': 0, 'stint_number': 0, 'lap_number': 0, 'lap_time_seconds': 0}.
- Unknown compound labels retained for the nominal analyses:
  0.
- Stints shorter than 8 clean laps: 373;
  multi-compound stints: 0;
  stints with no tyre-age variation: 0.
- Laps removed by optional >3%-slower-than-median filter: **0** (filter disabled).
- Correlation of tyre age with within-stint lap number:
  **r=0.9773**. This high value is
  expected because tyre age usually advances once per lap until a pit stop
  resets it. It is not itself a bug; the important distinction is that V3
  estimates a slope within each stint rather than trying to estimate that
  slope alongside a separate fixed effect for every stint.

## Proof of the v2 identification problem

Actual race used for the diagnostic: 2022-1 (893 laps).
The v2 design rank is 130 for
133 columns; its condition number is
3.133e+16. Regressing tyre age on just the
driver-stint and race-lap fixed-effect columns leaves a maximum absolute
residual of 6.11e-13 laps.
Thus, age is an exact (to floating-point precision) linear combination of the
effects; its interaction with compound cannot be separately identified.

The corrected design uses one driver effect per driver, not per stint, with
race-lap effects, compound intercepts, and tyre-age-by-compound terms. For
2022-1 its rank is 75 of
75, condition number
407.3, and full-rank status is
**True**. Across observed races,
60 were full rank,
6 were rank deficient, and
0 failed. Rank-deficient races are not
reported as having slopes.

## Primary stint slope estimates

Weights are stint lap counts. Intervals below are percentile 95% intervals
from 1,000 whole-race bootstrap resamples per compound.
The following table reports the required fuel sensitivity; negative slopes
remain visible.

| fuel_effect_s_per_kg | compound | pooled_slope_seconds_per_lap | lower_95 | upper_95 | median_slope_seconds_per_lap | negative_stint_slope_share | stints | races | pooled_SOFT_gt_MEDIUM_gt_HARD |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0200 | HARD | 0.0217 | 0.0078 | 0.0334 | 0.0356 | 0.2596 | 1175 | 64 | True |
| 0.0200 | MEDIUM | 0.0221 | -0.0033 | 0.0445 | 0.0434 | 0.2956 | 1167 | 65 | True |
| 0.0200 | SOFT | 0.0229 | -0.0548 | 0.0905 | 0.0690 | 0.1898 | 469 | 39 | True |
| 0.0300 | HARD | 0.0405 | 0.0274 | 0.0524 | 0.0530 | 0.1779 | 1175 | 64 | False |
| 0.0300 | MEDIUM | 0.0404 | 0.0137 | 0.0655 | 0.0608 | 0.2339 | 1167 | 65 | False |
| 0.0300 | SOFT | 0.0409 | -0.0361 | 0.1097 | 0.0860 | 0.1301 | 469 | 39 | False |
| 0.0400 | HARD | 0.0592 | 0.0463 | 0.0708 | 0.0715 | 0.1013 | 1175 | 64 | False |
| 0.0400 | MEDIUM | 0.0588 | 0.0322 | 0.0810 | 0.0791 | 0.1740 | 1167 | 65 | False |
| 0.0400 | SOFT | 0.0590 | -0.0164 | 0.1244 | 0.1035 | 0.0959 | 469 | 39 | False |

Circuit pools are shown only when at least 3 distinct races
contribute; other circuit/compound combinations use the cross-circuit pool
and are flagged as fallbacks by the API.

| fuel_effect_s_per_kg | circuit | compound | pooled_slope_seconds_per_lap | lower_95 | upper_95 | median_slope_seconds_per_lap | stints | races | bootstrap_replicates | pool_scope |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 0.0200 | Abu Dhabi Grand Prix | HARD | 0.0404 | 0.0391 | 0.0411 | 0.0371 | 81 | 3 | 1000 | circuit-specific |
| 0.0200 | Abu Dhabi Grand Prix | MEDIUM | 0.0930 | 0.0645 | 0.1149 | 0.0787 | 58 | 3 | 1000 | circuit-specific |
| 0.0200 | Australian Grand Prix | HARD | -0.0147 | -0.0453 | 0.0328 | -0.0090 | 72 | 3 | 1000 | circuit-specific |
| 0.0200 | Australian Grand Prix | MEDIUM | 0.0265 | -0.0269 | 0.0587 | 0.0075 | 23 | 3 | 1000 | circuit-specific |
| 0.0200 | Austrian Grand Prix | HARD | 0.0624 | 0.0533 | 0.0679 | 0.0623 | 78 | 3 | 1000 | circuit-specific |
| 0.0200 | Austrian Grand Prix | MEDIUM | 0.0670 | 0.0415 | 0.0915 | 0.0674 | 81 | 3 | 1000 | circuit-specific |
| 0.0200 | Azerbaijan Grand Prix | HARD | 0.0006 | -0.0193 | 0.0174 | -0.0014 | 65 | 3 | 1000 | circuit-specific |
| 0.0200 | Azerbaijan Grand Prix | MEDIUM | 0.0191 | -0.0225 | 0.0910 | 0.0200 | 36 | 3 | 1000 | circuit-specific |
| 0.0200 | Bahrain Grand Prix | HARD | 0.0805 | 0.0767 | 0.1190 | 0.0782 | 73 | 3 | 1000 | circuit-specific |
| 0.0200 | Bahrain Grand Prix | SOFT | 0.1373 | 0.0999 | 0.1663 | 0.1349 | 84 | 3 | 1000 | circuit-specific |
| 0.0200 | Belgian Grand Prix | HARD | 0.0725 | 0.0337 | 0.3151 | 0.0561 | 38 | 3 | 1000 | circuit-specific |
| 0.0200 | Belgian Grand Prix | MEDIUM | 0.1438 | 0.0555 | 0.1847 | 0.1171 | 72 | 3 | 1000 | circuit-specific |
| 0.0200 | Belgian Grand Prix | SOFT | 0.1146 | 0.0016 | 0.1653 | 0.1116 | 27 | 3 | 1000 | circuit-specific |
| 0.0200 | British Grand Prix | HARD | 0.0157 | -0.0009 | 0.0564 | 0.0141 | 18 | 3 | 1000 | circuit-specific |
| 0.0200 | British Grand Prix | MEDIUM | -0.0461 | -0.4194 | 0.1966 | 0.0110 | 57 | 3 | 1000 | circuit-specific |
| 0.0200 | British Grand Prix | SOFT | -0.0447 | -0.2704 | 0.1022 | 0.0184 | 41 | 3 | 1000 | circuit-specific |
| 0.0200 | Canadian Grand Prix | HARD | 0.0096 | -0.2456 | 0.0250 | 0.0248 | 61 | 3 | 1000 | circuit-specific |
| 0.0200 | Canadian Grand Prix | MEDIUM | -0.0769 | -0.2632 | 0.0081 | -0.0222 | 46 | 3 | 1000 | circuit-specific |
| 0.0200 | Dutch Grand Prix | HARD | 0.0251 | -0.0345 | 0.0316 | 0.0271 | 35 | 3 | 1000 | circuit-specific |
| 0.0200 | Dutch Grand Prix | MEDIUM | 0.0291 | 0.0070 | 0.0343 | 0.0301 | 51 | 3 | 1000 | circuit-specific |
| 0.0200 | Dutch Grand Prix | SOFT | -0.1448 | -0.3041 | 0.0484 | 0.0295 | 67 | 3 | 1000 | circuit-specific |
| 0.0200 | Hungarian Grand Prix | HARD | 0.0643 | 0.0558 | 0.0740 | 0.0674 | 67 | 3 | 1000 | circuit-specific |
| 0.0200 | Hungarian Grand Prix | MEDIUM | 0.0511 | 0.0196 | 0.0686 | 0.0500 | 69 | 3 | 1000 | circuit-specific |
| 0.0200 | Hungarian Grand Prix | SOFT | 0.1649 | -0.1234 | 0.1844 | 0.1577 | 22 | 3 | 1000 | circuit-specific |
| 0.0200 | Italian Grand Prix | HARD | 0.0463 | 0.0281 | 0.0724 | 0.0461 | 58 | 3 | 1000 | circuit-specific |
| 0.0200 | Italian Grand Prix | MEDIUM | 0.0396 | 0.0081 | 0.0719 | 0.0458 | 60 | 3 | 1000 | circuit-specific |
| 0.0200 | Mexico City Grand Prix | HARD | -0.0193 | -0.1051 | 0.0470 | 0.0226 | 42 | 3 | 1000 | circuit-specific |
| 0.0200 | Mexico City Grand Prix | MEDIUM | -0.0006 | -0.0681 | 0.0625 | 0.0374 | 60 | 3 | 1000 | circuit-specific |
| 0.0200 | Miami Grand Prix | HARD | 0.0040 | -0.0117 | 0.0139 | 0.0068 | 56 | 3 | 1000 | circuit-specific |
| 0.0200 | Miami Grand Prix | MEDIUM | -0.0056 | -0.0351 | 0.0129 | -0.0119 | 60 | 3 | 1000 | circuit-specific |
| 0.0200 | Monaco Grand Prix | HARD | -0.0228 | -0.3270 | 0.0935 | -0.0089 | 35 | 3 | 1000 | circuit-specific |
| 0.0200 | Monaco Grand Prix | MEDIUM | -0.0312 | -0.2381 | 0.1740 | -0.0597 | 29 | 3 | 1000 | circuit-specific |
| 0.0200 | Saudi Arabian Grand Prix | HARD | -0.0288 | -0.0335 | -0.0256 | -0.0345 | 48 | 3 | 1000 | circuit-specific |
| 0.0200 | Saudi Arabian Grand Prix | MEDIUM | -0.0120 | -0.0361 | 0.0316 | -0.0074 | 39 | 3 | 1000 | circuit-specific |
| 0.0200 | Singapore Grand Prix | MEDIUM | -0.0121 | -0.2918 | 0.0529 | -0.0152 | 49 | 3 | 1000 | circuit-specific |
| 0.0200 | Singapore Grand Prix | SOFT | -0.1037 | -0.2921 | 0.0209 | -0.0189 | 13 | 3 | 1000 | circuit-specific |
| 0.0200 | Spanish Grand Prix | HARD | 0.0599 | 0.0547 | 0.1494 | 0.0528 | 36 | 3 | 1000 | circuit-specific |
| 0.0200 | Spanish Grand Prix | MEDIUM | 0.0734 | 0.0488 | 0.0909 | 0.0715 | 60 | 3 | 1000 | circuit-specific |
| 0.0200 | Spanish Grand Prix | SOFT | 0.1010 | 0.0366 | 0.1537 | 0.0935 | 91 | 3 | 1000 | circuit-specific |
| 0.0200 | United States Grand Prix | HARD | 0.0220 | 0.0039 | 0.0482 | 0.0282 | 64 | 3 | 1000 | circuit-specific |
| 0.0200 | United States Grand Prix | MEDIUM | 0.0319 | 0.0098 | 0.0647 | 0.0428 | 72 | 3 | 1000 | circuit-specific |
| 0.0300 | Abu Dhabi Grand Prix | HARD | 0.0593 | 0.0580 | 0.0601 | 0.0560 | 81 | 3 | 1000 | circuit-specific |
| 0.0300 | Abu Dhabi Grand Prix | MEDIUM | 0.1120 | 0.0835 | 0.1339 | 0.0977 | 58 | 3 | 1000 | circuit-specific |
| 0.0300 | Australian Grand Prix | HARD | 0.0050 | -0.0246 | 0.0521 | 0.0102 | 72 | 3 | 1000 | circuit-specific |
| 0.0300 | Australian Grand Prix | MEDIUM | 0.0459 | -0.0061 | 0.0780 | 0.0264 | 23 | 3 | 1000 | circuit-specific |
| 0.0300 | Austrian Grand Prix | HARD | 0.0779 | 0.0688 | 0.0834 | 0.0778 | 78 | 3 | 1000 | circuit-specific |
| 0.0300 | Austrian Grand Prix | MEDIUM | 0.0825 | 0.0570 | 0.1070 | 0.0829 | 81 | 3 | 1000 | circuit-specific |
| 0.0300 | Azerbaijan Grand Prix | HARD | 0.0224 | 0.0023 | 0.0389 | 0.0201 | 65 | 3 | 1000 | circuit-specific |
| 0.0300 | Azerbaijan Grand Prix | MEDIUM | 0.0409 | -0.0010 | 0.1125 | 0.0418 | 36 | 3 | 1000 | circuit-specific |
| 0.0300 | Bahrain Grand Prix | HARD | 0.0998 | 0.0960 | 0.1383 | 0.0975 | 73 | 3 | 1000 | circuit-specific |
| 0.0300 | Bahrain Grand Prix | SOFT | 0.1566 | 0.1334 | 0.1856 | 0.1542 | 84 | 3 | 1000 | circuit-specific |
| 0.0300 | Belgian Grand Prix | HARD | 0.0975 | 0.0587 | 0.3401 | 0.0811 | 38 | 3 | 1000 | circuit-specific |
| 0.0300 | Belgian Grand Prix | MEDIUM | 0.1688 | 0.0805 | 0.2097 | 0.1421 | 72 | 3 | 1000 | circuit-specific |
| 0.0300 | Belgian Grand Prix | SOFT | 0.1396 | 0.0266 | 0.1903 | 0.1366 | 27 | 3 | 1000 | circuit-specific |
| 0.0300 | British Grand Prix | HARD | 0.0369 | 0.0203 | 0.0775 | 0.0352 | 18 | 3 | 1000 | circuit-specific |
| 0.0300 | British Grand Prix | MEDIUM | -0.0250 | -0.3983 | 0.1565 | 0.0321 | 57 | 3 | 1000 | circuit-specific |
| 0.0300 | British Grand Prix | SOFT | -0.0236 | -0.2493 | 0.1234 | 0.0395 | 41 | 3 | 1000 | circuit-specific |
| 0.0300 | Canadian Grand Prix | HARD | 0.0253 | -0.2299 | 0.0407 | 0.0405 | 61 | 3 | 1000 | circuit-specific |
| 0.0300 | Canadian Grand Prix | MEDIUM | -0.0612 | -0.2475 | 0.0238 | -0.0064 | 46 | 3 | 1000 | circuit-specific |
| 0.0300 | Dutch Grand Prix | HARD | 0.0404 | -0.0162 | 0.0469 | 0.0423 | 35 | 3 | 1000 | circuit-specific |
| 0.0300 | Dutch Grand Prix | MEDIUM | 0.0448 | 0.0254 | 0.0496 | 0.0454 | 51 | 3 | 1000 | circuit-specific |
| 0.0300 | Dutch Grand Prix | SOFT | -0.1279 | -0.2858 | 0.0637 | 0.0474 | 67 | 3 | 1000 | circuit-specific |
| 0.0300 | Hungarian Grand Prix | HARD | 0.0800 | 0.0715 | 0.0897 | 0.0831 | 67 | 3 | 1000 | circuit-specific |
| 0.0300 | Hungarian Grand Prix | MEDIUM | 0.0668 | 0.0353 | 0.0843 | 0.0657 | 69 | 3 | 1000 | circuit-specific |
| 0.0300 | Hungarian Grand Prix | SOFT | 0.1806 | -0.1077 | 0.2002 | 0.1734 | 22 | 3 | 1000 | circuit-specific |
| 0.0300 | Italian Grand Prix | HARD | 0.0678 | 0.0489 | 0.0940 | 0.0679 | 58 | 3 | 1000 | circuit-specific |
| 0.0300 | Italian Grand Prix | MEDIUM | 0.0616 | 0.0289 | 0.0935 | 0.0692 | 60 | 3 | 1000 | circuit-specific |
| 0.0300 | Mexico City Grand Prix | HARD | -0.0038 | -0.0896 | 0.0625 | 0.0381 | 42 | 3 | 1000 | circuit-specific |
| 0.0300 | Mexico City Grand Prix | MEDIUM | 0.0149 | -0.0526 | 0.0780 | 0.0529 | 60 | 3 | 1000 | circuit-specific |
| 0.0300 | Miami Grand Prix | HARD | 0.0233 | 0.0076 | 0.0332 | 0.0261 | 56 | 3 | 1000 | circuit-specific |
| 0.0300 | Miami Grand Prix | MEDIUM | 0.0137 | -0.0158 | 0.0322 | 0.0074 | 60 | 3 | 1000 | circuit-specific |
| 0.0300 | Monaco Grand Prix | HARD | -0.0060 | -0.3098 | 0.1135 | 0.0076 | 35 | 3 | 1000 | circuit-specific |
| 0.0300 | Monaco Grand Prix | MEDIUM | -0.0142 | -0.1513 | 0.1940 | -0.0456 | 29 | 3 | 1000 | circuit-specific |
| 0.0300 | Saudi Arabian Grand Prix | HARD | -0.0068 | -0.0115 | -0.0036 | -0.0125 | 48 | 3 | 1000 | circuit-specific |
| 0.0300 | Saudi Arabian Grand Prix | MEDIUM | 0.0100 | -0.0141 | 0.0536 | 0.0146 | 39 | 3 | 1000 | circuit-specific |
| 0.0300 | Singapore Grand Prix | MEDIUM | 0.0058 | -0.2732 | 0.0707 | 0.0026 | 49 | 3 | 1000 | circuit-specific |
| 0.0300 | Singapore Grand Prix | SOFT | -0.0856 | -0.2735 | 0.0386 | -0.0003 | 13 | 3 | 1000 | circuit-specific |
| 0.0300 | Spanish Grand Prix | HARD | 0.0766 | 0.0714 | 0.1661 | 0.0694 | 36 | 3 | 1000 | circuit-specific |
| 0.0300 | Spanish Grand Prix | MEDIUM | 0.0901 | 0.0655 | 0.1202 | 0.0882 | 60 | 3 | 1000 | circuit-specific |
| 0.0300 | Spanish Grand Prix | SOFT | 0.1177 | 0.0533 | 0.1704 | 0.1101 | 91 | 3 | 1000 | circuit-specific |
| 0.0300 | United States Grand Prix | HARD | 0.0416 | 0.0235 | 0.0678 | 0.0478 | 64 | 3 | 1000 | circuit-specific |
| 0.0300 | United States Grand Prix | MEDIUM | 0.0515 | 0.0295 | 0.0844 | 0.0625 | 72 | 3 | 1000 | circuit-specific |
| 0.0400 | Abu Dhabi Grand Prix | HARD | 0.0783 | 0.0770 | 0.0790 | 0.0750 | 81 | 3 | 1000 | circuit-specific |
| 0.0400 | Abu Dhabi Grand Prix | MEDIUM | 0.1309 | 0.1024 | 0.1528 | 0.1167 | 58 | 3 | 1000 | circuit-specific |
| 0.0400 | Australian Grand Prix | HARD | 0.0247 | -0.0038 | 0.0714 | 0.0293 | 72 | 3 | 1000 | circuit-specific |
| 0.0400 | Australian Grand Prix | MEDIUM | 0.0652 | 0.0147 | 0.0973 | 0.0454 | 23 | 3 | 1000 | circuit-specific |
| 0.0400 | Austrian Grand Prix | HARD | 0.0934 | 0.0843 | 0.0989 | 0.0933 | 78 | 3 | 1000 | circuit-specific |
| 0.0400 | Austrian Grand Prix | MEDIUM | 0.0980 | 0.0725 | 0.1225 | 0.0984 | 81 | 3 | 1000 | circuit-specific |
| 0.0400 | Azerbaijan Grand Prix | HARD | 0.0441 | 0.0239 | 0.0605 | 0.0417 | 65 | 3 | 1000 | circuit-specific |
| 0.0400 | Azerbaijan Grand Prix | MEDIUM | 0.0627 | 0.0206 | 0.1341 | 0.0636 | 36 | 3 | 1000 | circuit-specific |
| 0.0400 | Bahrain Grand Prix | HARD | 0.1191 | 0.1153 | 0.1576 | 0.1168 | 73 | 3 | 1000 | circuit-specific |
| 0.0400 | Bahrain Grand Prix | SOFT | 0.1759 | 0.1385 | 0.2049 | 0.1735 | 84 | 3 | 1000 | circuit-specific |
| 0.0400 | Belgian Grand Prix | HARD | 0.1225 | 0.0837 | 0.3651 | 0.1061 | 38 | 3 | 1000 | circuit-specific |
| 0.0400 | Belgian Grand Prix | MEDIUM | 0.1938 | 0.1055 | 0.2347 | 0.1671 | 72 | 3 | 1000 | circuit-specific |
| 0.0400 | Belgian Grand Prix | SOFT | 0.1646 | 0.0516 | 0.2153 | 0.1616 | 27 | 3 | 1000 | circuit-specific |
| 0.0400 | British Grand Prix | HARD | 0.0580 | 0.0414 | 0.0987 | 0.0564 | 18 | 3 | 1000 | circuit-specific |
| 0.0400 | British Grand Prix | MEDIUM | -0.0038 | -0.3771 | 0.2390 | 0.0533 | 57 | 3 | 1000 | circuit-specific |
| 0.0400 | British Grand Prix | SOFT | -0.0024 | -0.2281 | 0.1445 | 0.0607 | 41 | 3 | 1000 | circuit-specific |
| 0.0400 | Canadian Grand Prix | HARD | 0.0411 | -0.2141 | 0.0564 | 0.0562 | 61 | 3 | 1000 | circuit-specific |
| 0.0400 | Canadian Grand Prix | MEDIUM | -0.0455 | -0.2318 | 0.0395 | 0.0093 | 46 | 3 | 1000 | circuit-specific |
| 0.0400 | Dutch Grand Prix | HARD | 0.0558 | 0.0022 | 0.0622 | 0.0576 | 35 | 3 | 1000 | circuit-specific |
| 0.0400 | Dutch Grand Prix | MEDIUM | 0.0605 | 0.0437 | 0.0648 | 0.0607 | 51 | 3 | 1000 | circuit-specific |
| 0.0400 | Dutch Grand Prix | SOFT | -0.1110 | -0.2674 | 0.0790 | 0.0646 | 67 | 3 | 1000 | circuit-specific |
| 0.0400 | Hungarian Grand Prix | HARD | 0.0958 | 0.0872 | 0.1054 | 0.0989 | 67 | 3 | 1000 | circuit-specific |
| 0.0400 | Hungarian Grand Prix | MEDIUM | 0.0825 | 0.0510 | 0.1000 | 0.0815 | 69 | 3 | 1000 | circuit-specific |
| 0.0400 | Hungarian Grand Prix | SOFT | 0.1963 | -0.0920 | 0.2159 | 0.1891 | 22 | 3 | 1000 | circuit-specific |
| 0.0400 | Italian Grand Prix | HARD | 0.0893 | 0.0696 | 0.1155 | 0.0899 | 58 | 3 | 1000 | circuit-specific |
| 0.0400 | Italian Grand Prix | MEDIUM | 0.0837 | 0.0496 | 0.1151 | 0.0919 | 60 | 3 | 1000 | circuit-specific |
| 0.0400 | Mexico City Grand Prix | HARD | 0.0117 | -0.0741 | 0.0780 | 0.0536 | 42 | 3 | 1000 | circuit-specific |
| 0.0400 | Mexico City Grand Prix | MEDIUM | 0.0304 | -0.0371 | 0.0935 | 0.0684 | 60 | 3 | 1000 | circuit-specific |
| 0.0400 | Miami Grand Prix | HARD | 0.0426 | 0.0269 | 0.0525 | 0.0454 | 56 | 3 | 1000 | circuit-specific |
| 0.0400 | Miami Grand Prix | MEDIUM | 0.0330 | 0.0035 | 0.0515 | 0.0267 | 60 | 3 | 1000 | circuit-specific |
| 0.0400 | Monaco Grand Prix | HARD | 0.0109 | -0.2926 | 0.1335 | 0.0217 | 35 | 3 | 1000 | circuit-specific |
| 0.0400 | Monaco Grand Prix | MEDIUM | 0.0027 | -0.2038 | 0.2140 | -0.0315 | 29 | 3 | 1000 | circuit-specific |
| 0.0400 | Saudi Arabian Grand Prix | HARD | 0.0152 | 0.0105 | 0.0184 | 0.0095 | 48 | 3 | 1000 | circuit-specific |
| 0.0400 | Saudi Arabian Grand Prix | MEDIUM | 0.0320 | 0.0079 | 0.0756 | 0.0366 | 39 | 3 | 1000 | circuit-specific |
| 0.0400 | Singapore Grand Prix | MEDIUM | 0.0237 | -0.2546 | 0.0884 | 0.0203 | 49 | 3 | 1000 | circuit-specific |
| 0.0400 | Singapore Grand Prix | SOFT | -0.0675 | -0.2549 | 0.0564 | 0.0183 | 13 | 3 | 1000 | circuit-specific |
| 0.0400 | Spanish Grand Prix | HARD | 0.0933 | 0.0881 | 0.1828 | 0.0861 | 36 | 3 | 1000 | circuit-specific |
| 0.0400 | Spanish Grand Prix | MEDIUM | 0.1067 | 0.0822 | 0.1368 | 0.1048 | 60 | 3 | 1000 | circuit-specific |
| 0.0400 | Spanish Grand Prix | SOFT | 0.1343 | 0.0700 | 0.1870 | 0.1268 | 91 | 3 | 1000 | circuit-specific |
| 0.0400 | United States Grand Prix | HARD | 0.0613 | 0.0432 | 0.0875 | 0.0675 | 64 | 3 | 1000 | circuit-specific |
| 0.0400 | United States Grand Prix | MEDIUM | 0.0712 | 0.0491 | 0.1040 | 0.0821 | 72 | 3 | 1000 | circuit-specific |

### Corrected race fixed-effects cross-check

This model uses one driver fixed effect per race, race-lap fixed effects,
compound intercepts, and a separate tyre-age slope for each compound. A race
is used only if its design has full column rank.

Rank/failure status by race:

| race_id | circuit | status | design_rank | design_columns | condition_number |
| --- | --- | --- | --- | --- | --- |
| 2022-1 | Bahrain Grand Prix | full_rank | 75 | 75 | 407.3103 |
| 2022-10 | British Grand Prix | full_rank | 67 | 67 | 525.8315 |
| 2022-11 | Austrian Grand Prix | full_rank | 91 | 91 | 710.6742 |
| 2022-12 | French Grand Prix | full_rank | 70 | 70 | 731.1118 |
| 2022-13 | Hungarian Grand Prix | full_rank | 91 | 91 | 751.6171 |
| 2022-14 | Belgian Grand Prix | full_rank | 62 | 62 | 277.0926 |
| 2022-15 | Dutch Grand Prix | full_rank | 90 | 90 | 585.0678 |
| 2022-16 | Italian Grand Prix | full_rank | 69 | 69 | 489.1822 |
| 2022-17 | Singapore Grand Prix | full_rank | 44 | 44 | 1600.5130 |
| 2022-19 | United States Grand Prix | rank_deficient | 69 | 70 | 446757689850501888.0000 |
| 2022-2 | Saudi Arabian Grand Prix | full_rank | 61 | 61 | 711.0486 |
| 2022-20 | Mexico City Grand Prix | full_rank | 94 | 94 | 1146.8678 |
| 2022-21 | São Paulo Grand Prix | full_rank | 81 | 81 | 673.3036 |
| 2022-22 | Abu Dhabi Grand Prix | full_rank | 81 | 81 | 761.1332 |
| 2022-3 | Australian Grand Prix | full_rank | 68 | 68 | 989.1712 |
| 2022-4 | Emilia Romagna Grand Prix | full_rank | 68 | 68 | 12719.8090 |
| 2022-5 | Miami Grand Prix | full_rank | 74 | 74 | 798.8907 |
| 2022-6 | Spanish Grand Prix | full_rank | 89 | 89 | 618.0700 |
| 2022-7 | Monaco Grand Prix | rank_deficient | 75 | 76 | 124232325109571440.0000 |
| 2022-8 | Azerbaijan Grand Prix | full_rank | 70 | 70 | 664.0393 |
| 2022-9 | Canadian Grand Prix | full_rank | 82 | 82 | 1108.1187 |
| 2023-1 | Bahrain Grand Prix | full_rank | 80 | 80 | 544.8807 |
| 2023-10 | British Grand Prix | full_rank | 69 | 69 | 595.1532 |
| 2023-11 | Hungarian Grand Prix | full_rank | 91 | 91 | 1177.9915 |
| 2023-12 | Belgian Grand Prix | full_rank | 66 | 66 | 333.3428 |
| 2023-13 | Dutch Grand Prix | full_rank | 77 | 77 | 1568.6960 |
| 2023-14 | Italian Grand Prix | full_rank | 71 | 71 | 723.0163 |
| 2023-15 | Singapore Grand Prix | full_rank | 79 | 79 | 918.3994 |
| 2023-16 | Japanese Grand Prix | full_rank | 72 | 72 | 506.4627 |
| 2023-17 | Qatar Grand Prix | full_rank | 75 | 75 | 466.9908 |
| 2023-18 | United States Grand Prix | full_rank | 79 | 79 | 572.7320 |
| 2023-19 | Mexico City Grand Prix | full_rank | 89 | 89 | 1049.1202 |
| 2023-2 | Saudi Arabian Grand Prix | full_rank | 70 | 70 | 807.9217 |
| 2023-20 | São Paulo Grand Prix | full_rank | 87 | 87 | 785.8599 |
| 2023-21 | Las Vegas Grand Prix | full_rank | 64 | 64 | 2329.4115 |
| 2023-22 | Abu Dhabi Grand Prix | full_rank | 79 | 79 | 774.7301 |
| 2023-3 | Australian Grand Prix | full_rank | 68 | 68 | 1999.5675 |
| 2023-4 | Azerbaijan Grand Prix | rank_deficient | 70 | 71 | 2108367377232834304.0000 |
| 2023-5 | Miami Grand Prix | full_rank | 80 | 80 | 1348.2729 |
| 2023-6 | Monaco Grand Prix | full_rank | 78 | 78 | 1218.6418 |
| 2023-7 | Spanish Grand Prix | full_rank | 89 | 89 | 805.4954 |
| 2023-8 | Canadian Grand Prix | full_rank | 87 | 87 | 1173.2138 |
| 2023-9 | Austrian Grand Prix | rank_deficient | 89 | 90 | 1599954538605961216.0000 |
| 2024-1 | Bahrain Grand Prix | full_rank | 78 | 78 | 725.9314 |
| 2024-10 | Spanish Grand Prix | full_rank | 89 | 89 | 670.4987 |
| 2024-11 | Austrian Grand Prix | full_rank | 94 | 94 | 856.0178 |
| 2024-12 | British Grand Prix | full_rank | 63 | 63 | 481.5259 |
| 2024-13 | Hungarian Grand Prix | full_rank | 93 | 93 | 1007.6516 |
| 2024-14 | Belgian Grand Prix | full_rank | 67 | 67 | 410.6161 |
| 2024-15 | Dutch Grand Prix | full_rank | 95 | 95 | 1380.6814 |
| 2024-16 | Italian Grand Prix | rank_deficient | 75 | 76 | 1326689465013512960.0000 |
| 2024-17 | Azerbaijan Grand Prix | full_rank | 71 | 71 | 1032.9639 |
| 2024-18 | Singapore Grand Prix | full_rank | 85 | 85 | 872.3390 |
| 2024-19 | United States Grand Prix | full_rank | 75 | 75 | 2020.1701 |
| 2024-2 | Saudi Arabian Grand Prix | full_rank | 69 | 69 | 1193.8098 |
| 2024-20 | Mexico City Grand Prix | full_rank | 87 | 87 | 1267.4620 |
| 2024-22 | Las Vegas Grand Prix | full_rank | 73 | 73 | 719.0287 |
| 2024-23 | Qatar Grand Prix | full_rank | 67 | 67 | 998.8065 |
| 2024-24 | Abu Dhabi Grand Prix | full_rank | 78 | 78 | 955.5593 |
| 2024-3 | Australian Grand Prix | full_rank | 78 | 78 | 798.8299 |
| 2024-4 | Japanese Grand Prix | full_rank | 73 | 73 | 515.8710 |
| 2024-5 | Chinese Grand Prix | full_rank | 69 | 69 | 750.2103 |
| 2024-6 | Miami Grand Prix | full_rank | 74 | 74 | 674.2021 |
| 2024-7 | Emilia Romagna Grand Prix | full_rank | 86 | 86 | 1168.8251 |
| 2024-8 | Monaco Grand Prix | full_rank | 96 | 96 | 2716.3552 |
| 2024-9 | Canadian Grand Prix | rank_deficient | 46 | 47 | 65659383071576104.0000 |

Random-effects pooled cross-check slopes:

| compound | pooled_slope_seconds_per_lap | lower_95 | upper_95 | race_estimates | negative_slope_share | tau_squared |
| --- | --- | --- | --- | --- | --- | --- |
| HARD | 0.0507 | 0.0438 | 0.0576 | 58 | 0.0690 | 0.0006 |
| MEDIUM | 0.0629 | 0.0542 | 0.0717 | 59 | 0.0339 | 0.0010 |
| SOFT | 0.0910 | 0.0753 | 0.1067 | 52 | 0.1154 | 0.0021 |

The cross-check is not the primary estimate. Its coverage is limited to the
full-rank races listed above.

## Synthetic parameter recovery

Synthetic races have known degradation rates (SOFT 0.10, MEDIUM 0.06, HARD
0.03 s/lap), 110 kg starting fuel, the assumed 0.03 s/kg fuel effect, driver
pace differences, varied pit schedules, used-tyre starting ages, and 0.22 s
lap noise.

| method | compound | true_slope | recovered_slope | error | full_rank_races | rank | columns |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Primary stint slopes | SOFT | 0.1000 | 0.0997 | -0.0003 | 12 | — | — |
| Corrected race fixed effects | SOFT | 0.1000 | 0.0997 | -0.0003 | 12 | — | — |
| Primary stint slopes | MEDIUM | 0.0600 | 0.0593 | -0.0007 | 12 | — | — |
| Corrected race fixed effects | MEDIUM | 0.0600 | 0.0595 | -0.0005 | 12 | — | — |
| Primary stint slopes | HARD | 0.0300 | 0.0303 | 0.0003 | 12 | — | — |
| Corrected race fixed effects | HARD | 0.0300 | 0.0304 | 0.0004 | 12 | — | — |
| Flawed v2 design | all | — | — | — | 0 | 121.0000 | 124.0000 |

The primary method is considered to recover synthetic truth only when each
pooled estimate is within 0.03 s/lap of its known slope. The flawed v2 design
is not assigned a recovered slope when rank deficient.

## Out-of-sample evaluation

No random split is used. Leave-one-race-out withholds all laps and stints from
each race. The chronological holdout trains on 2022-2023 and tests on 2024.
The relative lap target is fuel-corrected time minus that stint's first-three-
clean-lap median. Slope error compares each held-out stint's prediction with
that stint's directly observed OLS slope. The zero baseline predicts no
relative degradation and a slope of zero.

Leave-one-race-out summary:

| validation | races | baseline_relative_mae_seconds | model_relative_mae_seconds | baseline_stint_slope_mae_seconds_per_lap | model_stint_slope_mae_seconds_per_lap | plausible_observed_slope_share | unpooled_stints |
| --- | --- | --- | --- | --- | --- | --- | --- |
| leave-one-race-out | 66 | 1.1153 | 1.0784 | 0.1053 | 0.0929 | 0.7516 | 0 |

Chronological summary:

| validation | races | baseline_relative_mae_seconds | model_relative_mae_seconds | baseline_stint_slope_mae_seconds_per_lap | model_stint_slope_mae_seconds_per_lap | plausible_observed_slope_share | unpooled_stints |
| --- | --- | --- | --- | --- | --- | --- | --- |
| train 2022-2023, test 2024 | 23 | 0.9818 | 0.8704 | 0.0942 | 0.0738 | 0.8571 | 0 |

Per-race leave-one-out errors:

| race_id | year | round | circuit | laps | stints | baseline_relative_mae | model_relative_mae | baseline_slope_mae | model_slope_mae | plausible_observed_slope_share | unpooled_stints |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2022-1 | 2022 | 1 | Bahrain Grand Prix | 748 | 55 | 1.0747 | 0.8826 | 0.1669 | 0.1312 | 1.0000 | 0 |
| 2022-10 | 2022 | 10 | British Grand Prix | 656 | 41 | 1.5670 | 1.6906 | 0.3427 | 0.3591 | 0.4878 | 0 |
| 2022-11 | 2022 | 11 | Austrian Grand Prix | 839 | 42 | 0.9663 | 0.6365 | 0.0824 | 0.0527 | 0.9524 | 0 |
| 2022-12 | 2022 | 12 | French Grand Prix | 800 | 39 | 0.6790 | 0.5423 | 0.0739 | 0.0412 | 0.9744 | 0 |
| 2022-13 | 2022 | 13 | Hungarian Grand Prix | 1200 | 59 | 0.9649 | 0.7406 | 0.1265 | 0.0895 | 1.0000 | 0 |
| 2022-14 | 2022 | 14 | Belgian Grand Prix | 602 | 46 | 1.1018 | 0.9094 | 0.1973 | 0.1587 | 1.0000 | 0 |
| 2022-15 | 2022 | 15 | Dutch Grand Prix | 1072 | 68 | 0.6234 | 0.4184 | 0.0625 | 0.0386 | 0.8971 | 0 |
| 2022-16 | 2022 | 16 | Italian Grand Prix | 770 | 38 | 0.6729 | 0.5168 | 0.0567 | 0.0305 | 0.9211 | 0 |
| 2022-17 | 2022 | 17 | Singapore Grand Prix | 263 | 14 | 3.6240 | 3.9638 | 0.3035 | 0.3471 | 0.0000 | 0 |
| 2022-19 | 2022 | 19 | United States Grand Prix | 733 | 45 | 0.6559 | 0.6164 | 0.0642 | 0.0437 | 0.8889 | 0 |
| 2022-2 | 2022 | 2 | Saudi Arabian Grand Prix | 639 | 34 | 0.8360 | 1.1029 | 0.0592 | 0.0657 | 0.5588 | 0 |
| 2022-20 | 2022 | 20 | Mexico City Grand Prix | 1283 | 42 | 0.8350 | 0.6170 | 0.0537 | 0.0224 | 1.0000 | 0 |
| 2022-21 | 2022 | 21 | São Paulo Grand Prix | 930 | 57 | 0.7557 | 0.5511 | 0.0741 | 0.0532 | 0.8596 | 0 |
| 2022-22 | 2022 | 22 | Abu Dhabi Grand Prix | 1026 | 50 | 0.9222 | 0.6168 | 0.1005 | 0.0643 | 0.9800 | 0 |
| 2022-3 | 2022 | 3 | Australian Grand Prix | 802 | 36 | 1.0552 | 1.3753 | 0.0360 | 0.0535 | 0.4444 | 0 |
| 2022-4 | 2022 | 4 | Emilia Romagna Grand Prix | 771 | 23 | 2.3760 | 3.1123 | 0.0700 | 0.0989 | 0.2174 | 0 |
| 2022-5 | 2022 | 5 | Miami Grand Prix | 865 | 41 | 0.5527 | 0.7105 | 0.0454 | 0.0614 | 0.4390 | 0 |
| 2022-6 | 2022 | 6 | Spanish Grand Prix | 1093 | 69 | 1.1789 | 0.9417 | 0.1632 | 0.1320 | 0.9710 | 0 |
| 2022-7 | 2022 | 7 | Monaco Grand Prix | 520 | 18 | 5.4956 | 6.0977 | 0.2703 | 0.3139 | 0.0000 | 0 |
| 2022-8 | 2022 | 8 | Azerbaijan Grand Prix | 686 | 35 | 0.7012 | 0.7029 | 0.0760 | 0.0553 | 0.8857 | 0 |
| 2022-9 | 2022 | 9 | Canadian Grand Prix | 985 | 43 | 0.7777 | 0.6611 | 0.0380 | 0.0331 | 0.7907 | 0 |
| 2023-1 | 2023 | 1 | Bahrain Grand Prix | 877 | 61 | 0.8202 | 0.5790 | 0.1331 | 0.0961 | 1.0000 | 0 |
| 2023-10 | 2023 | 10 | British Grand Prix | 774 | 38 | 0.5310 | 0.3829 | 0.0357 | 0.0254 | 0.8684 | 0 |
| 2023-11 | 2023 | 11 | Hungarian Grand Prix | 1131 | 50 | 0.8579 | 0.6120 | 0.0682 | 0.0449 | 0.8800 | 0 |
| 2023-12 | 2023 | 12 | Belgian Grand Prix | 675 | 45 | 1.4922 | 1.2836 | 0.1918 | 0.1583 | 0.9556 | 0 |
| 2023-13 | 2023 | 13 | Dutch Grand Prix | 786 | 39 | 3.1527 | 3.5183 | 0.3669 | 0.3764 | 0.6923 | 0 |
| 2023-14 | 2023 | 14 | Italian Grand Prix | 878 | 44 | 0.8503 | 0.5415 | 0.0949 | 0.0604 | 0.9545 | 0 |
| 2023-15 | 2023 | 15 | Singapore Grand Prix | 958 | 42 | 0.9805 | 1.1702 | 0.0571 | 0.0645 | 0.5476 | 0 |
| 2023-16 | 2023 | 16 | Japanese Grand Prix | 660 | 42 | 0.9506 | 0.6861 | 0.1321 | 0.0927 | 1.0000 | 0 |
| 2023-17 | 2023 | 17 | Qatar Grand Prix | 784 | 58 | 0.6318 | 0.6857 | 0.0870 | 0.0953 | 0.4655 | 0 |
| 2023-18 | 2023 | 18 | United States Grand Prix | 895 | 51 | 0.7106 | 0.5645 | 0.0776 | 0.0558 | 0.8235 | 0 |
| 2023-19 | 2023 | 19 | Mexico City Grand Prix | 1088 | 41 | 1.5043 | 1.3767 | 0.1543 | 0.1454 | 0.6098 | 0 |
| 2023-2 | 2023 | 2 | Saudi Arabian Grand Prix | 798 | 36 | 0.8358 | 1.0845 | 0.0452 | 0.0627 | 0.3889 | 0 |
| 2023-20 | 2023 | 20 | São Paulo Grand Prix | 981 | 49 | 1.0309 | 0.8634 | 0.1720 | 0.1647 | 0.6531 | 0 |
| 2023-21 | 2023 | 21 | Las Vegas Grand Prix | 710 | 40 | 0.9355 | 1.1521 | 0.0810 | 0.1032 | 0.3250 | 0 |
| 2023-22 | 2023 | 22 | Abu Dhabi Grand Prix | 1055 | 54 | 0.6619 | 0.4065 | 0.0689 | 0.0339 | 0.9815 | 0 |
| 2023-3 | 2023 | 3 | Australian Grand Prix | 706 | 19 | 1.3824 | 2.1814 | 0.0494 | 0.0817 | 0.1579 | 0 |
| 2023-4 | 2023 | 4 | Azerbaijan Grand Prix | 799 | 31 | 0.5323 | 0.8266 | 0.0218 | 0.0445 | 0.4516 | 0 |
| 2023-5 | 2023 | 5 | Miami Grand Prix | 1073 | 37 | 0.7346 | 0.5731 | 0.0292 | 0.0269 | 0.7838 | 0 |
| 2023-6 | 2023 | 6 | Monaco Grand Prix | 999 | 27 | 1.7370 | 1.8186 | 0.2503 | 0.2259 | 0.7778 | 0 |
| 2023-7 | 2023 | 7 | Spanish Grand Prix | 1184 | 58 | 0.7803 | 0.5583 | 0.0711 | 0.0438 | 0.9483 | 0 |
| 2023-8 | 2023 | 8 | Canadian Grand Prix | 1066 | 46 | 0.6029 | 0.5557 | 0.0339 | 0.0295 | 0.7391 | 0 |
| 2023-9 | 2023 | 9 | Austrian Grand Prix | 1168 | 56 | 0.8283 | 0.5105 | 0.0662 | 0.0418 | 0.8393 | 0 |
| 2024-1 | 2024 | 1 | Bahrain Grand Prix | 1010 | 60 | 0.8499 | 0.5934 | 0.1073 | 0.0700 | 0.9833 | 0 |
| 2024-10 | 2024 | 10 | Spanish Grand Prix | 1192 | 60 | 0.9781 | 0.6977 | 0.0867 | 0.0539 | 0.9500 | 0 |
| 2024-11 | 2024 | 11 | Austrian Grand Prix | 1263 | 61 | 0.9490 | 0.5970 | 0.0987 | 0.0607 | 1.0000 | 0 |
| 2024-12 | 2024 | 12 | British Grand Prix | 651 | 37 | 1.4419 | 1.2647 | 0.1831 | 0.1553 | 0.8919 | 0 |
| 2024-13 | 2024 | 13 | Hungarian Grand Prix | 1209 | 49 | 1.0449 | 0.7467 | 0.0873 | 0.0558 | 0.9388 | 0 |
| 2024-14 | 2024 | 14 | Belgian Grand Prix | 712 | 46 | 0.5834 | 0.4181 | 0.0780 | 0.0502 | 0.9565 | 0 |
| 2024-15 | 2024 | 15 | Dutch Grand Prix | 1354 | 46 | 0.9704 | 0.5174 | 0.0518 | 0.0222 | 0.9565 | 0 |
| 2024-16 | 2024 | 16 | Italian Grand Prix | 918 | 47 | 0.6127 | 0.4841 | 0.0534 | 0.0360 | 0.8298 | 0 |
| 2024-17 | 2024 | 17 | Azerbaijan Grand Prix | 881 | 36 | 0.6398 | 0.7287 | 0.0547 | 0.0478 | 0.7500 | 0 |
| 2024-18 | 2024 | 18 | Singapore Grand Prix | 1099 | 40 | 0.8847 | 0.6587 | 0.0679 | 0.0375 | 0.9250 | 0 |
| 2024-19 | 2024 | 19 | United States Grand Prix | 933 | 40 | 0.6336 | 0.6772 | 0.0395 | 0.0353 | 0.7500 | 0 |
| 2024-2 | 2024 | 2 | Saudi Arabian Grand Prix | 735 | 22 | 0.5514 | 0.9118 | 0.0292 | 0.0481 | 0.4545 | 0 |
| 2024-20 | 2024 | 20 | Mexico City Grand Prix | 1048 | 35 | 0.7621 | 0.5582 | 0.0626 | 0.0338 | 1.0000 | 0 |
| 2024-22 | 2024 | 22 | Las Vegas Grand Prix | 790 | 50 | 0.6985 | 0.6871 | 0.1005 | 0.0775 | 0.9000 | 0 |
| 2024-23 | 2024 | 23 | Qatar Grand Prix | 702 | 34 | 0.9886 | 1.3801 | 0.0686 | 0.0927 | 0.2647 | 0 |
| 2024-24 | 2024 | 24 | Abu Dhabi Grand Prix | 908 | 39 | 0.8042 | 0.4343 | 0.0901 | 0.0511 | 1.0000 | 0 |
| 2024-3 | 2024 | 3 | Australian Grand Prix | 776 | 40 | 0.5773 | 0.4437 | 0.0568 | 0.0306 | 0.9250 | 0 |
| 2024-4 | 2024 | 4 | Japanese Grand Prix | 764 | 46 | 1.4538 | 1.2156 | 0.2902 | 0.2682 | 0.8261 | 0 |
| 2024-5 | 2024 | 5 | Chinese Grand Prix | 669 | 42 | 0.9607 | 0.6606 | 0.1312 | 0.0946 | 0.9762 | 0 |
| 2024-6 | 2024 | 6 | Miami Grand Prix | 913 | 43 | 0.5110 | 0.4667 | 0.0393 | 0.0335 | 0.8837 | 0 |
| 2024-7 | 2024 | 7 | Emilia Romagna Grand Prix | 1136 | 40 | 1.2419 | 0.6947 | 0.0863 | 0.0474 | 1.0000 | 0 |
| 2024-8 | 2024 | 8 | Monaco Grand Prix | 1178 | 21 | 2.3051 | 3.3815 | 0.0509 | 0.0773 | 0.3333 | 0 |
| 2024-9 | 2024 | 9 | Canadian Grand Prix | 290 | 18 | 3.2058 | 3.6153 | 0.2871 | 0.3299 | 0.0000 | 0 |

## Before and after

The v1 absolute-time errors cannot be compared directly to v2/v3 relative-time
errors. The v1 absolute MAEs were naive 2.2831 s, pooled linear 9.3359 s,
MixedLM 9.3344 s, and gradient boosting 2.9892 s. V2's relative-target result
was worse than its zero baseline and its slopes are invalid as explained above.

| version | LO-race relative MAE | 2024 relative MAE | slope status |
| --- | --- | --- | --- |
| v1 absolute-time models | not measured; absolute MAE is incomparable | not measured | 25/60 negative; old exploratory estimates |
| v2 flawed race FE | 1.1356 s (worse than 1.0986 s zero baseline) | 0.9980 s (worse than 0.8867 s zero baseline) | invalid; 66/66 designs rank deficient |
| v3 stint slope | 1.0784 s vs zero 1.1153 s | 0.8704 s vs zero 0.9818 s | 19.3% negative, 80.5% in (0, 0.5) |

## Limitations and conclusion

This model is **not validated** unless it both recovers synthetic truth and
beats the zero-degradation baseline with intervals excluding zero. Synthetic
recovery results are shown above; the real-data MAE comparison determines
whether it beats the baseline. Some compound intervals may include zero, and
the compounds are only the weekend-relative SOFT/MEDIUM/HARD labels, not the
underlying Pirelli C1-C5 rubber.

Fuel effects and the 110 kg starting load are approximate, not measured.
Stint-level slopes can still absorb track evolution, traffic, weather, setup,
and tyre management. The minimum eight-lap rule excludes shorter stints and is
counted above. Drivers often pit before tyres fall off, creating survivorship
bias. Circuit pools with fewer than three race clusters fall back to the
cross-circuit estimate. Do not treat these exploratory estimates as causal
wear rates or pit-strategy advice.

No schema changes were made. The v3 artifact is
`models/tyre_degradation_v3.joblib`.
