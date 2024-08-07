import logging
import os
import pickle
import random
from collections import defaultdict

import numpy as np
import torch
import wandb
from args import DataArguments, ModelArguments, TrainingArguments
from datasets import load_dataset, load_from_disk
from peft import LoraConfig, PrefixTuningConfig, TaskType, get_peft_model
from scipy.stats import ttest_ind
from torch import nn
from torch.utils.data import DataLoader
from torchmetrics.functional import retrieval_reciprocal_rank
from tqdm import tqdm
from transformers import (AdamW, AutoConfig, AutoModel, AutoTokenizer,
                          HfArgumentParser, RobertaModel,
                          get_linear_schedule_with_warmup)

logger = logging.getLogger()
logger.setLevel(level=logging.INFO)
console = logging.StreamHandler()
console.setLevel(level=logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s: %(message)s')
console.setFormatter(formatter)
logger.addHandler(console)

DEVICE = 'cuda' if torch.cuda.is_available() else 'cpu'


class DualEncoderModel(nn.Module):
    def __init__(self, code_encoder, nl_encoder):
        super().__init__()
        self.code_encoder = code_encoder
        self.nl_encoder = nl_encoder

    def forward(self, input_ids_code, inputs_ids_nl,
                attention_mask_code, attention_mask_nl):
        emb_code = self.code_encoder(input_ids_code, attention_mask_code)
        emb_nl = self.nl_encoder(inputs_ids_nl, attention_mask_nl)
        return emb_code['pooler_output'], emb_nl['pooler_output']


COLUMN_INTER_DUPLICATED = "is_duplicated"


def tokenize_function(examples, tokenizer, max_len, column):
    dic = tokenizer(examples[column], padding="max_length", truncation=True, max_length=max_len)
    dic_new = {x + "_" + column: y for x, y in dic.items()}
    return dic_new


def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)

    os.environ["CUDA_LAUNCH_BLOCKING"] = "1"
    os.environ["CUBLAS_WORKSPACE_CONFIG"] = ":16:8"
    torch.use_deterministic_algorithms(True)

    # Enable CUDNN deterministic mode
    torch.backends.cudnn.deterministic = True
    torch.backends.cudnn.benchmark = False


# TODO set input to train
def train(train_set, eval_dataset,
          model, checkpoint, batch_size_train=32, lr=5e-5, epochs=1, gradient_accumulation=1,
          max_grad_norm=1,
          log_steps=100, input_ids_code='input_ids_tokens', inputs_ids_nl='input_ids_nl',
          attention_mask_code='attention_mask_tokens', attention_mask_nl='attention_mask_nl',
          batch_size_eval=1000,
          patience=2,
          wandb_logger=None
          ):
    train_set.set_format("torch")
    train_dataloader = DataLoader(train_set, shuffle=True, batch_size=batch_size_train)
    model.to(DEVICE)
    optimizer = AdamW(filter(lambda p: p.requires_grad, model.parameters()), lr=lr, eps=1e-8)

    criterion = torch.nn.CrossEntropyLoss()

    logger.info('Training phase!')
    logger.info(f'Effective batch size: {batch_size_train * gradient_accumulation}')
    logger.info(f'Initial lr: {lr}')
    logger.info(f'Epochs: {epochs}')
    logger.info(f'Parameters: {sum(map(torch.numel, filter(lambda p: p.requires_grad, model.parameters())))} ')
    req_params = sum(map(torch.numel, filter(lambda p: p.requires_grad, model.parameters())))
    all_params = sum(map(torch.numel, model.parameters()))
    logger.info(f'Trainable %: {req_params * 100 / all_params:.2f}')

    num_training_steps = epochs * len(train_dataloader)
    scheduler = get_linear_schedule_with_warmup(optimizer, num_warmup_steps=num_training_steps * 0.1,
                                                num_training_steps=num_training_steps)
    progress_bar = tqdm(range(num_training_steps))
    steps = 0
    best_mrr = 0
    e_count = 0
    for epoch in range(1, epochs + 1):
        train_loss = 0.0
        model.train()
        for j, batch in enumerate(train_dataloader):
            batch = {k: v.to(DEVICE) for k, v in batch.items()}
            emb_code, emb_nl = model(input_ids_code=batch[input_ids_code], inputs_ids_nl=batch[inputs_ids_nl],
                                     attention_mask_code=batch[attention_mask_code],
                                     attention_mask_nl=batch[attention_mask_nl])
            scores = torch.matmul(emb_nl, torch.transpose(emb_code, 0, 1))
            loss = criterion(scores, torch.arange(scores.shape[0]).to(DEVICE))

            train_loss += loss.item()
            loss = loss / gradient_accumulation

            loss.backward()
            torch.nn.utils.clip_grad_norm_(filter(lambda p: p.requires_grad, model.parameters()), max_grad_norm)

            if ((j + 1) % gradient_accumulation == 0) or (j + 1 == len(train_dataloader)):
                optimizer.step()
                optimizer.zero_grad()
                scheduler.step()

            progress_bar.update(1)
            steps += 1
            if steps % log_steps == 0:
                logger.info(
                    f'Epoch {epoch} | step={steps} | train_loss={train_loss / (j + 1):.4f}'
                )
                if wandb_logger is not None:
                    wandb_logger.log(
                        {
                            'train_loss': train_loss / (j + 1),
                            'epoch': epoch
                        },
                        step=steps,
                    )
        rrs = evaluate(eval_dataset=eval_dataset,
                       model=model,
                       batch_size_eval=batch_size_eval,
                       input_ids_code='input_ids_tokens',
                       inputs_ids_nl='input_ids_nl',
                       attention_mask_code='attention_mask_tokens',
                       attention_mask_nl='attention_mask_nl')
        full_mrr = np.mean(rrs[0] + rrs[1])
        if full_mrr > best_mrr:
            best_mrr = full_mrr
            e_count = 0
            logger.info('Saving model!')
            torch.save(model.state_dict(), checkpoint)
            logger.info(f'Model saved: {checkpoint}')
        else:
            e_count += 1
        if e_count == patience:
            break
        logger.info(
            f'Epoch {epoch} | train_loss={train_loss / len(train_dataloader):.4f} | mrr={full_mrr:.4f}'
        )
        if wandb_logger is not None:
            wandb_logger.log(
                {
                    'train_loss': train_loss / len(train_dataloader),
                    'mrr': full_mrr,
                    'epoch': epoch
                },
                step = steps
            )


def evaluate(eval_dataset, model, batch_size_eval=5000, input_ids_code='input_ids_tokens', inputs_ids_nl='input_ids_nl',
             attention_mask_code='attention_mask_tokens', attention_mask_nl='attention_mask_nl'):
    model.eval()
    rrs = defaultdict(list)
    eval_dataset.set_format("torch")
    dataloader = DataLoader(eval_dataset, shuffle=False, batch_size=batch_size_eval)
    for batch in tqdm(dataloader, desc='Evaluation loop'):
        batch = {k: v.to(DEVICE) for k, v in batch.items()}
        with torch.no_grad():
            emb_code, emb_nl = model(input_ids_code=batch[input_ids_code], inputs_ids_nl=batch[inputs_ids_nl],
                                     attention_mask_code=batch[attention_mask_code],
                                     attention_mask_nl=batch[attention_mask_nl])
            scores = torch.matmul(emb_nl, torch.transpose(emb_code, 0, 1))
        for scs, tgt, group in zip(scores, torch.eye(scores.shape[0]).to(DEVICE), batch[COLUMN_INTER_DUPLICATED]):
            rr = retrieval_reciprocal_rank(scs, tgt).item()
            rrs[int(group.item())].append(rr)
    return rrs


def cohend(d1, d2):
    # calculate the size of samples
    n1, n2 = len(d1), len(d2)
    # calculate the variance of the samples
    s1, s2 = np.var(d1, ddof=1), np.var(d2, ddof=1)
    # calculate the pooled standard deviation
    s = np.sqrt(((n1 - 1) * s1 + (n2 - 1) * s2) / (n1 + n2 - 2))
    # calculate the means of the samples
    u1, u2 = np.mean(d1), np.mean(d2)
    # calculate the effect size
    return (u1 - u2) / s


def main():
    parser = HfArgumentParser((ModelArguments, DataArguments, TrainingArguments))
    model_args, data_args, training_args = parser.parse_args_into_dataclasses()

    os.makedirs(os.path.dirname(model_args.checkpoint), exist_ok=True)
    file = logging.FileHandler(model_args.checkpoint + '.log')
    
    file.setLevel(level=logging.INFO)
    formatter = logging.Formatter('[%(asctime)s | %(filename)s | line %(lineno)d] - %(levelname)s: %(message)s')
    file.setFormatter(formatter)
    logger.addHandler(file)
    
    logger.info(f"seed: {training_args.seed}")
    set_seed(training_args.seed)
    if not model_args.is_baseline:
        model = AutoModel.from_pretrained(model_args.model_name_or_path)
    else:
        config = AutoConfig.from_pretrained(model_args.model_name_or_path)
        config.num_hidden_layers = model_args.num_layers
        model = RobertaModel(config)

    if model_args.lora:
        peft_config = LoraConfig(r=8, lora_alpha=16, lora_dropout=0.1, task_type=TaskType.FEATURE_EXTRACTION)
        model = get_peft_model(model, peft_config)
    elif model_args.prefix_tuning:
        peft_config = PrefixTuningConfig(task_type=TaskType.FEATURE_EXTRACTION, inference_mode=False,
                                         num_virtual_tokens=20, prefix_projection=True)
        model = get_peft_model(model, peft_config)
    dual_encoder_model = DualEncoderModel(model, model)
    if model_args.telly > 0:
        for n, p in dual_encoder_model.named_parameters():
            if 'embeddings' in n:
                p.requires_grad = False
            for j in range(0, model_args.telly):
                if f'encoder.layer.{j}.' in n:
                    p.requires_grad = False

    tokenizer = AutoTokenizer.from_pretrained(model_args.model_name_or_path)

    dataset = load_dataset(data_args.data_path_hf)
    dataset = dataset.remove_columns([c for c in dataset["train"].column_names if c not in
                                      [data_args.tokens_column, data_args.nl_column, COLUMN_INTER_DUPLICATED]])
    dataset = dataset.map(lambda example: {data_args.tokens_column: ' '.join(example[data_args.tokens_column])})

    dataset = dataset.map(lambda examples: tokenize_function(examples,
                                                             tokenizer=tokenizer,
                                                             max_len=TrainingArguments.max_code_len,
                                                             column=data_args.tokens_column),
                          batched=True, load_from_cache_file=True).remove_columns([data_args.tokens_column])
    dataset = dataset.map(lambda examples: tokenize_function(examples,
                                                             tokenizer=tokenizer,
                                                             max_len=TrainingArguments.max_nl_len,
                                                             column=data_args.nl_column),
                          batched=True, load_from_cache_file=True).remove_columns([data_args.nl_column])
    full_test_dataset = dataset["test"]

    if training_args.do_train:
        # wandb_logger = wandb.init(project="code-inter-dataset-duplication", config={
        #     'model_args': model_args,
        #     'data_args': data_args,
        #     'training_args': training_args
        # })
        wandb_logger = None

        train(train_set=dataset["train"],
              eval_dataset=dataset["validation"],
              model=dual_encoder_model,
              checkpoint=model_args.checkpoint,
              batch_size_train=training_args.per_device_train_batch_size,
              lr=training_args.learning_rate,
              epochs=training_args.num_train_epochs,
              gradient_accumulation=training_args.gradient_accumulation_steps,
              max_grad_norm=training_args.max_grad_norm,
              log_steps=training_args.logging_steps,
              input_ids_code='input_ids_tokens',
              inputs_ids_nl='input_ids_nl',
              attention_mask_code='attention_mask_tokens',
              attention_mask_nl='attention_mask_nl',
              batch_size_eval=training_args.batch_size_eval,
              patience=training_args.patience, wandb_logger=wandb_logger)


    dual_encoder_model.load_state_dict(torch.load(model_args.checkpoint))
    dual_encoder_model.to(DEVICE)

    rrs = evaluate(eval_dataset=full_test_dataset,
                   model=dual_encoder_model,
                   batch_size_eval=training_args.batch_size_eval,
                   input_ids_code='input_ids_tokens',
                   inputs_ids_nl='input_ids_nl',
                   attention_mask_code='attention_mask_tokens',
                   attention_mask_nl='attention_mask_nl')
    mrrs = {x: np.mean(y) for x, y in rrs.items()}
    logger.info(f'MRRs: {mrrs}')
    logger.info(f'Full mrr: {np.mean(rrs[0] + rrs[1]):.4f}')
    logger.info(f'T-test: {ttest_ind(rrs[0], rrs[1]).pvalue:.4f}')
    logger.info(f'Cohen d: {cohend(rrs[0], rrs[1]):.4f}')

    # wandb_logger.log({
    #     'mrrs': mrrs,
    #     'full_mrr': np.mean(rrs[0] + rrs[1]),
    #     't-test': ttest_ind(rrs[0], rrs[1]).pvalue,
    #     'cohen_d': cohend(rrs[0], rrs[1])
    # })

    with open(f'{model_args.checkpoint}.pkl', 'wb') as handle:
        pickle.dump(rrs, handle, protocol=pickle.HIGHEST_PROTOCOL)


if __name__ == '__main__':
    main()
