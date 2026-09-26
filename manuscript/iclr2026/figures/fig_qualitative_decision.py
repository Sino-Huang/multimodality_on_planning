"""Re-render the largest frontier menu and validation rank histogram.

Source: outputs/choice-frontier/v4/seeds/metrics/all-episode-metrics.json
records.{teacher_agreements,teacher_decisions,teacher_chance_sum};
v3/evaluation/episodes and v4/seeds/evaluation/episodes selected events[].
{menu,raw_output,trusted_runtime_result}; matching cached scene VFGs.
Prespecified rule: take the success rule's selected adapter episode and
choose its largest frontier menu, breaking ties by earliest decision.
Success-task selection and numerical asserts live in fig_qualitative.py.
Output: fig_qualitative_decision.pdf/.svg/.png.
"""

import fig_qualitative as figures


def main():
    figures.prepare_renderer()
    key, seed, _, _ = figures.selected_cases()
    adapter = figures.episode(*key, "learned_adapter", seed)
    figures.decision_plot(*key, seed, adapter)


if __name__ == "__main__":
    main()
