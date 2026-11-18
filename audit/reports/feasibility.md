# Feasibility

Window 60 s, splits (0.7, 0.1, 0.2), a class counts in a home if its test period has at least 10 windows. Windows labelled 'other' (majority vote with 'other' included) dropped after the split.

## Classes

Kept if present in at least 50% of homes.

| class | homes_with_class | share_of_homes | total_test_windows | keep_class |
|---|---|---|---|---|
| eat | 29 | 0.97 | 4366 | True |
| personal_hygiene | 29 | 0.97 | 25730 | True |
| relax | 29 | 0.97 | 15809 | True |
| rest | 29 | 0.97 | 15069 | True |
| chores | 28 | 0.93 | 6832 | True |
| cook | 28 | 0.93 | 9969 | True |
| social | 28 | 0.93 | 14184 | True |
| enter_home | 27 | 0.9 | 1404 | True |
| leave_home | 26 | 0.87 | 1582 | True |
| work | 26 | 0.87 | 12919 | True |

## Homes

A home passes with at least 5 kept classes in its test period (and the day and coverage thresholds, if profiled).

| home | train_windows | test_windows | kept_classes_in_test | missing_kept_classes | passes | labelled_days | label_coverage_events |
|---|---|---|---|---|---|---|---|
| csh101 | 14178 | 4110 | 10 |  | True | 60 | 1.0 |
| csh102 | 9438 | 2686 | 10 |  | True | 62 | 1.0 |
| csh103 | 4604 | 1349 | 10 |  | True | 58 | 1.0 |
| csh104 | 11956 | 3294 | 10 |  | True | 61 | 1.0 |
| csh105 | 4723 | 1315 | 10 |  | True | 46 | 1.0 |
| csh106 | 7468 | 2097 | 10 |  | True | 62 | 1.0 |
| csh107 | 8741 | 2393 | 10 |  | True | 32 | 1.0 |
| csh108 | 7887 | 2147 | 10 |  | True | 61 | 1.0 |
| csh109 | 9784 | 2957 | 10 |  | True | 61 | 1.0 |
| csh110 | 4516 | 1287 | 9 | leave_home | True | 27 | 1.0 |
| csh111 | 11797 | 3555 | 10 |  | True | 61 | 1.0 |
| csh112 | 18320 | 5015 | 10 |  | True | 106 | 1.0 |
| csh113 | 105315 | 27527 | 10 |  | True | 496 | 1.0 |
| csh114 | 3793 | 1131 | 9 | enter_home | True | 31 | 1.0 |
| csh115 | 69608 | 19748 | 10 |  | True | 314 | 1.0 |
| csh116 | 13526 | 3845 | 10 |  | True | 62 | 1.0 |
| csh117 | 24594 | 6565 | 10 |  | True | 292 | 1.0 |
| csh118 | 3445 | 1027 | 8 | enter_home, leave_home | True | 20 | 1.0 |
| csh119 | 3341 | 982 | 10 |  | True | 31 | 1.0 |
| csh120 | 11196 | 3087 | 10 |  | True | 64 | 1.0 |
| csh121 | 3279 | 976 | 8 | social, leave_home | False | 11 | 1.0 |
| csh122 | 4201 | 1135 | 9 | enter_home | True | 30 | 1.0 |
| csh123 | 3896 | 1125 | 9 | work | True | 31 | 1.0 |
| csh124 | 577 | 48 | 3 | eat, personal_hygiene, relax, rest, chores, cook, work | False | 61 | 1.0 |
| csh125 | 6856 | 1990 | 10 |  | True | 61 | 1.0 |
| csh126 | 2678 | 760 | 9 | social | True | 37 | 1.0 |
| csh127 | 3315 | 933 | 9 | work | True | 27 | 1.0 |
| csh128 | 8245 | 2262 | 10 |  | True | 61 | 1.0 |
| csh129 | 3429 | 971 | 8 | leave_home, work | True | 31 | 1.0 |
| csh130 | 5696 | 1547 | 8 | chores, cook | True | 30 | 1.0 |

