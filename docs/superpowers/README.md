# Internal Plans & Specs (private)

This directory **does not contain the actual plan/spec documents**.

Internal planning documents live outside the repo at the path resolved
by `tools.paths.private_docs_dir()`:

```python
from tools.paths import private_docs_dir
print(private_docs_dir())
# Default: <repo>/docs/superpowers
# Override: $STOCK_ANALYSIS_PRIVATE_DOCS_DIR
```

Set the env var to keep plans/specs outside the repo:

```sh
export STOCK_ANALYSIS_PRIVATE_DOCS_DIR="$HOME/Documents/stock-analysis-agent-private/superpowers"
```

The directory layout under `${STOCK_ANALYSIS_PRIVATE_DOCS_DIR}` mirrors
what used to live here:

```
${STOCK_ANALYSIS_PRIVATE_DOCS_DIR}/
├── plans/
│   └── YYYY-MM-DD-<slug>.md
└── specs/
    └── YYYY-MM-DD-<slug>-design.md
```

Why: planning docs sometimes contain unrotated API keys, internal
roadmap details, or other content that should not be advertised in a
public repository. See CLAUDE.md §12 (Trust Boundary) for the broader
rationale.
