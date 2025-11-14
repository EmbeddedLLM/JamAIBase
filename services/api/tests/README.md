# API Server Tests

Some tests are split into two files:

- `test_<module>.py` for OSS and Cloud tests. Cloud-only tests must be marked with `pytest.mark.cloud`.
- `test_<module>_cloud.py` for Cloud-only tests. Usually Cloud-only modules are imported. These files will be removed when running OSS tests.
