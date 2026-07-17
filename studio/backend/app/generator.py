"""Template Engine (constitution section 10).

Renders the `industrial_monitoring` template directory into a fresh
generated-project directory using the approved SystemSpec as Jinja2
context. This is the ONLY place that writes files derived from a spec --
per constitution 6.2 ("templates before arbitrary code"), nothing here
invents new architecture per request; it fills in a fixed, reviewed
template.
"""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
from typing import Any, Dict, List, Optional

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .models import EngineeringAgentResult, GenerationManifest, SystemSpec

_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_TEMPLATES_ROOT = os.path.join(_APP_DIR, "templates")
TEMPLATE_NAME = "industrial_monitoring"
TEMPLATE_VERSION = "1.0.0"


def _spec_hash(spec: SystemSpec) -> str:
    payload = spec.model_dump_json().encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:16]


def generate_project(
    spec: SystemSpec,
    project_id: str,
    output_dir: str,
    engineering_agents: Optional[List[EngineeringAgentResult]] = None,
    knowledge_context: Optional[List[Dict[str, Any]]] = None,
) -> GenerationManifest:
    """Renders every file in the template directory (Jinja2 for .j2 files,
    verbatim copy for anything else) into `output_dir`. Returns a manifest
    describing exactly what was produced."""
    template_dir = os.path.join(_TEMPLATES_ROOT, TEMPLATE_NAME)
    if not os.path.isdir(template_dir):
        raise FileNotFoundError(f"unknown template '{TEMPLATE_NAME}'")

    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(template_dir),
        undefined=StrictUndefined,
        keep_trailing_newline=True,
    )
    context = {
        "spec": spec,
        "engineering_agents": engineering_agents or [],
        "knowledge_context": knowledge_context or [],
        "generation_year": datetime.datetime.now(datetime.timezone.utc).year,
    }

    written: List[str] = []
    for root, dirs, files in os.walk(template_dir):
        rel_root = os.path.relpath(root, template_dir)
        for fname in files:
            src_path = os.path.join(root, fname)
            rel_path = os.path.normpath(os.path.join(rel_root, fname)) if rel_root != "." else fname

            if fname.endswith(".j2"):
                template_rel = rel_path.replace(os.sep, "/")
                template = env.get_template(template_rel)
                rendered = template.render(**context)
                dest_rel = rel_path[: -len(".j2")]
            else:
                with open(src_path, "r", encoding="utf-8") as f:
                    rendered = f.read()
                dest_rel = rel_path

            dest_path = os.path.join(output_dir, dest_rel)
            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
            with open(dest_path, "w", encoding="utf-8") as f:
                f.write(rendered)
            written.append(dest_rel.replace(os.sep, "/"))

    # write the spec itself into the generated project (constitution 6.8: reproducibility)
    spec_path = os.path.join(output_dir, "system_spec.json")
    with open(spec_path, "w", encoding="utf-8") as f:
        f.write(spec.model_dump_json(indent=2))
    written.append("system_spec.json")

    # write the engineering-team review into the generated project
    review_path = os.path.join(output_dir, "engineering_review.json")
    with open(review_path, "w", encoding="utf-8") as f:
        json.dump([a.model_dump() for a in (engineering_agents or [])], f, indent=2)
    written.append("engineering_review.json")

    # write retrieved knowledge context into the generated project
    knowledge_path = os.path.join(output_dir, "knowledge_context.json")
    with open(knowledge_path, "w", encoding="utf-8") as f:
        json.dump(knowledge_context or [], f, indent=2)
    written.append("knowledge_context.json")

    # outputs/ directory must exist for the simulator to write into
    outputs_dir = os.path.join(output_dir, "outputs")
    os.makedirs(outputs_dir, exist_ok=True)
    gitkeep = os.path.join(outputs_dir, ".gitkeep")
    if not os.path.exists(gitkeep):
        open(gitkeep, "w").close()
        written.append("outputs/.gitkeep")

    manifest = GenerationManifest(
        project_id=project_id,
        project_name=spec.project.name,
        template=TEMPLATE_NAME,
        template_version=TEMPLATE_VERSION,
        spec_hash=_spec_hash(spec),
        files=sorted(set(written)),
        engineering_agents=engineering_agents or [],
        knowledge_context=knowledge_context or [],
    )
    manifest_path = os.path.join(output_dir, "generation_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        f.write(manifest.model_dump_json(indent=2))

    return manifest
