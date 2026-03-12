from __future__ import annotations

from typer.testing import CliRunner

from code_atlas import cli


def test_graph_help_includes_visualize_option():
    runner = CliRunner()
    result = runner.invoke(cli.app, ["graph", "--help"])
    assert result.exit_code == 0
    # the visualize option should be documented in the help output
    assert "--visualize" in result.output
    assert "Generate an HTML visualization" in result.output
    # output flag should also appear
    assert "--output" in result.output
    assert "Output filename for the visualization" in result.output
