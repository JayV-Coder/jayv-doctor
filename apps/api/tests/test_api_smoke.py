import aid_api


def test_package_imports_with_version() -> None:
    assert aid_api.__version__ == "0.0.0"
