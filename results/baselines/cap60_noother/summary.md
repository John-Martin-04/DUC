# Baselines: cap60_noother

28 homes, 10 classes, seeds [0, 1, 2, 3, 4]. Macro-F1 per home over the classes in its test period; mean, median and worst home per seed, averaged over seeds (sd = spread of the mean over seeds).

| setup | mean_f1 | mean_f1_sd | median_f1 | worst_home_f1 |
|---|---|---|---|---|
| central | 0.49 | 0.007 | 0.501 | 0.24 |
| finetune | 0.558 | 0.004 | 0.566 | 0.312 |
| local | 0.541 | 0.005 | 0.55 | 0.303 |

Weakest homes (macro-F1 averaged over seeds):

| setup | home | macro_f1 |
|---|---|---|
| central | csh111 | 0.24 |
| central | csh110 | 0.382 |
| central | csh130 | 0.393 |
| finetune | csh111 | 0.312 |
| finetune | csh114 | 0.461 |
| finetune | csh117 | 0.482 |
| local | csh111 | 0.303 |
| local | csh101 | 0.425 |
| local | csh114 | 0.444 |

F1 per class, pooled over homes and seeds (confusion_<setup>.csv shows what each class is mistaken for):

| class | local | central | finetune | test_windows |
|---|---|---|---|---|
| chores | 0.337 | 0.224 | 0.397 | 3879 |
| cook | 0.697 | 0.699 | 0.711 | 6575 |
| eat | 0.488 | 0.388 | 0.508 | 3317 |
| enter_home | 0.532 | 0.542 | 0.581 | 694 |
| leave_home | 0.536 | 0.499 | 0.538 | 738 |
| personal_hygiene | 0.885 | 0.841 | 0.887 | 12760 |
| relax | 0.801 | 0.718 | 0.799 | 11155 |
| rest | 0.848 | 0.823 | 0.858 | 6304 |
| social | 0.554 | 0.398 | 0.54 | 7425 |
| work | 0.738 | 0.641 | 0.749 | 7345 |
