# Baselines: cap14_noother

28 homes, 10 classes, seeds [0]. Macro-F1 per home over the classes in its test period; mean, median and worst home per seed, averaged over seeds (sd = spread of the mean over seeds).

| setup | mean_f1 | mean_f1_sd | median_f1 | worst_home_f1 |
|---|---|---|---|---|
| central | 0.492 |  | 0.48 | 0.29 |
| local | 0.535 |  | 0.54 | 0.269 |

Weakest homes (macro-F1 averaged over seeds):

| setup | home | macro_f1 |
|---|---|---|
| central | csh114 | 0.29 |
| central | csh127 | 0.376 |
| central | csh117 | 0.4 |
| local | csh117 | 0.269 |
| local | csh114 | 0.355 |
| local | csh111 | 0.37 |
