"""Tests for deterministic project manifest loading and room classification."""

from __future__ import annotations

from pathlib import Path

from mempalace.application.project_classification import (
    ProjectClassifier,
    find_project_root,
    load_project_manifest,
)


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_load_project_manifest_uses_yaml_when_present(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace"
    _write(
        project_root / "mempalace.yaml",
        "\n".join(
            [
                "wing: payments_core",
                "rooms:",
                "  - name: backend",
                "    description: Backend code",
                "    keywords: [api, database]",
            ]
        ),
    )

    manifest = load_project_manifest(
        project_root,
        manifest_path=project_root / "mempalace.yaml",
        default_room_name="general",
    )

    assert manifest.wing == "payments_core"
    assert {room.name for room in manifest.rooms} == {"backend", "general"}
    assert manifest.manifest_path is not None


def test_project_classifier_prefers_path_then_filename_then_content(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace"
    _write(
        project_root / "mempalace.yaml",
        "\n".join(
            [
                "wing: billing_app",
                "rooms:",
                "  - name: backend",
                "    keywords: [api, database]",
                "  - name: frontend",
                "    keywords: [react, ui]",
                "  - name: planning",
                "    keywords: [roadmap, milestone]",
            ]
        ),
    )
    classifier = ProjectClassifier.from_project_root(
        project_root,
        manifest_filenames=["mempalace.yaml"],
        default_room_name="general",
    )

    path_match = classifier.classify(project_root / "backend" / "service.py", "print('ok')")
    assert path_match.room == "backend"
    assert path_match.strategy == "path_token"

    filename_match = classifier.classify(project_root / "src" / "frontend_widget.py", "print('ok')")
    assert filename_match.room == "frontend"
    assert filename_match.strategy == "filename_token"

    content_match = classifier.classify(
        project_root / "notes" / "summary.md",
        "This roadmap defines the next milestone and delivery plan.",
    )
    assert content_match.room == "planning"
    assert content_match.strategy == "content_keyword"

    fallback = classifier.classify(project_root / "misc" / "README.md", "plain text without signals")
    assert fallback.room == "general"
    assert fallback.strategy == "default_room"


def test_project_classifier_can_fallback_without_manifest(tmp_path: Path) -> None:
    project_root = tmp_path / "Payments Service"
    classifier = ProjectClassifier.from_project_root(
        project_root,
        manifest_filenames=["mempalace.yaml"],
        default_room_name="general",
        wing_override=None,
    )

    assert classifier.manifest.wing == "payments_service"
    classification = classifier.classify(project_root / "src" / "worker.py", "plain worker text")
    assert classification.wing == "payments_service"
    assert classification.room == "general"


def test_find_project_root_prefers_nearest_manifest_ancestor(tmp_path: Path) -> None:
    project_root = tmp_path / "workspace"
    nested_file = project_root / "services" / "billing" / "handler.py"
    _write(project_root / "mempalace.yaml", "wing: billing_app\n")
    _write(nested_file, "print('ok')\n")

    detected_root = find_project_root(nested_file, manifest_filenames=["mempalace.yaml"])
    assert detected_root == project_root

    classifier = ProjectClassifier.from_path(
        nested_file,
        manifest_filenames=["mempalace.yaml"],
        default_room_name="general",
    )
    assert classifier.project_root == project_root
    assert classifier.manifest.wing == "billing_app"
