import pytest

def pytest_configure(config):
    config.addinivalue_line("markers", "critical: must pass before release")
    config.addinivalue_line("markers", "high: must pass before QA sign-off")
    config.addinivalue_line("markers", "medium: should pass, non-blocking with justification")
    config.addinivalue_line("markers", "low: nice to have, non-blocking")
