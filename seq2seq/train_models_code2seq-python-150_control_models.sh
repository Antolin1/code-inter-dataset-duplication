seeds=(123 72 93)

for seed in "${seeds[@]}";
do
  echo "Seed: $seed"
  #T5
  python train.py \
    --architecture "encoder-decoder" \
    --encoder_decoder "t5-base" \
    --data_path_hf "antolin/python-150_interduplication" \
    --source_column "tokens" \
    --is_split_source \
    --target_column "nl" \
    --output_dir "code2text/seed_$seed/t5" \
    --num_train_epochs 10 \
    --max_length_source 256 \
    --max_length_target 128 \
    --patience 3 \
    --generation_max_length 128 \
    --prefix "Summarize Python: " \
    --seed $seed

  python generate_predictions.py \
    --checkpoint "code2text/seed_$seed/t5/best_checkpoint" \
    --tokenizer_source "t5-base" \
    --tokenizer_target "t5-base" \
    --data_path_hf "antolin/python-150_interduplication" \
    --source_column "tokens" \
    --is_split_source \
    --target_column "nl" \
    --max_length_source 256 \
    --max_length_target 128 \
    --prefix "Summarize Python: "

  # bart
  python train.py \
    --architecture "encoder-decoder" \
    --encoder_decoder "facebook/bart-base" \
    --data_path_hf "antolin/python-150_interduplication" \
    --source_column "tokens" \
    --is_split_source \
    --target_column "nl" \
    --output_dir "code2text/seed_$seed/bart" \
    --num_train_epochs 10 \
    --max_length_source 256 \
    --max_length_target 128 \
    --patience 3 \
    --generation_max_length 128 \
    --seed $seed

  python generate_predictions.py \
    --checkpoint "code2text/seed_$seed/bart/best_checkpoint" \
    --tokenizer_source "facebook/bart-base" \
    --tokenizer_target "facebook/bart-base" \
    --data_path_hf "antolin/python-150_interduplication" \
    --source_column "tokens" \
    --is_split_source \
    --target_column "nl" \
    --max_length_source 256 \
    --max_length_target 128

  #T5v1
  python train.py \
    --architecture "encoder-decoder" \
    --encoder_decoder "google/t5-v1_1-small" \
    --data_path_hf "antolin/python-150_interduplication" \
    --source_column "tokens" \
    --is_split_source \
    --target_column "nl" \
    --output_dir "code2text/seed_$seed/t5v1" \
    --num_train_epochs 10 \
    --max_length_source 256 \
    --max_length_target 128 \
    --patience 3 \
    --generation_max_length 128 \
    --prefix "Summarize Python: " \
    --fp16 False \
    --seed $seed

  python generate_predictions.py \
    --checkpoint "code2text/seed_$seed/t5v1/best_checkpoint" \
    --tokenizer_source "google/t5-v1_1-small" \
    --tokenizer_target "google/t5-v1_1-small" \
    --data_path_hf "antolin/python-150_interduplication" \
    --source_column "tokens" \
    --is_split_source \
    --target_column "nl" \
    --max_length_source 256 \
    --max_length_target 128 \
    --prefix "Summarize Python: "

  # rand rand
  python train.py \
    --architecture "rand+rand" \
    --encoder "microsoft/codebert-base" \
    --data_path_hf "antolin/python-150_interduplication" \
    --source_column "tokens" \
    --is_split_source \
    --target_column "nl" \
    --output_dir "code2text/seed_$seed/rand66" \
    --num_train_epochs 10 \
    --max_length_source 256 \
    --max_length_target 128 \
    --patience 3 \
    --generation_max_length 128 \
    --seed $seed

  python generate_predictions.py \
    --checkpoint "code2text/seed_$seed/rand66/best_checkpoint" \
    --tokenizer_source "microsoft/codebert-base" \
    --tokenizer_target "microsoft/codebert-base" \
    --data_path_hf "antolin/python-150_interduplication" \
    --source_column "tokens" \
    --is_split_source \
    --target_column "nl" \
    --max_length_source 256 \
    --max_length_target 128

  python train.py \
    --architecture "rand+rand" \
    --encoder "microsoft/codebert-base" \
    --data_path_hf "antolin/python-150_interduplication" \
    --source_column "tokens" \
    --is_split_source \
    --target_column "nl" \
    --output_dir "code2text/seed_$seed/rand63" \
    --num_train_epochs 10 \
    --max_length_source 256 \
    --max_length_target 128 \
    --patience 3 \
    --generation_max_length 128 \
    --decoder_rand_layers 3 \
    --seed $seed

  python generate_predictions.py \
    --checkpoint "code2text/seed_$seed/rand63/best_checkpoint" \
    --tokenizer_source "microsoft/codebert-base" \
    --tokenizer_target "microsoft/codebert-base" \
    --data_path_hf "antolin/python-150_interduplication" \
    --source_column "tokens" \
    --is_split_source \
    --target_column "nl" \
    --max_length_source 256 \
    --max_length_target 128

  python train.py \
    --architecture "rand+rand" \
    --encoder "microsoft/codebert-base" \
    --data_path_hf "antolin/python-150_interduplication" \
    --source_column "tokens" \
    --is_split_source \
    --target_column "nl" \
    --output_dir "code2text/seed_$seed/rand33" \
    --num_train_epochs 10 \
    --max_length_source 256 \
    --max_length_target 128 \
    --patience 3 \
    --generation_max_length 128 \
    --decoder_rand_layers 3 \
    --encoder_rand_layers 3 \
    --seed $seed

  python generate_predictions.py \
    --checkpoint "code2text/seed_$seed/rand33/best_checkpoint" \
    --tokenizer_source "microsoft/codebert-base" \
    --tokenizer_target "microsoft/codebert-base" \
    --data_path_hf "antolin/python-150_interduplication" \
    --source_column "tokens" \
    --is_split_source \
    --target_column "nl" \
    --max_length_source 256 \
    --max_length_target 128
done