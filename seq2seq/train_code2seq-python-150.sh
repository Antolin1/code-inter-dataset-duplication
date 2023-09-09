
python train.py \
  --architecture "encoder+rand" \
  --encoder "microsoft/codebert-base" \
  --decoder_rand_layers 6 \
  --data_path_hf "antolin/python-150_interduplication" \
  --source_column "tokens" \
  --is_split_source \
  --target_column "nl" \
  --output_dir "codebertrand_code2text_python-150" \
  --num_train_epochs 10 \
  --max_length_source 256 \
  --max_length_target 128 \
  --patience 3 \
  --generation_max_length 128 \
  --metric_for_best_model "bleu-code2text-cxg" \
