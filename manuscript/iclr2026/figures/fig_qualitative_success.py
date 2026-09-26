"""Re-render the illustrative success filmstrip from pinned validation evidence.

Source: outputs/choice-frontier/v4/seeds/metrics/all-episode-metrics.json
records.{task,algorithm,training_seed,auc}; v2/metrics/all-episode-metrics.json
records.{arm,task,algorithm,auc}; v2/zoo/episodes and v3/evaluation/episodes
selected events[].trusted_runtime_result; scene catalog path_bindings and VFGs.
Prespecified rule: choose the validation task--algorithm pair with largest
three-seed-mean adapter-minus-random-valid M1 (ties lexicographically),
then the adapter seed with highest episode M1 (ties smallest seed); compare
with its exact reference and seed-17 random-valid zoo episode. The rule's
implementation and numerical asserts live in fig_qualitative.py.
Output: fig_qualitative_success.pdf/.svg/.png.
"""

import fig_qualitative as figures


def main():
    figures.prepare_renderer()
    key, seed, _, _ = figures.selected_cases()
    exact = figures.episode(*key, "exact_reference")
    adapter = figures.episode(*key, "learned_adapter", seed)
    random_valid = figures.episode(*key, "random_valid")
    figures.success_plot(*key, seed, (exact, adapter, random_valid))


if __name__ == "__main__":
    main()
