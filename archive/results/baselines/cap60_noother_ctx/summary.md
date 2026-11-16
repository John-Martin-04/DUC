# Baselines: cap60_noother_ctx

28 homes, 10 classes, seeds [0, 1, 2, 3, 4]. Macro-F1 per home over the classes in its test period; mean, median and worst home per seed, averaged over seeds (sd = spread of the mean over seeds).

| setup | mean_f1 | mean_f1_sd | median_f1 | worst_home_f1 |
|---|---|---|---|---|
| central | 0.647 | 0.003 | 0.669 | 0.34 |
| finetune | 0.678 | 0.005 | 0.698 | 0.366 |
| local | 0.649 | 0.003 | 0.662 | 0.365 |

Weakest homes (macro-F1 averaged over seeds):

| setup | home | macro_f1 |
|---|---|---|
| central | csh111 | 0.34 |
| central | csh130 | 0.509 |
| central | csh110 | 0.512 |
| finetune | csh111 | 0.366 |
| finetune | csh110 | 0.583 |
| finetune | csh114 | 0.586 |
| local | csh111 | 0.365 |
| local | csh104 | 0.468 |
| local | csh114 | 0.493 |

F1 per class, pooled over homes and seeds (confusion_<setup>.csv shows what each class is mistaken for):

| class | local | central | finetune | test_windows |
|---|---|---|---|---|
| chores | 0.484 | 0.479 | 0.523 | 3879 |
| cook | 0.729 | 0.729 | 0.75 | 6575 |
| eat | 0.573 | 0.55 | 0.589 | 3317 |
| enter_home | 0.885 | 0.902 | 0.917 | 694 |
| leave_home | 0.804 | 0.828 | 0.843 | 738 |
| personal_hygiene | 0.901 | 0.882 | 0.901 | 12760 |
| relax | 0.818 | 0.78 | 0.819 | 11155 |
| rest | 0.872 | 0.883 | 0.902 | 6304 |
| social | 0.639 | 0.578 | 0.647 | 7425 |
| work | 0.785 | 0.714 | 0.781 | 7345 |
