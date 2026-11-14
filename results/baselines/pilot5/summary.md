# Baselines: pilot5

5 homes, 10 classes, seeds [0]. Macro-F1 per home over the classes in its test period; mean, median and worst home per seed, averaged over seeds (sd = spread of the mean over seeds).

| setup | mean_f1 | mean_f1_sd | median_f1 | worst_home_f1 |
|---|---|---|---|---|
| central | 0.56 |  | 0.534 | 0.515 |
| finetune | 0.556 |  | 0.556 | 0.486 |
| local | 0.542 |  | 0.56 | 0.44 |

Weakest homes (macro-F1 averaged over seeds):

| setup | home | macro_f1 |
|---|---|---|
| central | csh101 | 0.515 |
| central | csh123 | 0.53 |
| central | csh119 | 0.534 |
| finetune | csh123 | 0.486 |
| finetune | csh101 | 0.492 |
| finetune | csh119 | 0.556 |
| local | csh101 | 0.44 |
| local | csh123 | 0.487 |
| local | csh119 | 0.56 |
