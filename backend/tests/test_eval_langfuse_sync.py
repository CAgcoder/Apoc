from eval import langfuse_sync


class FakeClient:
    """Mirrors the langfuse>=4 SDK surface we use (create_score / dataset items)."""

    def __init__(self):
        self.scores = []
        self.datasets = []
        self.items = []

    def create_score(self, **kw):
        self.scores.append(kw)

    def create_dataset(self, **kw):
        self.datasets.append(kw)

    def create_dataset_item(self, **kw):
        self.items.append(kw)


def test_push_scores_emits_one_score_per_metric_per_contestant():
    client = FakeClient()
    per_contestant = {
        "canonical": {"alternatives_count": 6, "risk_specificity": 8},
        "opus_solo": {"alternatives_count": 3, "risk_specificity": 5},
    }
    langfuse_sync.push_scores(
        client, dataset_run="run-1", brief_slug="fincore", per_contestant=per_contestant
    )
    # 2 contestants x 2 metrics = 4 scores
    assert len(client.scores) == 4
    names = {s["name"] for s in client.scores}
    assert names == {"alternatives_count", "risk_specificity"}
    # every score is tagged with its contestant for the compare view
    assert all("contestant" in s["metadata"] for s in client.scores)


def test_push_coverage_dataset_creates_one_item_per_requirement():
    client = FakeClient()
    design = {"requirements_mapping": [
        {"requirement": "R1", "how_addressed": "versioned chart"},
    ]}
    checklist = ["R1 must exist", "R2 must exist", "R3 must exist"]

    langfuse_sync.push_coverage_dataset(
        client, dataset_name="apoc-coverage", brief_slug="fincore",
        contestant="canonical", design=design, checklist=checklist,
    )

    # dataset created once, one item per checklist requirement
    assert len(client.datasets) == 1
    assert client.datasets[0]["name"] == "apoc-coverage"
    assert len(client.items) == 3
    # each item: input = the requirement; expected_output carries the design mapping
    inputs = [it["input"] for it in client.items]
    assert "R1 must exist" in inputs
    assert all("versioned chart" in it["expected_output"] for it in client.items)
    # tagged so a Langfuse-side evaluator + the compare view can slice by contestant
    assert all(it["metadata"]["contestant"] == "canonical" for it in client.items)
    assert all(it["metadata"]["brief"] == "fincore" for it in client.items)
