# Tyre degradation model: before the relative-pace redesign

This snapshot records the most recent results before changing the modeling
approach. They use 2022–2024 race data, absolute fuel-corrected lap times, and
the earlier regression and evaluation methods.

## Absolute lap-time cross-validation

| Model | Mean race MAE (seconds) | SD across races | Races |
|---|---:|---:|---:|
| Naive circuit/compound mean | 2.283070 | 2.550846 | 66 |
| HistGradientBoostingRegressor | 2.989151 | 2.980710 | 66 |
| Driver random-intercept MixedLM | 9.334432 | 5.917129 | 66 |
| Pooled driver-fixed-effects linear | 9.335910 | 5.909792 | 66 |

These are absolute lap-time scores, not scores on the relative-pace target
introduced in the new analysis.

## Existing per-circuit, per-compound slopes

Using the old driver-fixed-effects linear fits and the minimum-data screen
(100 laps, five drivers), 60 of 74 circuit/compound groups were fitted. The
input had 60,706 rows; 479 rows missing a field required for this fit were
explicitly excluded. The slopes ranged from -0.159 to +0.146 seconds per
tyre-age lap; the median was +0.015. Twenty-five of the 60 fitted slopes were
negative (41.7%). Twenty-eight were negative or greater than +0.1 seconds per
lap.

| Circuit | Compound | Slope (seconds per lap) | Laps | Drivers | Races |
|---|---|---:|---:|---:|---:|
| Abu Dhabi Grand Prix | HARD | +0.0289 | 2,026 | 26 | 3 |
| Abu Dhabi Grand Prix | MEDIUM | +0.0518 | 923 | 25 | 3 |
| Australian Grand Prix | HARD | -0.0197 | 1,957 | 24 | 3 |
| Australian Grand Prix | MEDIUM | +0.0347 | 461 | 23 | 3 |
| Austrian Grand Prix | HARD | +0.0584 | 1,882 | 24 | 3 |
| Austrian Grand Prix | MEDIUM | +0.0623 | 1,409 | 24 | 3 |
| Azerbaijan Grand Prix | HARD | -0.0332 | 1,946 | 26 | 3 |
| Azerbaijan Grand Prix | MEDIUM | +0.0449 | 533 | 25 | 3 |
| Bahrain Grand Prix | HARD | +0.0425 | 1,335 | 21 | 3 |
| Bahrain Grand Prix | MEDIUM | +0.1369 | 302 | 20 | 2 |
| Bahrain Grand Prix | SOFT | +0.0745 | 1,194 | 23 | 3 |
| Belgian Grand Prix | HARD | -0.0235 | 619 | 23 | 3 |
| Belgian Grand Prix | MEDIUM | +0.0574 | 1,025 | 23 | 3 |
| Belgian Grand Prix | SOFT | +0.0074 | 473 | 20 | 3 |
| British Grand Prix | HARD | +0.0081 | 306 | 17 | 3 |
| British Grand Prix | MEDIUM | -0.0221 | 1,258 | 24 | 3 |
| British Grand Prix | SOFT | -0.0652 | 576 | 23 | 3 |
| Canadian Grand Prix | HARD | +0.0079 | 1,609 | 22 | 3 |
| Canadian Grand Prix | MEDIUM | -0.0570 | 823 | 24 | 3 |
| Chinese Grand Prix | HARD | +0.0493 | 423 | 18 | 1 |
| Chinese Grand Prix | MEDIUM | +0.0832 | 283 | 20 | 1 |
| Dutch Grand Prix | HARD | +0.0206 | 1,079 | 23 | 3 |
| Dutch Grand Prix | MEDIUM | +0.0178 | 1,075 | 24 | 3 |
| Dutch Grand Prix | SOFT | -0.0881 | 1,144 | 24 | 3 |
| Emilia Romagna Grand Prix | HARD | +0.0416 | 715 | 19 | 2 |
| Emilia Romagna Grand Prix | MEDIUM | -0.0112 | 1,166 | 23 | 2 |
| French Grand Prix | HARD | +0.0186 | 523 | 19 | 1 |
| French Grand Prix | MEDIUM | +0.0314 | 310 | 20 | 1 |
| Hungarian Grand Prix | HARD | +0.0538 | 1,795 | 21 | 3 |
| Hungarian Grand Prix | MEDIUM | +0.0452 | 1,472 | 23 | 3 |
| Hungarian Grand Prix | SOFT | +0.1464 | 348 | 19 | 3 |
| Italian Grand Prix | HARD | +0.0466 | 1,413 | 23 | 3 |
| Italian Grand Prix | MEDIUM | +0.0503 | 1,012 | 26 | 3 |
| Italian Grand Prix | SOFT | +0.0173 | 158 | 12 | 2 |
| Japanese Grand Prix | HARD | +0.0008 | 919 | 19 | 2 |
| Japanese Grand Prix | MEDIUM | -0.0340 | 459 | 18 | 2 |
| Japanese Grand Prix | SOFT | -0.1590 | 114 | 9 | 2 |
| Las Vegas Grand Prix | HARD | -0.0191 | 1,216 | 22 | 2 |
| Las Vegas Grand Prix | MEDIUM | +0.0220 | 340 | 21 | 2 |
| Mexico City Grand Prix | HARD | -0.0189 | 1,352 | 23 | 3 |
| Mexico City Grand Prix | MEDIUM | -0.0018 | 1,713 | 24 | 3 |
| Mexico City Grand Prix | SOFT | +0.0450 | 414 | 17 | 3 |
| Miami Grand Prix | HARD | -0.0086 | 1,719 | 24 | 3 |
| Miami Grand Prix | MEDIUM | -0.0275 | 1,096 | 24 | 3 |
| Monaco Grand Prix | HARD | -0.0145 | 1,644 | 22 | 3 |
| Monaco Grand Prix | MEDIUM | -0.0411 | 1,025 | 17 | 3 |
| Qatar Grand Prix | HARD | -0.0932 | 567 | 20 | 2 |
| Qatar Grand Prix | MEDIUM | -0.1119 | 932 | 20 | 2 |
| Saudi Arabian Grand Prix | HARD | -0.0383 | 1,477 | 22 | 3 |
| Saudi Arabian Grand Prix | MEDIUM | -0.0479 | 737 | 22 | 3 |
| Singapore Grand Prix | HARD | +0.0293 | 1,034 | 20 | 2 |
| Singapore Grand Prix | MEDIUM | +0.0143 | 1,079 | 24 | 3 |
| Singapore Grand Prix | SOFT | +0.1032 | 231 | 11 | 3 |
| Spanish Grand Prix | HARD | +0.0499 | 889 | 20 | 3 |
| Spanish Grand Prix | MEDIUM | -0.0156 | 1,238 | 24 | 3 |
| Spanish Grand Prix | SOFT | +0.0156 | 1,390 | 24 | 3 |
| Sao Paulo Grand Prix | MEDIUM | +0.0423 | 806 | 20 | 2 |
| Sao Paulo Grand Prix | SOFT | -0.0481 | 1,111 | 21 | 2 |
| United States Grand Prix | HARD | -0.0106 | 1,403 | 25 | 3 |
| United States Grand Prix | MEDIUM | -0.0213 | 1,219 | 25 | 3 |

Season-by-season, 46 of 137 fitted estimates were negative. SOFT > MEDIUM >
HARD held in 3 of 9 season/circuit groups with all three slopes fitted (33%).

## Existing prediction examples

The old saved MixedLM predicted the following loss at tyre age 20 relative to
age one:

| Circuit | Compound | Predicted loss (seconds) |
|---|---|---:|
| Bahrain Grand Prix | SOFT | -0.3792 |
| Italian Grand Prix | MEDIUM | -0.1356 |
| Dutch Grand Prix | HARD | +0.0749 |

The negative losses are not physically plausible evidence of tyre
improvement. The old artifact and its API are preserved under `models/legacy/`;
the new relative-pace fit is not asserted to be validated unless it beats the
no-degradation baseline and has uncertainty intervals that exclude zero.
