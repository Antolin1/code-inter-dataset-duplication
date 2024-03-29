import argparse
import json
import math
from re import finditer

import lizard
import numpy as np
from dpu_utils.codeutils import get_language_keywords
from dpu_utils.codeutils.deduplication import DuplicateDetector
from scipy.stats import ttest_ind
from tqdm import tqdm

from register_in_db import load_dataset


def camel_case_split(identifier):
    matches = finditer('.+?(?:(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|$)', identifier)
    return [m.group(0) for m in matches]


def normalize_code(tokens, lang):
    # return [t.lower() for t in tokens if t != '']
    new_tokens = []
    for t in tokens:
        if lang == "java":
            # camel case
            new_tokens += camel_case_split(t)
        elif lang == "python":
            if '_' in t:
                new_tokens += t.split('_')
    return [t.lower() for t in new_tokens if t != '']


def cohen_d(group1, group2):
    """Calculate Cohen's d for two groups."""
    mean_diff = abs(np.mean(group1) - np.mean(group2))
    pooled_std = math.sqrt((np.std(group1, ddof=1) ** 2 + np.std(group2, ddof=1) ** 2) / 2)
    cohen_d = mean_diff / pooled_std
    return cohen_d


def compute_statistics(dataset, lang, inter, task, rep, split):
    # load dup_ids
    with open(inter, 'r') as json_file:
        dup_ids = json.load(json_file)

    # representatives
    with open(rep, 'r') as json_file:
        representatives = json.load(json_file)
    new_dataset = []
    for d in tqdm(dataset, desc='Computing things'):
        if d['id_within_dataset'] not in representatives:
            continue
        d['is_duplicated'] = d['id_within_dataset'] in dup_ids
        d['tokens_filtered'] = [t for t in d['tokens'] if t not in get_language_keywords(lang)
                                and DuplicateDetector.IDENTIFIER_REGEX.match(t)]
        try:
            d['cc'] = lizard.analyze_file.analyze_source_code(f"test.{'py' if lang == 'python' else 'java'}",
                                                              d['snippet'])
            d['cc'] = d['cc'].function_list[0].cyclomatic_complexity
            new_dataset.append(d)
        except:
            # print(f"Excluding {d['id_within_dataset']}")
            continue

    print('Global statistics')
    tokens_length = [len(p['tokens']) for p in new_dataset]
    print(f'Avg tokens length: {sum(tokens_length) / len(tokens_length):.2f} +- {np.std(tokens_length):.2f}')

    print(f'Avg tokens length (filtered): {np.mean([len(p["tokens_filtered"]) for p in new_dataset]):.2f}'
          f'+- {np.std([len(p["tokens_filtered"]) for p in new_dataset]):.2f}')

    print('Statistics per group')
    g_dup = [p for p in new_dataset if p['is_duplicated'] and (p['split_within_dataset'] == split
                                                               if split != 'all' else True)]
    g_nondup = [p for p in new_dataset if not p['is_duplicated'] and (p['split_within_dataset'] == split
                                                                      if split != 'all' else True)]
    print(f'Samples duplicated: {len(g_dup)}')
    print(f'Samples non-duplicated: {len(g_nondup)}')

    print(f'Avg tokens length without filtering (duplicated): {np.mean([len(p["tokens"]) for p in g_dup]):.2f}'
          f'+- {np.std([len(p["tokens"]) for p in g_dup]):.2f}')
    print(f'Avg tokens length without filtering (non-duplicated): {np.mean([len(p["tokens"]) for p in g_nondup]):.2f}'
          f'+- {np.std([len(p["tokens"]) for p in g_nondup]):.2f}')
    print(f'Effect size: {cohen_d([len(p["tokens"]) for p in g_dup], [len(p["tokens"]) for p in g_nondup]):.2f}')

    print(f'Avg tokens length (duplicated): {np.mean([len(p["tokens_filtered"]) for p in g_dup]):.2f}'
          f'+- {np.std([len(p["tokens_filtered"]) for p in g_dup]):.2f}')
    print(f'Avg tokens length (non-duplicated): {np.mean([len(p["tokens_filtered"]) for p in g_nondup]):.2f}'
          f'+- {np.std([len(p["tokens_filtered"]) for p in g_nondup]):.2f}')
    print(f'p-val: '
          f'{ttest_ind([len(p["tokens_filtered"]) for p in g_dup], [len(p["tokens_filtered"]) for p in g_nondup]).pvalue:.2f}')
    print(
        f'Effect size: {cohen_d([len(p["tokens_filtered"]) for p in g_dup], [len(p["tokens_filtered"]) for p in g_nondup]):.2f}')

    print(f'Avg cc (duplicated): {np.mean([p["cc"] for p in g_dup]):.2f} +- {np.std([p["cc"] for p in g_dup]):.2f}')
    print(f'Avg cc (non-duplicated): {np.mean([p["cc"] for p in g_nondup]):.2f} '
          f'+- {np.std([p["cc"] for p in g_nondup]):.2f}')
    print(f'p-val: '
          f'{ttest_ind([p["cc"] for p in g_dup], [p["cc"] for p in g_nondup]).pvalue:.4f}')
    print(f'Effect size: {cohen_d([p["cc"] for p in g_dup], [p["cc"] for p in g_nondup]):.2f}')

    if task == "code2text":
        # overlapping snippet nl
        overlap_dup = [len(set(normalize_code(p['tokens'], lang)).intersection(set(p['nl'].lower().split()))) / len(
            set(p['nl'].lower().split()))
                       for p in g_dup]
        overlap_nondup = [len(set(normalize_code(p['tokens'], lang)).intersection(set(p['nl'].lower().split()))) / len(
            set(p['nl'].lower().split()))
                          for p in g_nondup]
        print(f'Avg overlapping snippet nl (duplicated): {np.mean(overlap_dup):.2f} +- {np.std(overlap_dup):.2f}')
        print(f'Avg overlapping snippet nl (non-duplicated): {np.mean(overlap_nondup):.2f} '
              f'+- {np.std(overlap_nondup):.2f}')
        print(f'p-val: '
              f'{ttest_ind(overlap_dup, overlap_nondup).pvalue:.4f}')
        print(f'Effect size: {cohen_d(overlap_dup, overlap_nondup):.2f}')


def main(args):
    dataset = load_dataset(args.data)
    compute_statistics(dataset, args.lang, args.inter, args.task, args.rep, args.split)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=str, required=True)
    parser.add_argument('--lang', type=str, required=True)
    parser.add_argument('--inter', type=str, required=True)
    parser.add_argument('--rep', type=str, required=True)
    parser.add_argument('--task', type=str, required=True, choices=['code2text', 'codetrans', 'clone'])
    parser.add_argument('--split', default='all', type=str, choices=['test', 'valid', 'train', 'all'])
    args = parser.parse_args()
    main(args)
