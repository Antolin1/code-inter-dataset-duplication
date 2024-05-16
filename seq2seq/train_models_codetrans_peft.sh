
# Check if there are no arguments
if [ $# -eq 0 ]; then
    echo "Error: No arguments provided. Please provide at least one argument."
    exit 1
fi

# Check if the first argument is empty
if [ -z "$1" ]; then
    echo "Error: The first argument is empty. Please provide a non-empty argument."
    exit 1
fi

path="$1"
echo "Path: $path"

seeds=(123 72 93 12345 789)

for seed in "${seeds[@]}";
do
  echo "Seed: $seed"
  # lora
  python train.py \
    --architecture "encoder-decoder" \
    --encoder_decoder "Salesforce/codet5-large" \
    --data_path_hf "antolin/codetrans_interduplication" \
    --source_column "snippet" \
    --target_column "cs" \
    --output_dir "$path/codetrans/seed_$seed/codet5large_lora" \
    --max_length_source 512 \
    --max_length_target 512 \
    --num_train_epochs 150 \
    --patience 3 \
    --generation_max_length 512 \
    --save_strategy "steps" \
    --evaluation_strategy "steps" \
    --eval_steps 5000 \
    --max_steps 15000 \
    --save_steps 5000 \
    --seed $seed \
    --per_device_train_batch_size 8 \
    --gradient_accumulation_steps 2 \
    --lora \
    --learning_rate 3e-4

  python generate_predictions.py \
    --checkpoint "$path/codetrans/seed_$seed/codet5large_lora/best_checkpoint" \
    --tokenizer_source "Salesforce/codet5-large" \
    --tokenizer_target "Salesforce/codet5-large" \
    --data_path_hf "antolin/codetrans_interduplication" \
    --source_column "snippet" \
    --target_column "cs" \
    --max_length_source 512 \
    --max_length_target 512 \
    --lora \
    --base_model "Salesforce/codet5-large"

  # prefix
  python train.py \
    --architecture "encoder-decoder" \
    --encoder_decoder "Salesforce/codet5-large" \
    --data_path_hf "antolin/codetrans_interduplication" \
    --source_column "snippet" \
    --target_column "cs" \
    --output_dir "$path/codetrans/seed_$seed/codet5large_prefix" \
    --max_length_source 512 \
    --max_length_target 512 \
    --num_train_epochs 150 \
    --patience 3 \
    --generation_max_length 512 \
    --save_strategy "steps" \
    --evaluation_strategy "steps" \
    --eval_steps 5000 \
    --max_steps 15000 \
    --save_steps 5000 \
    --seed $seed \
    --per_device_train_batch_size 8 \
    --gradient_accumulation_steps 2 \
    --prefix_tuning \
    --learning_rate 3e-4

  python generate_predictions.py \
    --checkpoint "$path/codetrans/seed_$seed/codet5large_prefix/best_checkpoint" \
    --tokenizer_source "Salesforce/codet5-large" \
    --tokenizer_target "Salesforce/codet5-large" \
    --data_path_hf "antolin/codetrans_interduplication" \
    --source_column "snippet" \
    --target_column "cs" \
    --max_length_source 512 \
    --max_length_target 512 \
    --prefix_tuning \
    --base_model "Salesforce/codet5-large"

  done
