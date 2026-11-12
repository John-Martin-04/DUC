# Feasibility

Window 60 s, splits (0.7, 0.1, 0.2), a class counts in a home if its test period has at least 10 windows. 'other' kept as a class.

## Classes

Kept if present in at least 50% of homes.

| class | homes_with_class | share_of_homes | total_test_windows | keep_class |
|---|---|---|---|---|
| other | 30 | 1.0 | 37200 | True |
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
| csh101 | 16267 | 4648 | 11 |  | True | 60 | 1.0 |
| csh102 | 13184 | 3768 | 11 |  | True | 62 | 1.0 |
| csh103 | 6843 | 1956 | 11 |  | True | 58 | 1.0 |
| csh104 | 16824 | 4807 | 11 |  | True | 61 | 1.0 |
| csh105 | 7335 | 2096 | 11 |  | True | 46 | 1.0 |
| csh106 | 10842 | 3098 | 11 |  | True | 62 | 1.0 |
| csh107 | 10484 | 2996 | 11 |  | True | 32 | 1.0 |
| csh108 | 12322 | 3521 | 11 |  | True | 61 | 1.0 |
| csh109 | 14090 | 4026 | 11 |  | True | 61 | 1.0 |
| csh110 | 5632 | 1610 | 10 | leave_home | True | 27 | 1.0 |
| csh111 | 13709 | 3918 | 11 |  | True | 61 | 1.0 |
| csh112 | 24434 | 6982 | 11 |  | True | 106 | 1.0 |
| csh113 | 131422 | 37550 | 11 |  | True | 496 | 1.0 |
| csh114 | 5524 | 1579 | 10 | enter_home | True | 31 | 1.0 |
| csh115 | 82741 | 23641 | 11 |  | True | 314 | 1.0 |
| csh116 | 15550 | 4443 | 11 |  | True | 62 | 1.0 |
| csh117 | 33440 | 9555 | 11 |  | True | 292 | 1.0 |
| csh118 | 4855 | 1388 | 9 | enter_home, leave_home | True | 20 | 1.0 |
| csh119 | 4982 | 1424 | 11 |  | True | 31 | 1.0 |
| csh120 | 13281 | 3795 | 11 |  | True | 64 | 1.0 |
| csh121 | 4239 | 1212 | 9 | social, leave_home | False | 11 | 1.0 |
| csh122 | 5874 | 1679 | 10 | enter_home | True | 30 | 1.0 |
| csh123 | 4668 | 1334 | 10 | work | True | 31 | 1.0 |
| csh124 | 775 | 222 | 4 | eat, personal_hygiene, relax, rest, chores, cook, work | False | 61 | 1.0 |
| csh125 | 9263 | 2647 | 11 |  | True | 61 | 1.0 |
| csh126 | 4393 | 1256 | 10 | social | True | 37 | 1.0 |
| csh127 | 4424 | 1264 | 10 | work | True | 27 | 1.0 |
| csh128 | 17705 | 5059 | 11 |  | True | 61 | 1.0 |
| csh129 | 5602 | 1601 | 9 | leave_home, work | True | 31 | 1.0 |
| csh130 | 6959 | 1989 | 9 | chores, cook | True | 30 | 1.0 |

