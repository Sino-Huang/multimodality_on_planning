"""Re-render the illustrative held-out failure trace and cached scenes.

Source: outputs/choice-frontier/v4/panels/metrics/all-episode-metrics.json
p2[].{task,algorithm,decision_cap,termination,training_seed};
v4/panels/p2/{evaluation,zoo}/episodes selected events[].trusted_runtime_result;
v4/panels/views/.../scenes/catalog.json.gz and adapter views[].vfg.
Prespecified rule: choose the held-out task--algorithm pair with the largest
cap on which the exact reference solves and every adapter seed exhausts its
cap (ties lexicographically), and illustrate the fixed training seed 17.
The rule's implementation and asserts live in fig_qualitative.py.
Output: fig_qualitative_failure.pdf/.svg/.png.
"""

import fig_qualitative as figures


def main():
    figures.prepare_renderer()
    _, _, failure, cap = figures.selected_cases()
    exact = figures.episode(*failure, "exact_reference")
    adapter = figures.episode(*failure, "learned_adapter", 17)
    figures.failure_plot(*failure, cap, exact, adapter)


if __name__ == "__main__":
    main()
