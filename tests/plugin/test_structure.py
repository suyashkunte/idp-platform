import json
import os
import re

import pytest
import yaml

from tests.plugin.conftest import PLUGIN, ROOT


def frontmatter(path):
    m = re.match(r"^---\n(.*?)\n---\n", path.read_text(), re.DOTALL)
    assert m, f"{path} has no YAML frontmatter"
    return yaml.safe_load(m.group(1))


@pytest.mark.ac("IDP-10:AC-1")
@pytest.mark.ac("IDP-10:AC-6")
def test_marketplace_lists_plugin_with_matching_manifest():
    market = json.loads((ROOT / ".claude-plugin" / "marketplace.json").read_text())
    [entry] = [p for p in market["plugins"] if p["name"] == "idp-agentic"]
    manifest = json.loads((PLUGIN / ".claude-plugin" / "plugin.json").read_text())
    assert (ROOT / entry["source"]).resolve() == PLUGIN
    assert manifest["name"] == "idp-agentic"
    assert manifest["version"] == entry["version"]


@pytest.mark.ac("IDP-10:AC-6")
@pytest.mark.parametrize("skill", sorted(p.parent.name for p in (PLUGIN / "skills").glob("*/SKILL.md")))
def test_every_skill_has_name_and_description(skill):
    fm = frontmatter(PLUGIN / "skills" / skill / "SKILL.md")
    assert fm["name"] == skill
    assert len(fm["description"]) >= 40


@pytest.mark.ac("IDP-10:AC-6")
@pytest.mark.parametrize("agent", sorted(p.stem for p in (PLUGIN / "agents").glob("*.md")))
def test_every_agent_has_name_description_and_tools(agent):
    fm = frontmatter(PLUGIN / "agents" / f"{agent}.md")
    assert fm["name"] == agent
    assert fm["description"]
    assert fm["tools"]


@pytest.mark.ac("IDP-10:AC-6")
def test_reviewers_are_read_only():
    for agent in ("code-reviewer", "security-reviewer", "ci-triage", "pr-composer"):
        tools = {t.strip() for t in frontmatter(PLUGIN / "agents" / f"{agent}.md")["tools"].split(",")}
        assert not tools & {"Edit", "Write", "MultiEdit", "NotebookEdit"}, agent


@pytest.mark.ac("IDP-10:AC-6")
def test_hooks_reference_existing_executable_scripts():
    hooks = json.loads((PLUGIN / "hooks" / "hooks.json").read_text())["hooks"]
    commands = [h["command"] for groups in hooks.values() for g in groups for h in g["hooks"]]
    assert {"PreToolUse", "PostToolUse", "Stop"} <= set(hooks)
    for cmd in commands:
        [rel] = re.findall(r"\$\{CLAUDE_PLUGIN_ROOT\}/([^\"\s]+)", cmd)
        script = PLUGIN / rel
        assert script.is_file(), rel
        assert os.access(script, os.X_OK), f"{rel} is not executable"


@pytest.mark.ac("IDP-10:AC-1")
def test_project_settings_enable_plugin_from_github_marketplace():
    settings = json.loads((ROOT / ".claude" / "settings.json").read_text())
    assert settings["enabledPlugins"]["idp-agentic@idp-platform"] is True
    source = settings["extraKnownMarketplaces"]["idp-platform"]["source"]
    assert source == {"source": "github", "repo": "suyashkunte/idp-platform"}
    deny = settings["permissions"]["deny"]
    for must in (
        "Bash(gh pr merge:*)",
        "Bash(make approve-spec:*)",
        "Edit(.github/**)",
        "Bash(git push origin main:*)",
    ):
        assert must in deny
