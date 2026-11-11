

@pytest.mark.parametrize("expression", [
    "SUM(CASE WHEN orders.amount > 0 THEN 1 ELSE 0 END) / COUNT(orders.order_id)",
    "PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY orders.amount) / COUNT(orders.order_id)",
    "(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY orders.amount) / COUNT(orders.order_id)) / SUM(orders.amount)",
])
def test_other_generated_aggregations_survive_real_cli_parser(tmp_path, expression):
    source = tmp_path / "input.yaml"
    source.write_text(_document(expression).to_ossie_yaml())
    for iteration in range(3):
        manifest_path = tmp_path / f"aggregation-{iteration}.json"
        target = tmp_path / f"aggregation-{iteration}.yaml"
        assert "[WARNING]" not in _cli("ossie-to-msi", source, manifest_path).stderr
        assert "[WARNING]" not in _cli("msi-to-ossie", manifest_path, target).stderr
        assert [m["name"] for m in yaml.safe_load(target.read_text())["metrics"]] == ["avg"]
        source = target
