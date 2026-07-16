import os
import shutil
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.generator import generate_project  # noqa: E402
from app.spec_agent import heuristic_extract  # noqa: E402
from app import packager, validator  # noqa: E402

DEMO_PROMPT = (
    "Build a monitoring system for an industrial water pump using vibration and "
    "temperature sensors. Ignore isolated noise spikes. Reduce speed when vibration "
    "stays above 7 mm/s for five samples. Shut down when vibration reaches 10 mm/s "
    "or temperature exceeds 105 C. It must continue operating without cloud access."
)

TMP_DIR = "/tmp/bds_generator_tests"


def setup_module(module):
    shutil.rmtree(TMP_DIR, ignore_errors=True)
    os.makedirs(TMP_DIR, exist_ok=True)


def test_generate_project_produces_expected_structure():
    spec, _ = heuristic_extract(DEMO_PROMPT)
    out_dir = os.path.join(TMP_DIR, "gen1", spec.project.name)
    manifest = generate_project(spec, "proj0001", out_dir)

    for expected_dir in ["config", "src/black_dragon_app", "simulation", "dashboard", "tests", "outputs"]:
        assert os.path.isdir(os.path.join(out_dir, expected_dir)), expected_dir
    for expected_file in ["README.md", "system_spec.json", "generation_manifest.json", "pyproject.toml"]:
        assert os.path.isfile(os.path.join(out_dir, expected_file)), expected_file
    assert manifest.template == "industrial_monitoring"
    assert len(manifest.files) > 10


def test_generated_project_has_no_unrendered_jinja():
    spec, _ = heuristic_extract(DEMO_PROMPT)
    out_dir = os.path.join(TMP_DIR, "gen2", spec.project.name)
    generate_project(spec, "proj0002", out_dir)
    for root, _dirs, files in os.walk(out_dir):
        for fname in files:
            if fname.endswith(".j2"):
                raise AssertionError(f"unrendered template file left behind: {fname}")
            path = os.path.join(root, fname)
            if fname.endswith((".py", ".md", ".yaml", ".json")):
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read()
                assert "{{" not in content, f"unrendered jinja variable in {path}"
                assert "{%" not in content, f"unrendered jinja tag in {path}"


def test_full_validation_pipeline_passes_for_demo_prompt():
    spec, _ = heuristic_extract(DEMO_PROMPT)
    out_dir = os.path.join(TMP_DIR, "gen3", spec.project.name)
    manifest = generate_project(spec, "proj0003", out_dir)

    results = validator.run_pre_package_pipeline(spec, out_dir)
    for r in results:
        assert r.passed, f"{r.stage} failed: {r.details}"

    zip_path = os.path.join(TMP_DIR, "gen3", "export", f"{spec.project.name}.zip")
    packager.make_zip(out_dir, zip_path, spec.project.name)
    stage5 = validator.stage5_package_validation(out_dir, zip_path, manifest.files)
    assert stage5.passed, stage5.details
