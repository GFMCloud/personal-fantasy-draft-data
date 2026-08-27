from draft_data.config import load_config


def test_registry_loads_and_flags_work():
    cfg = load_config()
    assert "nflverse" in cfg.sources
    assert cfg.max_age_hours > 0
    names = {s.name for s in cfg.enabled_sources()}
    assert "nflverse" in names
