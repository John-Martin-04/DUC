# Baselines: cap60_noother_ctx

28 homes, 10 classes, seeds [0]. Macro-F1 per home over the classes in its test period; mean, median and worst home per seed, averaged over seeds (sd = spread of the mean over seeds).

| setup | mean_f1 | mean_f1_sd | median_f1 | worst_home_f1 |
|---|---|---|---|---|
| central | 0.644 |  | 0.666 | 0.338 |
| finetune | 0.679 |  | 0.701 | 0.361 |
| local | 0.657 |  | 0.675 | 0.372 |

Weakest homes (macro-F1 averaged over seeds):

| setup | home | macro_f1 |
|---|---|---|
| central | csh111 | 0.338 |
| central | csh110 | 0.47 |
| central | csh130 | 0.485 |
| finetune | csh111 | 0.361 |
| finetune | csh110 | 0.508 |
| finetune | csh114 | 0.584 |
| local | csh111 | 0.372 |
| local | csh110 | 0.537 |
| local | csh123 | 0.547 |

F1 per class, pooled over homes and seeds (confusion_<setup>.csv shows what each class is mistaken for):

| class | local | central | finetune | test_windows |
|---|---|---|---|---|
| chores | 0.517 | 0.556 | 0.58 | 3879 |
| cook | 0.693 | 0.701 | 0.716 | 6575 |
| eat | 0.557 | 0.519 | 0.555 | 3317 |
| enter_home | 0.873 | 0.889 | 0.902 | 694 |
| leave_home | 0.77 | 0.787 | 0.809 | 738 |
| personal_hygiene | 0.89 | 0.878 | 0.894 | 12760 |
| relax | 0.78 | 0.76 | 0.774 | 11155 |
| rest | 0.861 | 0.876 | 0.876 | 6304 |
| social | 0.621 | 0.578 | 0.624 | 7425 |
| work | 0.772 | 0.696 | 0.75 | 7345 |
