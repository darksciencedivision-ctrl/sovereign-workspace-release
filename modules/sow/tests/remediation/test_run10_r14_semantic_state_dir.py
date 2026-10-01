"""R-14: the semantic DEEP executor honours an explicit state_dir and defaults to the runtime dir.

Found by mutating `state_dir is not None` in SemanticDeepExecutor.__init__: the whole suite passed,
because every test passed a state_dir equal to the default, so the argument itself was unobserved.
"""
from test_sw25_state_root import P, _NoClient, _install, clean_env  # noqa: F401


def test_an_explicit_state_dir_wins_and_the_default_is_the_runtime_dir(clean_env, tmp_path):  # noqa: F811
    from sovereign_product.semantic_deep import SemanticDeepExecutor

    root = _install(tmp_path, layout="external")
    P.resolve_product_paths(root, create=True)
    custom = tmp_path / "custom-state"
    explicit = SemanticDeepExecutor(root, _NoClient(), state_dir=custom)
    assert explicit.state_dir == custom.resolve()
    assert explicit.artifact_root == (custom / "evidence" / "semantic_deep").resolve()
    default = SemanticDeepExecutor(root, _NoClient())
    assert default.state_dir == P.resolve_runtime_dir(root).resolve()
    assert default.state_dir != explicit.state_dir
