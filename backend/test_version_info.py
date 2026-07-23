import update_manager


def test_version_info_uses_packaged_app_version():
    assert update_manager.version_info() == {"version": update_manager.APP_VERSION}
